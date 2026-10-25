"""
Thread dispatch and logging controller mixin for Smart Download (SD).
"""
import threading
from typing import Callable

try:
    import tkinter as tk
except Exception:
    tk = None  # type: ignore

from smart_download.utils import _drain_bg_tk_callbacks


class DispatchControllerMixin:
    """Handles thread-safe main-loop event dispatching and text console activity logging."""

    def log(self, message: str):
        """Appends message to activity log console."""
        if getattr(self, "_closing", False):
            return
        job_box = [None]
        def _append():
            try:
                if hasattr(self, "_log_jobs") and job_box[0] in self._log_jobs:
                    self._log_jobs.remove(job_box[0])
                if not getattr(self, "_closing", False) and hasattr(self, "txt_log") and tk:
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


__all__ = ["DispatchControllerMixin"]
