"""
SettingsModal: Frameless dark application settings dialog with per-platform sniffer filtering.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Any, Optional, List, Tuple

try:
    import tkinter as tk
    from tkinter import ttk, filedialog
except Exception:
    tk = ttk = filedialog = None  # type: ignore

from smart_download.i18n import tr
from smart_download.config import (
    get_setting,
    set_setting,
    get_base_downloads_dir,
    get_resource_path,
    DEFAULT_SNIFFER_PLATFORMS,
)
from smart_download.services import is_startup_enabled, enable_startup, disable_startup
from smart_download.ui.modals.quality_modal_helpers import build_quality_title_bar
from smart_download.utils.tk_helpers import _detach_photo_tk

_BaseToplevel = tk.Toplevel if tk is not None else object


class SettingsModal(_BaseToplevel):
    """Frameless dark theme modal dialog for user preferences and platform sniffer toggles."""

    PLATFORM_DEFS: List[Tuple[str, str]] = [
        ("youtube", "plat_youtube"),
        ("tiktok", "plat_tiktok"),
        ("instagram", "plat_instagram"),
        ("facebook", "plat_facebook"),
        ("twitter", "plat_twitter"),
        ("direct_files", "plat_direct_files"),
        ("reddit", "plat_reddit"),
        ("twitch", "plat_twitch"),
        ("vimeo", "plat_vimeo"),
        ("dailymotion", "plat_dailymotion"),
        ("pinterest", "plat_pinterest"),
        ("threads", "plat_threads"),
    ]

    RES_OPTIONS: List[Tuple[int, str]] = [
        (0, "0 (Ask / Best)"),
        (2160, "2160p (4K UHD)"),
        (1440, "1440p (2K QHD)"),
        (1080, "1080p (Full HD)"),
        (720, "720p (HD)"),
        (480, "480p (SD)"),
        (360, "360p (Low)"),
        (-1, "Audio Only (MP3)"),
    ]

    def __init__(self, parent: Any = None, parent_app: Any = None, theme: Optional[Dict[str, str]] = None):
        if tk is not None: super().__init__(parent)
        self.parent_app = parent_app
        self.theme = theme or (parent_app._theme_dict() if parent_app and hasattr(parent_app, "_theme_dict") else {
            "c_bg": "#0f172a", "c_panel": "#1e293b", "c_panel_light": "#334155", "c_border": "#475569",
            "c_accent": "#38bdf8", "c_accent_dark": "#0284c7", "c_text_bright": "#f8fafc",
            "c_text_muted": "#94a3b8", "c_success": "#10b981", "c_danger": "#ef4444", "c_input_bg": "#0b1220",
        })
        self.c_bg = self.theme.get("c_bg", "#0f172a")
        self.c_panel = self.theme.get("c_panel", "#1e293b")
        self.c_panel_light = self.theme.get("c_panel_light", "#334155")
        self.c_border = self.theme.get("c_border", "#475569")
        self.c_accent = self.theme.get("c_accent", "#38bdf8")
        self.c_accent_dark = self.theme.get("c_accent_dark", "#0284c7")
        self.c_text_bright = self.theme.get("c_text_bright", "#f8fafc")
        self.c_text_muted = self.theme.get("c_text_muted", "#94a3b8")
        self.c_success = self.theme.get("c_success", "#10b981")
        self.c_danger = self.theme.get("c_danger", "#ef4444")
        self.c_input_bg = self.theme.get("c_input_bg", "#0b1220")

        self.title(tr("settings_modal_title", "⚙ Application Settings — Smart Download"))
        try: self.overrideredirect(True)
        except Exception: pass

        dpi_scale = getattr(parent_app, "dpi_scale", 1.0) if parent_app else 1.0
        sw = self.winfo_screenwidth() if hasattr(self, "winfo_screenwidth") else 1920
        sh = self.winfo_screenheight() if hasattr(self, "winfo_screenheight") else 1080
        dlg_w, dlg_h = min(int(700 * dpi_scale), max(620, int(sw * 0.92))), min(int(620 * dpi_scale), max(540, int(sh * 0.90)))

        try:
            if parent and parent.winfo_exists() and parent.winfo_viewable():
                self.transient(parent)
                x = parent.winfo_x() + ((parent.winfo_width() or dlg_w) - dlg_w) // 2
                y = parent.winfo_y() + ((parent.winfo_height() or dlg_h) - dlg_h) // 2
            else: x, y = max(0, (sw - dlg_w) // 2), max(0, (sh - dlg_h) // 2)
        except Exception: x, y = max(0, (sw - dlg_w) // 2), max(0, (sh - dlg_h) // 2)

        pos_x = f"+{int(x)}" if int(x) >= 0 else f"{int(x)}"
        pos_y = f"+{int(y)}" if int(y) >= 0 else f"{int(y)}"
        self.geometry(f"{dlg_w}x{dlg_h}{pos_x}{pos_y}")

        ico_path, png_path = get_resource_path("app_icon.ico"), get_resource_path("app_icon.png")
        if os.path.isfile(ico_path):
            try: self.iconbitmap(ico_path)
            except Exception: pass
        if os.path.isfile(png_path):
            try:
                from PIL import ImageTk
                self._modal_icon_photo = ImageTk.PhotoImage(file=png_path)
                self.iconphoto(True, self._modal_icon_photo)
            except Exception: pass

        if self.parent_app and hasattr(self.parent_app, "sniffer_platforms") and isinstance(self.parent_app.sniffer_platforms, dict):
            self.sniffer_platforms = dict(self.parent_app.sniffer_platforms)
        else:
            self.sniffer_platforms = dict(get_setting("sniffer_platforms", DEFAULT_SNIFFER_PLATFORMS) or DEFAULT_SNIFFER_PLATFORMS)

        self._plat_buttons: Dict[str, tk.Button] = {}
        self._build_ui()
        self.bind("<Escape>", lambda e: self._on_close())

        self._topmost_job = None
        self._idle_job = None
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self._topmost_job = self.after(250, lambda: self.attributes("-topmost", False) if self.winfo_exists() else None)
            self._idle_job = self.after_idle(lambda: (self.lift(), self.focus_force()) if self.winfo_exists() else None)
        except Exception:
            pass

    def _on_drag_press(self, event):
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()

    def _on_drag_motion(self, event):
        x = event.x_root - getattr(self, "_drag_offset_x", 0)
        y = event.y_root - getattr(self, "_drag_offset_y", 0)
        pos_x = f"+{int(x)}" if int(x) >= 0 else f"{int(x)}"
        pos_y = f"+{int(y)}" if int(y) >= 0 else f"{int(y)}"
        self.geometry(f"{pos_x}{pos_y}")

    def grab_set(self): pass
    def grab_set_global(self): pass

    def _sync_dir_to_parent_app(self, new_dir: str):
        try:
            if not new_dir or not self.parent_app or not hasattr(self.parent_app, "entry_dest") or not self.parent_app.entry_dest:
                return
            eng = getattr(self.parent_app, "engine", None)
            if eng and (getattr(eng, "is_running", False)() if callable(getattr(eng, "is_running", False)) else getattr(eng, "is_running", False)):
                return
            cur_dest = self.parent_app.entry_dest.get().strip()
            if not cur_dest or os.path.isdir(cur_dest):
                target = new_dir
            else:
                fn = os.path.basename(cur_dest)
                target = os.path.join(new_dir, fn) if fn else new_dir
            self.parent_app.entry_dest.delete(0, tk.END if tk is not None else "end")
            self.parent_app.entry_dest.insert(0, target)
        except Exception:
            pass

    def _save_manual_dir_if_valid(self):
        if hasattr(self, "entry_dir") and self.entry_dir:
            try:
                typed = self.entry_dir.get().strip()
                if typed and os.path.isdir(typed):
                    set_setting("last_download_dir", typed)
                    if self.parent_app and hasattr(self.parent_app, "log") and callable(self.parent_app.log):
                        self.parent_app.log(f"[SETTINGS] Default download directory set to: {typed}")
                    self._sync_dir_to_parent_app(typed)
            except Exception: pass

    def _on_close(self):
        self._save_manual_dir_if_valid()
        self.destroy()

    def destroy(self):
        try: self.withdraw()
        except Exception: pass
        for job_attr in ("_topmost_job", "_idle_job"):
            job = getattr(self, job_attr, None)
            if job:
                try: self.after_cancel(job)
                except Exception: pass
                setattr(self, job_attr, None)
        if self.parent_app and getattr(self.parent_app, "_settings_modal", None) is self:
            self.parent_app._settings_modal = None
        for p in ("_modal_icon_photo", "_modal_title_photo"):
            if hasattr(self, p) and getattr(self, p): _detach_photo_tk(getattr(self, p))
        super().destroy()

    def _build_ui(self):
        outer = tk.Frame(self, bg=self.c_border, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        self.title_bar = build_quality_title_bar(
            self, outer, self.theme, tr("settings_modal_title", "⚙ Application Settings — Smart Download"), self._on_close
        )
        body = tk.Frame(outer, bg=self.c_bg, padx=14, pady=10)
        body.pack(fill=tk.BOTH, expand=True)

        nb = ttk.Notebook(body, style="Custom.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        tab_sniffer = tk.Frame(nb, bg=self.c_bg, padx=12, pady=10, bd=0, highlightthickness=1, highlightbackground=self.c_border, highlightcolor=self.c_border)
        tab_downloads = tk.Frame(nb, bg=self.c_bg, padx=12, pady=10, bd=0, highlightthickness=1, highlightbackground=self.c_border, highlightcolor=self.c_border)
        tab_system = tk.Frame(nb, bg=self.c_bg, padx=12, pady=10, bd=0, highlightthickness=1, highlightbackground=self.c_border, highlightcolor=self.c_border)

        nb.add(tab_sniffer, text=tr("settings_tab_sniffer", " ⚙ Clipboard Sniffer "))
        nb.add(tab_downloads, text=tr("settings_tab_downloads", " ❖ Downloads & Media "))
        nb.add(tab_system, text=tr("settings_tab_system", " ⚡ System & Startup "))

        self._build_sniffer_tab(tab_sniffer)
        self._build_downloads_tab(tab_downloads)
        self._build_system_tab(tab_system)

        footer = tk.Frame(body, bg=self.c_bg)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(
            footer, text=tr("settings_btn_save_close", "Close"), font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light, fg=self.c_text_bright, relief="flat", activebackground=self.c_accent_dark,
            activeforeground="white", cursor="hand2", padx=18, pady=4, command=self._on_close
        ).pack(side=tk.RIGHT)

    def _build_sniffer_tab(self, parent: tk.Frame):
        """Constructs Tab 1: Clipboard Sniffer & per-platform toggles."""
        active = getattr(self.parent_app, "_clipboard_sniffer_active", True) if self.parent_app else bool(get_setting("clipboard_sniffer_active", True))
        self.btn_master_sniffer = tk.Button(
            parent, text=tr("settings_sniffer_master_on") if active else tr("settings_sniffer_master_off"),
            font=("Segoe UI", 9, "bold"), bg="#0f292a" if active else "#182234",
            fg=self.c_success if active else self.c_text_muted, relief="flat", highlightthickness=1,
            highlightbackground="#10b981" if active else self.c_border, cursor="hand2", padx=14, pady=6,
            command=self._toggle_master_sniffer
        )
        self.btn_master_sniffer.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            parent, text=tr("settings_sniffer_hint", "Disabling any platform below stops automatic clipboard capture and popup prompts, while manual URL paste and download remain fully functional."),
            font=("Segoe UI", 8), bg=self.c_bg, fg=self.c_text_muted, wraplength=640, justify="left"
        ).pack(fill=tk.X, pady=(0, 8))

        row_actions = tk.Frame(parent, bg=self.c_bg)
        row_actions.pack(fill=tk.X, pady=(0, 8))
        tk.Button(row_actions, text=tr("settings_btn_enable_all_platforms", "✓ Enable All"), font=("Segoe UI", 8, "bold"),
                  bg=self.c_panel_light, fg=self.c_success, relief="flat", cursor="hand2", padx=12, pady=3,
                  command=lambda: self._set_all_platforms(True)).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(row_actions, text=tr("settings_btn_disable_all_platforms", "✕ Disable All"), font=("Segoe UI", 8, "bold"),
                  bg=self.c_panel_light, fg=self.c_danger, relief="flat", cursor="hand2", padx=12, pady=3,
                  command=lambda: self._set_all_platforms(False)).pack(side=tk.LEFT)

        grid_frame = tk.Frame(parent, bg=self.c_bg)
        grid_frame.pack(fill=tk.BOTH, expand=True)
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        for idx, (plat_key, tr_key) in enumerate(self.PLATFORM_DEFS):
            plat_name = tr(tr_key)
            is_on = bool(self.sniffer_platforms.get(plat_key, True))
            btn = tk.Button(
                grid_frame, text=f"[✓] {plat_name}" if is_on else f"[  ] {plat_name}",
                font=("Segoe UI", 8, "bold"), bg="#0f292a" if is_on else "#182234",
                fg=self.c_success if is_on else self.c_text_muted, relief="flat",
                highlightthickness=1, highlightbackground="#10b981" if is_on else self.c_border,
                cursor="hand2", anchor="w", padx=10, pady=4,
                command=lambda k=plat_key, tk_k=tr_key: self._toggle_platform(k, tk_k)
            )
            btn.grid(row=idx // 2, column=idx % 2, padx=4, pady=3, sticky="ew")
            self._plat_buttons[plat_key] = btn

    def _toggle_master_sniffer(self):
        if self.parent_app and hasattr(self.parent_app, "toggle_clipboard_sniffer"):
            self.parent_app.toggle_clipboard_sniffer()
            active = getattr(self.parent_app, "_clipboard_sniffer_active", True)
        else:
            active = not bool(get_setting("clipboard_sniffer_active", True))
            set_setting("clipboard_sniffer_active", active)
        self.btn_master_sniffer.configure(
            text=tr("settings_sniffer_master_on") if active else tr("settings_sniffer_master_off"),
            bg="#0f292a" if active else "#182234", fg=self.c_success if active else self.c_text_muted,
            highlightbackground="#10b981" if active else self.c_border,
        )

    def _toggle_platform(self, key: str, tr_key: str):
        nxt = not bool(self.sniffer_platforms.get(key, True))
        if key == "threads":
            self.sniffer_platforms["threads"] = self.sniffer_platforms["snapchat"] = self.sniffer_platforms["rumble"] = nxt
        else:
            self.sniffer_platforms[key] = nxt
        set_setting("sniffer_platforms", self.sniffer_platforms)
        if self.parent_app:
            self.parent_app.sniffer_platforms = dict(self.sniffer_platforms)
            if hasattr(self.parent_app, "log") and callable(self.parent_app.log):
                self.parent_app.log(f"[SETTINGS] Clipboard sniffer for {key}: {'Enabled' if nxt else 'Disabled'}")
        self._refresh_platform_btn(key, tr_key)

    def _refresh_platform_btn(self, key: str, tr_key: str):
        btn = self._plat_buttons.get(key)
        if not btn: return
        is_on = bool(self.sniffer_platforms.get(key, True))
        name = tr(tr_key)
        btn.configure(
            text=f"[✓] {name}" if is_on else f"[  ] {name}",
            bg="#0f292a" if is_on else "#182234", fg=self.c_success if is_on else self.c_text_muted,
            highlightbackground="#10b981" if is_on else self.c_border,
        )

    def _set_all_platforms(self, state: bool):
        for k in list(DEFAULT_SNIFFER_PLATFORMS.keys()): self.sniffer_platforms[k] = bool(state)
        set_setting("sniffer_platforms", self.sniffer_platforms)
        if self.parent_app:
            self.parent_app.sniffer_platforms = dict(self.sniffer_platforms)
            if hasattr(self.parent_app, "log") and callable(self.parent_app.log):
                self.parent_app.log(f"[SETTINGS] {'Enabled' if state else 'Disabled'} all platforms for clipboard sniffer.")
        for k, tk_k in self.PLATFORM_DEFS: self._refresh_platform_btn(k, tk_k)

    def _build_downloads_tab(self, parent: tk.Frame):
        """Constructs Tab 2: Downloads, folders, threads, cookies & media resolution."""
        tk.Label(parent, text=tr("settings_downloads_save_dir", "Default Save Folder:"), font=("Segoe UI", 9, "bold"), bg=self.c_bg, fg=self.c_accent).pack(anchor="w", pady=(0, 2))
        dir_row = tk.Frame(parent, bg=self.c_bg)
        dir_row.pack(fill=tk.X, pady=(0, 8))
        self.entry_dir = tk.Entry(dir_row, font=("Segoe UI", 9), bg=self.c_input_bg, fg=self.c_text_bright, insertbackground=self.c_text_bright, relief="flat", highlightthickness=1, highlightbackground=self.c_border)
        self.entry_dir.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)
        self.entry_dir.insert(0, str(get_setting("last_download_dir", "") or get_base_downloads_dir()))
        self.entry_dir.bind("<Return>", lambda e: self._save_manual_dir_if_valid())
        self.entry_dir.bind("<FocusOut>", lambda e: self._save_manual_dir_if_valid())
        tk.Button(dir_row, text=tr("settings_btn_browse", "⋯ Browse..."), font=("Segoe UI", 8, "bold"), bg=self.c_panel_light, fg=self.c_accent, relief="flat", cursor="hand2", padx=10, pady=2, command=self._browse_save_dir).pack(side=tk.RIGHT)

        toggles_frame = tk.Frame(parent, bg=self.c_bg)
        toggles_frame.pack(fill=tk.X, pady=(0, 8))
        toggles_frame.columnconfigure(0, weight=1)
        toggles_frame.columnconfigure(1, weight=1)

        auto_cat = getattr(self.parent_app, "auto_categorize_folders", True) if self.parent_app else bool(get_setting("auto_categorize_folders", True))
        self.btn_auto_cat = tk.Button(
            toggles_frame, text=tr("settings_downloads_auto_cat_on") if auto_cat else tr("settings_downloads_auto_cat_off"),
            font=("Segoe UI", 8, "bold"), bg="#0f292a" if auto_cat else "#182234",
            fg=self.c_success if auto_cat else self.c_text_muted, relief="flat", highlightthickness=1,
            highlightbackground="#10b981" if auto_cat else self.c_border, cursor="hand2", padx=10, pady=4, command=self._toggle_auto_cat
        )
        self.btn_auto_cat.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        unpack = bool(get_setting("auto_unpack_archives", False))
        self.btn_unpack = tk.Button(
            toggles_frame, text=tr("settings_downloads_unpack_on") if unpack else tr("settings_downloads_unpack_off"),
            font=("Segoe UI", 8, "bold"), bg="#0f292a" if unpack else "#182234",
            fg=self.c_success if unpack else self.c_text_muted, relief="flat", highlightthickness=1,
            highlightbackground="#10b981" if unpack else self.c_border, cursor="hand2", padx=10, pady=4, command=self._toggle_unpack
        )
        self.btn_unpack.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        selectors = tk.Frame(parent, bg=self.c_bg)
        selectors.pack(fill=tk.X, pady=(0, 6))

        r1 = tk.Frame(selectors, bg=self.c_bg)
        r1.pack(fill=tk.X, pady=3)
        tk.Label(r1, text=tr("settings_downloads_threads_lbl", "Default Concurrent Connections:"), font=("Segoe UI", 9), bg=self.c_bg, fg=self.c_text_bright).pack(side=tk.LEFT)
        cur_conn = str(get_setting("max_connections", 8))
        self.cb_threads = ttk.Combobox(r1, values=["1", "2", "4", "8", "16", "32"], state="readonly", width=8)
        self.cb_threads.set(cur_conn if cur_conn in ["1", "2", "4", "8", "16", "32"] else "8")
        self.cb_threads.pack(side=tk.RIGHT)
        self.cb_threads.bind("<<ComboboxSelected>>", self._on_threads_changed)

        r2 = tk.Frame(selectors, bg=self.c_bg)
        r2.pack(fill=tk.X, pady=3)
        tk.Label(r2, text=tr("settings_downloads_pref_res_lbl", "Preferred Video Resolution:"), font=("Segoe UI", 9), bg=self.c_bg, fg=self.c_text_bright).pack(side=tk.LEFT)
        res_val = int(get_setting("preferred_video_height", 0))
        self.cb_res = ttk.Combobox(r2, values=[lbl for _, lbl in self.RES_OPTIONS], state="readonly", width=18)
        self.cb_res.set(next((lbl for h, lbl in self.RES_OPTIONS if h == res_val), "0 (Ask / Best)"))
        self.cb_res.pack(side=tk.RIGHT)
        self.cb_res.bind("<<ComboboxSelected>>", self._on_res_changed)

        r3 = tk.Frame(selectors, bg=self.c_bg)
        r3.pack(fill=tk.X, pady=3)
        tk.Label(r3, text=tr("settings_downloads_cookies_lbl", "Browser Cookies Source:"), font=("Segoe UI", 9), bg=self.c_bg, fg=self.c_text_bright).pack(side=tk.LEFT)
        cur_cookies = str(get_setting("cookies_browser", "auto") or "auto").lower()
        if cur_cookies in ("file", "file...") or bool(get_setting("cookies_file", "")):
            cookie_init = "file..."
        elif cur_cookies in ["auto", "edge", "chrome", "firefox", "brave", "none"]:
            cookie_init = cur_cookies
        else:
            cookie_init = "auto"
        self.cb_cookies = ttk.Combobox(r3, values=["auto", "edge", "chrome", "firefox", "brave", "file...", "none"], state="readonly", width=12)
        self.cb_cookies.set(cookie_init)
        self.cb_cookies.pack(side=tk.RIGHT)
        self.cb_cookies.bind("<<ComboboxSelected>>", self._on_cookies_changed)

    def _browse_save_dir(self):
        try:
            cur = self.entry_dir.get().strip() or get_base_downloads_dir()
            chosen = filedialog.askdirectory(parent=self, initialdir=cur) if filedialog else ""
            if chosen and os.path.isdir(chosen):
                self.entry_dir.delete(0, tk.END)
                self.entry_dir.insert(0, chosen)
                set_setting("last_download_dir", chosen)
                if self.parent_app and hasattr(self.parent_app, "log") and callable(self.parent_app.log):
                    self.parent_app.log(f"[SETTINGS] Default download directory set to: {chosen}")
                self._sync_dir_to_parent_app(chosen)
        except Exception:
            pass

    def _toggle_auto_cat(self):
        if self.parent_app and hasattr(self.parent_app, "toggle_auto_categorize"):
            self.parent_app.toggle_auto_categorize()
            state = getattr(self.parent_app, "auto_categorize_folders", True)
        else:
            state = not bool(get_setting("auto_categorize_folders", True))
            set_setting("auto_categorize_folders", state)
        self.btn_auto_cat.configure(
            text=tr("settings_downloads_auto_cat_on") if state else tr("settings_downloads_auto_cat_off"),
            bg="#0f292a" if state else "#182234", fg=self.c_success if state else self.c_text_muted,
            highlightbackground="#10b981" if state else self.c_border,
        )

    def _toggle_unpack(self):
        nxt = not bool(get_setting("auto_unpack_archives", False))
        set_setting("auto_unpack_archives", nxt)
        if self.parent_app:
            self.parent_app.auto_unpack_archives = nxt
            if hasattr(self.parent_app, "log") and callable(self.parent_app.log):
                self.parent_app.log(f"[SETTINGS] Auto-unpack archives: {'Enabled' if nxt else 'Disabled'}")
        self.btn_unpack.configure(
            text=tr("settings_downloads_unpack_on") if nxt else tr("settings_downloads_unpack_off"),
            bg="#0f292a" if nxt else "#182234", fg=self.c_success if nxt else self.c_text_muted,
            highlightbackground="#10b981" if nxt else self.c_border,
        )

    def _on_threads_changed(self, event=None):
        try:
            n = int(self.cb_threads.get())
            set_setting("max_connections", n)
            if self.parent_app and hasattr(self.parent_app, "conn_var"): self.parent_app.conn_var.set(self.cb_threads.get())
            if self.parent_app and hasattr(self.parent_app, "log") and callable(self.parent_app.log):
                self.parent_app.log(f"[SETTINGS] Default connections set to: {n}")
        except Exception: pass

    def _on_res_changed(self, event=None):
        val = next((h for h, lbl in self.RES_OPTIONS if lbl == self.cb_res.get()), 0)
        set_setting("preferred_video_height", val)
        if self.parent_app and hasattr(self.parent_app, "log") and callable(self.parent_app.log):
            self.parent_app.log(f"[SETTINGS] Preferred video resolution height set to: {val}")

    def _on_cookies_changed(self, event=None):
        sel = self.cb_cookies.get()
        if sel == "file...":
            chosen = filedialog.askopenfilename(
                parent=self, title="Select Netscape cookies.txt file",
                filetypes=[("Text / Cookie files", "*.txt;*.cookies"), ("All files", "*.*")]
            ) if filedialog else ""
            if chosen and os.path.isfile(chosen):
                set_setting("cookies_file", chosen)
                set_setting("cookies_browser", "file")
                if self.parent_app:
                    self.parent_app.cookies_file = chosen
                    self.parent_app.cookies_browser = "file"
                    if hasattr(self.parent_app, "_update_cookies_btn"): self.parent_app._update_cookies_btn()
                    if hasattr(self.parent_app, "log") and callable(self.parent_app.log):
                        self.parent_app.log(f"[SETTINGS] Cookies file set to: {chosen}")
            else:
                self.cb_cookies.set("none")
                set_setting("cookies_file", "")
                set_setting("cookies_browser", "none")
                if self.parent_app:
                    self.parent_app.cookies_file = ""
                    self.parent_app.cookies_browser = "none"
                    if hasattr(self.parent_app, "_update_cookies_btn"): self.parent_app._update_cookies_btn()
        else:
            set_setting("cookies_file", "")
            set_setting("cookies_browser", sel)
            if self.parent_app:
                self.parent_app.cookies_file = ""
                self.parent_app.cookies_browser = sel
                if hasattr(self.parent_app, "_update_cookies_btn"): self.parent_app._update_cookies_btn()
                if hasattr(self.parent_app, "log") and callable(self.parent_app.log):
                    self.parent_app.log(f"[SETTINGS] Cookie browser set to: {sel.capitalize()}")

    def _build_system_tab(self, parent: tk.Frame):
        """Constructs Tab 3: Windows Startup, system tray on close, and browser guide."""
        st_on = is_startup_enabled()
        self.btn_startup = tk.Button(
            parent, text=tr("settings_system_startup_on") if st_on else tr("settings_system_startup_off"),
            font=("Segoe UI", 9, "bold"), bg="#0f292a" if st_on else "#182234",
            fg=self.c_success if st_on else self.c_text_muted, relief="flat", highlightthickness=1,
            highlightbackground="#10b981" if st_on else self.c_border, cursor="hand2", padx=14, pady=8,
            command=self._toggle_startup
        )
        self.btn_startup.pack(fill=tk.X, pady=(0, 10))

        tray_on = getattr(self.parent_app, "minimize_to_tray", True) if self.parent_app else bool(get_setting("minimize_to_tray", True))
        self.btn_tray = tk.Button(
            parent, text=tr("settings_system_tray_on") if tray_on else tr("settings_system_tray_off"),
            font=("Segoe UI", 9, "bold"), bg="#0f292a" if tray_on else "#182234",
            fg=self.c_success if tray_on else self.c_text_muted, relief="flat", highlightthickness=1,
            highlightbackground="#10b981" if tray_on else self.c_border, cursor="hand2", padx=14, pady=8,
            command=self._toggle_tray
        )
        self.btn_tray.pack(fill=tk.X, pady=(0, 14))

        tk.Button(
            parent, text=tr("settings_btn_browser_integration", "❖ Open Browser Extension Integration Guide"),
            font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_accent, relief="flat",
            highlightthickness=1, highlightbackground=self.c_accent_dark, cursor="hand2", padx=14, pady=8,
            command=self._open_browser_guide
        ).pack(fill=tk.X)

    def _toggle_startup(self):
        if self.parent_app and hasattr(self.parent_app, "toggle_startup_setting"):
            st_on = self.parent_app.toggle_startup_setting()
        else:
            cur = is_startup_enabled()
            if cur:
                disable_startup()
                st_on = False
                set_setting("startup_enabled", False)
            else:
                enable_startup(minimized=True)
                st_on = True
                set_setting("startup_enabled", True)
        self.btn_startup.configure(
            text=tr("settings_system_startup_on") if st_on else tr("settings_system_startup_off"),
            bg="#0f292a" if st_on else "#182234", fg=self.c_success if st_on else self.c_text_muted,
            highlightbackground="#10b981" if st_on else self.c_border,
        )

    def _toggle_tray(self):
        if self.parent_app and hasattr(self.parent_app, "toggle_minimize_to_tray_setting"):
            tray_on = self.parent_app.toggle_minimize_to_tray_setting()
        else:
            tray_on = not bool(get_setting("minimize_to_tray", True))
            set_setting("minimize_to_tray", tray_on)
        self.btn_tray.configure(
            text=tr("settings_system_tray_on") if tray_on else tr("settings_system_tray_off"),
            bg="#0f292a" if tray_on else "#182234", fg=self.c_success if tray_on else self.c_text_muted,
            highlightbackground="#10b981" if tray_on else self.c_border,
        )

    def _open_browser_guide(self):
        if self.parent_app:
            if hasattr(self.parent_app, "open_browser_integration_dialog"):
                self.parent_app.open_browser_integration_dialog()
            elif hasattr(self.parent_app, "_open_browser_integration_dialog"):
                self.parent_app._open_browser_integration_dialog()


__all__ = ["SettingsModal"]
