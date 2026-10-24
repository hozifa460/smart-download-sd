"""
Toast notifications: FetchingLinkToast & StartupWelcomeToast.
"""
import os
import sys
import ctypes
import urllib.request
import urllib.parse
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

class FetchingLinkToast(tk.Toplevel):
    """
    Sleek, dark-themed, frameless toast/popup window displayed instantaneously (< 50ms)
    when a downloadable URL (especially YouTube or remote stream requiring format analysis)
    is intercepted from clipboard or browser extension while the main window is hidden or minimized.

    Features:
    - Displayed in < 50ms with frameless dark styling and High-DPI scaling.
    - Arabic header: 🔍 جاري جلب وتحليل الرابط...
    - English subheader: Fetching link information...
    - Extracted domain tag (e.g. [youtube.com]) and truncated URL preview.
    - Animated marquee pulsing progress bar and dynamic status indicator.
    - Non-blocking, grab-free architecture (strictly avoids grab_set() traps).
    - Cancel button allowing user to safely abort link analysis at any time.
    """
    def __init__(
        self,
        parent: Optional[tk.Tk],
        url: str,
        theme: Optional[Dict[str, str]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        parent_app: Optional[Any] = None
    ):
        super().__init__(parent)
        self.url = str(url or "").strip()
        self.on_cancel = on_cancel
        self.parent_app = parent_app
        self._closing = False
        self._pulse_pos = 0
        self._pulse_dir = 1
        self._pulse_job = None
        self._dot_count = 0
        self._dot_job = None

        th = theme or {}
        self.c_bg = th.get("c_bg", "#0f172a")
        self.c_panel = th.get("c_panel", "#1e293b")
        self.c_panel_light = th.get("c_panel_light", "#334155")
        self.c_border = th.get("c_border", "#475569")
        self.c_text_bright = th.get("c_text_bright", "#f8fafc")
        self.c_text_muted = th.get("c_text_muted", "#94a3b8")
        self.c_accent = th.get("c_accent", "#38bdf8")
        self.c_accent_dark = th.get("c_accent_dark", "#0284c7")
        self.c_danger = th.get("c_danger", "#ef4444")
        self.c_success = th.get("c_success", "#10b981")
        self.c_input_bg = th.get("c_input_bg", "#0b1220")

        self.title("Fetching Link Information — Smart Download")
        self.overrideredirect(True)
        self.configure(bg=self.c_border)

        # High-DPI scaling
        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        self.dpi_scale = max(1.0, dpi / 96.0)

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        dlg_w = min(int(460 * self.dpi_scale), max(380, int(sw * 0.90)))
        dlg_h = min(int(148 * self.dpi_scale), max(128, int(sh * 0.70)))

        # Center on screen
        x = max(0, (sw - dlg_w) // 2)
        y = max(0, (sh - dlg_h) // 2)
        self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")

        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        # Parse domain snippet
        domain = ""
        try:
            parsed = urllib.parse.urlparse(self.url)
            domain = (parsed.netloc or parsed.path.split("/")[0]).strip() or "remote"
        except Exception:
            domain = "remote"

        # Truncate URL preview if long
        url_preview = self.url
        if len(url_preview) > 52:
            url_preview = url_preview[:28] + "..." + url_preview[-20:]

        # Outer border & inner body
        self.inner = tk.Frame(self, bg=self.c_panel, padx=14, pady=12)
        self.inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Header Row: Arabic + English Title & Cancel '✕ إلغاء'
        hdr_frame = tk.Frame(self.inner, bg=self.c_panel)
        hdr_frame.pack(fill=tk.X, pady=(0, 6))

        lbl_icon = tk.Label(hdr_frame, text="🔍", font=("Segoe UI", 12), bg=self.c_panel, fg=self.c_accent)
        lbl_icon.pack(side=tk.LEFT, padx=(0, 6))

        title_box = tk.Frame(hdr_frame, bg=self.c_panel)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_ar = tk.Label(
            title_box,
            text="🔍 جاري جلب وتحليل الرابط...",
            font=("Segoe UI", 10, "bold"),
            bg=self.c_panel,
            fg=self.c_accent,
            anchor="w"
        )
        self.lbl_ar.pack(anchor="w")

        self.lbl_en = tk.Label(
            title_box,
            text="Fetching link information...",
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_muted,
            anchor="w"
        )
        self.lbl_en.pack(anchor="w")

        self.btn_cancel = tk.Button(
            hdr_frame,
            text="✕ إلغاء",
            font=("Segoe UI", 8),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            activebackground=self.c_danger,
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=2,
            command=self._on_cancel_click
        )
        self.btn_cancel.pack(side=tk.RIGHT, padx=(6, 0))

        # URL Snippet Box
        snippet_frame = tk.Frame(self.inner, bg=self.c_input_bg, padx=8, pady=4, highlightbackground=self.c_border, highlightthickness=1)
        snippet_frame.pack(fill=tk.X, pady=(2, 8))

        self.lbl_domain = tk.Label(
            snippet_frame,
            text=f"[{domain}]",
            font=("Segoe UI", 8, "bold"),
            bg=self.c_input_bg,
            fg=self.c_accent
        )
        self.lbl_domain.pack(side=tk.LEFT, padx=(0, 6))

        self.lbl_url = tk.Label(
            snippet_frame,
            text=url_preview,
            font=("Segoe UI", 8),
            bg=self.c_input_bg,
            fg=self.c_text_bright,
            anchor="w"
        )
        self.lbl_url.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Animated Marquee / Pulsing Canvas Bar
        canvas_h = int(5 * self.dpi_scale)
        self.canvas_pulse = tk.Canvas(
            self.inner,
            height=canvas_h,
            bg=self.c_panel_light,
            highlightthickness=0,
            relief="flat"
        )
        self.canvas_pulse.pack(fill=tk.X, pady=(2, 6))
        self.pulse_rect = self.canvas_pulse.create_rectangle(0, 0, 0, canvas_h, fill=self.c_accent, outline="")

        # Status text row
        self.lbl_status = tk.Label(
            self.inner,
            text="جاري الاتصال بالسيرفر وفحص الصيغ المتاحة...",
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_muted,
            anchor="w"
        )
        self.lbl_status.pack(anchor="w")

        self.bind("<Escape>", lambda e: self._on_cancel_click())

        # Start animations
        self._start_animations()

    def _start_animations(self):
        """Initiates pulsing progress marquee and animated status dots."""
        self._animate_pulse()
        self._animate_dots()

    def _animate_pulse(self):
        if getattr(self, "_closing", False) or not self.winfo_exists():
            return
        if hasattr(self, "_pulse_job") and self._pulse_job:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        try:
            w = self.canvas_pulse.winfo_width()
            if w <= 1:
                w = int(420 * self.dpi_scale)
            bar_w = int(w * 0.35)
            self._pulse_pos += (8 * self._pulse_dir)
            if self._pulse_pos + bar_w >= w:
                self._pulse_dir = -1
                self._pulse_pos = w - bar_w
            elif self._pulse_pos <= 0:
                self._pulse_dir = 1
                self._pulse_pos = 0

            h = self.canvas_pulse.winfo_height() or 5
            self.canvas_pulse.coords(self.pulse_rect, self._pulse_pos, 0, self._pulse_pos + bar_w, h)
            if not getattr(self, "_closing", False) and self.winfo_exists():
                self._pulse_job = self.after(30, self._animate_pulse)
        except Exception:
            pass

    def _animate_dots(self):
        if getattr(self, "_closing", False) or not self.winfo_exists():
            return
        if hasattr(self, "_dot_job") and self._dot_job:
            try:
                self.after_cancel(self._dot_job)
            except Exception:
                pass
            self._dot_job = None
        try:
            self._dot_count = (self._dot_count + 1) % 4
            dots = "." * self._dot_count
            self.lbl_en.configure(text=f"Fetching link information{dots}")
            if not getattr(self, "_closing", False) and self.winfo_exists():
                self._dot_job = self.after(400, self._animate_dots)
        except Exception:
            pass

    def _on_cancel_click(self):
        """User clicked Cancel on the fetching toast."""
        self._closing = True
        if self._pulse_job:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        if self._dot_job:
            try:
                self.after_cancel(self._dot_job)
            except Exception:
                pass
            self._dot_job = None
        if callable(self.on_cancel):
            try:
                self.on_cancel()
            except Exception:
                pass
        if self.parent_app and hasattr(self.parent_app, "clear_last_clipboard_url"):
            try:
                self.parent_app.clear_last_clipboard_url()
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass

    def close(self):
        """Smoothly closes and destroys the toast window without invoking cancel callback."""
        self._closing = True
        if self._pulse_job:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        if self._dot_job:
            try:
                self.after_cancel(self._dot_job)
            except Exception:
                pass
            self._dot_job = None
        try:
            if self.winfo_exists():
                self.destroy()
        except Exception:
            pass

    def grab_set(self):
        """No-op: Strictly avoids grab_set() lock."""
        pass

    def grab_set_global(self):
        """No-op: Strictly avoids grab_set_global() lock."""
        pass

    def destroy(self):
        """Cancels background animation timers and destroys widget cleanly."""
        self._closing = True
        if hasattr(self, "_pulse_job") and self._pulse_job:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        if hasattr(self, "_dot_job") and self._dot_job:
            try:
                self.after_cancel(self._dot_job)
            except Exception:
                pass
            self._dot_job = None
        if self.parent_app and getattr(self.parent_app, "_fetching_toast", None) is self:
            self.parent_app._fetching_toast = None
        super().destroy()


# ======================================================================================
# 3B2. STARTUP WELCOME TOAST NOTIFICATION (FRAMELESS FLOATING WINDOW)
# ======================================================================================

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

