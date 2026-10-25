"""
Toast notifications controller mixin for Smart Download (SD).
"""
import os
from typing import Optional, Callable

try:
    import tkinter as tk
except Exception:
    tk = None  # type: ignore

from smart_download.i18n import tr
from smart_download.config import get_setting
from smart_download.ui.modals.toasts import StartupWelcomeToast, FetchingLinkToast


class ToastControllerMixin:
    """Handles background startup welcome toasts, fetching toasts, and system notification toasts."""

    def _show_background_startup_notification(self):
        """Displays Windows startup welcome toast when running in background on boot."""
        if getattr(self, "_closing", False):
            return
        if not getattr(self, "_start_hidden", False) and not getattr(self, "_was_started_hidden", False):
            return
        if os.environ.get("SD_DISABLE_STARTUP_TOAST") == "1":
            return
        if not get_setting("show_startup_toast", True):
            return

        try:
            self._dismiss_bg_toast()
            theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
            self._bg_toast = StartupWelcomeToast(
                self.root,
                parent_app=self,
                theme=theme_dict,
                duration_ms=4000
            )
        except Exception:
            pass

    def _show_background_toast(self, message: str):
        """Displays a brief, non-intrusive dark-themed toast notification at the bottom-right corner."""
        try:
            self._dismiss_bg_toast()

            c_border = getattr(self, "c_border", "#475569")
            c_panel = getattr(self, "c_panel", "#1e293b")
            c_accent = getattr(self, "c_accent", "#38bdf8")
            c_text_bright = getattr(self, "c_text_bright", "#f8fafc")
            c_text_muted = getattr(self, "c_text_muted", "#94a3b8")

            toast = tk.Toplevel(self.root)
            self._bg_toast = toast
            toast.overrideredirect(True)
            toast.configure(bg=c_border)
            try:
                toast.attributes("-topmost", True)
            except Exception:
                pass

            try:
                dpi = float(self.root.winfo_fpixels('1i')) if self.root.winfo_exists() else 96.0
            except Exception:
                dpi = 96.0
            scale = max(1.0, dpi / 96.0)

            w = int(370 * scale)
            h = int(76 * scale)
            sw = toast.winfo_screenwidth()
            sh = toast.winfo_screenheight()
            x = max(0, sw - w - int(24 * scale))
            y = max(0, sh - h - int(48 * scale))
            toast.geometry(f"{w}x{h}+{x}+{y}")

            inner = tk.Frame(toast, bg=c_panel, padx=12, pady=10)
            inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

            lbl_ico = tk.Label(inner, text="🚀", font=("Segoe UI", 16), bg=c_panel, fg=c_accent)
            lbl_ico.pack(side=tk.LEFT, padx=(0, 10))

            text_frame = tk.Frame(inner, bg=c_panel)
            text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            lbl_t = tk.Label(text_frame, text="Smart Download (SD)", font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_accent, anchor="w")
            lbl_t.pack(anchor="w")

            lbl_m = tk.Label(text_frame, text=message, font=("Segoe UI", 8), bg=c_panel, fg=c_text_bright, anchor="w")
            lbl_m.pack(anchor="w")

            btn_close = tk.Label(inner, text="✕", font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_muted, cursor="hand2")
            btn_close.pack(side=tk.RIGHT, padx=(4, 0))
            btn_close.bind("<Button-1>", lambda e: self._dismiss_bg_toast())

            # Auto-dismiss after 3200ms
            toast._dismiss_job = toast.after(3200, self._dismiss_bg_toast)
        except Exception:
            pass

    def _dismiss_bg_toast(self):
        """Safely dismisses the background notification toast."""
        if hasattr(self, "_bg_toast") and self._bg_toast:
            try:
                if hasattr(self._bg_toast, "_close"):
                    self._bg_toast._close()
                elif hasattr(self._bg_toast, "_dismiss_job") and self._bg_toast._dismiss_job:
                    try:
                        self._bg_toast.after_cancel(self._bg_toast._dismiss_job)
                    except Exception:
                        pass
                    self._bg_toast._dismiss_job = None
                if self._bg_toast and hasattr(self._bg_toast, "winfo_exists") and self._bg_toast.winfo_exists():
                    self._bg_toast.destroy()
            except Exception:
                pass
            self._bg_toast = None

    def _show_fetching_toast(self, url: str, on_cancel: Optional[Callable[[], None]] = None) -> Optional[FetchingLinkToast]:
        """Displays instantaneous (< 50ms) sleek dark-themed fetching indicator toast."""
        self._close_fetching_toast()
        try:
            def _handle_cancel():
                if hasattr(self, "log") and callable(self.log):
                    self.log(f"[FETCHING] Link analysis cancelled by user for: {url}")
                if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
                    self._yt_cancel_event.set()
                if callable(on_cancel):
                    try:
                        on_cancel()
                    except Exception:
                        pass
                self._fetching_toast = None
                if hasattr(self, "clear_last_clipboard_url") and callable(self.clear_last_clipboard_url):
                    self.clear_last_clipboard_url()
                try:
                    self.btn_start.configure(state="normal")
                    self.btn_pause.configure(state="disabled")
                    self.btn_cancel.configure(state="disabled")
                    self.card_size.configure(text=tr("status_ready", "Ready"))
                except Exception:
                    pass

            theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
            self._fetching_toast = FetchingLinkToast(
                parent=self.root,
                url=url,
                theme=theme_dict,
                on_cancel=_handle_cancel,
                parent_app=self
            )
            return self._fetching_toast
        except Exception as e:
            if hasattr(self, "log") and callable(self.log):
                self.log(f"[FETCHING] Failed to display fetching toast: {e}")
            return None

    def _close_fetching_toast(self):
        """Safely closes active fetching indicator toast."""
        if hasattr(self, "_fetching_toast") and self._fetching_toast:
            try:
                self._fetching_toast.close()
            except Exception:
                pass
            self._fetching_toast = None


__all__ = ["ToastControllerMixin"]
