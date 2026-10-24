"""
SystemTrayManager: Windows system tray notification area icon, context menu, and background lifecycle.
"""
import os
import sys
import threading
import weakref
import time
from typing import Optional, Callable, Any
try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import pystray
    from pystray import MenuItem as TrayMenuItem, Menu as TrayMenu
    PYSTRAY_AVAILABLE = True
except Exception:
    pystray = None
    TrayMenuItem = None
    TrayMenu = None
    PYSTRAY_AVAILABLE = False

from ..config import get_resource_path
from ..locales.i18n import tr, LocalizationManager
from ..services.startup_service import is_startup_enabled

class SystemTrayManager:
    """
    Manages the Windows System Tray (Notification Area) icon and right-click context menu.
    Integrates non-blocking background icon loop with Tkinter main thread.
    Features:
    1. Modern application icon (app_icon.ico / app_icon.png) rendered cleanly.
    2. Single-click and double-click restore and elevate main application window.
    3. Right-click context menu:
       - 🖥️ Open Smart Download (SD)
       - 📋 Clipboard Sniffer: Active / Paused
       - 🚀 Start with Windows: ON / OFF
       - ❌ Exit Completely
    4. Non-blocking thread-safe execution communicating with Tkinter main thread.
    5. Clean teardown unregistering tray icon without leaving ghost icons.
    """
    def __init__(self, app: Any):
        try:
            self._app_ref = weakref.ref(app) if app is not None else (lambda: None)
        except TypeError:
            self._app_ref = lambda: app
        self.icon: Optional[Any] = None
        self._running = False
        self._lock = threading.Lock()

    @property
    def app(self) -> Any:
        return self._app_ref()

    @app.setter
    def app(self, value: Any):
        if value is None:
            self._app_ref = lambda: None
        else:
            try:
                self._app_ref = weakref.ref(value)
            except TypeError:
                self._app_ref = lambda: value

    def _get_icon_image(self):
        """Loads application icon image for tray area."""
        ico_path = get_resource_path("app_icon.ico")
        png_path = get_resource_path("app_icon.png")
        if os.path.isfile(png_path):
            try:
                from PIL import Image
                return Image.open(png_path)
            except Exception:
                pass
        if os.path.isfile(ico_path):
            try:
                from PIL import Image
                return Image.open(ico_path)
            except Exception:
                pass
        try:
            from PIL import Image
            return Image.new("RGBA", (32, 32), color=(14, 165, 233, 255))
        except Exception:
            return None

    def _get_sniffer_text(self, item=None) -> str:
        app = self.app
        active = getattr(app, "_clipboard_sniffer_active", True) if app is not None else True
        return tr("tray_sniffer_active") if active else tr("tray_sniffer_paused")

    def _get_startup_text(self, item=None) -> str:
        enabled = is_startup_enabled()
        return tr("tray_startup_on") if enabled else tr("tray_startup_off")

    def _on_menu_open(self, icon=None, item=None):
        app = self.app
        if app is None:
            return
        if hasattr(app, "dispatch_to_main_thread"):
            app.dispatch_to_main_thread(app.restore_window)
        else:
            app.restore_window()

    def _on_menu_toggle_sniffer(self, icon=None, item=None):
        app = self.app
        if app is None:
            return
        if hasattr(app, "dispatch_to_main_thread"):
            app.dispatch_to_main_thread(self._do_toggle_sniffer)
        else:
            self._do_toggle_sniffer()

    def _do_toggle_sniffer(self):
        app = self.app
        if app is not None and hasattr(app, "toggle_clipboard_sniffer"):
            app.toggle_clipboard_sniffer()
        self.update_menu()

    def _on_menu_toggle_startup(self, icon=None, item=None):
        app = self.app
        if app is None:
            return
        if hasattr(app, "dispatch_to_main_thread"):
            app.dispatch_to_main_thread(self._do_toggle_startup)
        else:
            self._do_toggle_startup()

    def _do_toggle_startup(self):
        app = self.app
        if app is not None and hasattr(app, "toggle_startup_setting"):
            app.toggle_startup_setting()
        self.update_menu()

    def _on_menu_exit(self, icon=None, item=None):
        app = self.app
        if app is None:
            return
        if hasattr(app, "dispatch_to_main_thread"):
            app.dispatch_to_main_thread(app.exit_completely)
        else:
            app.exit_completely()

    def _build_menu(self):
        if not PYSTRAY_AVAILABLE or TrayMenuItem is None or TrayMenu is None:
            return None
        return TrayMenu(
            TrayMenuItem(tr("tray_open"), self._on_menu_open, default=True),
            TrayMenuItem(self._get_sniffer_text, self._on_menu_toggle_sniffer),
            TrayMenuItem(self._get_startup_text, self._on_menu_toggle_startup),
            TrayMenuItem(tr("tray_exit"), self._on_menu_exit),
        )

    @property
    def is_running(self) -> bool:
        with self._lock:
            return bool(self._running and self.icon is not None)

    def start(self):
        """Starts the tray icon in a background worker thread."""
        if not PYSTRAY_AVAILABLE or pystray is None:
            return
        if os.environ.get("SD_DISABLE_SYSTEM_TRAY") == "1":
            with self._lock:
                self._running = True
            return
        with self._lock:
            if self._running and self.icon is not None:
                return
            img = self._get_icon_image()
            if img is None:
                return
            menu = self._build_menu()
            try:
                self.icon = pystray.Icon("SmartDownload", img, "Smart Download (SD)", menu=menu)
                # Patch notify to catch both WM_LBUTTONUP (0x0202) and WM_LBUTTONDBLCLK (0x0203)
                orig_notify = getattr(self.icon, "_on_notify", None)
                if orig_notify:
                    def _patched_notify(wparam, lparam):
                        if lparam in (0x0202, 0x0203):
                            try:
                                if self.icon is not None:
                                    self.icon()
                            except Exception:
                                pass
                            return
                        return orig_notify(wparam, lparam)
                    self.icon._on_notify = _patched_notify
                # Run in a daemon thread so it never blocks Python process termination
                tray_thread = threading.Thread(target=self.icon.run, daemon=True, name='SmartDownloadTrayThread')
                self._thread = tray_thread
                tray_thread.start()
                self._running = True
            except Exception:
                self._running = False
                self.icon = None

    def stop(self):
        """Stops the tray icon and removes it from the Windows notification area."""
        with self._lock:
            self._running = False
            self.app = None
            if self.icon is not None:
                try:
                    q = getattr(self.icon, "_Icon__queue", None)
                    if q is not None and q.empty():
                        try:
                            q.put_nowait(True)
                        except Exception:
                            pass
                    self.icon.stop()
                except Exception:
                    pass
                self.icon = None
            if hasattr(self, "_thread") and self._thread and self._thread != threading.current_thread():
                try:
                    self._thread.join(timeout=0.5)
                except Exception:
                    pass
                self._thread = None

    def update_menu(self):
        """Refreshes dynamic labels in context menu."""
        with self._lock:
            if self.icon is not None:
                try:
                    self.icon.menu = self._build_menu()
                    if getattr(self.icon, "visible", False):
                        self.icon.update_menu()
                except Exception:
                    pass

    def notify(self, message: str, title: str = "Smart Download (SD)"):
        """Displays Windows system tray notification balloon if supported."""
        with self._lock:
            if self.icon is not None and getattr(self.icon, "visible", False):
                try:
                    self.icon.notify(message, title)
                except Exception:
                    pass
            elif self.icon is not None:
                def _delayed_notify():
                    time.sleep(0.5)
                    with self._lock:
                        if self.icon is not None and getattr(self.icon, "visible", False):
                            try:
                                self.icon.notify(message, title)
                            except Exception:
                                pass
                threading.Thread(target=_delayed_notify, daemon=True, name="DelayedTrayNotify").start()

