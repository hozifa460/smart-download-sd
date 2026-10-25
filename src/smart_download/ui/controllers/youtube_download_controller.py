"""
YouTube and social media stream download controller mixin for Smart Download (SD).
"""
import os
import threading
from typing import Dict, Any, Optional

try:
    import tkinter as tk
except Exception:
    tk = None  # type: ignore

from smart_download.i18n import tr
from smart_download.utils.file_ops import resolve_categorized_path
from smart_download.core.stream_coordinator import StreamDownloadCoordinator
from smart_download.services.youtube_service import (
    YouTubeResolver,
    VideoFormatOption,
    extract_media_platform,
    sanitize_filename,
)
from ..modals.quality_modal import QualitySelectionModal
from ..modals.confirm_modal import DownloadConfirmationModal


class YouTubeDownloadControllerMixin:
    """Handles YouTube & social media stream format analysis, quality dialogs, and stream coordinators."""

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
        if hasattr(self, "is_window_hidden_or_minimized") and self.is_window_hidden_or_minimized():
            try:
                self._show_fetching_toast(url)
            except Exception:
                pass

        def _resolve_and_prompt():
            try:
                resolver = YouTubeResolver(
                    on_log=self.log,
                    cookies_from_browser=getattr(self, "cookies_browser", "auto"),
                    cookies_file=getattr(self, "cookies_file", "")
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
                if getattr(self, "auto_categorize_folders", True) and hasattr(self, "_is_downloads_or_category_subfolder") and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                    initial_dest = resolve_categorized_path(downloads_dir, initial_fn, auto_categorize=True)
                else:
                    initial_dest = os.path.join(dest_dir, initial_fn)

                def _show_modal():
                    try:
                        if hasattr(self, "_close_fetching_toast"):
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
                            if hasattr(self, "clear_last_clipboard_url"):
                                self.clear_last_clipboard_url()
                            try:
                                is_hidden = self.is_window_hidden_or_minimized() if hasattr(self, "is_window_hidden_or_minimized") else False
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
                            if hasattr(self, "clear_last_clipboard_url"):
                                self.clear_last_clipboard_url()
                            if hasattr(self, "restore_window"):
                                self.restore_window()
                            try:
                                _start_coordinator(selected_opt, final_dest, yt_modal=None)
                            except Exception as e:
                                self._quality_modal = None
                                self.log(f"[{tag} START ERROR] {e}")
                                self._engine_error_cb(str(e))

                        def _on_cancel():
                            self._quality_modal = None
                            if hasattr(self, "clear_last_clipboard_url"):
                                self.clear_last_clipboard_url()
                            try:
                                self.btn_start.configure(state="normal")
                                self.btn_pause.configure(state="disabled")
                                self.btn_cancel.configure(state="disabled")
                                self.card_size.configure(text=tr("status_ready", "Ready"))
                            except Exception:
                                pass
                            self.log(f"[{tag}] Video quality selection cancelled.")

                        theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {
                            "c_bg": getattr(self, "c_bg", "#0f172a"),
                            "c_panel": getattr(self, "c_panel", "#1e293b"),
                            "c_panel_light": getattr(self, "c_panel_light", "#334155"),
                            "c_border": getattr(self, "c_border", "#475569"),
                            "c_accent": getattr(self, "c_accent", "#38bdf8"),
                            "c_accent_dark": getattr(self, "c_accent_dark", "#0284c7"),
                            "c_success": getattr(self, "c_success", "#10b981"),
                            "c_danger": getattr(self, "c_danger", "#ef4444"),
                            "c_text_bright": getattr(self, "c_text_bright", "#f8fafc"),
                            "c_text_muted": getattr(self, "c_text_muted", "#94a3b8"),
                            "c_input_bg": getattr(self, "c_input_bg", "#090d16")
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
                        if hasattr(self, "clear_last_clipboard_url"):
                            self.clear_last_clipboard_url()
                        self.log(f"[{tag} MODAL ERROR] {e}")
                        self._engine_error_cb(str(e))

                try:
                    self.dispatch_to_main_thread(_show_modal)
                except Exception:
                    pass

            except Exception as e:
                if hasattr(self, "clear_last_clipboard_url"):
                    self.clear_last_clipboard_url()
                try:
                    if hasattr(self, "_close_fetching_toast"):
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


__all__ = ["YouTubeDownloadControllerMixin"]
