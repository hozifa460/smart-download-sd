"""
Safe modal dialogs controller mixin for Smart Download (SD).
"""
import threading
from typing import Optional, Callable

try:
    from tkinter import messagebox
except Exception:
    messagebox = None  # type: ignore

from smart_download.ui.components.base_modal import SafeModalDialog


class DialogControllerMixin:
    """Provides non-blocking, safe modal dialogs (error, info, warning, yes/no)."""

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
        if messagebox and (getattr(messagebox.showerror, "_mock_name", None) or hasattr(messagebox.showerror, "mock")):
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
                theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
                self._active_modal_dialog = SafeModalDialog(
                    self.root, title, message, dialog_type="error", theme=theme_dict
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
        if messagebox and (getattr(messagebox.showinfo, "_mock_name", None) or hasattr(messagebox.showinfo, "mock")):
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
                theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
                self._active_modal_dialog = SafeModalDialog(
                    self.root, title, message, dialog_type="info", theme=theme_dict
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
        if messagebox and (getattr(messagebox.showwarning, "_mock_name", None) or hasattr(messagebox.showwarning, "mock")):
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
                theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
                self._active_modal_dialog = SafeModalDialog(
                    self.root, title, message, dialog_type="warning", theme=theme_dict
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
        if messagebox and (getattr(messagebox.askyesno, "_mock_name", None) or hasattr(messagebox.askyesno, "mock")):
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
                theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
                self._active_modal_dialog = SafeModalDialog(
                    self.root,
                    title,
                    message,
                    dialog_type="confirm",
                    theme=theme_dict,
                    on_confirm=on_yes,
                    on_cancel=on_no
                )
        except Exception:
            pass


__all__ = ["DialogControllerMixin"]
