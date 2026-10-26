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
from typing import Any, Tuple, Callable, Optional

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


_EXISTING_QUEUE = getattr(tk.Misc, "_sd_bg_callback_queue", None)
if _EXISTING_QUEUE is None:
    _EXISTING_QUEUE = queue.Queue()
    setattr(tk.Misc, "_sd_bg_callback_queue", _EXISTING_QUEUE)
_BG_TK_CALLBACK_QUEUE: "queue.Queue[Tuple[Any, Callable, Tuple]]" = _EXISTING_QUEUE


def _drain_bg_tk_callbacks() -> None:
    """Drains any widget.after() or after_idle() callbacks queued from background threads on the Tkinter main thread."""
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


if not hasattr(tk.Misc, "_sd_orig_destroy"):
    tk.Misc._sd_orig_destroy = tk.Misc.destroy
if not hasattr(tk.Misc, "_sd_orig_Toplevel_destroy"):
    tk.Misc._sd_orig_Toplevel_destroy = tk.Toplevel.destroy
if not hasattr(tk.Misc, "_sd_orig_after"):
    tk.Misc._sd_orig_after = tk.Misc.after
if not hasattr(tk.Misc, "_sd_orig_after_idle"):
    tk.Misc._sd_orig_after_idle = tk.Misc.after_idle
if not hasattr(tk.Misc, "_sd_orig_update"):
    tk.Misc._sd_orig_update = tk.Misc.update
if not hasattr(tk.Misc, "_sd_orig_update_idletasks"):
    tk.Misc._sd_orig_update_idletasks = tk.Misc.update_idletasks
if not hasattr(tk.Misc, "_sd_orig_after_cancel"):
    tk.Misc._sd_orig_after_cancel = tk.Misc.after_cancel
if not hasattr(tk.Misc, "_sd_orig_winfo_exists"):
    tk.Misc._sd_orig_winfo_exists = tk.Misc.winfo_exists
if not hasattr(tk.Misc, "_sd_orig_grab_release"):
    tk.Misc._sd_orig_grab_release = tk.Misc.grab_release
if not hasattr(tk.Misc, "_sd_orig_grab_current"):
    tk.Misc._sd_orig_grab_current = tk.Misc.grab_current
if not hasattr(tk.Misc, "_sd_orig_basewidget_destroy"):
    tk.Misc._sd_orig_basewidget_destroy = tk.BaseWidget.destroy
if not hasattr(tk.Misc, "_sd_orig_tk_destroy"):
    tk.Misc._sd_orig_tk_destroy = tk.Tk.destroy

_ORIG_MISC_DESTROY = tk.Misc._sd_orig_destroy
_ORIG_TOPLEVEL_DESTROY = tk.Misc._sd_orig_Toplevel_destroy
_ORIG_MISC_AFTER = tk.Misc._sd_orig_after
_ORIG_MISC_AFTER_IDLE = tk.Misc._sd_orig_after_idle
_ORIG_MISC_UPDATE = tk.Misc._sd_orig_update
_ORIG_MISC_UPDATE_IDLETASKS = tk.Misc._sd_orig_update_idletasks
_ORIG_MISC_AFTER_CANCEL = tk.Misc._sd_orig_after_cancel
_ORIG_MISC_WINFO_EXISTS = tk.Misc._sd_orig_winfo_exists
_ORIG_MISC_GRAB_RELEASE = tk.Misc._sd_orig_grab_release
_ORIG_MISC_GRAB_CURRENT = tk.Misc._sd_orig_grab_current
_ORIG_BASEWIDGET_DESTROY = tk.Misc._sd_orig_basewidget_destroy
_ORIG_TK_DESTROY = tk.Misc._sd_orig_tk_destroy


def _safe_winfo_exists(self):
    if getattr(self, "tk", None) is None or getattr(self, "_closing", False):
        return 0
    if threading.current_thread() is not threading.main_thread():
        return 1
    try:
        return _ORIG_MISC_WINFO_EXISTS(self)
    except Exception:
        return 0


def _safe_misc_update(self):
    if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
        return
    _drain_bg_tk_callbacks()
    return _ORIG_MISC_UPDATE(self)


def _safe_misc_update_idletasks(self):
    if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
        return
    _drain_bg_tk_callbacks()
    return _ORIG_MISC_UPDATE_IDLETASKS(self)


def _safe_misc_after(self, ms, func=None, *args):
    if getattr(self, "tk", None) is None or getattr(self, "_closing", False):
        return None
    if threading.current_thread() is not threading.main_thread():
        if func is not None:
            try:
                w_ref = weakref.ref(self)
            except Exception:
                w_ref = lambda: self
            _BG_TK_CALLBACK_QUEUE.put((w_ref, func, args))
        return "bg_queued"
    return _ORIG_MISC_AFTER(self, ms, func, *args)


