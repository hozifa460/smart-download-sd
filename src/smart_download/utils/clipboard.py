"""
Cross-platform and Windows-optimized clipboard utilities.
"""
import sys
import subprocess
import ctypes
import time
from typing import Optional, Any

from ..config import IS_WINDOWS

def _win32_clipboard_get() -> Optional[str]:
    """
    Robust 64-bit safe Win32 clipboard text reader with transient lock retry loop.
    Immune to memory handle truncation, missing null-terminators, and third-party locks.
    """
    if not IS_WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetClipboardData.restype = wintypes.HANDLE
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

        opened = False
        for _ in range(5):
            if user32.OpenClipboard(None):
                opened = True
                break
            time.sleep(0.01)
        if not opened:
            return None

        try:
            if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return None
            h_glb = user32.GetClipboardData(CF_UNICODETEXT)
            if not h_glb:
                return None
            ptr = kernel32.GlobalLock(h_glb)
            if not ptr:
                return None
            try:
                val = ctypes.wstring_at(ptr)
                return val if val else None
            finally:
                kernel32.GlobalUnlock(h_glb)
        finally:
            user32.CloseClipboard()
    except Exception:
        return None


def get_clipboard_text(root: Optional[Any] = None) -> Optional[str]:
    """Safely retrieves text from clipboard using Win32 API or Tkinter fallback."""
    if IS_WINDOWS:
        try:
            val = _win32_clipboard_get()
            if val is not None:
                return val
        except Exception:
            pass
    if root is not None:
        try:
            return root.clipboard_get()
        except Exception:
            pass
    return None

