"""
BrowserSettingsModalMixin: Browser WebExtension setup dialog, native messaging
host registration, and intercepted download dispatching.
"""
import os
import sys
import json
import shutil
import threading
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional

import tkinter as tk
from tkinter import ttk

from ...config import get_resource_path, get_setting, set_setting
from ...locales.i18n import tr
from ...utils.tk_helpers import _detach_photo_tk
from ...utils.url_utils import is_potential_html_url, derive_download_filename
from ...utils.file_ops import resolve_categorized_path
from ...services.startup_service import IS_WINDOWS, is_startup_enabled
from ...services.youtube_service import is_media_url, extract_media_platform, sanitize_filename
from ...services.browser.bridge_server import BrowserBridgeServer, DEFAULT_BRIDGE_PORT
from ...services.browser.registry import (
    register_native_host,
    unregister_native_host,
    check_and_register_browser,
    get_status as get_browser_reg_status,
)


class BrowserSettingsModalMixin:
    """
    Mixin providing browser integration dialog and background self-registration
    for ModernFramelessGUI.
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

    def _open_browser_integration_dialog(self):
        """Displays settings, connection status, and extension installation instructions."""
        if hasattr(self, "_browser_integration_dlg") and self._browser_integration_dlg:
            try:
                if hasattr(self._browser_integration_dlg, "_browser_icon_photo"):
                    _detach_photo_tk(self._browser_integration_dlg._browser_icon_photo)
                    self._browser_integration_dlg._browser_icon_photo = None
                if self._browser_integration_dlg.winfo_exists():
                    self._browser_integration_dlg.destroy()
            except Exception:
                pass
            self._browser_integration_dlg = None

        dlg = tk.Toplevel(self.root)
        self._browser_integration_dlg = dlg
        dlg.title(tr("browser_dlg_title", "🌐 Browser Integration & WebExtension Setup"))
        dlg.transient(self.root)
        dlg.grab_set = lambda: None
        dlg.grab_set_global = lambda: None
        try:
            dlg.lift()
            dlg.attributes("-topmost", True)
            dlg.focus_force()
        except Exception:
            pass

        dpi_scale = getattr(self, "dpi_scale", 1.0)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        dlg_w = min(int(680 * dpi_scale), max(600, int(sw * 0.92)))
        dlg_h = min(int(740 * dpi_scale), max(640, int(sh * 0.90)))
        try:
            px = self.root.winfo_x()
            py = self.root.winfo_y()
            pw = self.root.winfo_width() or self.width
            ph = self.root.winfo_height() or self.height
        except Exception:
            px, py, pw, ph = 0, 0, self.width, self.height
        x = max(0, px + (pw - dlg_w) // 2)
        y = max(0, py + (ph - dlg_h) // 2)
        dlg.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
        dlg.minsize(min(580, dlg_w), min(540, dlg_h))
        dlg.configure(bg=self.c_bg)

        # Apply application icon to dialog window
        ico_path = get_resource_path("app_icon.ico")
        png_path = get_resource_path("app_icon.png")
        if os.path.isfile(ico_path):
            try:
                dlg.iconbitmap(ico_path)
            except Exception:
                pass
        if os.path.isfile(png_path):
            try:
                from PIL import ImageTk
                dlg._browser_icon_photo = ImageTk.PhotoImage(file=png_path)
                dlg.iconphoto(True, dlg._browser_icon_photo)
                dlg.bind(
                    "<Destroy>",
                    lambda e: _detach_photo_tk(getattr(dlg, "_browser_icon_photo", None)) if e.widget == dlg else None,
                    add="+"
                )
            except Exception:
                pass

        # Header
        header = tk.Frame(dlg, bg=self.c_panel, height=44, padx=16)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        lbl_head = tk.Label(
            header,
            text=tr("browser_dlg_header", "🌐 BROWSER INTEGRATION & EXTENSION SETUP"),
            font=("Segoe UI", 10, "bold"),
            bg=self.c_panel,
            fg=self.c_accent
        )
        lbl_head.pack(side=tk.LEFT)

        btn_dlg_updates = tk.Button(
            header,
            text=tr("btn_check_updates", "🔄 Check for Updates"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=10,
            pady=2,
            command=self.check_for_updates_manual
        )
        btn_dlg_updates.pack(side=tk.RIGHT, pady=8)

        # Main Body
        body = tk.Frame(dlg, bg=self.c_bg, padx=16, pady=12)
        body.pack(fill=tk.BOTH, expand=True)

        # 0. Zero-Install Universal Clipboard Sniffer Card (TDM Style)
        card_sniff = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_sniff.pack(fill=tk.X, pady=(0, 10))

        lbl_sniff_t = tk.Label(card_sniff, text=tr("browser_card_sniffer_title", "📋 ZERO-INSTALL CLIPBOARD MONITOR (SD SMART CAPTURE — ALL BROWSERS)"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_success)
        lbl_sniff_t.pack(anchor="w")

        sniff_row = tk.Frame(card_sniff, bg=self.c_panel)
        sniff_row.pack(fill=tk.X, pady=(6, 0))

        lbl_sniff_desc = tk.Label(
            sniff_row,
            text=tr("browser_card_sniffer_desc", "Works 100% across ALL browsers (Chrome, Edge, Firefox, Brave, Opera, Safari) without any extension.\nJust right-click any link or video and choose 'Copy Link Address' — Smart Download catches it instantly!"),
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_bright,
            justify="left"
        )
        lbl_sniff_desc.pack(side=tk.LEFT)

        def _update_dlg_sniff_btn():
            if self._clipboard_sniffer_active:
                btn_dlg_sniff.configure(text=tr("btn_sniffer_active", "📋 Sniffer: Active"), fg=self.c_success, bg=self.c_panel_light)
            else:
                btn_dlg_sniff.configure(text=tr("btn_sniffer_paused", "📋 Sniffer: Paused"), fg=self.c_text_muted, bg=self.c_panel)

        def _on_dlg_sniff_toggle():
            self.toggle_clipboard_sniffer()
            _update_dlg_sniff_btn()

        btn_dlg_sniff = tk.Button(
            sniff_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            command=_on_dlg_sniff_toggle
        )
        btn_dlg_sniff.pack(side=tk.RIGHT)
        _update_dlg_sniff_btn()

        # 1. Server Status Card
        card_server = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_server.pack(fill=tk.X, pady=(0, 10))

        lbl_s_title = tk.Label(card_server, text=tr("browser_card_server_title", "LOCAL IPC LOOPBACK LISTENER"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted)
        lbl_s_title.pack(anchor="w")

        s_row = tk.Frame(card_server, bg=self.c_panel)
        s_row.pack(fill=tk.X, pady=(6, 0))

        lbl_status = tk.Label(s_row, text="", font=("Segoe UI", 9, "bold"), bg=self.c_panel)
        lbl_status.pack(side=tk.LEFT)

        def _update_server_status_label():
            if self.bridge_server and self.bridge_server.is_running:
                lbl_status.configure(text=tr("browser_server_active", f"● Active on http://{self.bridge_server.host}:{self.bridge_server.port}").format(host=self.bridge_server.host, port=self.bridge_server.port), fg=self.c_success)
                btn_toggle_server.configure(text=tr("browser_btn_stop_server", "⏹ Stop Server"), bg=self.c_danger)
            else:
                lbl_status.configure(text=tr("browser_server_stopped", "● Listener Stopped / Offline"), fg=self.c_danger)
                btn_toggle_server.configure(text=tr("browser_btn_start_server", "▶ Start Server"), bg=self.c_success)

        def _toggle_bridge():
            if self.bridge_server and self.bridge_server.is_running:
                self.bridge_server.stop()
            else:
                if not self.bridge_server:
                    self.bridge_server = BrowserBridgeServer(
                        port=DEFAULT_BRIDGE_PORT,
                        on_download=self._on_browser_download_received,
                        on_log=self.log
                    )
                self.bridge_server.start()
            _update_server_status_label()

        def _test_ping():
            port = self.bridge_server.port if self.bridge_server else DEFAULT_BRIDGE_PORT
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/ping")
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode())
                        self.show_safe_info("Ping Successful", f"Loopback server is responding perfectly!\n\nApp: {data.get('app')}\nVersion: {data.get('version')}")
                        return
            except Exception as e:
                self.show_safe_error("Ping Failed", f"Could not reach loopback server:\n\n{e}")

        btn_test = tk.Button(
            s_row,
            text=tr("browser_btn_test_ping", "⚡ Test Ping"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            cursor="hand2",
            command=_test_ping
        )
        btn_test.pack(side=tk.RIGHT, padx=(6, 0))

        btn_toggle_server = tk.Button(
            s_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=10,
            command=_toggle_bridge
        )
        btn_toggle_server.pack(side=tk.RIGHT)
        _update_server_status_label()

        # 2. Windows Registry Native Messaging Integration Card
        card_reg = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_reg.pack(fill=tk.X, pady=(0, 10))

        lbl_reg_title = tk.Label(card_reg, text=tr("browser_card_reg_title", "WINDOWS REGISTRY DIRECT BROWSER LINK (NATIVE MESSAGING)"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent)
        lbl_reg_title.pack(anchor="w")

        reg_row = tk.Frame(card_reg, bg=self.c_panel)
        reg_row.pack(fill=tk.X, pady=(6, 0))

        lbl_reg_status = tk.Label(reg_row, text="", font=("Segoe UI", 9, "bold"), bg=self.c_panel)
        lbl_reg_status.pack(side=tk.LEFT)

        def _update_reg_status_label():
            status = get_browser_reg_status()
            if status.get("is_registered"):
                chrome_str = "Chrome ✓" if status.get("chrome_registered") else "Chrome ✕"
                edge_str = "Edge ✓" if status.get("edge_registered") else "Edge ✕"
                lbl_reg_status.configure(text=tr("browser_reg_active", f"● Registry Active: {chrome_str}  {edge_str} (com.smartdownload.host)").format(chrome=chrome_str, edge=edge_str), fg=self.c_success)
                btn_reg.configure(text=tr("browser_btn_reregister", "🔄 Re-Register"), bg=self.c_panel_light)
            else:
                lbl_reg_status.configure(text=tr("browser_reg_inactive", "● Not Registered in Windows Registry"), fg=self.c_warning)
                btn_reg.configure(text=tr("browser_btn_register", "🔗 1-Click Register (Chrome & Edge)"), bg=self.c_success)

        def _on_register_click():
            res = register_native_host()
            _update_reg_status_label()
            if res.get("success"):
                self.show_safe_info(
                    "Registration Successful! 🚀",
                    "Native Messaging Host successfully linked in Windows Registry for Google Chrome and Microsoft Edge!\n\n"
                    f"Host Name: com.smartdownload.host\n"
                    f"Manifest: {res.get('manifest_path')}"
                )
            else:
                self.show_safe_error("Registration Error", f"Failed to register in Windows Registry:\n\n{res.get('error', 'Unknown error')}")

        def _on_unregister_click():
            unregister_native_host()
            _update_reg_status_label()
            self.show_safe_info("Unregistered", "Removed Native Messaging Host registry entries for Chrome & Edge.")

        btn_unreg = tk.Button(
            reg_row,
            text=tr("browser_btn_unregister", "Unregister"),
            font=("Segoe UI", 8),
            bg=self.c_panel_light,
            fg=self.c_text_muted,
            relief="flat",
            cursor="hand2",
            padx=8,
            command=_on_unregister_click
        )
        btn_unreg.pack(side=tk.RIGHT, padx=(6, 0))

        btn_reg = tk.Button(
            reg_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=12,
            command=_on_register_click
        )
        btn_reg.pack(side=tk.RIGHT)
        _update_reg_status_label()

        # 3. Windows Startup Auto-Boot Card (Silent Background Mode)
        card_boot = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_boot.pack(fill=tk.X, pady=(0, 10))

        lbl_boot_title = tk.Label(card_boot, text=tr("browser_card_boot_title", "🚀 WINDOWS STARTUP AUTO-BOOT (SILENT BACKGROUND MODE)"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent)
        lbl_boot_title.pack(anchor="w")

        boot_row = tk.Frame(card_boot, bg=self.c_panel)
        boot_row.pack(fill=tk.X, pady=(6, 0))

        lbl_boot_status = tk.Label(boot_row, text="", font=("Segoe UI", 9, "bold"), bg=self.c_panel)
        lbl_boot_status.pack(side=tk.LEFT)

        def _update_dlg_boot_status():
            try:
                if not dlg.winfo_exists() or not lbl_boot_status.winfo_exists():
                    return
            except Exception:
                return
            enabled = is_startup_enabled()
            if enabled:
                lbl_boot_status.configure(text=tr("browser_boot_enabled", "● Start with Windows: Enabled (Silent Background)"), fg=self.c_success)
                btn_dlg_boot.configure(text=tr("browser_btn_boot_enabled", "🚀 Start on Boot: Enabled"), fg=self.c_success, bg=self.c_panel_light)
            else:
                lbl_boot_status.configure(text=tr("browser_boot_disabled", "● Start with Windows: Disabled"), fg=self.c_warning)
                btn_dlg_boot.configure(text=tr("browser_btn_boot_disabled", "🚀 Start on Boot: Disabled"), fg=self.c_text_muted, bg=self.c_panel)

        self._update_dlg_startup_ui = _update_dlg_boot_status
        try:
            dlg.bind("<Destroy>", lambda e: setattr(self, "_update_dlg_startup_ui", None) if e.widget == dlg else None, add="+")
        except Exception:
            pass

        def _on_dlg_boot_toggle():
            self.toggle_startup_setting()
            _update_dlg_boot_status()

        btn_dlg_boot = tk.Button(
            boot_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            command=_on_dlg_boot_toggle
        )
        btn_dlg_boot.pack(side=tk.RIGHT)
        _update_dlg_boot_status()

        # 3b. Windows System Tray & Background Minimization Card
        card_tray = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_tray.pack(fill=tk.X, pady=(0, 10))

        lbl_tray_title = tk.Label(card_tray, text=tr("browser_card_tray_title", "🔔 WINDOWS SYSTEM TRAY & BACKGROUND MINIMIZATION"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent)
        lbl_tray_title.pack(anchor="w")

        tray_row = tk.Frame(card_tray, bg=self.c_panel)
        tray_row.pack(fill=tk.X, pady=(6, 0))

        lbl_tray_status = tk.Label(tray_row, text="", font=("Segoe UI", 9, "bold"), bg=self.c_panel)
        lbl_tray_status.pack(side=tk.LEFT)

        def _update_dlg_tray_status():
            try:
                if not dlg.winfo_exists() or not lbl_tray_status.winfo_exists():
                    return
            except Exception:
                return
            enabled = getattr(self, "minimize_to_tray", True)
            if enabled:
                lbl_tray_status.configure(text=tr("browser_tray_enabled", "● Close (✕) Action: Minimize to System Tray"), fg=self.c_success)
                btn_dlg_tray.configure(text=tr("browser_btn_tray_enabled", "[✓] Minimize to System Tray on Close (✕)"), fg=self.c_success, bg=self.c_panel_light)
            else:
                lbl_tray_status.configure(text=tr("browser_tray_disabled", "● Close (✕) Action: Exit Application Completely"), fg=self.c_warning)
                btn_dlg_tray.configure(text=tr("browser_btn_tray_disabled", "[  ] Minimize to System Tray on Close (✕)"), fg=self.c_text_muted, bg=self.c_panel)

        self._update_dlg_tray_ui = _update_dlg_tray_status
        try:
            dlg.bind("<Destroy>", lambda e: (setattr(self, "_update_dlg_startup_ui", None), setattr(self, "_update_dlg_tray_ui", None)) if e.widget == dlg else None, add="+")
        except Exception:
            pass

        def _on_dlg_tray_toggle():
            self.toggle_minimize_to_tray_setting()
            _update_dlg_tray_status()

        btn_dlg_tray = tk.Button(
            tray_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            command=_on_dlg_tray_toggle
        )
        btn_dlg_tray.pack(side=tk.RIGHT)
        _update_dlg_tray_status()

        # 3c. Auto-Unpack Archives Card (AeroArchive Engine)
        card_unpack = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_unpack.pack(fill=tk.X, pady=(0, 10))

        lbl_unpack_title = tk.Label(card_unpack, text=tr("browser_card_unpack_title", "📦 AUTOMATIC ARCHIVE EXTRACTION (AEROARCHIVE ENGINE)"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent)
        lbl_unpack_title.pack(anchor="w")

        unpack_row = tk.Frame(card_unpack, bg=self.c_panel)
        unpack_row.pack(fill=tk.X, pady=(6, 0))

        lbl_unpack_status = tk.Label(unpack_row, text="", font=("Segoe UI", 9, "bold"), bg=self.c_panel)
        lbl_unpack_status.pack(side=tk.LEFT)

        def _update_dlg_unpack_status():
            try:
                if not dlg.winfo_exists() or not lbl_unpack_status.winfo_exists():
                    return
            except Exception:
                return
            enabled = get_setting("auto_unpack_archives", False)
            if enabled:
                lbl_unpack_status.configure(text=tr("browser_unpack_enabled", "● Auto-Unpack: Enabled"), fg=self.c_success)
                btn_dlg_unpack.configure(text=tr("browser_btn_unpack_enabled", "[✓] Auto-Unpack Archives after Download"), fg=self.c_success, bg=self.c_panel_light)
            else:
                lbl_unpack_status.configure(text=tr("browser_unpack_disabled", "● Auto-Unpack: Disabled"), fg=self.c_warning)
                btn_dlg_unpack.configure(text=tr("browser_btn_unpack_disabled", "[  ] Auto-Unpack Archives after Download"), fg=self.c_text_muted, bg=self.c_panel)

        def _on_dlg_unpack_toggle():
            cur = get_setting("auto_unpack_archives", False)
            set_setting("auto_unpack_archives", not cur)
            _update_dlg_unpack_status()

        btn_dlg_unpack = tk.Button(
            unpack_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            command=_on_dlg_unpack_toggle
        )
        btn_dlg_unpack.pack(side=tk.RIGHT)
        _update_dlg_unpack_status()

        # 4. Extension Directory Card
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            persistent_ext_dir = os.path.join(exe_dir, "extension")
            if hasattr(sys, "_MEIPASS"):
                bundled_ext = os.path.join(sys._MEIPASS, "extension")
                if os.path.isdir(bundled_ext):
                    try:
                        shutil.copytree(bundled_ext, persistent_ext_dir, dirs_exist_ok=True)
                    except Exception:
                        pass
            ext_dir = persistent_ext_dir if os.path.isdir(persistent_ext_dir) else os.path.join(getattr(sys, "_MEIPASS", exe_dir), "extension")
        else:
            base_app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ext_dir = os.path.join(base_app_dir, "extension")

        card_ext = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_ext.pack(fill=tk.X, pady=(0, 10))

        lbl_e_title = tk.Label(card_ext, text=tr("browser_card_ext_title", "WEBEXTENSION ARTIFACT (MANIFEST V3)"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted)
        lbl_e_title.pack(anchor="w")

        e_row = tk.Frame(card_ext, bg=self.c_panel)
        e_row.pack(fill=tk.X, pady=(4, 0))

        lbl_path = tk.Label(e_row, text=ext_dir, font=("Consolas", 8), bg=self.c_input_bg, fg=self.c_accent, padx=6, pady=4, anchor="w")
        lbl_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        def _open_folder():
            if os.path.exists(ext_dir):
                if IS_WINDOWS:
                    os.startfile(ext_dir)
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", ext_dir])

        btn_open = tk.Button(
            e_row,
            text=tr("browser_btn_open_folder", "📂 Open Folder"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_accent_dark,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=_open_folder
        )
        btn_open.pack(side=tk.RIGHT)

        # 3. Installation Guide Notebook
        nb = ttk.Notebook(body, style="Custom.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Chrome / Brave tab
        tab_chrome = tk.Frame(nb, bg=self.c_panel, padx=12, pady=10)
        nb.add(tab_chrome, text=tr("browser_tab_chrome", " Chrome & Brave "))

        chrome_txt = tr(
            "browser_guide_chrome",
            "1. Open Chrome or Brave and type chrome://extensions in the address bar.\n"
            "2. Turn ON 'Developer mode' using the toggle in the top-right corner.\n"
            "3. Click the 'Load unpacked' button at the top-left.\n"
            "4. Select the extension directory displayed above.\n"
            "5. The ⚡ Smart Download icon will appear in your extensions bar!"
        )
        tk.Label(tab_chrome, text=chrome_txt, font=("Segoe UI", 9), bg=self.c_panel, fg=self.c_text_bright, justify="left").pack(anchor="w")

        # Edge tab
        tab_edge = tk.Frame(nb, bg=self.c_panel, padx=12, pady=10)
        nb.add(tab_edge, text=tr("browser_tab_edge", " Microsoft Edge "))

        edge_txt = tr(
            "browser_guide_edge",
            "1. Open Edge and navigate to edge://extensions in the address bar.\n"
            "2. Turn ON 'Developer mode' in the left-hand navigation sidebar.\n"
            "3. Click the 'Load unpacked' button.\n"
            "4. Select the extension directory displayed above.\n"
            "5. Pin the extension to your toolbar for one-click access."
        )
        tk.Label(tab_edge, text=edge_txt, font=("Segoe UI", 9), bg=self.c_panel, fg=self.c_text_bright, justify="left").pack(anchor="w")

        # Firefox tab
        tab_firefox = tk.Frame(nb, bg=self.c_panel, padx=12, pady=10)
        nb.add(tab_firefox, text=tr("browser_tab_firefox", " Mozilla Firefox "))

        firefox_txt = tr(
            "browser_guide_firefox",
            "1. Open Firefox and type about:debugging#/runtime/this-firefox in the address bar.\n"
            "2. Click the 'Load Temporary Add-on...' button.\n"
            "3. Select the 'manifest.json' file inside the extension folder.\n"
            "4. The extension is immediately loaded and connects to Smart Download."
        )
        tk.Label(tab_firefox, text=firefox_txt, font=("Segoe UI", 9), bg=self.c_panel, fg=self.c_text_bright, justify="left").pack(anchor="w")

        # Close button
        btn_close = tk.Button(
            body,
            text=tr("browser_btn_close", "Close"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=4,
            command=dlg.destroy
        )
        btn_close.pack(side=tk.RIGHT)
