"""
Re-export module for localization utilities.
"""
from .locales.i18n import (
    LocalizationManager,
    tr,
    get_current_language,
    set_current_language,
    TRANSLATIONS,
)

__all__ = [
    "LocalizationManager",
    "tr",
    "get_current_language",
    "set_current_language",
    "TRANSLATIONS",
]