def _safe_misc_after_idle(self, func, *args):
    if getattr(self, "tk", None) is None or getattr(self, "_closing", False):
        return None
    if threading.current_thread() is not threading.main_thread():
        if func is not None:
            try:
                w_ref = weakref.ref(self)
            except Exception:
                w_ref = lambda: self
            _BG_TK_CALLBACK_QUEUE.put((w_ref, func, args))
        return "bg_queued_idle"
    return _ORIG_MISC_AFTER_IDLE(self, func, *args)


def _safe_after_cancel(self, id):
    if (
        getattr(self, "tk", None) is None
        or not id
        or id in ("bg_queued", "bg_queued_idle")
        or threading.current_thread() is not threading.main_thread()
    ):
        return
    try:
        return _ORIG_MISC_AFTER_CANCEL(self, id)
    except Exception:
        return


def _safe_grab_release(self):
    if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
        return
    try:
        return _ORIG_MISC_GRAB_RELEASE(self)
    except Exception:
        return


def _safe_grab_current(self):
    if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
        return None
    try:
        return _ORIG_MISC_GRAB_CURRENT(self)
    except Exception:
        return None


def _safe_misc_destroy(self):
    self._closing = True
    if getattr(self, "tk", None) is None:
        _detach_widget_tk_refs(self)
        return
    try:
        _ORIG_MISC_DESTROY(self)
    finally:
        _detach_widget_tk_refs(self)


def _safe_toplevel_destroy(self):
    self._closing = True
    if getattr(self, "tk", None) is None:
        _detach_widget_tk_refs(self)
        return
    try:
        _ORIG_TOPLEVEL_DESTROY(self)
    finally:
        _detach_widget_tk_refs(self)


def _safe_basewidget_destroy(self):
    self._closing = True
    if getattr(self, "tk", None) is None:
        _detach_widget_tk_refs(self)
        return
    try:
        _ORIG_BASEWIDGET_DESTROY(self)
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
        _ORIG_TK_DESTROY(self)
    finally:
        _detach_widget_tk_refs(self)


tk.Misc.winfo_exists = _safe_winfo_exists
tk.Misc.update = _safe_misc_update
tk.Misc.update_idletasks = _safe_misc_update_idletasks
tk.Misc.after = _safe_misc_after
tk.Misc.after_idle = _safe_misc_after_idle
tk.Misc.after_cancel = _safe_after_cancel
tk.Misc.grab_release = _safe_grab_release
tk.Misc.grab_current = _safe_grab_current
tk.Misc.destroy = _safe_misc_destroy
tk.Toplevel.destroy = _safe_toplevel_destroy
tk.BaseWidget.destroy = _safe_basewidget_destroy
tk.Tk.destroy = _safe_tk_destroy
tk.Misc._sd_safe_destroy_patched = True


def animate_window_open(win: Any, duration_ms: int = 140, steps: int = 7) -> None:
    """Immediately sets window alpha to 1.0 and deiconifies cleanly without multi-step alpha flicker."""
    if not win:
        return
    try:
        if hasattr(win, "wm_attributes"):
            try:
                win.wm_attributes("-alpha", 1.0)
            except Exception:
                pass
        elif hasattr(win, "attributes"):
            try:
                win.attributes("-alpha", 1.0)
            except Exception:
                pass
        if hasattr(win, "deiconify"):
            try:
                win.deiconify()
            except Exception:
                pass
    except Exception:
        pass


def animate_window_close(
    win: Any,
    on_done: Optional[Callable[[], None]] = None,
    duration_ms: int = 120,
    steps: int = 6,
    **kwargs: Any
) -> None:
    """Cancels any pending _sd_anim_job on win and immediately executes on_done() (or win.destroy()) without delay."""
    actual_on_done = on_done
    if not callable(actual_on_done):
        if "on_done" in kwargs and callable(kwargs["on_done"]):
            actual_on_done = kwargs["on_done"]
        elif callable(steps):
            actual_on_done = steps

    if win is not None:
        try:
            job = getattr(win, "_sd_anim_job", None)
            if job and hasattr(win, "after_cancel"):
                try:
                    win.after_cancel(job)
                except Exception:
                    pass
                setattr(win, "_sd_anim_job", None)
        except Exception:
            pass

    try:
        if callable(actual_on_done):
            actual_on_done()
        elif win is not None and hasattr(win, "destroy"):
            win.destroy()
    except Exception:
        pass




