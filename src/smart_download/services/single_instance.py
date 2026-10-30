"""
Single instance detection and IPC dispatch to running instance.
"""
import sys
import json
import urllib.request
import urllib.error
from typing import Optional

from .browser.bridge_server import DEFAULT_BRIDGE_PORT
from ..utils.url_utils import is_downloadable_url

_SINGLE_INSTANCE_MUTEX_HANDLE = None


def acquire_single_instance_mutex(mutex_name: str = "Local\\SmartDownload_SingleInstance_Mutex") -> bool:
    """
    Attempts to acquire a Win32 Named Mutex to guarantee that only one instance of the
    application starts up. If another process already holds the mutex, returns False.
    Returns True if successfully acquired or if not on Windows.
    Stores the mutex handle globally to prevent garbage collection until process exit.
    """
    global _SINGLE_INSTANCE_MUTEX_HANDLE
    if not sys.platform.startswith("win"):
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, mutex_name)
        if not handle:
            return True
        last_error = kernel32.GetLastError()
        ERROR_ALREADY_EXISTS = 183
        if last_error == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        _SINGLE_INSTANCE_MUTEX_HANDLE = handle
        return True
    except Exception:
        return True


def release_single_instance_mutex() -> None:
    """Releases the Win32 Named Mutex handle if currently held."""
    global _SINGLE_INSTANCE_MUTEX_HANDLE
    if _SINGLE_INSTANCE_MUTEX_HANDLE:
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(_SINGLE_INSTANCE_MUTEX_HANDLE)
        except Exception:
            pass
        _SINGLE_INSTANCE_MUTEX_HANDLE = None

def notify_running_instance(url: Optional[str] = None, show: bool = True) -> bool:
    """
    Checks if an existing instance of Turbo Downloader is running by probing the
    loopback IPC port. If active, wakes up the existing instance and optionally
    dispatches the download URL. Returns True if an existing instance was handled.
    """
    try:
        req = urllib.request.Request("http://127.0.0.1:9242/ping", headers={"User-Agent": "SmartDownload-Launcher"})
        with urllib.request.urlopen(req, timeout=0.6) as resp:
            if resp.status == 200:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                if data.get("app") in ("Smart Download (SD)", "Smart Download", "Turbo Download Manager Pro"):
                    if url and is_downloadable_url(url):
                        try:
                            post_data = json.dumps({"url": url, "start_immediately": False}).encode("utf-8")
                            post_req = urllib.request.Request(
                                "http://127.0.0.1:9242/download",
                                data=post_data,
                                headers={"Content-Type": "application/json"}
                            )
                            with urllib.request.urlopen(post_req, timeout=1.0) as _:
                                pass
                        except Exception:
                            pass
                    if show:
                        try:
                            show_req = urllib.request.Request(
                                "http://127.0.0.1:9242/show",
                                headers={"User-Agent": "SmartDownload-Launcher"}
                            )
                            with urllib.request.urlopen(show_req, timeout=1.0) as _:
                                pass
                        except Exception:
                            pass
                    return True
    except Exception:
        pass
    return False

