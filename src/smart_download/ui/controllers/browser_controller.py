"""
BrowserControllerMixin: Handles background browser self-registration and intercepted download dispatching.
"""
import os
import sys
import threading
import urllib.parse
from typing import Dict, Any, Optional

import tkinter as tk

from ...utils.url_utils import is_potential_html_url, derive_download_filename
from ...utils.file_ops import resolve_categorized_path
from ...services.youtube_service import is_media_url, extract_media_platform, sanitize_filename
from ...services.browser.registry import check_and_register_browser


class BrowserControllerMixin:
    """
    Mixin handling background browser extension self-registration and intercepted download dispatching.
    """

    def _start_browser_self_registration(self):
        """Asynchronously checks and registers or heals browser integration in background without blocking GUI."""
        def _task():
            try:
                check_and_register_browser()
            except Exception:
                pass
        t = threading.Thread(target=_task, daemon=True, name="BrowserAutoRegisterThread")
        t.start()

    def _on_browser_download_received(self, download_info: Dict[str, Any]):
        """Dispatches intercepted download from browser bridge thread to Tkinter main thread."""
        self.dispatch_to_main_thread(self._apply_browser_download, download_info)

    def _apply_browser_download(self, download_info: Dict[str, Any]):
        """Applies intercepted download parameters to the GUI and starts transfer if requested."""
        url = download_info.get("url", "").strip()
        filename = download_info.get("filename", "").strip()
        start_immediately = download_info.get("start_immediately", True)

        if not url:
            return

        self.log(f"[BROWSER] Intercepted download from browser extension: {url}")

        # Populate URL entry
        self.entry_url.delete(0, tk.END)
        self.entry_url.insert(0, url)

        # Populate Destination entry
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        cur_dest = self.entry_dest.get().strip()
        dest_dir = os.path.dirname(cur_dest) if cur_dest else downloads_dir
        if not os.path.isdir(dest_dir):
            dest_dir = downloads_dir

        target_fn = sanitize_filename(urllib.parse.unquote(filename)) if filename else derive_download_filename(url)
        if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
            new_dest = resolve_categorized_path(downloads_dir, target_fn, auto_categorize=True)
        else:
            new_dest = os.path.join(dest_dir, target_fn)

        self.entry_dest.delete(0, tk.END)
        self.entry_dest.insert(0, new_dest)

        # DO NOT force-restore the main window if hidden or minimized in tray
        if not self.is_window_hidden_or_minimized():
            try:
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass

        # Handle Media (YouTube / Social media) vs regular file downloads
        if is_media_url(url):
            plat = extract_media_platform(url)
            if self.engine and self.engine.is_running:
                self.log(f"[BROWSER] Note: Active task is running. {plat} stream queued in URL field.")
            else:
                self.log(f"[BROWSER] {plat} stream detected: {url}. Starting format analysis...")
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
            if self.engine and self.engine.is_running:
                self.log(f"[BROWSER] Note: Active transfer in progress. URL '{os.path.basename(new_dest)}' queued in inputs.")
                return

            if is_potential_html_url(url):
                def _on_browser_resolved(info: Dict[str, Any]):
                    if self.engine and self.engine.is_running:
                        return

                    real_url = info.get("url") or url
                    if info.get("resolved"):
                        self.log(f"[LINK RESOLVER] Web page detected. Real file found: {real_url}")
                    self._last_probed_info = dict(info)

                    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                    cur_d = self.entry_dest.get().strip()
                    dest_dir = os.path.dirname(cur_d) if cur_d else downloads_dir
                    if not os.path.isdir(dest_dir):
                        dest_dir = downloads_dir

                    target_fn = info.get("filename") or (sanitize_filename(urllib.parse.unquote(filename)) if filename else derive_download_filename(real_url))
                    if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                        resolved_dest = resolve_categorized_path(downloads_dir, target_fn, auto_categorize=True)
                    else:
                        resolved_dest = os.path.join(dest_dir, target_fn)

                    try:
                        self.entry_url.delete(0, tk.END)
                        self.entry_url.insert(0, real_url)
                        self.entry_dest.delete(0, tk.END)
                        self.entry_dest.insert(0, resolved_dest)
                    except Exception:
                        pass

                    if not self.is_window_hidden_or_minimized():
                        try:
                            self.root.lift()
                            self.root.focus_force()
                        except Exception:
                            pass

                    if self.is_window_hidden_or_minimized() or not start_immediately or getattr(self, "_auto_start_clipboard", True) or getattr(self, "_was_started_hidden", False):
                        self._show_download_confirmation_dialog(real_url, resolved_dest)
                    else:
                        self._on_start_download(skip_resolver=True)

                self._resolve_real_url_async(url, on_resolved=_on_browser_resolved, show_toast=True)
            elif self.is_window_hidden_or_minimized() or not start_immediately or getattr(self, "_auto_start_clipboard", True) or getattr(self, "_was_started_hidden", False):
                self._show_download_confirmation_dialog(url, new_dest)
            else:
                self._on_start_download(skip_resolver=True)
