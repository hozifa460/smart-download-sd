"""
Windows High-DPI awareness and work area metrics utilities.
"""
import sys
import ctypes
from typing import Tuple, Optional

from ..config import IS_WINDOWS

def enable_high_dpi_awareness():
    """
    Configures Windows High-DPI awareness so Desktop Window Manager (DWM)
    renders vector typography and widgets crisply at native screen resolution
    without blurry bitmap scaling on 125%, 150%, 200% displays.
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes
            # Explicit AppUserModelID ensures Windows taskbar associates the app with its high-res icon
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SmartDownload.SD.App")
            except Exception:
                pass
            # 1. Windows 10 Creators Update (1703+) Per-Monitor V2
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
            try:
                res = ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
                if res:
                    return
            except Exception:
                pass
            # 2. Windows 8.1+ Per-Monitor DPI Aware (PROCESS_PER_MONITOR_DPI_AWARE = 2)
            try:
                hr = ctypes.windll.shcore.SetProcessDpiAwareness(2)
                if hr == 0:
                    return
            except Exception:
                pass
            # 3. Windows Vista+ System DPI Aware
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        except Exception:
            pass


def get_windows_work_area() -> Optional[Tuple[int, int, int, int]]:
    """Returns (left, top, right, bottom) coordinates of the Windows work area (excluding taskbars)."""
    if sys.platform != "win32":
        return None
    try:
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long)
            ]
        rect = RECT()
        SPI_GETWORKAREA = 0x0030
        if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    except Exception:
        pass
    return None

