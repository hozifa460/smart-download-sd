"""
Locale and UI dynamic language translation controller mixin for Smart Download (SD).
"""
from smart_download.i18n import LocalizationManager, tr
from smart_download.utils import format_speed


class LocaleControllerMixin:
    """Provides methods for managing UI localization dynamically in-place."""

    def toggle_language(self):
        """Toggles active language between Arabic and English dynamically in-place."""
        new_lang = LocalizationManager.get_instance().toggle_language()
        self._update_ui_language()
        if hasattr(self, "log") and callable(self.log):
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
        if hasattr(self, "btn_refresh_url") and self.btn_refresh_url and self.btn_refresh_url.winfo_exists():
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
        if hasattr(self, "combo_speed") and self.combo_speed and self.combo_speed.winfo_exists():
            speed_presets = [tr("lbl_unlimited", "Unlimited"), "512 KB/s", "1 MB/s", "2 MB/s", "5 MB/s", "10 MB/s", "20 MB/s"]
            self.combo_speed["values"] = speed_presets
            cur_preset_var = getattr(self, "speed_preset_var", None) or getattr(self, "limit_preset_var", None)
            if cur_preset_var:
                cur_val = cur_preset_var.get()
                if cur_val in ("Unlimited", "بدون حد", tr("lbl_unlimited", "Unlimited")):
                    cur_preset_var.set(tr("lbl_unlimited", "Unlimited"))

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
        if hasattr(self, "btn_quality_main") and self.btn_quality_main.winfo_exists():
            self.btn_quality_main.configure(text=tr("btn_quality_reopen"))
        if hasattr(self, "btn_check_updates") and self.btn_check_updates.winfo_exists():
            self.btn_check_updates.configure(text=tr("btn_check_updates"))

        if hasattr(self, "_update_sniffer_btn") and callable(self._update_sniffer_btn):
            self._update_sniffer_btn()
        if hasattr(self, "_update_startup_btn") and callable(self._update_startup_btn):
            self._update_startup_btn()
        if hasattr(self, "_update_cookies_btn") and callable(self._update_cookies_btn):
            self._update_cookies_btn()
        if hasattr(self, "_update_auto_cat_btn") and callable(self._update_auto_cat_btn):
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
        if not getattr(self, "engine", None) and hasattr(self, "card_threads") and self.card_threads.winfo_exists():
            self.card_threads.configure(text=f"0 / 0 {tr('lbl_threads_unit', 'Threads')}")

        # Chunk visualizer card
        if hasattr(self, "lbl_chunk_vis_title") and self.lbl_chunk_vis_title.winfo_exists():
            self.lbl_chunk_vis_title.configure(text=tr("lbl_chunk_vis_title"))
        if hasattr(self, "lbl_chunk_vis_legend") and self.lbl_chunk_vis_legend.winfo_exists():
            self.lbl_chunk_vis_legend.configure(text=tr("lbl_chunk_vis_legend"))
        if hasattr(self, "_draw_chunk_segments") and callable(self._draw_chunk_segments):
            self._last_chunk_canvas_sig = None
            self._draw_chunk_segments(getattr(self.engine, "chunks", []) if getattr(self, "engine", None) else [])

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
        if hasattr(self, "btn_hist_quality") and self.btn_hist_quality.winfo_exists():
            self.btn_hist_quality.configure(text=tr("ctx_redownload_quality"))
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
            if hasattr(self, "_refresh_history_table") and callable(self._refresh_history_table):
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

        # Media Options Bar
        if hasattr(self, "lbl_main_quality") and self.lbl_main_quality.winfo_exists():
            self.lbl_main_quality.configure(text=tr("lbl_main_quality", "🎞️ Quality:"))
        if hasattr(self, "lbl_main_audio") and self.lbl_main_audio.winfo_exists():
            self.lbl_main_audio.configure(text=tr("lbl_main_audio", "🎙️ Audio:"))
        if hasattr(self, "lbl_main_sub") and self.lbl_main_sub.winfo_exists():
            self.lbl_main_sub.configure(text=tr("lbl_main_sub", "💬 Subtitles:"))
        if hasattr(self, "lbl_main_sub_mode") and self.lbl_main_sub_mode.winfo_exists():
            self.lbl_main_sub_mode.configure(text=tr("lbl_main_sub_mode", "⚙️ Mode:"))
        if hasattr(self, "btn_reopen_quality") and self.btn_reopen_quality.winfo_exists():
            self.btn_reopen_quality.configure(text=tr("btn_media_quality_options", "⚙️ Options..."))

        # Tray menu
        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.update_menu()
            except Exception:
                pass


__all__ = ["LocaleControllerMixin"]
