from .dpi import enable_high_dpi_awareness, get_windows_work_area
from .clipboard import _win32_clipboard_get, get_clipboard_text
from .speed_utils import parse_speed_limit, format_speed
from .url_utils import (
    COMMON_DOWNLOAD_EXTENSIONS,
    WEB_SCRIPT_EXTENSIONS,
    is_downloadable_url,
    clean_download_filename,
    derive_download_filename,
    is_potential_html_url,
    parse_filename_from_cd_header,
)
from .magic_detector import MagicBytesDetector
from .archive_utils import calculate_file_integrity, auto_unpack_archive
from .file_ops import (
    get_file_category_and_icon,
    CATEGORY_SUBFOLDERS,
    resolve_categorized_path,
    open_downloaded_file,
    open_containing_folder,
    generate_unique_destination_path,
    apply_media_filename_tags,
    get_base_downloads_dir,
)

_TK_HELPER_NAMES = {
    "_detach_photo_tk",
    "_detach_widget_tk_refs",
    "_drain_bg_tk_callbacks",
    "animate_window_open",
    "animate_window_close",
}


def __getattr__(name: str):
    if name in _TK_HELPER_NAMES:
        try:
            from . import tk_helpers
            val = getattr(tk_helpers, name)
            globals()[name] = val
            return val
        except Exception:
            def _dummy(*args, **kwargs):
                if name == "animate_window_close":
                    on_done = kwargs.get("on_done") or (args[1] if len(args) > 1 else None)
                    if on_done:
                        on_done()
            globals()[name] = _dummy
            return _dummy
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


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
    "generate_unique_destination_path",
    "apply_media_filename_tags",
    "get_base_downloads_dir",
    "_detach_photo_tk",
    "_detach_widget_tk_refs",
    "_drain_bg_tk_callbacks",
]
