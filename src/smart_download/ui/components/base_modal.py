"""
SafeModalDialog: Resilient, High-DPI scaled, localized dialog base modal.
"""
import os
import sys
try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore
from typing import Optional, Callable, Dict, Any

from ...config import get_resource_path
from ...locales.i18n import tr, LocalizationManager
from ...utils.tk_helpers import _detach_photo_tk

_BaseToplevel = tk.Toplevel if tk is not None else object

class SafeModalDialog(_BaseToplevel):
    """
    Sleek, theme-consistent modal dialog designed specifically for borderless / overrideredirect windows.
    Replaces native Win32 messageboxes to eliminate window hierarchy corruption, message pump deadlocks,
    and process exits on Windows.
    """
    def __init__(
        self,
        parent: Optional[Any],
        title: str,
        message: str,
        dialog_type: str = "error",  # "error", "info", "warning", "confirm"
        theme: Optional[Dict[str, str]] = None,
        on_confirm: Optional[Callable[[], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.dialog_type = dialog_type
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.result = False

        th = theme or {}
        c_bg = th.get("c_bg", "#0f172a")
        c_panel = th.get("c_panel", "#1e293b")
        c_panel_light = th.get("c_panel_light", "#334155")
        c_border = th.get("c_border", "#475569")
        c_text_bright = th.get("c_text_bright", "#f8fafc")
        c_text_muted = th.get("c_text_muted", "#94a3b8")
        c_accent = th.get("c_accent", "#38bdf8")
        c_accent_dark = th.get("c_accent_dark", "#0284c7")
        c_danger = th.get("c_danger", "#ef4444")
        c_warning = th.get("c_warning", "#f59e0b")
        c_success = th.get("c_success", "#10b981")

        if dialog_type == "error":
            accent_col = c_danger
            icon_str = "⚠"
        elif dialog_type == "warning":
            accent_col = c_warning
            icon_str = "⚠"
        elif dialog_type == "confirm":
            accent_col = c_accent
            icon_str = "?"
        else:
            accent_col = c_accent
            icon_str = "ℹ"

        self.title(title)
        self.configure(bg=c_bg)
        try:
            self.overrideredirect(True)
        except Exception:
            pass
        # Do not use grab_set(): with borderless / overrideredirect windows,
        # grab_set traps Win32 input messages and locks the main window pump.

        # Dimensions & Centering with DPI scaling
        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        dpi_scale = max(1.0, dpi / 96.0)

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        dlg_w = min(int(520 * dpi_scale), max(440, int(sw * 0.90)))
        dlg_h = min(int(280 * dpi_scale), max(240, int(sh * 0.70)))

        is_parent_visible = False
        try:
            if parent and parent.winfo_exists() and parent.winfo_viewable() and parent.state() == "normal":
                is_parent_visible = True
        except Exception:
            is_parent_visible = False

        if is_parent_visible:
            try:
                self.transient(parent)
            except Exception:
                pass
            try:
                px = parent.winfo_x()
                py = parent.winfo_y()
                pw = parent.winfo_width() or dlg_w
                ph = parent.winfo_height() or dlg_h
                x = px + (pw - dlg_w) // 2
                y = max(0, py + (ph - dlg_h) // 2)
            except Exception:
                x = max(0, (sw - dlg_w) // 2)
                y = max(0, (sh - dlg_h) // 2)
        else:
            try:
                self.transient("")
                self.deiconify()
            except Exception:
                pass
            x = max(0, (sw - dlg_w) // 2)
            y = max(0, (sh - dlg_h) // 2)

        self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
        self.minsize(min(440, dlg_w), min(240, dlg_h))

        # Apply application icon to modal window
        ico_path = get_resource_path("app_icon.ico")
        png_path = get_resource_path("app_icon.png")
        if os.path.isfile(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass
        if os.path.isfile(png_path):
            try:
                from PIL import ImageTk
                self._modal_icon_photo = ImageTk.PhotoImage(file=png_path)
                self.iconphoto(True, self._modal_icon_photo)
            except Exception:
                pass

        # Elevate and focus
        self._topmost_after_id = None
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self._topmost_after_id = self.after(250, lambda: self.attributes("-topmost", False) if self.winfo_exists() else None)
        except Exception:
            pass

        outer = tk.Frame(self, bg=c_border, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        # Custom dark frameless title bar
        title_bar = tk.Frame(outer, bg=c_panel, height=30)
        title_bar.pack(fill=tk.X, side=tk.TOP)

        lbl_app_icon = None
        if os.path.isfile(png_path):
            try:
                from PIL import Image, ImageTk
                img = Image.open(png_path).resize((16, 16), getattr(Image, "Resampling", Image).LANCZOS if hasattr(Image, "Resampling") else getattr(Image, "ANTIALIAS", 1))
                self._modal_title_photo = ImageTk.PhotoImage(img)
                lbl_app_icon = tk.Label(title_bar, image=self._modal_title_photo, bg=c_panel)
                lbl_app_icon.pack(side=tk.LEFT, padx=(8, 4), pady=4)
            except Exception:
                pass
        if not lbl_app_icon:
            lbl_app_icon = tk.Label(title_bar, text="⚡", font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_accent)
            lbl_app_icon.pack(side=tk.LEFT, padx=(8, 4), pady=4)

        lbl_win_title = tk.Label(title_bar, text=title, font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_bright, anchor="w")
        lbl_win_title.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 6))

        btn_close = tk.Label(title_bar, text="✕", font=("Segoe UI", 10, "bold"), bg=c_panel, fg=c_text_muted, width=3, cursor="hand2")
        btn_close.pack(side=tk.RIGHT, fill=tk.Y)
        btn_close.bind("<Enter>", lambda e: btn_close.configure(bg=c_danger, fg="white"))
        btn_close.bind("<Leave>", lambda e: btn_close.configure(bg=c_panel, fg=c_text_muted))
        btn_close.bind("<Button-1>", lambda e: self._on_close())

        for w in (title_bar, lbl_win_title, lbl_app_icon):
            w.bind("<ButtonPress-1>", self._on_drag_press)
            w.bind("<B1-Motion>", self._on_drag_motion)

        sep = tk.Frame(outer, bg=c_border, height=1)
        sep.pack(fill=tk.X, side=tk.TOP)

        body = tk.Frame(outer, bg=c_bg, padx=18, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        # Header with icon and title
        hdr_frame = tk.Frame(body, bg=c_bg)
        hdr_frame.pack(fill=tk.X, pady=(0, 10))

        lbl_icon = tk.Label(hdr_frame, text=icon_str, font=("Segoe UI", 16), bg=c_bg, fg=accent_col)
        lbl_icon.pack(side=tk.LEFT, padx=(0, 8))

        lbl_title = tk.Label(hdr_frame, text=title, font=("Segoe UI", 11, "bold"), bg=c_bg, fg=accent_col, anchor="w")
        lbl_title.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Message box (Scrollable text or wrap label)
        msg_frame = tk.Frame(body, bg=c_panel, padx=12, pady=10, highlightbackground=c_border, highlightthickness=1)
        msg_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 14))

        txt_msg = tk.Text(
            msg_frame,
            font=("Segoe UI", 9),
            bg=c_panel,
            fg=c_text_bright,
            wrap=tk.WORD,
            relief="flat",
            highlightthickness=0,
            height=4
        )
        txt_scroll = ttk.Scrollbar(msg_frame, orient=tk.VERTICAL, command=txt_msg.yview)
        txt_msg.configure(yscrollcommand=txt_scroll.set)
        txt_msg.insert("1.0", str(message or ""))
        txt_msg.configure(state="disabled")
        txt_msg.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        txt_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Buttons
        btn_frame = tk.Frame(body, bg=c_bg)
        btn_frame.pack(fill=tk.X)

        if dialog_type == "confirm":
            btn_yes = tk.Button(
                btn_frame,
                text=tr("btn_yes", "Yes"),
                font=("Segoe UI", 9, "bold"),
                bg=accent_col,
                fg="white",
                relief="flat",
                activebackground=c_accent_dark,
                cursor="hand2",
                padx=18,
                pady=5,
                command=self._on_ok
            )
            btn_yes.pack(side=tk.RIGHT, padx=(8, 0))

            btn_no = tk.Button(
                btn_frame,
                text=tr("btn_no", "No"),
                font=("Segoe UI", 9),
                bg=c_panel_light,
                fg=c_text_muted,
                relief="flat",
                activebackground=c_border,
                cursor="hand2",
                padx=18,
                pady=5,
                command=self._on_close
            )
            btn_no.pack(side=tk.RIGHT)
        else:
            btn_ok = tk.Button(
                btn_frame,
                text=tr("btn_ok", "OK"),
                font=("Segoe UI", 9, "bold"),
                bg=accent_col,
                fg="white",
                relief="flat",
                activebackground=c_accent_dark,
                cursor="hand2",
                padx=22,
                pady=5,
                command=self._on_ok
            )
            btn_ok.pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<Return>", lambda e: self._on_ok())

    def _on_drag_press(self, event):
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()

    def _on_drag_motion(self, event):
        x = event.x_root - getattr(self, "_drag_offset_x", 0)
        y = event.y_root - getattr(self, "_drag_offset_y", 0)
        pos_x = f"+{x}" if x >= 0 else f"{x}"
        pos_y = f"+{y}" if y >= 0 else f"{y}"
        self.geometry(f"{pos_x}{pos_y}")

    def grab_set(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def grab_set_global(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def destroy(self):
        if hasattr(self, "_topmost_after_id") and self._topmost_after_id:
            try:
                self.after_cancel(self._topmost_after_id)
            except Exception:
                pass
            self._topmost_after_id = None
        if hasattr(self, "_modal_title_photo") and self._modal_title_photo:
            _detach_photo_tk(self._modal_title_photo)
            self._modal_title_photo = None
        if hasattr(self, "_modal_icon_photo") and self._modal_icon_photo:
            _detach_photo_tk(self._modal_icon_photo)
            self._modal_icon_photo = None
        try:
            self.grab_release()
        except Exception:
            pass
        super().destroy()

    def _on_ok(self):
        self.result = True
        self.destroy()
        if self.on_confirm:
            try:
                self.on_confirm()
            except Exception:
                pass

    def _on_close(self):
        self.result = False
        self.destroy()
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass

