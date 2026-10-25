from .dpi import enable_high_dpi_awareness, get_windows_work_area
from .clipboard import _win32_clipboard_get, get_clipboard_text
from .url_utils import (
    COMMON_DOWNLOAD_EXTENSIONS,
    WEB_SCRIPT_EXTENSIONS,
    is_downloadable_url,
    clean_download_filename,
    derive_download_filename,
    is_potential_html_url,
    parse_filename_from_cd_header,
    parse_speed_limit,
    format_speed,
)
from .file_ops import (
    MagicBytesDetector,
    calculate_file_integrity,
    auto_unpack_archive,
    get_file_category_and_icon,
    CATEGORY_SUBFOLDERS,
    resolve_categorized_path,
    open_downloaded_file,
    open_containing_folder,
)

try:
    from .tk_helpers import _detach_photo_tk, _detach_widget_tk_refs, _drain_bg_tk_callbacks
except Exception:
    def _detach_photo_tk(photo=None):  # type: ignore
        pass
    def _detach_widget_tk_refs(widget=None):  # type: ignore
        pass
    def _drain_bg_tk_callbacks():  # type: ignore
        pass

__all__ = [
    "enable_high_dpi_awareness",
    "get_windows_work_area",
    "_win32_clipboard_get",
    "get_clipboard_text",
    "COMMON_DOWNLOAD_EXTENSIONS",
    "WEB_SCRIPT_EXTENSIONS",
    "is_downloadable_url",
    "clean_download_filename",
    "derive_download_filename",
    "is_potential_html_url",
    "parse_filename_from_cd_header",
    "parse_speed_limit",
    "format_speed",
    "MagicBytesDetector",
    "calculate_file_integrity",
    "auto_unpack_archive",
    "get_file_category_and_icon",
    "CATEGORY_SUBFOLDERS",
    "resolve_categorized_path",
    "open_downloaded_file",
    "open_containing_folder",
    "_detach_photo_tk",
    "_detach_widget_tk_refs",
    "_drain_bg_tk_callbacks",
]
