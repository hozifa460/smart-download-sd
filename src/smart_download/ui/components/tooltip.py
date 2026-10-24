"""
ToolTip: Lightweight hovered tooltip bubble for widgets.
"""
import tkinter as tk
from typing import Optional, Union, Callable

from ...locales.i18n import tr

class ToolTip:
    """
    Lightweight, high-DPI aware, floating tooltip for Tkinter widgets.
    Dynamically resolves localized text via callable or translation key.
    """
    def __init__(self, widget: tk.Widget, text_or_key: Union[str, Callable[[], str]]):
        self.widget = widget
        self.text_or_key = text_or_key
        self.tip_window: Optional[tk.Toplevel] = None
        self._show_job = None
        try:
            self.widget.bind("<Enter>", self._on_enter, add="+")
            self.widget.bind("<Leave>", self._on_leave, add="+")
            self.widget.bind("<ButtonPress>", self._on_leave, add="+")
            self.widget.bind("<Destroy>", self._on_destroy, add="+")
        except Exception:
            pass

    def _get_text(self) -> str:
        if callable(self.text_or_key):
            try:
                return str(self.text_or_key())
            except Exception:
                return ""
        return tr(self.text_or_key, self.text_or_key)

    def _on_enter(self, event=None):
        self._schedule()

    def _on_leave(self, event=None):
        self._unschedule()
        self._hide()

    def _on_destroy(self, event=None):
        self._unschedule()
        self._hide()

    def _schedule(self):
        self._unschedule()
        if hasattr(self.widget, "after"):
            try:
                self._show_job = self.widget.after(500, self._show)
            except Exception:
                pass

    def _unschedule(self):
        if self._show_job and hasattr(self.widget, "after_cancel"):
            try:
                self.widget.after_cancel(self._show_job)
            except Exception:
                pass
            self._show_job = None

    def _show(self):
        text = self._get_text()
        if not text:
            return
        try:
            if not self.widget.winfo_exists() or not self.widget.winfo_viewable():
                return
            if self.tip_window:
                return
            x = self.widget.winfo_rootx() + (self.widget.winfo_width() // 2)
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            tw.attributes("-topmost", True)
            label = tk.Label(
                tw,
                text=text,
                justify=tk.LEFT,
                background="#1e293b",
                foreground="#f8fafc",
                relief=tk.SOLID,
                borderwidth=1,
                font=("Segoe UI", 8),
                padx=6,
                pady=3
            )
            label.pack(ipadx=1)
        except Exception:
            self._hide()

    def _hide(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            try:
                tw.destroy()
            except Exception:
                pass

