"""
Tkinter widget and image reference decoupling and event queue drainage helpers.
"""
import sys
import gc
import weakref
import threading
import queue
import tkinter as tk
from tkinter import ttk
from typing import Any, Tuple, Callable

def _detach_photo_tk(photo: Any) -> None:
    """Detaches the underlying Tcl interpreter reference from a PhotoImage/Variable/Style so GC on any thread is safe."""
    if photo is None:
        return
    try:
        if hasattr(photo, "name"):
            photo.name = None
        if hasattr(photo, "tk"):
            photo.tk = None
        if hasattr(photo, "_tk"):
            photo._tk = None
        if hasattr(photo, "master"):
            photo.master = None
        inner = getattr(photo, "_PhotoImage__photo", None)
        if inner is not None:
            if hasattr(inner, "name"):
                inner.name = None
            if hasattr(inner, "tk"):
                inner.tk = None
            if hasattr(inner, "_tk"):
                inner._tk = None
    except Exception:
        pass


def _detach_widget_tk_refs(obj: Any) -> None:
    """Breaks parent-child widget cycles and detaches Tcl interpreter references after widget destruction."""
    if obj is None:
        return
    try:
        d = getattr(obj, "__dict__", None)
        if d:
            for v in list(d.values()):
                if v is None:
                    continue
                if isinstance(v, (tk.Variable, tk.Image, ttk.Style)) or hasattr(v, "_PhotoImage__photo"):
                    _detach_photo_tk(v)
        if hasattr(obj, "master"):
            obj.master = None
        if hasattr(obj, "tk"):
            obj.tk = None
        if hasattr(obj, "_tk"):
            obj._tk = None
    except Exception:
        pass


_BG_TK_CALLBACK_QUEUE: "queue.Queue[Tuple[Any, Callable, Tuple]]" = queue.Queue()


def _drain_bg_tk_callbacks() -> None:
    """Drains any widget.after() callbacks queued from background threads on the Tkinter main thread."""
    if threading.current_thread() is not threading.main_thread():
        return
    while not _BG_TK_CALLBACK_QUEUE.empty():
        try:
            w_ref, func, args = _BG_TK_CALLBACK_QUEUE.get_nowait()
        except Exception:
            break
        try:
            w = w_ref() if callable(w_ref) else w_ref
            if w is not None and getattr(w, "tk", None) is not None and not getattr(w, "_closing", False):
                func(*args)
        except Exception:
            pass


if not getattr(tk.Misc, "_sd_safe_destroy_patched", False):
    _orig_winfo_exists = tk.Misc.winfo_exists
    _orig_update = tk.Misc.update
    _orig_update_idletasks = tk.Misc.update_idletasks
    _orig_after = tk.Misc.after
    _orig_after_cancel = tk.Misc.after_cancel
    _orig_grab_release = tk.Misc.grab_release
    _orig_grab_current = tk.Misc.grab_current
    _orig_basewidget_destroy = tk.BaseWidget.destroy
    _orig_tk_destroy = tk.Tk.destroy

    def _safe_winfo_exists(self):
        if getattr(self, "tk", None) is None or getattr(self, "_closing", False):
            return 0
        if threading.current_thread() is not threading.main_thread():
            return 1
        try:
            return _orig_winfo_exists(self)
        except Exception:
            return 0

    def _safe_update(self):
        if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
            return
        _drain_bg_tk_callbacks()
        return _orig_update(self)

    def _safe_update_idletasks(self):
        if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
            return
        _drain_bg_tk_callbacks()
        return _orig_update_idletasks(self)

    def _safe_after(self, ms, func=None, *args):
        if getattr(self, "tk", None) is None or getattr(self, "_closing", False):
            return None
        if threading.current_thread() is not threading.main_thread():
            if func is not None:
                try:
                    w_ref = weakref.ref(self)
                except Exception:
                    w_ref = lambda: None
                _BG_TK_CALLBACK_QUEUE.put((w_ref, func, args))
            return "bg_queued"
        return _orig_after(self, ms, func, *args)

    def _safe_after_cancel(self, id):
        if (
            getattr(self, "tk", None) is None
            or not id
            or id == "bg_queued"
            or threading.current_thread() is not threading.main_thread()
        ):
            return
        try:
            return _orig_after_cancel(self, id)
        except Exception:
            return

    def _safe_grab_release(self):
        if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
            return
        try:
            return _orig_grab_release(self)
        except Exception:
            return

    def _safe_grab_current(self):
        if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
            return None
        try:
            return _orig_grab_current(self)
        except Exception:
            return None

    def _safe_basewidget_destroy(self):
        self._closing = True
        if getattr(self, "tk", None) is None:
            _detach_widget_tk_refs(self)
            return
        try:
            _orig_basewidget_destroy(self)
        finally:
            _detach_widget_tk_refs(self)

    def _safe_tk_destroy(self):
        self._closing = True
        while not _BG_TK_CALLBACK_QUEUE.empty():
            try:
                _BG_TK_CALLBACK_QUEUE.get_nowait()
            except Exception:
                break
        if getattr(self, "tk", None) is None:
            _detach_widget_tk_refs(self)
            return
        try:
            _orig_tk_destroy(self)
        finally:
            _detach_widget_tk_refs(self)

    tk.Misc.winfo_exists = _safe_winfo_exists
    tk.Misc.update = _safe_update
    tk.Misc.update_idletasks = _safe_update_idletasks
    tk.Misc.after = _safe_after
    tk.Misc.after_cancel = _safe_after_cancel
    tk.Misc.grab_release = _safe_grab_release
    tk.Misc.grab_current = _safe_grab_current
    tk.BaseWidget.destroy = _safe_basewidget_destroy
    tk.Tk.destroy = _safe_tk_destroy
    tk.Misc._sd_safe_destroy_patched = True



