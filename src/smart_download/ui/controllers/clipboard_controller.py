"""
Clipboard sniffer and URL interception controller mixin for Smart Download (SD).
"""
import os
import sys
import threading
import ctypes
from typing import Optional, Callable, Dict, Any

try:
    import tkinter as tk
except Exception:
    tk = None  # type: ignore

from smart_download.i18n import tr
from smart_download.utils import (
    get_clipboard_text,
    is_downloadable_url,
    is_potential_html_url,
    resolve_categorized_path,
    derive_download_filename,
)
from smart_download.core import resolve_real_download_url
from smart_download.services import is_media_url, extract_media_platform
from smart_download.ui.modals.confirm_modal import DownloadConfirmationModal
from smart_download.ui.components.base_modal import SafeModalDialog

IS_WINDOWS = sys.platform == "win32"


class ClipboardControllerMixin:
    """Provides automatic clipboard monitoring and candidate download URL interception."""

    def _init_clipboard_sniffer(self):
        """Initializes clipboard monitor state to current clipboard content so existing text doesn't trigger."""
        if IS_WINDOWS:
            try:
                self._last_clipboard_seq = ctypes.windll.user32.GetClipboardSequenceNumber()
            except Exception:
                self._last_clipboard_seq = None
        try:
            cur = get_clipboard_text(self.root)
            if cur:
                self._last_clipboard_url = cur.strip()
        except Exception:
            pass

        if hasattr(self, "root") and self.root:
            try:
                self._clipboard_job = self.root.after(self._clipboard_poll_interval, self._check_clipboard_tick)
            except Exception:
                pass

    def _check_clipboard_tick(self):
        """Periodic timer polling system clipboard for downloadable URLs."""
        if getattr(self, "_closing", False) or not hasattr(self, "root") or not self.root:
            return
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return

        if getattr(self, "_clipboard_sniffer_active", True):
            try:
                self._check_clipboard_now()
            except Exception:
                pass

        if not getattr(self, "_closing", False):
            try:
                if self.root.winfo_exists():
                    self._clipboard_job = self.root.after(self._clipboard_poll_interval, self._check_clipboard_tick)
            except Exception:
                pass

    def _check_clipboard_now(self, force: bool = False):
        """Checks if current clipboard contains a new downloadable URL and processes it."""
        seq = None
        if IS_WINDOWS and not force:
            try:
                seq = ctypes.windll.user32.GetClipboardSequenceNumber()
            except Exception:
                seq = None

            # Fast path: sequence number unchanged -> nothing was copied
            if seq is not None and getattr(self, "_last_clipboard_seq", None) is not None:
                if seq == self._last_clipboard_seq:
                    return

        text = get_clipboard_text(self.root)

        seq_changed = (seq is not None and getattr(self, "_last_clipboard_seq", None) is not None and seq != self._last_clipboard_seq)

        if seq is not None:
            self._last_clipboard_seq = seq

        if not text or not isinstance(text, str):
            return

        url = text.strip()
        if not url:
            return

        # Prevent duplicate prompt if URL matches last processed clipboard string and sequence unchanged.
        # But if sequence number changed (user explicitly copied the link again) or last URL was cleared, allow processing.
        if not seq_changed and (url == getattr(self, "_last_clipboard_url", None)):
            return

        self._last_clipboard_url = url

        if is_downloadable_url(url):
            self._on_clipboard_url_detected(url)

    def clear_last_clipboard_url(self):
        """Clears cached last clipboard URL string so re-copying or re-checking triggers immediately."""
        self._last_clipboard_url = None
        self._last_clipboard_seq = None

    def _resolve_real_url_async(
        self,
        url: str,
        on_resolved: Callable[[Dict[str, Any]], None],
        show_toast: bool = True,
        modal_to_close: Optional[Any] = None
    ):
        """Asynchronously probes and resolves a candidate download URL, handling HTML landing pages."""
        if show_toast:
            try:
                self._show_fetching_toast(url)
            except Exception:
                pass

        def _worker():
            info = resolve_real_download_url(url, ssl_context=getattr(self, "ssl_context", None))

            def _dispatch():
                try:
                    self._close_fetching_toast()
                except Exception:
                    pass

                candidates = info.get("candidates") or []

                if info.get("is_html") and not info.get("resolved"):
                    if len(candidates) > 1:
                        self.clear_last_clipboard_url()
                        if modal_to_close:
                            try:
                                modal_to_close.destroy()
                            except Exception:
                                pass
                            if getattr(self, "_confirm_modal", None) is modal_to_close:
                                self._confirm_modal = None
                        self.log(f"[LINK RESOLVER] Multiple download candidates ({len(candidates)}) detected on page: {url}")
                        self._show_multiple_candidates_dialog(url, candidates, page_title=info.get("page_title", ""))
                        return

                    self.clear_last_clipboard_url()
                    if modal_to_close:
                        try:
                            modal_to_close.destroy()
                        except Exception:
                            pass
                        if getattr(self, "_confirm_modal", None) is modal_to_close:
                            self._confirm_modal = None
                    try:
                        self.btn_start.configure(state="normal")
                        self.btn_pause.configure(state="disabled")
                        self.btn_cancel.configure(state="disabled")
                    except Exception:
                        pass
                    self.log(f"[LINK RESOLVER] Web page detected (not a download link): {url}")
                    msg = tr("dialog_not_download_msg")
                    SafeModalDialog(
                        self.root,
                        title=tr("dialog_not_download_title"),
                        message=msg,
                        dialog_type="warning",
                        theme=self._theme_dict()
                    )
                    return

                if len(candidates) > 1:
                    self.clear_last_clipboard_url()
                    if modal_to_close:
                        try:
                            modal_to_close.destroy()
                        except Exception:
                            pass
                        if getattr(self, "_confirm_modal", None) is modal_to_close:
                            self._confirm_modal = None
                    self.log(f"[LINK RESOLVER] Multiple download candidates ({len(candidates)}) detected on page: {url}")
                    self._show_multiple_candidates_dialog(url, candidates, page_title=info.get("page_title", ""))
                    return

                if len(candidates) == 1 and info.get("is_html"):
                    cand = candidates[0]
                    info["url"] = cand["url"]
                    if cand.get("filename"):
                        info["filename"] = cand["filename"]
                    info["resolved"] = True
                    info["is_html"] = False

                on_resolved(info)

            self.dispatch_to_main_thread(_dispatch)

        t = threading.Thread(target=_worker, daemon=True, name="LinkResolverThread")
        t.start()

    def _on_clipboard_url_detected(self, url: str):
        """Dispatches an intercepted downloadable URL from the clipboard."""
        self.log(f"[CLIPBOARD] Intercepted downloadable link from clipboard: {url}")

        # Populate URL entry
        try:
            self.entry_url.delete(0, tk.END)
            self.entry_url.insert(0, url)
        except Exception:
            pass

        # Derive and populate destination
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        cur_dest = ""
        try:
            cur_dest = self.entry_dest.get().strip()
        except Exception:
            pass
        dest_dir = os.path.dirname(cur_dest) if cur_dest else downloads_dir
        if not os.path.isdir(dest_dir):
            dest_dir = downloads_dir

        url_fn = derive_download_filename(url)
        if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
            new_dest = resolve_categorized_path(downloads_dir, url_fn, auto_categorize=True)
        else:
            new_dest = os.path.join(dest_dir, url_fn)
        try:
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, new_dest)
        except Exception:
            pass

        # DO NOT force-restore the main window if hidden or minimized in tray
        if not self.is_window_hidden_or_minimized():
            try:
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass

        # Non-blocking TDM-style download handling (no blocking modal dialogs / grab_set traps)
        if is_media_url(url):
            plat = extract_media_platform(url)
            if self.engine and self.engine.is_running:
                self.log(f"[CLIPBOARD] Note: Active task is running. {plat} stream queued in URL field.")
            elif getattr(self, "_auto_start_clipboard", True):
                self.log(f"[CLIPBOARD] {plat} stream detected: {url}. Starting format analysis...")
                try:
                    max_conn = int(self.conn_var.get())
                except Exception:
                    max_conn = 8
                try:
                    kb_limit = float(self.entry_custom_speed.get().strip())
                except Exception:
                    kb_limit = 0.0
                bytes_limit = kb_limit * 1024.0 if kb_limit > 0 else 0.0
                self._start_youtube_download(url, new_dest, max_conn, bytes_limit)
            else:
                self.log(f"[CLIPBOARD] {plat} stream populated: {url}. Ready for one-click start.")
        else:
            if self.engine and self.engine.is_running:
                self.log(f"[CLIPBOARD] Note: Active transfer in progress. URL '{url_fn}' populated in inputs.")
            elif is_potential_html_url(url):
                def _on_clipboard_resolved(info: Dict[str, Any]):
                    if self.engine and self.engine.is_running:
                        return

                    real_url = info.get("url") or url
                    if info.get("resolved"):
                        self.log(f"[LINK RESOLVER] Web page detected. Real file found: {real_url}")

                    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                    cur_d = ""
                    try:
                        cur_d = self.entry_dest.get().strip()
                    except Exception:
                        pass
                    dest_dir = os.path.dirname(cur_d) if cur_d else downloads_dir
                    if not os.path.isdir(dest_dir):
                        dest_dir = downloads_dir

                    resolved_fn = info.get("filename") or derive_download_filename(real_url)
                    if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                        final_dest = resolve_categorized_path(downloads_dir, resolved_fn, auto_categorize=True)
                    else:
                        final_dest = os.path.join(dest_dir, resolved_fn)

                    try:
                        self.entry_url.delete(0, tk.END)
                        self.entry_url.insert(0, real_url)
                        self.entry_dest.delete(0, tk.END)
                        self.entry_dest.insert(0, final_dest)
                    except Exception:
                        pass

                    if not self.is_window_hidden_or_minimized():
                        try:
                            self.root.lift()
                            self.root.focus_force()
                        except Exception:
                            pass

                    if getattr(self, "_auto_start_clipboard", True):
                        self.log(f"[CLIPBOARD] Intercepted link ready: '{resolved_fn}'. Showing TDM confirmation dialog...")
                        self._show_download_confirmation_dialog(real_url, final_dest)
                    else:
                        self.log(f"[CLIPBOARD] Intercepted link populated: '{resolved_fn}'. Ready for one-click start.")

                self._resolve_real_url_async(url, on_resolved=_on_clipboard_resolved, show_toast=True)
            elif getattr(self, "_auto_start_clipboard", True):
                self.log(f"[CLIPBOARD] Intercepted link ready: '{url_fn}'. Showing TDM confirmation dialog...")
                self._show_download_confirmation_dialog(url, new_dest)
            else:
                self.log(f"[CLIPBOARD] Intercepted link populated: '{url_fn}'. Ready for one-click start.")

    def _show_download_confirmation_dialog(self, url: str, default_dest: str):
        """Displays the TDM-style download confirmation dialog for intercepted URLs."""
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root:
                try:
                    self.root.after(0, lambda: self._show_download_confirmation_dialog(url, default_dest))
                except Exception:
                    pass
            return

        self._close_fetching_toast()

        if hasattr(self, "_confirm_modal") and self._confirm_modal:
            try:
                if self._confirm_modal.winfo_exists():
                    if getattr(self._confirm_modal, "is_in_progress_view", False) or getattr(self._confirm_modal, "is_completed", False):
                        # Modal is actively downloading or displaying completion actions; keep it intact
                        self.log(f"[CLIPBOARD] Active standalone download in progress; queued '{derive_download_filename(url)}' in inputs.")
                        return
                    self._confirm_modal.destroy()
            except Exception:
                pass
            self._confirm_modal = None

        def _on_start_in_window(final_dest: str, max_conn: int, bytes_limit: float, modal: DownloadConfirmationModal):
            # Keeps the main window hidden/minimized
            def _proceed_start(info: Dict[str, Any]):
                resolved_url = info.get("url") or url
                resolved_fn = info.get("filename") or derive_download_filename(resolved_url)
                dest_dir = os.path.dirname(final_dest) if final_dest else os.path.join(os.path.expanduser("~"), "Downloads")
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                    act_dest = resolve_categorized_path(downloads_dir, resolved_fn, auto_categorize=True)
                else:
                    act_dest = os.path.join(dest_dir, resolved_fn)
                self.log(f"[CLIPBOARD] Download started in standalone window: {os.path.basename(act_dest)} (Threads: {max_conn}, Speed Limit: {bytes_limit} B/s)")
                self._start_download_with_engine(resolved_url, act_dest, max_conn, bytes_limit, modal=modal)

            if is_potential_html_url(url):
                self._resolve_real_url_async(url, on_resolved=_proceed_start, modal_to_close=modal)
            else:
                self.log(f"[CLIPBOARD] Download started in standalone window: {os.path.basename(final_dest)} (Threads: {max_conn}, Speed Limit: {bytes_limit} B/s)")
                self._start_download_with_engine(url, final_dest, max_conn, bytes_limit, modal=modal)

        def _on_open_in_main(final_dest: str, max_conn: int, bytes_limit: float):
            self._confirm_modal = None
            self.restore_window()
            try:
                self.entry_url.delete(0, tk.END)
                self.entry_url.insert(0, url)
                self.entry_dest.delete(0, tk.END)
                self.entry_dest.insert(0, final_dest)
                self.conn_var.set(str(max_conn))
                if bytes_limit > 0:
                    self.entry_custom_speed.delete(0, tk.END)
                    self.entry_custom_speed.insert(0, str(int(bytes_limit / 1024.0)))
                else:
                    self.entry_custom_speed.delete(0, tk.END)
            except Exception:
                pass
            self.log(f"[CLIPBOARD] Download opened in main app: {os.path.basename(final_dest)}")
            self._on_start_download(skip_resolver=True)

        def _on_confirm(final_dest: str, *args):
            self._confirm_modal = None
            self.clear_last_clipboard_url()
            try:
                self.entry_dest.delete(0, tk.END)
                self.entry_dest.insert(0, final_dest)
            except Exception:
                pass
            self.log(f"[CLIPBOARD] Download confirmed by user: {os.path.basename(final_dest)}. Starting download...")
            self._on_start_download()

        def _on_cancel():
            self._confirm_modal = None
            self.clear_last_clipboard_url()
            self.log(f"[CLIPBOARD] Download cancelled by user for: {derive_download_filename(url)}")

        try:
            default_conn = 8
            try:
                default_conn = int(self.conn_var.get())
            except Exception:
                pass
            default_speed = 0.0
            try:
                kb = float(self.entry_custom_speed.get().strip())
                default_speed = kb * 1024.0 if kb > 0 else 0.0
            except Exception:
                pass

            self._confirm_modal = DownloadConfirmationModal(
                parent=self.root,
                url=url,
                default_dest_path=default_dest,
                theme=self._theme_dict(),
                on_confirm=_on_confirm,
                on_cancel=_on_cancel,
                on_start_in_window=_on_start_in_window,
                on_open_in_main=_on_open_in_main,
                parent_app=self,
                default_connections=default_conn,
                default_speed_limit=default_speed
            )
        except Exception as e:
            self._confirm_modal = None
            self.log(f"[CONFIRM MODAL ERROR] {e}")

    def _update_sniffer_btn(self):
        """Refreshes the visual state of the clipboard sniffer button."""
        if not hasattr(self, "btn_clipboard_sniffer"):
            return
        try:
            if not self.btn_clipboard_sniffer.winfo_exists():
                return
        except Exception:
            return
        if getattr(self, "_clipboard_sniffer_active", True):
            self.btn_clipboard_sniffer.configure(
                text=tr("btn_sniffer_active"),
                fg=self.c_success,
                bg=self.c_panel_light
            )
        else:
            self.btn_clipboard_sniffer.configure(
                text=tr("btn_sniffer_paused"),
                fg=self.c_text_muted,
                bg=self.c_panel
            )

    def toggle_clipboard_sniffer(self):
        """Toggles automatic clipboard URL monitoring on or off."""
        self._clipboard_sniffer_active = not getattr(self, "_clipboard_sniffer_active", True)
        self._update_sniffer_btn()
        if self._clipboard_sniffer_active:
            self.log("[CLIPBOARD] Sniffer Active: Monitoring system clipboard for downloadable links.")
            if getattr(self, "_clipboard_job", None) is None and hasattr(self, "root") and self.root:
                try:
                    if self.root.winfo_exists():
                        self._clipboard_job = self.root.after(self._clipboard_poll_interval, self._check_clipboard_tick)
                except Exception:
                    pass
        else:
            self.log("[CLIPBOARD] Sniffer Paused: Clipboard monitoring paused.")

        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.update_menu()
            except Exception:
                pass
