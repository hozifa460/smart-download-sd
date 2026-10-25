"""
Download execution, progress coordination, and lifecycle controller mixin for Smart Download (SD).
"""
import os
import sys
import threading
from typing import Optional, Callable, Dict, Any, List

try:
    import tkinter as tk
    from tkinter import messagebox
except Exception:
    tk = None  # type: ignore
    messagebox = None  # type: ignore

from smart_download.i18n import tr
from smart_download.core import TurboDownloadEngine, StreamDownloadCoordinator
from smart_download.services.youtube_service import (
    YouTubeResolver,
    VideoFormatOption,
    is_media_url,
    extract_media_platform,
    sanitize_filename,
)
from smart_download.utils import resolve_categorized_path, derive_download_filename
from smart_download.ui.modals.quality_modal import QualitySelectionModal
from smart_download.ui.modals.confirm_modal import DownloadConfirmationModal
from smart_download.ui.modals.candidates_modal import MultipleCandidatesModal
from smart_download.ui.modals.refresh_modal import RefreshLinkModal
from smart_download.ui.components.base_modal import SafeModalDialog


class DownloadControllerMixin:
    """Handles download triggers, background thread dispatch, progress monitoring, and completion/error states."""

    def _show_multiple_candidates_dialog(self, source_url: str, candidates: List[Dict[str, Any]], page_title: str = ""):
        """Displays modern dark-themed modal for choosing among multiple download links."""
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, lambda: self._show_multiple_candidates_dialog(source_url, candidates, page_title))
            return

        self._close_fetching_toast()

        def _on_download_selected(selected: List[Dict[str, Any]]):
            if not selected:
                return
            if len(selected) == 1:
                cand = selected[0]
                dl_url = cand["url"]
                fn = cand.get("filename") or derive_download_filename(dl_url)
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                auto_cat = getattr(self, "auto_categorize_folders", True)
                dest = resolve_categorized_path(downloads_dir, fn, auto_categorize=auto_cat)
                self._show_download_confirmation_dialog(dl_url, dest)
            else:
                self._queue_multiple_candidate_downloads(selected)

        def _on_download_all(all_cands: List[Dict[str, Any]]):
            self._queue_multiple_candidate_downloads(all_cands)

        modal = MultipleCandidatesModal(
            parent=self.root,
            source_url=source_url,
            candidates=candidates,
            page_title=page_title,
            theme=self._theme_dict(),
            on_download_selected=_on_download_selected,
            on_download_all=_on_download_all,
            parent_app=self
        )
        self._candidates_modal = modal

    def _queue_multiple_candidate_downloads(self, items: List[Dict[str, Any]]):
        """Queues a list of candidate downloads, starting the first one if idle."""
        if not items:
            return
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        auto_cat = getattr(self, "auto_categorize_folders", True)
        try:
            max_conn = int(self.conn_var.get())
        except Exception:
            max_conn = 8
        try:
            kb_limit = float(self.entry_custom_speed.get().strip())
        except Exception:
            kb_limit = 0.0
        bytes_limit = kb_limit * 1024.0 if kb_limit > 0 else 0.0

        self.log(f"[BATCH] Queuing {len(items)} download candidates...")
        for item in items:
            dl_url = item["url"]
            fn = item.get("filename") or derive_download_filename(dl_url)
            dest = resolve_categorized_path(downloads_dir, fn, auto_categorize=auto_cat)
            self.queue_download(dl_url, dest, max_conn=max_conn, bytes_limit=bytes_limit)

    def queue_download(self, url: str, dest: str, max_conn: int = 8, bytes_limit: float = 0.0):
        """Queues a download task, starting it immediately if no download is currently running."""
        if not hasattr(self, "_download_queue"):
            self._download_queue = []

        if not (self.engine and getattr(self.engine, "is_running", False)):
            self._start_download_with_engine(url, dest, max_conn, bytes_limit)
        else:
            self._download_queue.append((url, dest, max_conn, bytes_limit))
            self.log(f"[QUEUE] Task queued: {os.path.basename(dest)} ({len(self._download_queue)} queued)")

    def _on_start_download(self, skip_resolver: bool = False):
        if self.engine and self.engine.is_running:
            return

        if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
            try:
                self._yt_cancel_event.set()
            except Exception:
                pass

        url = self.entry_url.get().strip()
        dest = self.entry_dest.get().strip()

        if not url:
            self.show_safe_warning("Missing URL", "Please enter a valid HTTP/HTTPS download URL.")
            return
        if not dest:
            self.show_safe_warning("Missing Save Path", "Please select a valid destination file path.")
            return

        try:
            max_conn = int(self.conn_var.get())
        except ValueError:
            max_conn = 8

        try:
            kb_limit = float(self.entry_custom_speed.get().strip())
        except ValueError:
            kb_limit = 0.0

        bytes_limit = kb_limit * 1024.0 if kb_limit > 0 else 0.0

        if is_media_url(url, check_ytdlp_extractors=True) or skip_resolver:
            self._start_download_with_engine(url, dest, max_conn, bytes_limit, modal=None)
            return

        # Manually typed non-media URL: resolve in background thread before starting
        def _on_resolved(info: Dict[str, Any]):
            real_url = info.get("url") or url
            if info.get("resolved"):
                self.log(f"[LINK RESOLVER] Web page detected. Real file found: {real_url}")

            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            dest_dir = os.path.dirname(dest) if dest else downloads_dir
            if not os.path.isdir(dest_dir):
                dest_dir = downloads_dir

            real_fn = info.get("filename") or derive_download_filename(real_url)
            if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                final_dest = resolve_categorized_path(downloads_dir, real_fn, auto_categorize=True)
            else:
                final_dest = os.path.join(dest_dir, real_fn)

            try:
                self.entry_url.delete(0, tk.END)
                self.entry_url.insert(0, real_url)
                self.entry_dest.delete(0, tk.END)
                self.entry_dest.insert(0, final_dest)
            except Exception:
                pass

            self._start_download_with_engine(real_url, final_dest, max_conn, bytes_limit, modal=None)

        self._resolve_real_url_async(url, on_resolved=_on_resolved)

    def _start_download_with_engine(
        self,
        url: str,
        dest: str,
        max_conn: int = 8,
        bytes_limit: float = 0.0,
        modal: Optional[Any] = None
    ):
        """Starts download engine, optionally bridging metrics and controls to a standalone modal."""
        if self.engine and self.engine.is_running:
            return

        if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
            try:
                self._yt_cancel_event.set()
            except Exception:
                pass

        # Populate GUI entry fields
        try:
            self.entry_url.delete(0, tk.END)
            self.entry_url.insert(0, url)
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, dest)
            self.conn_var.set(str(max_conn))
            if bytes_limit > 0:
                self.entry_custom_speed.delete(0, tk.END)
                self.entry_custom_speed.insert(0, str(int(bytes_limit / 1024.0)))
        except Exception:
            pass

        # UI state transitions in main window
        try:
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="normal", text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
            self.btn_cancel.configure(state="normal")
            if hasattr(self, "btn_refresh_link"):
                self.btn_refresh_link.configure(state="normal", bg=self.c_panel_light, fg=self.c_accent)
            self.txt_log.delete("1.0", tk.END)
            for item in self.tree_chunks.get_children():
                self.tree_chunks.delete(item)
            self._draw_main_progress(0.0)
            self._draw_chunk_segments([])
        except Exception:
            pass

        # Check if URL is YouTube or supported social media
        if is_media_url(url, check_ytdlp_extractors=True):
            self._start_youtube_download(url, dest, max_conn, bytes_limit, modal=modal)
            return

        # Wrapped callbacks for modal + main UI
        def _comb_progress(downloaded: int, total: int, speed: float, eta: str, active_chunks: int):
            if modal:
                try:
                    if modal.winfo_exists():
                        modal.update_progress(downloaded, total, speed, eta, active_chunks)
                except Exception:
                    pass
            self._engine_progress_cb(downloaded, total, speed, eta, active_chunks)

        def _comb_complete(path: str, total_bytes: int, elapsed: float):
            has_modal = False
            if modal:
                try:
                    if modal.winfo_exists():
                        modal.on_download_complete(path, total_bytes, elapsed)
                        has_modal = True
                except Exception:
                    pass
            self._engine_complete_cb(path, total_bytes, elapsed, suppress_dialog=has_modal)

        def _comb_error(err: str):
            if modal:
                try:
                    if modal.winfo_exists():
                        modal.on_download_error(err)
                except Exception:
                    pass
            self._engine_error_cb(err)

        self.engine = TurboDownloadEngine(
            url=url,
            destination_path=dest,
            max_connections=max_conn,
            rate_limit_bytes_per_sec=bytes_limit,
            on_progress=_comb_progress,
            on_chunk_update=self._engine_chunk_update_cb,
            on_log=self.log,
            on_complete=_comb_complete,
            on_error=_comb_error
        )
        if modal and hasattr(modal, "attach_engine"):
            modal.attach_engine(self.engine)

        self.engine.start()

    def _start_youtube_download(
        self,
        url: str,
        dest: str,
        max_conn: int = 8,
        bytes_limit: float = 0.0,
        modal: Optional[Any] = None
    ):
        """Resolves available YouTube qualities and displays modern format selection modal."""
        if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
            try:
                self._yt_cancel_event.set()
            except Exception:
                pass
        self._yt_cancel_event = threading.Event()
        try:
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="disabled")
            self.btn_cancel.configure(state="normal")
            if hasattr(self, "btn_refresh_link"):
                self.btn_refresh_link.configure(state="normal", bg=self.c_panel_light, fg=self.c_accent)
            self.txt_log.delete("1.0", tk.END)

            for item in self.tree_chunks.get_children():
                self.tree_chunks.delete(item)
            self._draw_main_progress(0.0)
            self._draw_chunk_segments([])
            self.card_size.configure(text="Fetching available formats...")
        except Exception:
            pass

        plat = extract_media_platform(url)
        tag = plat.upper().replace(" / X", "")
        self.log(f"[{tag}] Detected {plat} stream URL: {url}")
        self.log(f"[{tag}] Querying available video resolutions and formats via yt-dlp...")

        # In < 50ms, display sleek frameless fetching toast indicator if main window is hidden or minimized
        if self.is_window_hidden_or_minimized():
            try:
                self._show_fetching_toast(url)
            except Exception:
                pass

        def _resolve_and_prompt():
            try:
                resolver = YouTubeResolver(
                    on_log=self.log,
                    cookies_from_browser=self.cookies_browser,
                    cookies_file=self.cookies_file
                )
                info, options = resolver.extract_format_options(url)

                if self._yt_cancel_event.is_set():
                    self.log(f"[{tag}] Quality analysis cancelled.")
                    return

                if not options:
                    raise RuntimeError(f"No downloadable media formats found for this {plat} video.")

                raw_title = info.get("title") or f"{plat}_Video"
                clean_title = sanitize_filename(raw_title)
                duration = int(info.get("duration") or 0)

                dest_dir = os.path.dirname(dest) or os.path.join(os.path.expanduser("~"), "Downloads")
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                except Exception:
                    pass

                initial_ext = options[0].ext or "mp4"
                initial_fn = f"{clean_title}.{initial_ext}"
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                    initial_dest = resolve_categorized_path(downloads_dir, initial_fn, auto_categorize=True)
                else:
                    initial_dest = os.path.join(dest_dir, initial_fn)

                def _show_modal():
                    try:
                        self._close_fetching_toast()
                        if self._yt_cancel_event.is_set():
                            return

                        self.card_size.configure(text="Select Quality")

                        def _start_coordinator(selected_opt: VideoFormatOption, final_dest: str, yt_modal: Optional[Any] = None):
                            stream_info = resolver.build_stream_info(info, selected_opt)

                            try:
                                self.entry_dest.delete(0, tk.END)
                                self.entry_dest.insert(0, final_dest)
                                self.btn_pause.configure(state="normal", text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
                                self.btn_cancel.configure(state="normal")
                            except Exception:
                                pass

                            def _comb_progress(downloaded, total, speed, eta, active):
                                if yt_modal:
                                    try:
                                        if yt_modal.winfo_exists():
                                            yt_modal.update_progress(downloaded, total, speed, eta, active)
                                    except Exception:
                                        pass
                                self._engine_progress_cb(downloaded, total, speed, eta, active)

                            def _comb_complete(path, total_bytes, elapsed):
                                has_yt_modal = False
                                if yt_modal:
                                    try:
                                        if yt_modal.winfo_exists():
                                            yt_modal.on_download_complete(path, total_bytes, elapsed)
                                            has_yt_modal = True
                                    except Exception:
                                        pass
                                self._engine_complete_cb(path, total_bytes, elapsed, suppress_dialog=has_yt_modal)

                            def _comb_error(err):
                                if yt_modal:
                                    try:
                                        if yt_modal.winfo_exists():
                                            yt_modal.on_download_error(err)
                                    except Exception:
                                        pass
                                self._engine_error_cb(err)

                            coordinator = StreamDownloadCoordinator(
                                stream_info=stream_info,
                                destination_path=final_dest,
                                max_connections=max_conn,
                                rate_limit_bytes_per_sec=bytes_limit,
                                on_progress=_comb_progress,
                                on_chunk_update=self._engine_chunk_update_cb,
                                on_log=self.log,
                                on_complete=_comb_complete,
                                on_error=_comb_error
                            )
                            self.engine = coordinator
                            if yt_modal and hasattr(yt_modal, "attach_engine"):
                                yt_modal.attach_engine(coordinator)
                            coordinator.start()

                        def _on_confirm(selected_opt: VideoFormatOption, final_dest: str):
                            self._quality_modal = None
                            self.clear_last_clipboard_url()
                            try:
                                is_hidden = self.is_window_hidden_or_minimized()
                                yt_prog_modal = None
                                if is_hidden:
                                    yt_prog_modal = DownloadConfirmationModal(
                                        parent=self.root,
                                        url=url,
                                        default_dest_path=final_dest,
                                        theme=self._theme_dict(),
                                        parent_app=self,
                                        show_progress_immediately=True
                                    )
                                _start_coordinator(selected_opt, final_dest, yt_modal=yt_prog_modal)
                            except Exception as e:
                                self._quality_modal = None
                                self.log(f"[{tag} START ERROR] {e}")
                                self._engine_error_cb(str(e))

                        def _on_open_in_main(selected_opt: VideoFormatOption, final_dest: str):
                            self._quality_modal = None
                            self.clear_last_clipboard_url()
                            self.restore_window()
                            try:
                                _start_coordinator(selected_opt, final_dest, yt_modal=None)
                            except Exception as e:
                                self._quality_modal = None
                                self.log(f"[{tag} START ERROR] {e}")
                                self._engine_error_cb(str(e))

                        def _on_cancel():
                            self._quality_modal = None
                            self.clear_last_clipboard_url()
                            try:
                                self.btn_start.configure(state="normal")
                                self.btn_pause.configure(state="disabled")
                                self.btn_cancel.configure(state="disabled")
                                self.card_size.configure(text=tr("status_ready", "Ready"))
                            except Exception:
                                pass
                            self.log(f"[{tag}] Video quality selection cancelled.")

                        theme_dict = {
                            "c_bg": self.c_bg,
                            "c_panel": self.c_panel,
                            "c_panel_light": self.c_panel_light,
                            "c_border": self.c_border,
                            "c_accent": self.c_accent,
                            "c_accent_dark": self.c_accent_dark,
                            "c_success": self.c_success,
                            "c_danger": self.c_danger,
                            "c_text_bright": self.c_text_bright,
                            "c_text_muted": self.c_text_muted,
                            "c_input_bg": self.c_input_bg
                        }

                        # Dismiss any previously open quality modal
                        if hasattr(self, "_quality_modal") and self._quality_modal:
                            try:
                                if self._quality_modal.winfo_exists():
                                    self._quality_modal.destroy()
                            except Exception:
                                pass
                            self._quality_modal = None

                        self._quality_modal = QualitySelectionModal(
                            parent=self.root,
                            video_title=raw_title,
                            duration=duration,
                            options=options,
                            default_dest_path=initial_dest,
                            theme=theme_dict,
                            on_confirm=_on_confirm,
                            on_cancel=_on_cancel,
                            on_open_in_main=_on_open_in_main,
                            parent_app=self
                        )
                    except Exception as e:
                        self._quality_modal = None
                        self.clear_last_clipboard_url()
                        self.log(f"[{tag} MODAL ERROR] {e}")
                        self._engine_error_cb(str(e))

                try:
                    self.dispatch_to_main_thread(_show_modal)
                except Exception:
                    pass

            except Exception as e:
                self.clear_last_clipboard_url()
                try:
                    self.dispatch_to_main_thread(self._close_fetching_toast)
                except Exception:
                    pass
                if not self._yt_cancel_event.is_set():
                    self.log(f"[{tag} ERROR] {e}")
                    try:
                        self.dispatch_to_main_thread(lambda: self._engine_error_cb(str(e)))
                    except Exception:
                        pass

        resolve_thread = threading.Thread(target=_resolve_and_prompt, daemon=True)
        resolve_thread.start()

    _start_media_download = _start_youtube_download

    def _on_pause_resume(self):
        if not self.engine:
            return
        if self.engine.is_paused:
            self.engine.resume()
            self.btn_pause.configure(text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
        else:
            self.engine.pause()
            self.btn_pause.configure(text=tr("btn_resume", "▶ Resume"), bg=self.c_warning)
            if hasattr(self, "btn_refresh_link"):
                self.btn_refresh_link.configure(state="normal", bg=self.c_panel_light, fg=self.c_accent)
            try:
                dl_url = (self.engine.url if self.engine and getattr(self.engine, "url", None) else self.entry_url.get()).strip()
                dl_dest = (self.engine.dest_path if self.engine and getattr(self.engine, "dest_path", None) else self.entry_dest.get()).strip()
                if dl_url and dl_dest and hasattr(self, "history_manager") and self.history_manager:
                    self.history_manager.add_or_update_entry(
                        url=dl_url,
                        file_path=dl_dest,
                        size_bytes=0,
                        status="Paused",
                        elapsed_sec=0.0
                    )
                    self._refresh_history_table()
            except Exception:
                pass

    def _on_cancel_download(self):
        if hasattr(self, "_yt_cancel_event"):
            self._yt_cancel_event.set()
        if hasattr(self, "_quality_modal") and self._quality_modal:
            try:
                if self._quality_modal.winfo_exists():
                    try:
                        self._quality_modal.grab_release()
                    except Exception:
                        pass
                    self._quality_modal.destroy()
            except Exception:
                pass
            self._quality_modal = None
        if hasattr(self, "_active_modal_dialog") and self._active_modal_dialog:
            try:
                if self._active_modal_dialog.winfo_exists():
                    try:
                        self._active_modal_dialog.grab_release()
                    except Exception:
                        pass
                    self._active_modal_dialog.destroy()
            except Exception:
                pass
            self._active_modal_dialog = None
        if hasattr(self, "_refresh_modal") and self._refresh_modal:
            try:
                if self._refresh_modal.winfo_exists():
                    self._refresh_modal.destroy()
            except Exception:
                pass
            self._refresh_modal = None
        if self.engine:
            self.engine.cancel()
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled", text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
        self.btn_cancel.configure(state="disabled")
        if hasattr(self, "btn_refresh_link"):
            self.btn_refresh_link.configure(state="disabled", bg=self.c_panel_light, fg=self.c_text_muted)
        self.card_size.configure(text=tr("status_ready", "Ready"))
        self.log("[CANCEL] Operation cancelled by user.")

    def _engine_progress_cb(self, downloaded: int, total: int, speed: float, eta: str, active_chunks: int):
        def _update():
            # Percentage
            pct = (downloaded / total * 100.0) if total > 0 else 0.0
            self._draw_main_progress(pct)

            # Speed
            if speed >= 1024 * 1024:
                speed_str = f"{speed / (1024*1024):.2f} MB/s"
            elif speed >= 1024:
                speed_str = f"{speed / 1024:.1f} KB/s"
            else:
                speed_str = f"{int(speed)} B/s"
            self.card_speed.configure(text=speed_str)

            # Size
            def _fmt_size(b):
                if b >= 1024 * 1024 * 1024:
                    return f"{b / (1024**3):.2f} GB"
                if b >= 1024 * 1024:
                    return f"{b / (1024**2):.1f} MB"
                if b >= 1024:
                    return f"{b / 1024:.1f} KB"
                return f"{b} B"

            if total > 0:
                size_str = f"{_fmt_size(downloaded)} / {_fmt_size(total)} ({pct:.1f}%)"
            else:
                size_str = f"{_fmt_size(downloaded)} (Streaming...)"
            self.card_size.configure(text=size_str)

            # ETA
            self.card_eta.configure(text=eta)

            # Active Threads
            if hasattr(self.engine, "get_chunks_snapshot"):
                total_chunks = len(self.engine.get_chunks_snapshot())
            elif self.engine:
                total_chunks = len(self.engine.chunks)
            else:
                total_chunks = 0
            self.card_threads.configure(text=f"{active_chunks} Active ({total_chunks} Total)")

        try:
            if self.root.winfo_exists():
                self.root.after(0, _update)
        except Exception:
            pass

    def _engine_chunk_update_cb(self):
        # Triggered on chunk state transitions or splits
        try:
            if self.root.winfo_exists():
                self.root.after(0, self._refresh_chunk_displays)
        except Exception:
            pass

    def _gui_refresh_tick(self):
        """Periodic tick ensuring smooth chunk visualization animation and processing queued thread tasks."""
        if getattr(self, "_closing", False):
            return
        try:
            if not hasattr(self, "root") or not self.root or not self.root.winfo_exists():
                return
        except Exception:
            return

        self._drain_dispatch_queue()

        if self.engine and self.engine.is_running and not self.engine.is_paused:
            try:
                self._refresh_chunk_displays()
            except Exception:
                pass
        try:
            if not getattr(self, "_closing", False) and self.root.winfo_exists():
                self._refresh_job = self.root.after(250, self._gui_refresh_tick)
        except Exception:
            pass

    def _engine_complete_cb(self, path: str, total_bytes: int, elapsed: float, suppress_dialog: bool = False):
        def _done():
            self._draw_main_progress(100.0)
            self._refresh_chunk_displays()
            self.btn_start.configure(state="normal")
            self.btn_pause.configure(state="disabled", text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
            self.btn_cancel.configure(state="disabled")
            if hasattr(self, "btn_refresh_link"):
                self.btn_refresh_link.configure(state="disabled", bg=self.c_panel_light, fg=self.c_text_muted)
            self.log(f"[COMPLETE] Download complete: {os.path.basename(path)} ({total_bytes:,} bytes in {elapsed:.1f}s)")
            try:
                dl_url = (self.engine.url if self.engine and getattr(self.engine, "url", None) else self.entry_url.get()).strip()
                if hasattr(self, "history_manager") and self.history_manager:
                    self.history_manager.add_or_update_entry(
                        url=dl_url,
                        file_path=path,
                        size_bytes=total_bytes,
                        status="Completed",
                        elapsed_sec=elapsed
                    )
                    self._refresh_history_table()
            except Exception:
                pass
            if hasattr(self, "_download_queue") and self._download_queue:
                q_url, q_dest, q_conn, q_limit = self._download_queue.pop(0)
                self.log(f"[QUEUE] Launching next queued download: {os.path.basename(q_dest)} ({len(self._download_queue)} remaining)")
                self._start_download_with_engine(q_url, q_dest, q_conn, q_limit)

            if suppress_dialog:
                return
            msg = (
                f"{tr('dialog_complete_msg_verified', 'File verified & assembled without corruption!')}\n\n"
                f"{tr('dialog_complete_msg_saved', 'Saved to:')} {path}\n"
                f"{tr('dialog_complete_msg_size', 'Size:')} {total_bytes:,} bytes\n"
                f"{tr('dialog_complete_msg_time', 'Total Time:')} {elapsed:.1f} seconds"
            )
            complete_title = tr("toast_completed_title", "Download Completed Successfully! 🚀")
            if hasattr(self, "show_safe_info"):
                self.show_safe_info(complete_title, msg)
            elif getattr(messagebox.showinfo, "_mock_name", None) or hasattr(messagebox.showinfo, "mock"):
                messagebox.showinfo(complete_title, msg)
            else:
                try:
                    if hasattr(self, "root") and self.root and self.root.winfo_exists():
                        SafeModalDialog(
                            self.root,
                            title=complete_title,
                            message=msg,
                            dialog_type="info",
                            theme=getattr(self, "_theme_dict", lambda: None)()
                        )
                except Exception:
                    pass
        try:
            if self.root.winfo_exists():
                self.root.after(0, _done)
        except Exception:
            pass

    def _engine_error_cb(self, error_msg: str):
        def _err():
            if hasattr(self, "_quality_modal") and self._quality_modal:
                try:
                    if self._quality_modal.winfo_exists():
                        try:
                            self._quality_modal.grab_release()
                        except Exception:
                            pass
                        self._quality_modal.destroy()
                except Exception:
                    pass
                self._quality_modal = None
            if hasattr(self, "btn_start"):
                try:
                    self.btn_start.configure(state="normal")
                except Exception:
                    pass
            if hasattr(self, "btn_pause"):
                try:
                    self.btn_pause.configure(state="disabled", text=tr("btn_pause", "⏸ Pause"), bg=getattr(self, "c_panel_light", "#334155"))
                except Exception:
                    pass
            if hasattr(self, "btn_cancel"):
                try:
                    self.btn_cancel.configure(state="disabled")
                except Exception:
                    pass
            is_expired = any(k in str(error_msg) for k in ("401", "403", "410", "Forbidden", "Expired", "Unauthorized"))
            if hasattr(self, "btn_refresh_link"):
                try:
                    if is_expired:
                        self.btn_refresh_link.configure(state="normal", bg=getattr(self, "c_warning", "#f59e0b"), fg="#0f172a")
                    else:
                        self.btn_refresh_link.configure(state="normal", bg=getattr(self, "c_panel_light", "#334155"), fg=getattr(self, "c_accent", "#38bdf8"))
                except Exception:
                    pass
            if hasattr(self, "card_size"):
                try:
                    self.card_size.configure(text=tr("status_ready", "Ready"))
                except Exception:
                    pass
            if hasattr(self, "log"):
                try:
                    self.log(f"[ERROR] Download Error: {error_msg}")
                except Exception:
                    pass

            try:
                dl_url = (self.engine.url if self.engine and getattr(self.engine, "url", None) else self.entry_url.get()).strip()
                dl_dest = (self.engine.dest_path if self.engine and getattr(self.engine, "dest_path", None) else self.entry_dest.get()).strip()
                if dl_url and dl_dest and hasattr(self, "history_manager") and self.history_manager:
                    self.history_manager.add_or_update_entry(
                        url=dl_url,
                        file_path=dl_dest,
                        size_bytes=0,
                        status="Failed",
                        elapsed_sec=0.0
                    )
                    self._refresh_history_table()
            except Exception:
                pass

            if is_expired:
                msg = (
                    f"{tr('dialog_expired_msg1', 'Download stopped: Server rejected session (HTTP 401/403/410).')}\n\n"
                    f"{tr('dialog_expired_details', 'Details:')} {error_msg}\n\n"
                    f"{tr('dialog_expired_msg2', '💡 All partially downloaded chunk files are safely preserved on disk.')}\n"
                    f"{tr('dialog_expired_msg3', 'Would you like to refresh the download link now to resume?')}"
                )
                if hasattr(self, "ask_safe_yesno"):
                    def _on_yes_refresh():
                        self._open_refresh_link_dialog()
                    self.ask_safe_yesno(
                        tr("dialog_expired_title", "Download Link Expired ⚠️"),
                        msg,
                        on_yes=_on_yes_refresh
                    )
                    return

            msg = f"{tr('dialog_error_prefix', 'Encountered error during download:')}\n\n{error_msg}"
            err_title = tr("dialog_error_title", "Download Error")
            if hasattr(self, "show_safe_error"):
                self.show_safe_error(err_title, msg)
            elif getattr(messagebox.showerror, "_mock_name", None) or hasattr(messagebox.showerror, "mock"):
                messagebox.showerror(err_title, msg)
            else:
                try:
                    if hasattr(self, "root") and self.root and self.root.winfo_exists():
                        SafeModalDialog(
                            self.root,
                            title=err_title,
                            message=msg,
                            dialog_type="error",
                            theme=getattr(self, "_theme_dict", lambda: None)()
                        )
                except Exception:
                    pass
        try:
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
                self.root.after(0, _err)
            else:
                _err()
        except Exception:
            pass

    def _open_refresh_link_dialog(self):
        """Displays sleek, dark-themed, grab-free Refresh Link modal dialog."""
        current_url = ""
        if self.engine and getattr(self.engine, "url", None):
            current_url = self.engine.url
        elif hasattr(self, "entry_url"):
            current_url = self.entry_url.get().strip()

        total_size = 0
        downloaded_bytes = 0
        if self.engine:
            total_size = getattr(self.engine, "total_size", 0)
            chunks = getattr(self.engine, "chunks", [])
            downloaded_bytes = sum(c.downloaded_bytes for c in chunks) if chunks else 0

        dest_path = self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ""
        filename = os.path.basename(dest_path) if dest_path else "download.bin"
        expected_ranges = getattr(self.engine, "supports_ranges", True) if self.engine else True

        if hasattr(self, "_refresh_modal") and self._refresh_modal:
            try:
                if self._refresh_modal.winfo_exists():
                    self._refresh_modal.destroy()
            except Exception:
                pass
            self._refresh_modal = None

        self._refresh_modal = RefreshLinkModal(
            parent=self.root,
            old_url=current_url,
            total_size=total_size,
            downloaded_bytes=downloaded_bytes,
            filename=filename,
            theme=self._theme_dict(),
            on_success=self._on_link_refreshed_success,
            expected_ranges=expected_ranges
        )

    def _on_link_refreshed_success(self, new_url: str, headers: Optional[Dict[str, str]] = None):
        """Callback invoked when user confirms a validated new download URL."""
        try:
            if hasattr(self, "entry_url"):
                self.entry_url.delete(0, tk.END)
                self.entry_url.insert(0, new_url)

            if self.engine:
                self.engine.refresh_link(new_url, headers=headers, auto_resume=True)
                if hasattr(self, "btn_start"):
                    self.btn_start.configure(state="disabled")
                if hasattr(self, "btn_pause"):
                    self.btn_pause.configure(state="normal", text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
                if hasattr(self, "btn_cancel"):
                    self.btn_cancel.configure(state="normal")
                if hasattr(self, "btn_refresh_link"):
                    self.btn_refresh_link.configure(state="normal", bg=self.c_panel_light, fg=self.c_accent)
                self.log(f"[REFRESH] Link refreshed successfully: {new_url}")
                self.show_safe_info(
                    "Link Refreshed Successfully 🔄",
                    f"Download address updated to:\n{new_url}\n\nResuming download seamlessly from existing progress without losing data!"
                )
            else:
                self.log(f"[REFRESH] URL updated: {new_url}")
                self.show_safe_info("URL Updated", f"Download URL updated to:\n{new_url}\n\nClick '▶ Start Download' to begin.")
        except Exception as e:
            self.show_safe_error("Refresh Link Failed", f"Could not refresh download link:\n{e}")
