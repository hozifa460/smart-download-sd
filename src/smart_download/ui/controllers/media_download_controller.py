"""
MediaDownloadControllerMixin: Handles YouTube/media format extraction, candidate modals, batch queueing, and link refresh.
"""
from .youtube_download_controller import YouTubeDownloadControllerMixin
from .batch_download_controller import BatchDownloadControllerMixin
from .link_refresh_controller import LinkRefreshControllerMixin


class MediaDownloadControllerMixin(
    YouTubeDownloadControllerMixin,
    BatchDownloadControllerMixin,
    LinkRefreshControllerMixin
):
    """Composite mixin providing YouTube format analysis, batch candidate dialogs, and link refresh."""
    pass


__all__ = [
    "MediaDownloadControllerMixin",
    "YouTubeDownloadControllerMixin",
    "BatchDownloadControllerMixin",
    "LinkRefreshControllerMixin",
]
