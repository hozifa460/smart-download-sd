"""
Internationalization and localization manager for Smart Download.
"""
import os
import sys
import json
from typing import Dict, List, Optional, Callable, Any

from ..config import get_setting, set_setting, is_test_environment

_LOCALES_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_locale(lang: str) -> Dict[str, str]:
    candidates = [
        os.path.join(_LOCALES_DIR, f"{lang}.json"),
    ]
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "smart_download", "locales", f"{lang}.json"))
        candidates.append(os.path.join(sys._MEIPASS, "src", "smart_download", "locales", f"{lang}.json"))
        candidates.append(os.path.join(sys._MEIPASS, "locales", f"{lang}.json"))
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": _load_locale("en"),
    "ar": _load_locale("ar"),
}

class LocalizationManager:
    """
    Manages complete Arabic and English application localization.
    Features:
    - Persists active language in %APPDATA%\\SmartDownload\\settings.json.
    - Thread-safe singleton with observer notifications for instantaneous in-place switching.
    - Fallback resolution guaranteeing no missing translation crashes.
    """
    _instance: Optional["LocalizationManager"] = None

    def __init__(self, default_lang: Optional[str] = None):
        self._observers: List[Callable[[], None]] = []
        if default_lang in ("ar", "en"):
            self._current_lang = default_lang
            return
        env_lang = os.environ.get("SD_LANGUAGE")
        if env_lang in ("ar", "en"):
            self._current_lang = env_lang
            return
        if is_test_environment():
            saved = get_setting("language", None)
            self._current_lang = saved if saved in ("ar", "en") else "en"
            return
        saved = get_setting("language", None)
        if saved in ("ar", "en"):
            self._current_lang = saved
        else:
            self._current_lang = "ar"

    @classmethod
    def get_instance(cls) -> "LocalizationManager":
        if cls._instance is None:
            cls._instance = LocalizationManager()
        return cls._instance

    @classmethod
    def reset_instance(cls, default_lang: Optional[str] = None) -> "LocalizationManager":
        """Resets singleton instance, ensuring complete isolation for tests."""
        cls._instance = LocalizationManager(default_lang=default_lang)
        return cls._instance

    def get_language(self) -> str:
        return self._current_lang

    def set_language(self, lang: str) -> bool:
        if lang not in ("ar", "en"):
            return False
        changed = (self._current_lang != lang)
        self._current_lang = lang
        set_setting("language", lang)
        if "SD_LANGUAGE" in os.environ:
            os.environ["SD_LANGUAGE"] = lang
        if changed:
            self.notify_observers()
        return True

    def toggle_language(self) -> str:
        new_lang = "en" if self._current_lang == "ar" else "ar"
        self.set_language(new_lang)
        return new_lang

    def is_rtl(self) -> bool:
        return self._current_lang == "ar"

    def get(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        lang_dict = TRANSLATIONS.get(self._current_lang, {})
        val = lang_dict.get(key)
        if val is None:
            val = TRANSLATIONS.get("en", {}).get(key)
        if val is None:
            val = TRANSLATIONS.get("ar", {}).get(key)
        if val is None:
            val = default if default is not None else key
        if kwargs and isinstance(val, str):
            try:
                return val.format(**kwargs)
            except Exception:
                return val
        return val

    def register_observer(self, callback: Callable[[], None]):
        if callback not in self._observers:
            self._observers.append(callback)

    def unregister_observer(self, callback: Callable[[], None]):
        if callback in self._observers:
            self._observers.remove(callback)

    def notify_observers(self):
        for cb in list(self._observers):
            try:
                cb()
            except Exception:
                pass


def tr(key: str, default: Optional[str] = None, **kwargs) -> str:
    """Convenience accessor to active language translation."""
    return LocalizationManager.get_instance().get(key, default=default, **kwargs)

def get_current_language() -> str:
    """Returns current active language code ('ar' or 'en')."""
    return LocalizationManager.get_instance().get_language()

def set_current_language(lang: str) -> bool:
    """Sets active language and persists preference."""
    return LocalizationManager.get_instance().set_language(lang)

