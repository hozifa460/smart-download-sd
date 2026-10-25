"""
User settings, preferences, and language controller mixin for Smart Download (SD).
"""
import os
from typing import Dict, Any

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    tk = None  # type: ignore
    filedialog = None  # type: ignore

from smart_download.i18n import LocalizationManager, tr
from smart_download.config import set_setting
from smart_download.utils import resolve_categorized_path, format_speed
from smart_download.services import is_startup_enabled, enable_startup, disable_startup


class SettingsControllerMixin:
    """Provides methods for managing UI localization, cookies, speed limit presets, and startup registry."""

    def toggle_language(self):
        """Toggles active language between Arabic and English dynamically in-place."""
        new_lang = LocalizationManager.get_instance().toggle_language()
        self._update_ui_language()
        self.log(f"[LOCALE] Switched interface language to: {new_lang.upper()}")

    def _update_ui_language(self):
        """Dynamically re-translates and updates all main UI widgets in-place."""
        cur_lang = LocalizationManager.get_instance().get_language()
        if hasattr(self, "btn_lang_toggle") and self.btn_lang_toggle.winfo_exists():
            self.btn_lang_toggle.configure(text="🌐 English" if cur_lang == "ar" else "🌐 العربية")

        if hasattr(self, "title_lbl") and self.title_lbl.winfo_exists():
            self.title_lbl.configure(text=tr("app_header"))
        if hasattr(self, "subtitle_lbl") and self.subtitle_lbl.winfo_exists():
            self.subtitle_lbl.configure(text=tr("app_subtitle"))
        try:
            self.root.title(tr("app_title"))
        except Exception:
            pass

        # Input card
        if hasattr(self, "lbl_url") and self.lbl_url.winfo_exists():
            self.lbl_url.configure(text=tr("lbl_url"))
        if hasattr(self, "btn_paste") and self.btn_paste.winfo_exists():
            self.btn_paste.configure(text=tr("btn_paste"))
        if hasattr(self, "btn_refresh_url") and self.btn_refresh_url.winfo_exists():
            self.btn_refresh_url.configure(text=tr("btn_refresh_url"))
        if hasattr(self, "lbl_dest") and self.lbl_dest.winfo_exists():
            self.lbl_dest.configure(text=tr("lbl_dest"))
        if hasattr(self, "btn_browse") and self.btn_browse.winfo_exists():
            self.btn_browse.configure(text=tr("btn_browse"))

        # Limiter & options card
        if hasattr(self, "lbl_conn") and self.lbl_conn.winfo_exists():
            self.lbl_conn.configure(text=tr("lbl_threads"))
        if hasattr(self, "lbl_limit") and self.lbl_limit.winfo_exists():
            self.lbl_limit.configure(text=tr("lbl_speed_limiter"))
        if hasattr(self, "lbl_custom") and self.lbl_custom.winfo_exists():
            self.lbl_custom.configure(text=tr("lbl_custom_speed"))
        if hasattr(self, "btn_apply_speed") and self.btn_apply_speed.winfo_exists():
            self.btn_apply_speed.configure(text=tr("btn_apply_limit"))
        if hasattr(self, "lbl_slider_title") and self.lbl_slider_title.winfo_exists():
            self.lbl_slider_title.configure(text=tr("lbl_live_throttle_slider"))

        # Actions card
        if hasattr(self, "btn_start") and self.btn_start.winfo_exists():
            self.btn_start.configure(text=tr("btn_start"))
        if hasattr(self, "btn_pause") and self.btn_pause.winfo_exists():
            if self.engine and getattr(self.engine, "is_paused", False):
                self.btn_pause.configure(text=tr("btn_resume"))
            else:
                self.btn_pause.configure(text=tr("btn_pause"))
        if hasattr(self, "btn_cancel") and self.btn_cancel.winfo_exists():
            self.btn_cancel.configure(text=tr("btn_cancel"))
        if hasattr(self, "btn_refresh_link") and self.btn_refresh_link.winfo_exists():
            self.btn_refresh_link.configure(text=tr("btn_refresh_url"))
        if hasattr(self, "btn_browser") and self.btn_browser.winfo_exists():
            self.btn_browser.configure(text=tr("btn_browser"))
        if hasattr(self, "btn_check_updates") and self.btn_check_updates.winfo_exists():
            self.btn_check_updates.configure(text=tr("btn_check_updates"))

        self._update_sniffer_btn()
        self._update_startup_btn()
        self._update_cookies_btn()
        self._update_auto_cat_btn()

        # Metrics card
        if hasattr(self, "lbl_t_speed") and self.lbl_t_speed.winfo_exists():
            self.lbl_t_speed.configure(text=tr("metric_speed"))
        if hasattr(self, "lbl_t_size") and self.lbl_t_size.winfo_exists():
            self.lbl_t_size.configure(text=tr("metric_total_size"))
        if hasattr(self, "lbl_t_eta") and self.lbl_t_eta.winfo_exists():
            self.lbl_t_eta.configure(text=tr("metric_eta"))
        if hasattr(self, "lbl_t_threads") and self.lbl_t_threads.winfo_exists():
            self.lbl_t_threads.configure(text=tr("metric_threads"))

        # Notebook tabs
        if hasattr(self, "notebook") and self.notebook.winfo_exists():
            try:
                self.notebook.tab(0, text=tr("tab_chunks"))
            except Exception:
                pass
            try:
                self.notebook.tab(1, text=tr("tab_logs"))
            except Exception:
                pass
            try:
                self.notebook.tab(2, text=tr("tab_history"))
            except Exception:
                pass

        # Chunks treeview headings
        if hasattr(self, "tree_chunks") and self.tree_chunks.winfo_exists():
            self.tree_chunks.heading("id", text=tr("col_chunk_id"))
            self.tree_chunks.heading("range", text=tr("col_chunk_range"))
            self.tree_chunks.heading("size", text=tr("col_chunk_size"))
            self.tree_chunks.heading("downloaded", text=tr("col_chunk_downloaded"))
            self.tree_chunks.heading("pct", text=tr("col_chunk_pct"))
            self.tree_chunks.heading("status", text=tr("col_chunk_status"))

        # History toolbar
        if hasattr(self, "lbl_filter") and self.lbl_filter.winfo_exists():
            self.lbl_filter.configure(text=tr("lbl_filter"))
        if hasattr(self, "btn_hist_open") and self.btn_hist_open.winfo_exists():
            self.btn_hist_open.configure(text=tr("btn_hist_open"))
        if hasattr(self, "btn_hist_folder") and self.btn_hist_folder.winfo_exists():
            self.btn_hist_folder.configure(text=tr("btn_hist_folder"))
        if hasattr(self, "btn_hist_redownload") and self.btn_hist_redownload.winfo_exists():
            self.btn_hist_redownload.configure(text=tr("btn_hist_redownload"))
        if hasattr(self, "btn_hist_remove") and self.btn_hist_remove.winfo_exists():
            self.btn_hist_remove.configure(text=tr("btn_hist_remove"))
        if hasattr(self, "btn_hist_clear") and self.btn_hist_clear.winfo_exists():
            self.btn_hist_clear.configure(text=tr("btn_hist_clear"))

        # History treeview headings
        if hasattr(self, "tree_history") and self.tree_history.winfo_exists():
            self.tree_history.heading("category", text=tr("col_hist_category"))
            self.tree_history.heading("filename", text=tr("col_hist_filename"))
            self.tree_history.heading("size", text=tr("col_hist_size"))
            self.tree_history.heading("status", text=tr("col_hist_status"))
            self.tree_history.heading("date", text=tr("col_hist_date"))
            self.tree_history.heading("path", text=tr("col_hist_path"))

        # History filter combo and table refresh
        if hasattr(self, "combo_history_filter") and self.combo_history_filter.winfo_exists():
            categories = [
                tr("cat_all", "All Categories"),
                tr("cat_video", "Video"),
                tr("cat_audio", "Audio"),
                tr("cat_programs", "Programs"),
                tr("cat_compressed", "Compressed"),
                tr("cat_documents", "Documents"),
                tr("cat_images", "Images"),
                tr("cat_general", "General"),
            ]
            self.combo_history_filter.configure(values=categories)
            cur = self.combo_history_filter.get()
            if not cur or cur in ("All Categories", "كافة التصنيفات", "All", "الكل"):
                self.combo_history_filter.set(categories[0])
            self._refresh_history_table()

        if hasattr(self, "lbl_active_limit") and self.lbl_active_limit.winfo_exists():
            cur_limit = getattr(self, "speed_limit", 0.0)
            if cur_limit <= 0:
                self.lbl_active_limit.configure(text=tr("lbl_current_unlimited", "● Current: Unlimited"))
            else:
                self.lbl_active_limit.configure(text=tr("lbl_current_limit", "● Current: {limit}").format(limit=format_speed(cur_limit)))
        if hasattr(self, "lbl_slider_val") and self.lbl_slider_val.winfo_exists():
            cur_val = getattr(self.slider_speed, "get", lambda: 0)() if hasattr(self, "slider_speed") else 0
            if cur_val <= 0:
                self.lbl_slider_val.configure(text=f"{tr('lbl_unlimited', 'Unlimited')} (0 KB/s)")
            else:
                self.lbl_slider_val.configure(text=f"{cur_val:,} KB/s ({cur_val/1024:.1f} MB/s)")

        # Tray menu
        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.update_menu()
            except Exception:
                pass

    def _theme_dict(self) -> Dict[str, str]:
        """Returns active theme dictionary for modals and child widgets."""
        return {
            "c_bg": self.c_bg,
            "c_panel": self.c_panel,
            "c_panel_light": self.c_panel_light,
            "c_border": self.c_border,
            "c_accent": self.c_accent,
            "c_accent_dark": self.c_accent_dark,
            "c_success": self.c_success,
            "c_danger": self.c_danger,
            "c_warning": self.c_warning,
            "c_text_bright": self.c_text_bright,
            "c_text_muted": self.c_text_muted,
            "c_input_bg": self.c_input_bg
        }

    def toggle_auto_categorize(self):
        """Toggles automatic categorization into subfolders (Videos, Music, etc.)."""
        self.auto_categorize_folders = not self.auto_categorize_folders
        set_setting("auto_categorize_folders", self.auto_categorize_folders)
        self._update_auto_cat_btn()
        if not (self.engine and getattr(self.engine, "is_running", False)):
            cur_dest = self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ""
            if cur_dest:
                fn = os.path.basename(cur_dest)
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                dest_dir = os.path.dirname(cur_dest)
                if self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                    new_dest = resolve_categorized_path(downloads_dir, fn, auto_categorize=self.auto_categorize_folders)
                    self.entry_dest.delete(0, tk.END)
                    self.entry_dest.insert(0, new_dest)

    def _update_auto_cat_btn(self):
        if not hasattr(self, "btn_auto_cat") or not self.btn_auto_cat.winfo_exists():
            return
        if self.auto_categorize_folders:
            self.btn_auto_cat.configure(
                text=tr("btn_auto_cat_on"),
                fg=self.c_success,
                bg=self.c_panel_light
            )
        else:
            self.btn_auto_cat.configure(
                text=tr("btn_auto_cat_off"),
                fg=self.c_text_muted,
                bg=self.c_panel
            )

    def _on_slider_moved(self, val_str):
        """Dynamic slider movement throttles engine in real-time."""
        try:
            kb_val = int(float(val_str))
        except ValueError:
            return

        if kb_val <= 0:
            self.lbl_slider_val.configure(text=f"{tr('lbl_unlimited', 'Unlimited')} (0 KB/s)", fg=self.c_success)
            self.lbl_active_limit.configure(text=tr("lbl_current_unlimited", "● Current: Unlimited"), fg=self.c_success)
            self.limit_preset_var.set("Unlimited")
            bytes_sec = 0.0
        else:
            if kb_val >= 1024:
                disp = f"{kb_val / 1024.0:.1f} MB/s ({kb_val:,} KB/s)"
                active_disp = tr("lbl_current_limit", "● Current: {limit}").format(limit=f"{kb_val / 1024.0:.2f} MB/s")
            else:
                disp = f"{kb_val} KB/s"
                active_disp = tr("lbl_current_limit", "● Current: {limit}").format(limit=f"{kb_val} KB/s")
            self.lbl_slider_val.configure(text=disp, fg=self.c_warning)
            self.lbl_active_limit.configure(text=active_disp, fg=self.c_warning)
            bytes_sec = kb_val * 1024.0

        self.speed_limit = bytes_sec

        # Sync entry box without triggering infinite callback
        self.entry_custom_speed.delete(0, tk.END)
        self.entry_custom_speed.insert(0, str(kb_val))

        if self.engine and self.engine.is_running:
            self.engine.set_speed_limit(bytes_sec)

    def _on_preset_selected(self, event=None):
        val = self.limit_preset_var.get()
        mapping = {
            "Unlimited": 0,
            "128 KB/s": 128,
            "256 KB/s": 256,
            "512 KB/s": 512,
            "1.0 MB/s": 1024,
            "2.0 MB/s": 2048,
            "5.0 MB/s": 5120,
            "10.0 MB/s": 10240,
            "20.0 MB/s": 20480,
        }
        if val in mapping:
            target_kb = mapping[val]
            self.entry_custom_speed.delete(0, tk.END)
            self.entry_custom_speed.insert(0, str(target_kb))
            self.slider_speed.set(target_kb)
            self._apply_speed_limit()
        elif val == "Custom":
            self.entry_custom_speed.focus_set()

    def _apply_speed_limit(self):
        """Applies speed limit dynamically to active engine."""
        try:
            kb_val = float(self.entry_custom_speed.get().strip())
        except ValueError:
            self.show_safe_warning("Invalid Speed", "Please enter a valid numeric speed limit in KB/s.")
            return

        kb_val = max(0.0, kb_val)
        bytes_sec = kb_val * 1024.0 if kb_val > 0 else 0.0
        self.speed_limit = bytes_sec

        if bytes_sec <= 0:
            self.lbl_active_limit.configure(text=tr("lbl_current_unlimited", "● Current: Unlimited"), fg=self.c_success)
            self.lbl_slider_val.configure(text=f"{tr('lbl_unlimited', 'Unlimited')} (0 KB/s)", fg=self.c_success)
            self.limit_preset_var.set("Unlimited")
            self.slider_speed.set(0)
        else:
            if bytes_sec >= 1024 * 1024:
                disp = f"{bytes_sec / (1024*1024):.2f} MB/s"
            else:
                disp = f"{bytes_sec / 1024:.0f} KB/s"
            self.lbl_active_limit.configure(text=tr("lbl_current_limit", "● Current: {limit}").format(limit=disp), fg=self.c_warning)
            self.lbl_slider_val.configure(text=disp, fg=self.c_warning)
            self.slider_speed.set(min(20480, int(kb_val)))

        if self.engine and self.engine.is_running:
            self.engine.set_speed_limit(bytes_sec)

    def _update_startup_btn(self):
        """Refreshes the visual state of the Windows auto-start button."""
        if hasattr(self, "btn_startup"):
            try:
                if not self.btn_startup.winfo_exists():
                    return
            except Exception:
                return
            enabled = is_startup_enabled()
            self._startup_enabled = enabled
            if enabled:
                self.btn_startup.configure(
                    text=tr("btn_startup_on"),
                    fg=self.c_success,
                    bg=self.c_panel_light
                )
            else:
                self.btn_startup.configure(
                    text=tr("btn_startup_off"),
                    fg=self.c_text_muted,
                    bg=self.c_panel
                )

    def _get_cookies_btn_text(self) -> str:
        """Returns the display label for the cookies setting button."""
        if self.cookies_file and os.path.isfile(self.cookies_file):
            return "🍪 Cookies: File"
        cb = (self.cookies_browser or "auto").lower()
        if cb in ("none", "off"):
            return "🍪 Cookies: Off"
        display_names = {
            "auto": "Auto",
            "edge": "Edge",
            "chrome": "Chrome",
            "firefox": "Firefox",
            "brave": "Brave",
            "opera": "Opera",
            "vivaldi": "Vivaldi",
        }
        return f"🍪 Cookies: {display_names.get(cb, cb.capitalize())}"

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
        cb = (self.cookies_browser or "auto").lower()
        has_cookies = not (cb in ("none", "off") and not (self.cookies_file and os.path.isfile(self.cookies_file)))

        self.btn_cookies.configure(
            text=btn_text,
            fg=self.c_accent if has_cookies else self.c_text_muted,
            bg=self.c_panel_light if has_cookies else self.c_panel
        )

    def cycle_cookies_setting(self):
        """
        Cycles through cookie options:
        ('auto', 'edge', 'chrome', 'firefox', 'brave', 'file...', 'none')
        Saves chosen setting to app configuration.
        """
        cycle_options = ["auto", "edge", "chrome", "firefox", "brave", "file...", "none"]
        current = "file..." if (self.cookies_file and os.path.isfile(self.cookies_file)) else (self.cookies_browser or "auto").lower()
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
            )
            if chosen and os.path.isfile(chosen):
                self.cookies_file = chosen
                self.cookies_browser = "file"
                set_setting("cookies_file", self.cookies_file)
                set_setting("cookies_browser", "file")
                self.log(f"[COOKIES] Loaded cookie file: {chosen}")
            else:
                # Cancelled file dialog -> skip to 'none'
                self.cookies_file = ""
                self.cookies_browser = "none"
                set_setting("cookies_file", "")
                set_setting("cookies_browser", "none")
                self.log("[COOKIES] Browser cookies disabled.")
        else:
            self.cookies_file = ""
            self.cookies_browser = next_val
            set_setting("cookies_file", "")
            set_setting("cookies_browser", next_val)
            if next_val == "none":
                self.log("[COOKIES] Browser cookies disabled.")
            else:
                self.log(f"[COOKIES] Cookie browser set to: {next_val.capitalize()}")

        self._update_cookies_btn()

    def toggle_startup_setting(self) -> bool:
        """Toggles Windows startup on boot registry entry with live feedback."""
        current = is_startup_enabled()
        if current:
            success = disable_startup()
            if success:
                self._startup_enabled = False
                self.log("[STARTUP] Windows Run on Boot: Disabled.")
            else:
                self.log("[STARTUP ERROR] Failed to disable Windows Run on Boot.")
        else:
            success = enable_startup(minimized=True)
            if success:
                self._startup_enabled = True
                self.log("[STARTUP] Windows Run on Boot: Enabled (Silent background mode).")
            else:
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
            self.log("[SETTINGS] Close button action set to: Minimize to System Tray.")
        else:
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
