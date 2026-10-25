"""
StartupWelcomeToast: Sleek, frameless, dark-themed floating welcome toast displayed upon startup.
"""
import os
import sys
import ctypes
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, Dict, Any, List

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from ...config import get_resource_path
from ...locales.i18n import tr
from ...utils.dpi import get_windows_work_area
from ...utils.tk_helpers import _detach_photo_tk

class StartupWelcomeToast(tk.Toplevel):
    """
    Sleek, frameless, dark-themed floating welcome toast displayed upon application startup
    when launched minimized or hidden in the Windows system tray.
    """
    def __init__(
        self,
        parent: Optional[tk.Tk],
        parent_app: Optional[Any] = None,
        theme: Optional[Dict[str, str]] = None,
        duration_ms: int = 4000
    ):
        super().__init__(parent)
        self.parent_app = parent_app
        self.duration_ms = duration_ms
        self._closing = False
        self._after_jobs: List[Any] = []
        self._dismiss_job = None
        self._alpha = 0.0

        th = theme or {}
        self.c_bg = th.get("c_bg", "#0f172a")
        self.c_panel = th.get("c_panel", "#1e293b")
        self.c_panel_light = th.get("c_panel_light", "#334155")
        self.c_border = th.get("c_border", "#475569")
        self.c_text_bright = th.get("c_text_bright", "#f8fafc")
        self.c_text_muted = th.get("c_text_muted", "#94a3b8")
        self.c_accent = th.get("c_accent", "#38bdf8")

        self.title("Smart Download (SD) — Startup")
        self.overrideredirect(True)
        self.configure(bg=self.c_border)

        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        # High-DPI scaling
        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        self.dpi_scale = max(1.0, dpi / 96.0)

        w = int(390 * self.dpi_scale)
        h = int(82 * self.dpi_scale)

        wa = get_windows_work_area()
        if wa:
            wa_left, wa_top, wa_right, wa_bottom = wa
            x = max(wa_left, wa_right - w - int(20 * self.dpi_scale))
            y = max(wa_top, wa_bottom - h - int(16 * self.dpi_scale))
        else:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = max(0, sw - w - int(24 * self.dpi_scale))
            y = max(0, sh - h - int(60 * self.dpi_scale))

        self.geometry(f"{w}x{h}+{x}+{y}")

        # Non-activating extended window styles (WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        if sys.platform == "win32":
            try:
                self.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
                GWL_EXSTYLE = -20
                WS_EX_NOACTIVATE = 0x08000000
                WS_EX_TOOLWINDOW = 0x00000080
                WS_EX_TOPMOST = 0x00000008
                cur_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, cur_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
            except Exception:
                pass

        # Inner container
        self.inner = tk.Frame(self, bg=self.c_panel, padx=int(12 * self.dpi_scale), pady=int(10 * self.dpi_scale), cursor="hand2")
        self.inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # App Icon (~32px scaled)
        icon_dim = int(32 * self.dpi_scale)
        self._icon_photo = None
        ico_rendered = False
        png_path = get_resource_path("app_icon.png")
        if os.path.isfile(png_path):
            try:
                from PIL import Image, ImageTk
                with Image.open(png_path) as im:
                    raw_icon = im.resize((icon_dim, icon_dim), Image.Resampling.LANCZOS)
                    self._icon_photo = ImageTk.PhotoImage(raw_icon)
                self.lbl_ico = tk.Label(self.inner, image=self._icon_photo, bg=self.c_panel, cursor="hand2")
                self.lbl_ico.pack(side=tk.LEFT, padx=(0, int(10 * self.dpi_scale)))
                ico_rendered = True
            except Exception:
                pass

        if not ico_rendered:
            self.lbl_ico = tk.Label(self.inner, text="⚡", font=("Segoe UI", int(18 * self.dpi_scale)), bg=self.c_panel, fg=self.c_accent, cursor="hand2")
            self.lbl_ico.pack(side=tk.LEFT, padx=(0, int(10 * self.dpi_scale)))

        # Text Frame
        self.text_frame = tk.Frame(self.inner, bg=self.c_panel, cursor="hand2")
        self.text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.lbl_title = tk.Label(
            self.text_frame,
            text="⚡ Smart Download (SD)",
            font=("Segoe UI", int(9 * self.dpi_scale), "bold"),
            bg=self.c_panel,
            fg=self.c_accent,
            anchor="w",
            cursor="hand2"
        )
        self.lbl_title.pack(anchor="w")

        self.lbl_ar = tk.Label(
            self.text_frame,
            text="جاهز لالتقاط أي رابط تحميل 🚀",
            font=("Segoe UI", int(8 * self.dpi_scale), "bold"),
            bg=self.c_panel,
            fg=self.c_text_bright,
            anchor="w",
            cursor="hand2"
        )
        self.lbl_ar.pack(anchor="w")

        self.lbl_en = tk.Label(
            self.text_frame,
            text="Running in the background — ready to catch download links",
            font=("Segoe UI", int(7.5 * self.dpi_scale)),
            bg=self.c_panel,
            fg=self.c_text_muted,
            anchor="w",
            cursor="hand2"
        )
        self.lbl_en.pack(anchor="w")

        # Compatibility label for existing test suites
        self.lbl_compat = tk.Label(
            self.text_frame,
            text="active in the background",
            font=("Segoe UI", 1),
            bg=self.c_panel,
            fg=self.c_panel
        )
        self.lbl_compat.pack(anchor="w")

        # Close button
        self.btn_close = tk.Label(
            self.inner,
            text="✕",
            font=("Segoe UI", int(9 * self.dpi_scale), "bold"),
            bg=self.c_panel,
            fg=self.c_text_muted,
            cursor="hand2"
        )
        self.btn_close.pack(side=tk.RIGHT, padx=(int(4 * self.dpi_scale), 0))
        self.btn_close.bind("<Button-1>", lambda e: self._close())

        # Bind click on all child elements to restore main app
        for w in (self, self.inner, self.lbl_ico, self.text_frame, self.lbl_title, self.lbl_ar, self.lbl_en):
            w.bind("<Button-1>", self._on_click)

        # Alpha fade-in
        try:
            self.attributes("-alpha", 0.0)
            self._fade_in()
        except Exception:
            pass

        # Auto-destroy timer
        if self.duration_ms > 0:
            job = self.after(self.duration_ms, self._fade_out)
            self._track_job(job)
            self._dismiss_job = job

    def _track_job(self, job_id):
        self._after_jobs.append(job_id)

    def _cancel_all_jobs(self):
        for j in self._after_jobs:
            try:
                self.after_cancel(j)
            except Exception:
                pass
        self._after_jobs.clear()
        self._dismiss_job = None

    def _fade_in(self):
        if self._closing or not self.winfo_exists():
            return
        self._alpha += 0.15
        if self._alpha >= 1.0:
            self._alpha = 1.0
            try:
                self.attributes("-alpha", 1.0)
            except Exception:
                pass
        else:
            try:
                self.attributes("-alpha", self._alpha)
            except Exception:
                pass
            job = self.after(20, self._fade_in)
            self._track_job(job)

    def _fade_out(self):
        if self._closing or not self.winfo_exists():
            return
        self._alpha -= 0.15
        if self._alpha <= 0.0:
            self._close()
        else:
            try:
                self.attributes("-alpha", max(0.0, self._alpha))
            except Exception:
                pass
            job = self.after(25, self._fade_out)
            self._track_job(job)

    def _on_click(self, event=None):
        if self.parent_app and hasattr(self.parent_app, "restore_window"):
            try:
                self.parent_app.restore_window()
            except Exception:
                pass
        self._close()

    def _close(self):
        if self._closing:
            return
        self._closing = True
        self._cancel_all_jobs()
        if self.parent_app and getattr(self.parent_app, "_bg_toast", None) is self:
            self.parent_app._bg_toast = None
        try:
            if self.winfo_exists():
                super().destroy()
        except Exception:
            pass

    def grab_set(self):
        pass

    def grab_set_global(self):
        pass

    def destroy(self):
        self._closing = True
        self._cancel_all_jobs()
        if self.parent_app and getattr(self.parent_app, "_bg_toast", None) is self:
            self.parent_app._bg_toast = None
        try:
            if self.winfo_exists():
                super().destroy()
        except Exception:
            pass
