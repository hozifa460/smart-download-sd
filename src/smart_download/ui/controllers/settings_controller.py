"""
User settings, preferences, and cookies controller mixin for Smart Download (SD).
"""
import os
from typing import Dict, Any

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    tk = None  # type: ignore
    filedialog = None  # type: ignore

from smart_download.i18n import tr
from smart_download.config import get_setting, set_setting, get_base_downloads_dir
from smart_download.utils import resolve_categorized_path
from smart_download.services import is_startup_enabled, enable_startup, disable_startup

from .locale_controller import LocaleControllerMixin
from .speed_limiter_controller import SpeedLimiterControllerMixin


class SettingsControllerMixin(LocaleControllerMixin, SpeedLimiterControllerMixin):
    """Provides methods for managing app preferences, cookies, startup registry, and categorization."""

    def toggle_auto_categorize(self):
        """Toggles automatic categorization into subfolders (Videos, Music, etc.)."""
        self.auto_categorize_folders = not getattr(self, "auto_categorize_folders", True)
        set_setting("auto_categorize_folders", self.auto_categorize_folders)
        self._update_auto_cat_btn()
        if not (self.engine and getattr(self.engine, "is_running", False)):
            cur_dest = self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ""
            if cur_dest:
                fn = os.path.basename(cur_dest)
                downloads_dir = self._get_base_downloads_dir() if hasattr(self, "_get_base_downloads_dir") else get_base_downloads_dir()
                dest_dir = os.path.dirname(cur_dest)
                if hasattr(self, "_is_downloads_or_category_subfolder") and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                    new_dest = resolve_categorized_path(downloads_dir, fn, auto_categorize=self.auto_categorize_folders)
                    self.entry_dest.delete(0, tk.END)
                    self.entry_dest.insert(0, new_dest)

    def _update_sniffer_btn(self):
        """Refreshes the visual state of the clipboard sniffer button."""
        btn = getattr(self, "btn_clipboard_sniffer", None) or getattr(self, "btn_sniffer", None)
        if not btn:
            return
        try:
            if not btn.winfo_exists():
                return
        except Exception:
            return
        if getattr(self, "_clipboard_sniffer_active", True):
            btn.configure(
                text=tr("btn_sniffer_active"),
                fg=self.c_success,
                bg="#0f292a",
                highlightbackground="#10b981",
                highlightthickness=1,
            )
        else:
            btn.configure(
                text=tr("btn_sniffer_paused"),
                fg=self.c_text_muted,
                bg="#182234",
                highlightbackground=self.c_border,
                highlightthickness=1,
            )

    def _update_auto_cat_btn(self):
        if not hasattr(self, "btn_auto_cat") or not self.btn_auto_cat.winfo_exists():
            return
        if getattr(self, "auto_categorize_folders", True):
            self.btn_auto_cat.configure(
                text=tr("btn_auto_cat_on"),
                fg=self.c_success,
                bg="#0f292a",
                highlightbackground="#10b981",
                highlightthickness=1,
            )
        else:
            self.btn_auto_cat.configure(
                text=tr("btn_auto_cat_off"),
                fg=self.c_text_muted,
                bg="#182234",
                highlightbackground=self.c_border,
                highlightthickness=1,
            )

    def _update_startup_btn(self):
        """Refreshes the visual state of the Windows auto-start button."""
        if hasattr(self, "btn_startup"):
            try:
                if not self.btn_startup.winfo_exists():
                    return
            except Exception:
                return
            if get_setting("startup_enabled", None) is True and not is_startup_enabled():
                try:
                    enable_startup(minimized=True)
                except Exception:
                    pass
            enabled = is_startup_enabled()
            self._startup_enabled = enabled
            if enabled:
                self.btn_startup.configure(
                    text=tr("btn_startup_on"),
                    fg=self.c_success,
                    bg="#0f292a",
                    highlightbackground="#10b981",
                    highlightthickness=1,
                )
            else:
                self.btn_startup.configure(
                    text=tr("btn_startup_off"),
                    fg=self.c_text_muted,
                    bg="#182234",
                    highlightbackground=self.c_border,
                    highlightthickness=1,
                )

    def _get_cookies_btn_text(self) -> str:
        """Returns the display label for the cookies setting button."""
        if getattr(self, "cookies_file", "") and os.path.isfile(self.cookies_file):
            display_val = "File"
        else:
            cb = (getattr(self, "cookies_browser", "auto") or "auto").lower()
            if cb in ("none", "off"):
                display_val = tr("lbl_cookies_off", "معطل")
            else:
                display_names = {
                    "auto": "Auto",
                    "edge": "Edge",
                    "chrome": "Chrome",
                    "firefox": "Firefox",
                    "brave": "Brave",
                    "opera": "Opera",
                    "vivaldi": "Vivaldi",
                }
                display_val = display_names.get(cb, cb.capitalize())
        prefix = tr("btn_cookies_prefix", "🍪 الكوكيز:").strip()
        return f"{prefix} {display_val}"

    def _update_cookies_btn(self):
        """Refreshes the visual text and theme colors of the cookies button."""
        if not hasattr(self, "btn_cookies"):
            return
        try:
            if not self.btn_cookies.winfo_exists():
                return
        except Exception:
            return

        btn_text = self._get_cookies_btn_text()
        cb = (getattr(self, "cookies_browser", "auto") or "auto").lower()
        has_cookies = not (cb in ("none", "off") and not (getattr(self, "cookies_file", "") and os.path.isfile(self.cookies_file)))

        if has_cookies:
            self.btn_cookies.configure(
                text=btn_text,
                bg="#172554",
                fg=self.c_accent,
                highlightbackground=self.c_accent_dark,
                highlightthickness=1,
            )
        else:
            self.btn_cookies.configure(
                text=btn_text,
                bg="#182234",
                fg=self.c_text_muted,
                highlightbackground=self.c_border,
                highlightthickness=1,
            )

    def cycle_cookies_setting(self):
        """
        Cycles through cookie options:
        ('auto', 'edge', 'chrome', 'firefox', 'brave', 'file...', 'none')
        Saves chosen setting to app configuration.
        """
        cycle_options = ["auto", "edge", "chrome", "firefox", "brave", "file...", "none"]
        current = "file..." if (getattr(self, "cookies_file", "") and os.path.isfile(self.cookies_file)) else (getattr(self, "cookies_browser", "auto") or "auto").lower()
        try:
            cur_idx = cycle_options.index(current)
        except ValueError:
            cur_idx = 0

        next_idx = (cur_idx + 1) % len(cycle_options)
        next_val = cycle_options[next_idx]

        if next_val == "file...":
            chosen = filedialog.askopenfilename(
                parent=self.root,
                title="Select Netscape cookies.txt file",
                filetypes=[("Text / Cookie files", "*.txt;*.cookies"), ("All files", "*.*")]
            ) if filedialog else ""
            if chosen and os.path.isfile(chosen):
                self.cookies_file = chosen
                self.cookies_browser = "file"
                set_setting("cookies_file", self.cookies_file)
                set_setting("cookies_browser", "file")
                if hasattr(self, "log") and callable(self.log):
                    self.log(f"[COOKIES] Loaded cookie file: {chosen}")
            else:
                # Cancelled file dialog -> skip to 'none'
                self.cookies_file = ""
                self.cookies_browser = "none"
                set_setting("cookies_file", "")
                set_setting("cookies_browser", "none")
                if hasattr(self, "log") and callable(self.log):
                    self.log("[COOKIES] Browser cookies disabled.")
        else:
            self.cookies_file = ""
            self.cookies_browser = next_val
            set_setting("cookies_file", "")
            set_setting("cookies_browser", next_val)
            if next_val == "none":
                if hasattr(self, "log") and callable(self.log):
                    self.log("[COOKIES] Browser cookies disabled.")
            else:
                if hasattr(self, "log") and callable(self.log):
                    self.log(f"[COOKIES] Cookie browser set to: {next_val.capitalize()}")

        self._update_cookies_btn()

    def toggle_startup_setting(self) -> bool:
        """Toggles Windows startup on boot registry entry with live feedback."""
        current = is_startup_enabled()
        if current:
            success = disable_startup()
            if success:
                self._startup_enabled = False
                try:
                    set_setting("startup_enabled", False)
                except Exception:
                    pass
                if hasattr(self, "log") and callable(self.log):
                    self.log("[STARTUP] Windows Run on Boot: Disabled.")
            else:
                if hasattr(self, "log") and callable(self.log):
                    self.log("[STARTUP ERROR] Failed to disable Windows Run on Boot.")
        else:
            success = enable_startup(minimized=True)
            if success:
                self._startup_enabled = True
                try:
                    set_setting("startup_enabled", True)
                except Exception:
                    pass
                if hasattr(self, "log") and callable(self.log):
                    self.log("[STARTUP] Windows Run on Boot: Enabled (Silent background mode).")
            else:
                if hasattr(self, "log") and callable(self.log):
                    self.log("[STARTUP ERROR] Failed to enable Windows Run on Boot.")

        self._update_startup_btn()
        if hasattr(self, "_update_dlg_startup_ui") and callable(self._update_dlg_startup_ui):
            try:
                self._update_dlg_startup_ui()
            except Exception:
                pass
        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.update_menu()
            except Exception:
                pass
        return self._startup_enabled

    def toggle_minimize_to_tray_setting(self) -> bool:
        """Toggles the 'minimize to tray on close' preference and persists to settings."""
        self.minimize_to_tray = not getattr(self, "minimize_to_tray", True)
        set_setting("minimize_to_tray", self.minimize_to_tray)
        if self.minimize_to_tray:
            if hasattr(self, "log") and callable(self.log):
                self.log("[SETTINGS] Close button action set to: Minimize to System Tray.")
        else:
            if hasattr(self, "log") and callable(self.log):
                self.log("[SETTINGS] Close button action set to: Exit Completely.")
        if hasattr(self, "_update_dlg_tray_ui") and callable(self._update_dlg_tray_ui):
            try:
                self._update_dlg_tray_ui()
            except Exception:
                pass
        return self.minimize_to_tray

    def set_minimize_to_tray(self, enabled: bool):
        """Explicitly sets and persists the 'minimize to tray on close' preference."""
        self.minimize_to_tray = bool(enabled)
        set_setting("minimize_to_tray", self.minimize_to_tray)
        if hasattr(self, "_update_dlg_tray_ui") and callable(self._update_dlg_tray_ui):
            try:
                self._update_dlg_tray_ui()
            except Exception:
                pass

    def _on_speed_preset_change(self, event=None):
        """Delegates speed preset changes to speed limiter controller if available, treating Unlimited, بدون حد as 0."""
        if hasattr(self, "_on_preset_selected") and callable(self._on_preset_selected):
            return self._on_preset_selected(event)
        var = getattr(self, "speed_preset_var", None) or getattr(self, "limit_preset_var", None)
        if not var:
            return
        val = str(var.get()).strip()
        if val in ("Unlimited", "بدون حد", tr("lbl_unlimited", "Unlimited")):
            self.speed_limit = 0.0
            if hasattr(self, "slider_speed"):
                self.slider_speed.set(0)
            if hasattr(self, "entry_custom_speed") and tk:
                self.entry_custom_speed.delete(0, tk.END)
                self.entry_custom_speed.insert(0, "0")
            if hasattr(self, "_apply_speed_limit") and callable(self._apply_speed_limit):
                self._apply_speed_limit()


__all__ = ["SettingsControllerMixin", "LocaleControllerMixin", "SpeedLimiterControllerMixin"]
