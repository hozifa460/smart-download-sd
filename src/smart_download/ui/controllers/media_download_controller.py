"""
MediaDownloadControllerMixin: Handles YouTube/media format extraction, candidate modals, batch queueing, and link refresh.
"""
import os
import sys
import time
import threading
from typing import Dict, Any, Optional, List

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

from smart_download.i18n import LocalizationManager, tr
from smart_download.utils.url_utils import derive_download_filename
from smart_download.utils.file_ops import resolve_categorized_path
from smart_download.core.stream_coordinator import StreamDownloadCoordinator
from smart_download.services.youtube_service import (
    YouTubeResolver,
    VideoFormatOption,
    extract_media_platform,
    sanitize_filename,
)
from ..modals.candidates_modal import MultipleCandidatesModal
from ..modals.quality_modal import QualitySelectionModal
from ..modals.confirm_modal import DownloadConfirmationModal
from ..modals.refresh_modal import RefreshLinkModal


class MediaDownloadControllerMixin:
    """Handles YouTube/media downloads, multi-candidate selection modals, and link refresh."""

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
                                self.btn_pause.configure(state="normal", text=tr("btn_pause", "âڈ¸ Pause"), bg=self.c_panel_light)
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
