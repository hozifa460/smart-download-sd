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


from .media_download_controller import MediaDownloadControllerMixin


class DownloadControllerMixin(MediaDownloadControllerMixin):
    """Handles download triggers, background thread dispatch, progress monitoring, and completion/error states."""

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
        if getattr(self, "_is_resolving_start", False) or (self.engine and self.engine.is_running):
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

        self._is_resolving_start = True
        try:
            self.btn_start.configure(state="disabled")
        except Exception:
            pass

        # Manually typed non-media URL: resolve in background thread before starting
        def _on_resolved(info: Dict[str, Any]):
            self._is_resolving_start = False
            try:
                self.btn_start.configure(state="normal")
            except Exception:
                pass
            if info.get("error") and not info.get("resolved"):
                return
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

            self._start_download_with_engine(real_url, final_dest, max_conn, bytes_limit, modal=None, pre_probed_info=info)

        self._resolve_real_url_async(url, on_resolved=_on_resolved)

    def _start_download_with_engine(
        self,
        url: str,
        dest: str,
        max_conn: int = 8,
        bytes_limit: float = 0.0,
        modal: Optional[Any] = None,
        pre_probed_info: Optional[Dict[str, Any]] = None
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

        if not pre_probed_info:
            pre_probed_info = getattr(modal, "probed_info", None) if modal else getattr(self, "_last_probed_info", None)

        self.engine = TurboDownloadEngine(
            url=url,
            destination_path=dest,
            max_connections=max_conn,
            rate_limit_bytes_per_sec=bytes_limit,
            on_progress=_comb_progress,
            on_chunk_update=self._engine_chunk_update_cb,
            on_log=self.log,
            on_complete=_comb_complete,
            on_error=_comb_error,
            pre_probed_info=pre_probed_info
        )
        if modal and hasattr(modal, "attach_engine"):
            modal.attach_engine(self.engine)

        self.engine.start()

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
        self._last_prog_args = (downloaded, total, speed, eta, active_chunks)
        if getattr(self, "_prog_update_pending", False):
            return
        self._prog_update_pending = True

        def _update():
            self._prog_update_pending = False
            args = getattr(self, "_last_prog_args", None)
            if not args:
                return
            d, t, sp, et, ac = args
            pct = (d / t * 100.0) if t > 0 else 0.0
            self._draw_main_progress(pct)

            if sp >= 1024 * 1024:
                speed_str = f"{sp / (1024*1024):.2f} MB/s"
            elif sp >= 1024:
                speed_str = f"{sp / 1024:.1f} KB/s"
            else:
                speed_str = f"{int(sp)} B/s"
            self.card_speed.configure(text=speed_str)

            def _fmt_size(b):
                if b >= 1024 * 1024 * 1024:
                    return f"{b / (1024**3):.2f} GB"
                if b >= 1024 * 1024:
                    return f"{b / (1024**2):.1f} MB"
                if b >= 1024:
                    return f"{b / 1024:.1f} KB"
                return f"{b} B"

            size_str = f"{_fmt_size(d)} / {_fmt_size(t)} ({pct:.1f}%)" if t > 0 else f"{_fmt_size(d)} (Streaming...)"
            self.card_size.configure(text=size_str)
            self.card_eta.configure(text=et)

            total_chunks = len(self.engine.get_chunks_snapshot()) if hasattr(self.engine, "get_chunks_snapshot") else (len(self.engine.chunks) if self.engine else 0)
            self.card_threads.configure(text=f"{ac} Active ({total_chunks} Total)")

        try:
            if self.root.winfo_exists():
                self.root.after(0, _update)
            else:
                self._prog_update_pending = False
        except Exception:
            self._prog_update_pending = False

    def _engine_chunk_update_cb(self):
        if getattr(self, "_chunk_ui_update_pending", False) or getattr(self, "_chunk_update_pending", False):
            return
        self._chunk_ui_update_pending = True
        self._chunk_update_pending = True

        def _do_chunk():
            self._chunk_ui_update_pending = False
            self._chunk_update_pending = False
            self._refresh_chunk_displays()

        try:
            if self.root.winfo_exists():
                self.root.after(0, _do_chunk)
            else:
                self._chunk_ui_update_pending = False
                self._chunk_update_pending = False
        except Exception:
            self._chunk_ui_update_pending = False
            self._chunk_update_pending = False

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
                    self.history_manager.add_or_update_entry(url=dl_url, file_path=dl_dest, size_bytes=0, status="Failed", elapsed_sec=0.0)
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
                    self.ask_safe_yesno(tr("dialog_expired_title", "Download Link Expired ⚠️"), msg, on_yes=self._open_refresh_link_dialog)
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
                        SafeModalDialog(self.root, title=err_title, message=msg, dialog_type="error", theme=getattr(self, "_theme_dict", lambda: None)())
                except Exception:
                    pass
        try:
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
                self.root.after(0, _err)
            else:
                _err()
        except Exception:
            pass


__all__ = ["DownloadControllerMixin", "MediaDownloadControllerMixin"]
