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
from smart_download.utils.dpi import get_windows_work_area
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
        self._is_maximized = False
        self._normal_geometry = f"{self.width}x{self.height}+{x}+{y}"
        self._min_width = max(820, int(820 * getattr(self, "dpi_scale", 1.0)))
        self._min_height = max(620, int(620 * getattr(self, "dpi_scale", 1.0)))
        self._resize_state = {}
        self._resize_grips = []
        self._setup_resizing()

        # Set Window Icons
        ico_path = get_resource_path("app_icon.ico")
        png_path = get_resource_path("app_icon.png")

        if os.path.isfile(ico_path):
            try: self.root.iconbitmap(ico_path)
            except Exception: pass
        if os.path.isfile(png_path):
            try:
                from PIL import ImageTk
                self._app_icon_photo = ImageTk.PhotoImage(file=png_path)
                self.root.iconphoto(True, self._app_icon_photo)
            except Exception: pass

        # Windows Taskbar Integration
        if IS_WINDOWS:
            self.root.update_idletasks()
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE) | WS_MINIMIZEBOX | WS_SYSMENU
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
                ex_style = (ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

                if os.path.isfile(ico_path):
                    try:
                        ctypes.windll.user32.LoadImageW.restype = ctypes.c_void_p
                        ctypes.windll.user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
                        sm_cx, sm_cy = ctypes.windll.user32.GetSystemMetrics(49) or 16, ctypes.windll.user32.GetSystemMetrics(50) or 16
                        hicon_sm = ctypes.windll.user32.LoadImageW(None, ico_path, 1, sm_cx, sm_cy, 0x10)
                        if hicon_sm: ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon_sm)
                        lg_cx, lg_cy = ctypes.windll.user32.GetSystemMetrics(11) or 32, ctypes.windll.user32.GetSystemMetrics(12) or 32
                        hicon_lg = ctypes.windll.user32.LoadImageW(None, ico_path, 1, lg_cx, lg_cy, 0x10)
                        if hicon_lg: ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon_lg)
                    except Exception: pass

                if getattr(self, "_start_hidden", False):
                    ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
                else:
                    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
            except Exception: pass

        if getattr(self, "_start_hidden", False):
            try: self.root.withdraw()
            except Exception: pass

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
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0043)
                ctypes.windll.user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0043)
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

        self.subtitle_lbl = tk.Label(
            title_bar,
            text=tr("app_subtitle"),
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_muted
        )
        self.subtitle_lbl.pack(side=tk.LEFT)

        # Window Control Buttons (Close, Maximize/Restore, Minimize)
        btn_close = tk.Label(title_bar, text="✕", font=("Segoe UI", 11, "bold"), bg=self.c_panel, fg=self.c_text_muted, width=4)
        btn_close.pack(side=tk.RIGHT, fill=tk.Y)
        btn_close.bind("<Enter>", lambda e: btn_close.configure(bg=self.c_danger, fg="white"))
        btn_close.bind("<Leave>", lambda e: btn_close.configure(bg=self.c_panel, fg=self.c_text_muted))
        btn_close.bind("<Button-1>", lambda e: self._on_close())

        self.btn_max = tk.Label(title_bar, text="□", font=("Segoe UI", 10, "bold"), bg=self.c_panel, fg=self.c_text_muted, width=4)
        self.btn_max.pack(side=tk.RIGHT, fill=tk.Y)
        self.btn_max.bind("<Enter>", lambda e: self.btn_max.configure(bg=self.c_panel_light, fg="white"))
        self.btn_max.bind("<Leave>", lambda e: self.btn_max.configure(bg=self.c_panel, fg=self.c_text_muted))
        self.btn_max.bind("<Button-1>", self.toggle_maximize)

        btn_min = tk.Label(title_bar, text="—", font=("Segoe UI", 10, "bold"), bg=self.c_panel, fg=self.c_text_muted, width=4)
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

        # Double-click and drag bindings on title bar and text labels
        for w in (title_bar, self.title_lbl, self.subtitle_lbl, lbl_ver):
            w.bind("<ButtonPress-1>", self._on_title_press)
            w.bind("<B1-Motion>", self._on_title_drag)
            w.bind("<ButtonRelease-1>", self._on_title_release)
            w.bind("<Double-Button-1>", self.toggle_maximize)

        # Separator Line
        sep = tk.Frame(parent, bg=self.c_panel_light, height=1)
        sep.pack(fill=tk.X, side=tk.TOP)

    def _on_title_press(self, event):
        self._drag_offset_x = event.x_root - self.root.winfo_x()
        self._drag_offset_y = event.y_root - self.root.winfo_y()

    def _on_title_release(self, event):
        if not getattr(self, "_is_maximized", False):
            try:
                self._normal_geometry = self.root.geometry()
            except Exception:
                pass

    def _on_title_drag(self, event):
        if getattr(self, "_is_maximized", False):
            cur_w = max(1, self.root.winfo_width())
            click_x_rel = event.x_root - self.root.winfo_x()
            ratio = max(0.0, min(1.0, click_x_rel / cur_w))

            norm_geo = getattr(self, "_normal_geometry", "")
            restored_w = getattr(self, "width", 850)
            restored_h = getattr(self, "height", 650)
            if norm_geo and "x" in norm_geo:
                try:
                    w_part, rest = norm_geo.split("x", 1)
                    restored_w = int(w_part)
                    restored_h = int(rest.split("+")[0].split("-")[0])
                except Exception:
                    pass

            self._is_maximized = False
            if hasattr(self, "btn_max") and self.btn_max:
                try:
                    self.btn_max.configure(text="□")
                except Exception:
                    pass
            self._show_resize_grips()

            self._drag_offset_x = int(restored_w * ratio)
            self._drag_offset_y = max(10, min(30, getattr(event, "y", 20)))
            x = event.x_root - self._drag_offset_x
            y = event.y_root - self._drag_offset_y
            self.root.geometry(f"{restored_w}x{restored_h}+{x}+{y}")
            return

        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    def toggle_maximize(self, event=None):
        """Toggles between maximized work area and restored normal window geometry."""
        if not getattr(self, "_is_maximized", False):
            try:
                self._normal_geometry = self.root.geometry()
            except Exception:
                pass
            hwnd = None
            try:
                hwnd = self.root.winfo_id()
            except Exception:
                pass
            wa = get_windows_work_area(hwnd) if IS_WINDOWS else None
            if wa:
                work_x, work_y = wa[0], wa[1]
                work_w, work_h = wa[2] - wa[0], wa[3] - wa[1]
            else:
                work_x, work_y = 0, 0
                try:
                    sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                except Exception:
                    sw, sh = 1920, 1080
                work_w, work_h = sw, max(getattr(self, "_min_height", 620), sh - 40)

            try:
                self.root.geometry(f"{work_w}x{work_h}+{work_x}+{work_y}")
            except Exception:
                pass
            self._is_maximized = True
            if hasattr(self, "btn_max") and self.btn_max:
                try:
                    self.btn_max.configure(text="❐")
                except Exception:
                    pass
            self._hide_resize_grips()
        else:
            norm_geo = getattr(self, "_normal_geometry", None)
            if norm_geo:
                try:
                    self.root.geometry(norm_geo)
                except Exception:
                    pass
            self._is_maximized = False
            if hasattr(self, "btn_max") and self.btn_max:
                try:
                    self.btn_max.configure(text="□")
                except Exception:
                    pass
            self._show_resize_grips()

    def _setup_resizing(self):
        """Initializes 8 edge & corner resize grips on the frameless root window."""
        if not hasattr(self, "root") or not self.root or tk is None:
            return
        try:
            self._resize_grips = []
            grip_configs = [
                ("nw", "size_nw_se", {"x": 0, "y": 0, "width": 8, "height": 8}),
                ("ne", "size_ne_sw", {"relx": 1.0, "x": -8, "y": 0, "width": 8, "height": 8}),
                ("sw", "size_ne_sw", {"x": 0, "rely": 1.0, "y": -8, "width": 8, "height": 8}),
                ("se", "size_nw_se", {"relx": 1.0, "x": -10, "rely": 1.0, "y": -10, "width": 10, "height": 10}),
                ("n",  "size_ns",    {"x": 8, "y": 0, "relwidth": 1.0, "width": -16, "height": 5}),
                ("s",  "size_ns",    {"x": 8, "rely": 1.0, "y": -5, "relwidth": 1.0, "width": -16, "height": 5}),
                ("w",  "size_we",    {"x": 0, "y": 8, "width": 5, "relheight": 1.0, "height": -16}),
                ("e",  "size_we",    {"relx": 1.0, "x": -5, "y": 8, "width": 5, "relheight": 1.0, "height": -16}),
            ]
            border_color = getattr(self, "c_border", "#2a2d32")
            for mode, cursor_name, place_kwargs in grip_configs:
                grip = tk.Frame(self.root, bg=border_color, cursor=cursor_name)
                grip.bind("<ButtonPress-1>", lambda e, m=mode: self._on_resize_press(e, m))
                grip.bind("<B1-Motion>", self._on_resize_drag)
                grip.bind("<ButtonRelease-1>", self._on_resize_release)
                grip.place(**place_kwargs)
                grip.lift()
                self._resize_grips.append((grip, place_kwargs))
        except Exception:
            pass

    def _lift_resize_grips(self):
        """Ensures all 8 resize grips stay above all container frames."""
        for grip, _ in getattr(self, "_resize_grips", []):
            try: grip.lift()
            except Exception: pass

    def _hide_resize_grips(self):
        """Temporarily hides resize grips when maximized."""
        for grip, _ in getattr(self, "_resize_grips", []):
            try: grip.place_forget()
            except Exception: pass

    def _show_resize_grips(self):
        """Restores resize grips when unmaximized."""
        for grip, place_kwargs in getattr(self, "_resize_grips", []):
            try:
                grip.place(**place_kwargs)
                grip.lift()
            except Exception: pass

    def _on_resize_press(self, event, mode: str):
        if getattr(self, "_is_maximized", False): return "break"
        try:
            win_w, win_h = self.root.winfo_width(), self.root.winfo_height()
            win_x, win_y = self.root.winfo_x(), self.root.winfo_y()
            if win_w <= 1 or win_h <= 1:
                norm_geo = getattr(self, "_normal_geometry", "")
                if norm_geo and "x" in norm_geo:
                    try:
                        w_p, rest = norm_geo.split("x", 1)
                        win_w = int(w_p)
                        pts = rest.replace("-", "+-").split("+")
                        win_h = int(pts[0])
                        if len(pts) >= 3: win_x, win_y = int(pts[1]), int(pts[2])
                    except Exception:
                        win_w, win_h = getattr(self, "width", 850), getattr(self, "height", 650)
                else:
                    win_w, win_h = getattr(self, "width", 850), getattr(self, "height", 650)
            self._resize_state = {
                "mode": mode, "x_root": event.x_root, "y_root": event.y_root,
                "win_x": win_x, "win_y": win_y, "win_w": win_w, "win_h": win_h,
            }
        except Exception: pass
        return "break"

    def _on_resize_drag(self, event):
        if getattr(self, "_is_maximized", False):
            return "break"
        mode = getattr(self, "_resize_state", {}).get("mode")
        if not mode:
            return "break"

        try:
            dx = event.x_root - self._resize_state["x_root"]
            dy = event.y_root - self._resize_state["y_root"]
            w = self._resize_state["win_w"]
            h = self._resize_state["win_h"]
            x = self._resize_state["win_x"]
            y = self._resize_state["win_y"]
            min_w = getattr(self, "_min_width", 820)
            min_h = getattr(self, "_min_height", 620)

            if "e" in mode:
                w = max(min_w, w + dx)
            if "s" in mode:
                h = max(min_h, h + dy)
            if "w" in mode:
                new_w = max(min_w, w - dx)
                x = x + (w - new_w)
                w = new_w
            if "n" in mode:
                new_h = max(min_h, h - dy)
                y = y + (h - new_h)
                h = new_h

            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self._normal_geometry = f"{w}x{h}+{x}+{y}"
            self.width, self.height = w, h
        except Exception:
            pass
        return "break"

    def _on_resize_release(self, event):
        if hasattr(self, "_resize_state"):
            self._resize_state.clear()
        return "break"


    def _detect_resize_edge(self, x: int, y: int, width: int, height: int, threshold: int = 6) -> str:
        """Determines the resize edge direction ('n', 's', 'e', 'w', 'nw', 'ne', 'sw', 'se') for coordinate (x, y)."""
        edge = ""
        if y <= threshold: edge += "n"
        elif y >= height - threshold: edge += "s"
        if x <= threshold: edge += "w"
        elif x >= width - threshold: edge += "e"
        return edge

    def _cursor_for_edge(self, edge: str) -> str:
        if edge in ("nw", "se"): return "size_nw_se"
        if edge in ("ne", "sw"): return "size_ne_sw"
        if edge in ("w", "e"): return "size_we"
        if edge in ("n", "s"): return "size_ns"
        return ""

    def _setup_border_resizing(self, widget):
        """Binds border motion and drag events to main_border for edge resizing."""
        if not widget: return
        widget.bind("<Motion>", self._on_border_motion)
        widget.bind("<ButtonPress-1>", self._on_border_press)
        widget.bind("<B1-Motion>", self._on_resize_drag)
        widget.bind("<ButtonRelease-1>", self._on_resize_release)

    def _on_border_motion(self, event):
        if getattr(self, "_is_maximized", False): return
        w, h = self.root.winfo_width(), self.root.winfo_height()
        edge = self._detect_resize_edge(event.x, event.y, w, h, 6)
        event.widget.configure(cursor=self._cursor_for_edge(edge))

    def _on_border_press(self, event):
        if getattr(self, "_is_maximized", False): return "break"
        w, h = self.root.winfo_width(), self.root.winfo_height()
        edge = self._detect_resize_edge(event.x, event.y, w, h, 6)
        return self._on_resize_press(event, edge) if edge else "break"

    def _on_minimize(self):
        """Minimize frameless window smoothly without TclError."""
        if IS_WINDOWS:
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
                return
            except Exception: pass
        try:
            self.root.overrideredirect(False)
            self.root.iconify()
        except Exception: pass

    def is_window_hidden_or_minimized(self) -> bool:
        """Determines if the main application window is minimized, iconic, withdrawn, or hidden."""
        if getattr(self, "_start_hidden", False): return True
        if not hasattr(self, "root") or not self.root: return False
        try:
            if not self.root.winfo_exists(): return False
            if self.root.state() in ("withdrawn", "iconic") or not self.root.winfo_viewable(): return True
            if IS_WINDOWS:
                try:
                    hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                    if ctypes.windll.user32.IsIconic(hwnd): return True
                except Exception: pass
        except Exception: pass
        return False


__all__ = [
    'WindowChromeMixin',
    'WindowLifecycleMixin',
    'ThemeControllerMixin',
    'DispatchControllerMixin',
]
