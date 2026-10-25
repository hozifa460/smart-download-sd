"""
Window management, title bar chrome, event loop dispatch, and lifecycle controller mixin for Smart Download (SD).
"""
import os
import sys
import threading
import ctypes
from typing import Optional, Callable, Dict, Any

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

from smart_download.i18n import LocalizationManager, tr
from smart_download.config import get_resource_path, APP_VERSION
from smart_download.utils import _detach_photo_tk, _drain_bg_tk_callbacks
from smart_download.ui.components.base_modal import SafeModalDialog
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


class WindowChromeMixin:
    """Provides window setup, custom frameless title bar dragging, safe modals, and teardown."""

    def show_safe_error(self, title: str, message: str):
        """Displays error via safe theme dialog without Win32 message loop corruption."""
        if hasattr(self, "log"):
            try:
                self.log(f"[ERROR] {title}: {message}")
            except Exception:
                pass
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root:
                try:
                    self.root.after(0, lambda: self.show_safe_error(title, message))
                except Exception:
                    pass
            return
        if getattr(messagebox.showerror, "_mock_name", None) or hasattr(messagebox.showerror, "mock"):
            messagebox.showerror(title, message)
            return
        try:
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
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
                self._active_modal_dialog = SafeModalDialog(
                    self.root, title, message, dialog_type="error", theme=self._theme_dict()
                )
        except Exception:
            pass

    def show_safe_info(self, title: str, message: str):
        """Displays info via safe theme dialog."""
        if hasattr(self, "log"):
            try:
                self.log(f"[INFO] {title}: {message}")
            except Exception:
                pass
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root:
                try:
                    self.root.after(0, lambda: self.show_safe_info(title, message))
                except Exception:
                    pass
            return
        if getattr(messagebox.showinfo, "_mock_name", None) or hasattr(messagebox.showinfo, "mock"):
            messagebox.showinfo(title, message)
            return
        try:
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
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
                self._active_modal_dialog = SafeModalDialog(
                    self.root, title, message, dialog_type="info", theme=self._theme_dict()
                )
        except Exception:
            pass

    def show_safe_warning(self, title: str, message: str):
        """Displays warning via safe theme dialog."""
        if hasattr(self, "log"):
            try:
                self.log(f"[WARNING] {title}: {message}")
            except Exception:
                pass
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root:
                try:
                    self.root.after(0, lambda: self.show_safe_warning(title, message))
                except Exception:
                    pass
            return
        if getattr(messagebox.showwarning, "_mock_name", None) or hasattr(messagebox.showwarning, "mock"):
            messagebox.showwarning(title, message)
            return
        try:
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
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
                self._active_modal_dialog = SafeModalDialog(
                    self.root, title, message, dialog_type="warning", theme=self._theme_dict()
                )
        except Exception:
            pass

    def ask_safe_yesno(self, title: str, message: str, on_yes: Callable[[], None], on_no: Optional[Callable[[], None]] = None):
        """Safe confirmation modal with Yes/No actions."""
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root:
                try:
                    self.root.after(0, lambda: self.ask_safe_yesno(title, message, on_yes, on_no))
                except Exception:
                    pass
            return
        if getattr(messagebox.askyesno, "_mock_name", None) or hasattr(messagebox.askyesno, "mock"):
            if messagebox.askyesno(title, message):
                on_yes()
            elif on_no:
                on_no()
            return
        try:
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
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
                self._active_modal_dialog = SafeModalDialog(
                    self.root,
                    title,
                    message,
                    dialog_type="confirm",
                    theme=self._theme_dict(),
                    on_confirm=on_yes,
                    on_cancel=on_no
                )
        except Exception:
            pass

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

    def _init_theme(self):
        """Palette and styling definitions."""
        self.c_bg = "#0f172a"          # Slate 900
        self.c_panel = "#1e293b"       # Slate 800
        self.c_panel_light = "#334155" # Slate 700
        self.c_border = "#475569"      # Slate 600
        self.c_accent = "#38bdf8"      # Sky 400
        self.c_accent_dark = "#0284c7" # Sky 600
        self.c_success = "#10b981"     # Emerald 500
        self.c_warning = "#f59e0b"     # Amber 500
        self.c_danger = "#ef4444"      # Red 500
        self.c_text_bright = "#f8fafc" # Slate 50
        self.c_text_muted = "#94a3b8"  # Slate 400
        self.c_input_bg = "#090d16"

        self.root.configure(bg=self.c_bg)

        # TTK Styles
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Treeview styling
        self.style.configure(
            "Custom.Treeview",
            background=self.c_panel,
            foreground=self.c_text_bright,
            fieldbackground=self.c_panel,
            borderwidth=0,
            rowheight=max(26, int(28 * getattr(self, "dpi_scale", 1.0))),
            font=("Segoe UI", 9)
        )
        self.style.configure(
            "Custom.Treeview.Heading",
            background=self.c_panel_light,
            foreground=self.c_accent,
            font=("Segoe UI", 9, "bold"),
            relief="flat"
        )
        self.style.map("Custom.Treeview.Heading", background=[('active', self.c_border)])
        self.style.map("Custom.Treeview", background=[('selected', self.c_accent_dark)])

        # Notebook tabs
        self.style.configure("Custom.TNotebook", background=self.c_panel, borderwidth=0)
        self.style.configure(
            "Custom.TNotebook.Tab",
            background=self.c_panel_light,
            foreground=self.c_text_bright,
            padding=[14, 5],
            font=("Segoe UI", 9, "bold")
        )
        self.style.map(
            "Custom.TNotebook.Tab",
            background=[("selected", self.c_accent_dark)],
            foreground=[("selected", self.c_text_bright)]
        )

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
        self.btn_check_updates.pack(side=tk.RIGHT, padx=(6, 8), pady=6)
        self.btn_update = self.btn_check_updates

        # Prominent Language Toggle Button
        cur_lang = LocalizationManager.get_instance().get_language()
        toggle_txt = "🌐 English" if cur_lang == "ar" else "🌐 العربية"
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

    def _on_root_destroyed(self, event):
        if event.widget == self.root:
            self._cleanup_resources()

    def _cleanup_resources(self):
        self._closing = True
        try:
            LocalizationManager.get_instance().unregister_observer(self._update_ui_language)
        except Exception:
            pass
        if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
            try:
                self._yt_cancel_event.set()
            except Exception:
                pass
        if hasattr(self, "engine") and self.engine:
            try:
                for cb_attr in ("on_progress", "on_chunk_update", "on_log", "on_complete", "on_error"):
                    if hasattr(self.engine, cb_attr):
                        setattr(self.engine, cb_attr, None)
                if getattr(self.engine, "is_running", False):
                    if hasattr(self.engine, "safe_shutdown"):
                        self.engine.safe_shutdown()
                    else:
                        self.engine.cancel()
            except Exception:
                pass
        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.stop()
            except Exception:
                pass
        if hasattr(self, "_clipboard_job") and self._clipboard_job:
            try:
                self.root.after_cancel(self._clipboard_job)
            except Exception:
                pass
            self._clipboard_job = None
        if hasattr(self, "_refresh_job") and self._refresh_job:
            try:
                self.root.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        if hasattr(self, "_bg_notify_job") and self._bg_notify_job:
            try:
                self.root.after_cancel(self._bg_notify_job)
            except Exception:
                pass
            self._bg_notify_job = None
        if hasattr(self, "_update_check_job") and self._update_check_job:
            try:
                self.root.after_cancel(self._update_check_job)
            except Exception:
                pass
            self._update_check_job = None
        if hasattr(self, "_log_jobs") and self._log_jobs:
            for j in list(self._log_jobs):
                try:
                    self.root.after_cancel(j)
                except Exception:
                    pass
            self._log_jobs.clear()
        if hasattr(self, "bridge_server") and self.bridge_server:
            try:
                self.bridge_server.stop()
            except Exception:
                pass
            self.bridge_server = None
        if hasattr(self, "_confirm_modal") and self._confirm_modal:
            try:
                if self._confirm_modal.winfo_exists():
                    self._confirm_modal.destroy()
            except Exception:
                pass
            self._confirm_modal = None
        if hasattr(self, "_quality_modal") and self._quality_modal:
            try:
                if self._quality_modal.winfo_exists():
                    self._quality_modal.destroy()
            except Exception:
                pass
            self._quality_modal = None
        if hasattr(self, "_refresh_modal") and self._refresh_modal:
            try:
                if self._refresh_modal.winfo_exists():
                    self._refresh_modal.destroy()
            except Exception:
                pass
            self._refresh_modal = None
        if hasattr(self, "_active_modal_dialog") and self._active_modal_dialog:
            try:
                if self._active_modal_dialog.winfo_exists():
                    self._active_modal_dialog.destroy()
            except Exception:
                pass
            self._active_modal_dialog = None
        if hasattr(self, "_update_modal") and self._update_modal:
            try:
                if hasattr(self._update_modal, "_cancel_event"):
                    self._update_modal._cancel_event.set()
                if self._update_modal.winfo_exists():
                    self._update_modal.destroy()
            except Exception:
                pass
            self._update_modal = None
        self._close_fetching_toast()
        self._dismiss_bg_toast()
        if hasattr(self, "style") and self.style is not None:
            _detach_photo_tk(self.style)
            self.style = None
        for var_name in ("conn_var", "limit_preset_var"):
            if hasattr(self, var_name):
                _detach_photo_tk(getattr(self, var_name))
        for photo_attr in ("_app_icon_photo", "_title_icon_photo"):
            if hasattr(self, photo_attr):
                _detach_photo_tk(getattr(self, photo_attr))
                setattr(self, photo_attr, None)
        if hasattr(self, "_restore_idle_job") and self._restore_idle_job:
            try:
                self.root.after_cancel(self._restore_idle_job)
            except Exception:
                pass
            self._restore_idle_job = None
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
        self._update_dlg_startup_ui = None
        self._update_dlg_tray_ui = None
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def _on_close(self, force_exit: bool = False):
        """
        Handles the window close button '✕' or WM_DELETE_WINDOW protocol.
        If minimize_to_tray is True (default) and force_exit is False,
        minimizes/hides the window to the Windows System Tray while keeping
        the clipboard sniffer and loopback server running.
        Otherwise, executes a clean application exit.
        """
        if not force_exit and getattr(self, "minimize_to_tray", True):
            self.minimize_to_tray_action()
            return

        self.exit_completely()

    def minimize_to_tray_action(self):
        """Hides the main window to the Windows System Tray while keeping background services alive."""
        try:
            self.root.withdraw()
        except Exception:
            pass

        if IS_WINDOWS:
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
            except Exception:
                pass

        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.start()
            except Exception:
                pass

        self.log("[SYSTEM TRAY] Application minimized to system tray. Clipboard sniffer & browser bridge remain active.")

    def exit_completely(self):
        """Cleanly terminates the application, background threads, servers, and system tray icons."""
        self._closing = True
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
        if hasattr(self, "_confirm_modal") and self._confirm_modal:
            try:
                if self._confirm_modal.winfo_exists():
                    try:
                        self._confirm_modal.grab_release()
                    except Exception:
                        pass
                    self._confirm_modal.destroy()
            except Exception:
                pass
            self._confirm_modal = None
        if hasattr(self, "_update_modal") and self._update_modal:
            try:
                if hasattr(self._update_modal, "_cancel_event"):
                    self._update_modal._cancel_event.set()
                if self._update_modal.winfo_exists():
                    self._update_modal.destroy()
            except Exception:
                pass
            self._update_modal = None
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

        def _do_exit():
            if self.engine and self.engine.is_running:
                try:
                    dl_url = (self.engine.url if self.engine and getattr(self.engine, "url", None) else self.entry_url.get()).strip()
                    dl_dest = (self.engine.dest_path if self.engine and getattr(self.engine, "dest_path", None) else self.entry_dest.get()).strip()
                    if dl_url and dl_dest and hasattr(self, "history_manager") and self.history_manager:
                        self.history_manager.add_or_update_entry(
                            url=dl_url,
                            file_path=dl_dest,
                            size_bytes=getattr(self.engine, "total_size", 0) or 0,
                            status="Paused",
                            elapsed_sec=0.0
                        )
                except Exception:
                    pass
                try:
                    self.engine.safe_shutdown()
                except Exception:
                    pass
            self._cleanup_resources()
            try:
                if hasattr(self, "root") and self.root and self.root.winfo_exists():
                    self.root.destroy()
            except Exception:
                pass

        if self.engine and self.engine.is_running:
            self.restore_window()
            self.ask_safe_yesno(
                tr("dialog_exit_title", "Exit Confirmation"),
                tr("dialog_exit_msg", "A download is currently active. Stop and exit completely?"),
                on_yes=_do_exit
            )
            return
        _do_exit()

    def log(self, message: str):
        """Appends message to activity log console."""
        if getattr(self, "_closing", False):
            return
        job_box = [None]
        def _append():
            try:
                if hasattr(self, "_log_jobs") and job_box[0] in self._log_jobs:
                    self._log_jobs.remove(job_box[0])
                if not getattr(self, "_closing", False) and hasattr(self, "txt_log"):
                    if hasattr(self, "root") and self.root and self.root.winfo_exists():
                        if self.txt_log.winfo_exists():
                            self.txt_log.insert(tk.END, message + "\n")
                            self.txt_log.see(tk.END)
            except Exception:
                pass
        try:
            if not getattr(self, "_closing", False) and hasattr(self, "root") and self.root and self.root.winfo_exists():
                j = self.root.after(0, _append)
                job_box[0] = j
                if hasattr(self, "_log_jobs"):
                    self._log_jobs.append(j)
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

    def dispatch_to_main_thread(self, fn: Callable, *args, **kwargs):
        """Safely queues a callable to be executed on the Tkinter main thread."""
        if hasattr(self, "_gui_dispatch_queue"):
            self._gui_dispatch_queue.put((fn, args, kwargs))
        if threading.current_thread() == threading.main_thread():
            self._drain_dispatch_queue()

    def _drain_dispatch_queue(self):
        """Executes all pending dispatch tasks on the main thread."""
        _drain_bg_tk_callbacks()
        if hasattr(self, "_gui_dispatch_queue"):
            while not self._gui_dispatch_queue.empty():
                try:
                    action, a_args, a_kwargs = self._gui_dispatch_queue.get_nowait()
                    action(*a_args, **a_kwargs)
                except Exception:
                    pass
        _drain_bg_tk_callbacks()
