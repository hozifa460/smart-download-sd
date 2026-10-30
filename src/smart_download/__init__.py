"""
Smart Download (SD) — High-Performance Enterprise Modular Download Engine
"""
__version__ = "2.0.2"

from .config import (
    APP_NAME,
    APP_TITLE,
    APP_ID,
    APP_VERSION,
    get_resource_path,
    get_config_dir,
    get_app_config_dir,
    get_settings_file_path,
    load_settings,
    save_settings,
    get_setting,
    set_setting,
    get_base_downloads_dir,
)
from .locales.i18n import LocalizationManager, tr, get_current_language, set_current_language
from .core.engine import TurboDownloadEngine
from .core.chunk import DownloadChunk, get_permissive_ssl_context
def __getattr__(name: str):
    if name in ("ModernFramelessGUI", "main"):
        try:
            import tkinter as tk
            if tk is None:
                raise ImportError("Tkinter not available")
            from .ui.main_window import ModernFramelessGUI as _ModernFramelessGUI, main as _main
            globals()["ModernFramelessGUI"] = _ModernFramelessGUI
            globals()["main"] = _main
            return globals()[name]
        except Exception:
            globals()["ModernFramelessGUI"] = None
            globals()["main"] = None
            return None
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__():
    return sorted(set(globals().keys()) | {"ModernFramelessGUI", "main"})

__all__ = [
    "__version__",
    "APP_NAME",
    "APP_TITLE",
    "APP_ID",
    "APP_VERSION",
    "get_resource_path",
    "get_config_dir",
    "get_app_config_dir",
    "get_settings_file_path",
    "load_settings",
    "save_settings",
    "get_setting",
    "set_setting",
    "get_base_downloads_dir",
    "LocalizationManager",
    "tr",
    "get_current_language",
    "set_current_language",
    "TurboDownloadEngine",
    "DownloadChunk",
    "get_permissive_ssl_context",
    "ModernFramelessGUI",
    "main",
]
