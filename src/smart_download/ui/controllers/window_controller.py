"""
Window management, title bar chrome, and geometry controller mixin for Smart Download (SD).
"""
import os
import ctypes

try:
    import tkinter as tk
except Exception:
    tk = None  # type: ignore

from smart_download.i18n import LocalizationManager, tr
from smart_download.config import get_resource_path, APP_VERSION
from smart_download.ui.components.tooltip import ToolTip
from smart_download.services import (
    IS_WINDOWS,
    GWL_STYLE,
    GWL_EXSTYLE,
    WS_EX_APPWINDOW,
    WS_EX_TOOLWINDOW,
    WS_MINIMIZEBOX,
    WS_SYSMENU,
    SW_HIDE,
    SW_MINIMIZE,
    SW_RESTORE,
    SW_SHOW,
)

from .lifecycle_controller import WindowLifecycleMixin
from .theme_controller import ThemeControllerMixin
from .dispatch_controller import DispatchControllerMixin


class WindowChromeMixin(ThemeControllerMixin, DispatchControllerMixin, WindowLifecycleMixin):
    """Provides window setup, custom frameless title bar dragging, and window geometry."""

    def _setup_window(self):
        """Configures frameless window, centering, and dragging."""
        self.root.overrideredirect(True)

        # Center on screen
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - self.width) // 2)
        y = max(0, (sh - self.height) // 2)
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

        # Set Window Icons
        ico_path = get_resource_path("app_icon.ico")
        png_path = get_resource_path("app_icon.png")

        if os.path.isfile(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception:
                pass

        if os.path.isfile(png_path):
            try:
                from PIL import ImageTk
                self._app_icon_photo = ImageTk.PhotoImage(file=png_path)
                self.root.iconphoto(True, self._app_icon_photo)
            except Exception:
                pass

        # Windows Taskbar Integration
        if IS_WINDOWS:
            self.root.update_idletasks()
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                style |= (WS_MINIMIZEBOX | WS_SYSMENU)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)

                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ex_style = (ex_style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

                # Set native taskbar and alt-tab icon via Win32 SendMessageW
                if os.path.isfile(ico_path):
                    try:
                        IMAGE_ICON = 1
                        LR_LOADFROMFILE = 0x00000010
                        WM_SETICON = 0x0080
                        ICON_SMALL = 0
                        ICON_BIG = 1

                        ctypes.windll.user32.LoadImageW.restype = ctypes.c_void_p
                        ctypes.windll.user32.LoadImageW.argtypes = [
                            ctypes.c_void_p,
                            ctypes.c_wchar_p,
                            ctypes.c_uint,
                            ctypes.c_int,
                            ctypes.c_int,
                            ctypes.c_uint
                        ]
                        ctypes.windll.user32.SendMessageW.argtypes = [
                            ctypes.c_void_p,
                            ctypes.c_uint,
                            ctypes.c_void_p,
                            ctypes.c_void_p
                        ]

                        sm_cx = ctypes.windll.user32.GetSystemMetrics(49) or 16
                        sm_cy = ctypes.windll.user32.GetSystemMetrics(50) or 16
                        hicon_sm = ctypes.windll.user32.LoadImageW(None, ico_path, IMAGE_ICON, sm_cx, sm_cy, LR_LOADFROMFILE)
                        if hicon_sm:
                            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_sm)

                        lg_cx = ctypes.windll.user32.GetSystemMetrics(11) or 32
                        lg_cy = ctypes.windll.user32.GetSystemMetrics(12) or 32
                        hicon_lg = ctypes.windll.user32.LoadImageW(None, ico_path, IMAGE_ICON, lg_cx, lg_cy, LR_LOADFROMFILE)
                        if hicon_lg:
                            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_lg)
                    except Exception:
                        pass

                if getattr(self, "_start_hidden", False):
                    try:
                        ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
                    except Exception:
                        pass
                    try:
                        self.root.withdraw()
                    except Exception:
                        pass
                else:
                    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
            except Exception:
                pass

        if getattr(self, "_start_hidden", False):
            try:
                self.root.withdraw()
            except Exception:
                pass

        # Draggable title bar coordinate tracking (Root-relative to prevent jitter)
        self._drag_offset_x = 0
        self._drag_offset_y = 0

    def restore_window(self):
        """Restores and brings the main window to foreground if hidden or minimized."""
        self._start_hidden = False
        try:
            self.root.deiconify()
        except Exception:
            pass
        if IS_WINDOWS:
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
                # Elevation pulse to overcome Windows OS focus-stealing prevention
                HWND_TOPMOST = -1
                HWND_NOTOPMOST = -2
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_SHOWWINDOW = 0x0040
                ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                ctypes.windll.user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self._restore_idle_job = self.root.after_idle(lambda: self.root.attributes("-topmost", False) if hasattr(self, "root") and self.root else None)
            self.root.focus_force()
        except Exception:
            pass

    def _build_title_bar(self, parent):
        """Constructs the custom dark draggable title bar."""
        tb_height = max(38, int(38 * getattr(self, "dpi_scale", 1.0)))
        title_bar = tk.Frame(parent, bg=self.c_panel, height=tb_height)
        title_bar.pack(fill=tk.X, side=tk.TOP)
        title_bar.pack_propagate(False)

        # Drag bindings using root coordinates for silky-smooth motion
        title_bar.bind("<ButtonPress-1>", self._on_title_press)
        title_bar.bind("<B1-Motion>", self._on_title_drag)

        # App Logo Icon in Title Bar
        png_path = get_resource_path("app_icon.png")
        if os.path.isfile(png_path):
            try:
                from PIL import Image, ImageTk
                icon_dim = max(20, int(20 * getattr(self, "dpi_scale", 1.0)))
                with Image.open(png_path) as im:
                    raw_icon = im.resize((icon_dim, icon_dim), Image.Resampling.LANCZOS)
                    self._title_icon_photo = ImageTk.PhotoImage(raw_icon)
                logo_lbl = tk.Label(title_bar, image=self._title_icon_photo, bg=self.c_panel)
                logo_lbl.pack(side=tk.LEFT, padx=(12, 4))
                logo_lbl.bind("<ButtonPress-1>", self._on_title_press)
                logo_lbl.bind("<B1-Motion>", self._on_title_drag)
            except Exception:
                pass

        # App Title
        self.title_lbl = tk.Label(
            title_bar,
            text=tr("app_header"),
            font=("Segoe UI", 10, "bold"),
            bg=self.c_panel,
            fg=self.c_accent
        )
        self.title_lbl.pack(side=tk.LEFT, padx=(6, 8))
        self.title_lbl.bind("<ButtonPress-1>", self._on_title_press)
        self.title_lbl.bind("<B1-Motion>", self._on_title_drag)

        self.subtitle_lbl = tk.Label(
            title_bar,
            text=tr("app_subtitle"),
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_muted
        )
        self.subtitle_lbl.pack(side=tk.LEFT)
        self.subtitle_lbl.bind("<ButtonPress-1>", self._on_title_press)
        self.subtitle_lbl.bind("<B1-Motion>", self._on_title_drag)

        # Window Control Buttons (Minimize & Close)
        btn_close = tk.Label(
            title_bar,
            text="✕",
            font=("Segoe UI", 11, "bold"),
            bg=self.c_panel,
            fg=self.c_text_muted,
            width=4
        )
        btn_close.pack(side=tk.RIGHT, fill=tk.Y)
        btn_close.bind("<Enter>", lambda e: btn_close.configure(bg=self.c_danger, fg="white"))
        btn_close.bind("<Leave>", lambda e: btn_close.configure(bg=self.c_panel, fg=self.c_text_muted))
        btn_close.bind("<Button-1>", lambda e: self._on_close())

        btn_min = tk.Label(
            title_bar,
            text="—",
            font=("Segoe UI", 10, "bold"),
            bg=self.c_panel,
            fg=self.c_text_muted,
            width=4
        )
        btn_min.pack(side=tk.RIGHT, fill=tk.Y)
        btn_min.bind("<Enter>", lambda e: btn_min.configure(bg=self.c_panel_light, fg="white"))
        btn_min.bind("<Leave>", lambda e: btn_min.configure(bg=self.c_panel, fg=self.c_text_muted))
        btn_min.bind("<Button-1>", lambda e: self._on_minimize())

        self.btn_check_updates = tk.Button(
            title_bar,
            text=tr("btn_check_updates", "↻ Check for Updates"),
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
        self.btn_check_updates.pack(side=tk.RIGHT, padx=(6, 8), pady=6)
        self.btn_update = self.btn_check_updates

        # Prominent Language Toggle Button
        cur_lang = LocalizationManager.get_instance().get_language()
        toggle_txt = "⇄ English" if cur_lang == "ar" else "⇄ العربية"
        self.btn_lang_toggle = tk.Button(
            title_bar,
            text=toggle_txt,
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=10,
            pady=2,
            command=self.toggle_language
        )
        self.btn_lang_toggle.pack(side=tk.RIGHT, padx=(4, 6), pady=6)
        ToolTip(self.btn_lang_toggle, "tip_lang_toggle")

        lbl_ver = tk.Label(
            title_bar,
            text=f"v{APP_VERSION}",
            font=("Consolas", 8, "bold"),
            bg=self.c_panel,
            fg=self.c_success
        )
        lbl_ver.pack(side=tk.RIGHT, padx=(4, 4))
        lbl_ver.bind("<ButtonPress-1>", self._on_title_press)
        lbl_ver.bind("<B1-Motion>", self._on_title_drag)

        # Separator Line
        sep = tk.Frame(parent, bg=self.c_panel_light, height=1)
        sep.pack(fill=tk.X, side=tk.TOP)

    def _on_title_press(self, event):
        self._drag_offset_x = event.x_root - self.root.winfo_x()
        self._drag_offset_y = event.y_root - self.root.winfo_y()

    def _on_title_drag(self, event):
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    def _on_minimize(self):
        """Minimize frameless window smoothly without TclError."""
        if IS_WINDOWS:
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
                return
            except Exception:
                pass
        try:
            self.root.overrideredirect(False)
            self.root.iconify()
        except Exception:
            pass

    def is_window_hidden_or_minimized(self) -> bool:
        """Determines if the main application window is minimized, iconic, withdrawn, or hidden."""
        if getattr(self, "_start_hidden", False):
            return True
        if not hasattr(self, "root") or not self.root:
            return False
        try:
            if not self.root.winfo_exists():
                return False
            state = self.root.state()
            if state in ("withdrawn", "iconic"):
                return True
            if not self.root.winfo_viewable():
                return True
            if IS_WINDOWS:
                try:
                    hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                    if ctypes.windll.user32.IsIconic(hwnd):
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False


__all__ = [
    'WindowChromeMixin',
    'WindowLifecycleMixin',
    'ThemeControllerMixin',
    'DispatchControllerMixin',
]
