"""
UI controller mixins for Smart Download.
"""
from .clipboard_controller import ClipboardControllerMixin
from .toast_controller import ToastControllerMixin
from .update_controller import UpdateControllerMixin
from .download_controller import DownloadControllerMixin
from .youtube_download_controller import YouTubeDownloadControllerMixin
from .batch_download_controller import BatchDownloadControllerMixin
from .link_refresh_controller import LinkRefreshControllerMixin
from .media_download_controller import MediaDownloadControllerMixin
from .locale_controller import LocaleControllerMixin
from .speed_limiter_controller import SpeedLimiterControllerMixin
from .settings_controller import SettingsControllerMixin
from .dialog_controller import DialogControllerMixin
from .lifecycle_controller import WindowLifecycleMixin
from .theme_controller import ThemeControllerMixin
from .dispatch_controller import DispatchControllerMixin
from .window_controller import WindowChromeMixin, WindowControllerMixin
from .browser_controller import BrowserControllerMixin

__all__ = [
    "ClipboardControllerMixin",
    "ToastControllerMixin",
    "UpdateControllerMixin",
    "DownloadControllerMixin",
    "YouTubeDownloadControllerMixin",
    "BatchDownloadControllerMixin",
    "LinkRefreshControllerMixin",
    "MediaDownloadControllerMixin",
    "LocaleControllerMixin",
    "SpeedLimiterControllerMixin",
    "SettingsControllerMixin",
    "DialogControllerMixin",
    "WindowLifecycleMixin",
    "ThemeControllerMixin",
    "DispatchControllerMixin",
    "WindowChromeMixin",
    "WindowControllerMixin",
    "BrowserControllerMixin",
]
