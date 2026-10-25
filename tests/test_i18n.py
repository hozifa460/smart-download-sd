"""
Automated Test Module for Smart Download (SD)
"""
import os
import sys
import tempfile
import time
import json
import shutil
import struct
import hashlib
import ssl
import re
import unittest
import threading
import subprocess
import http.server
import socketserver
import urllib.request
import urllib.error
import urllib.parse
from unittest.mock import patch, MagicMock
from typing import List, Dict, Optional, Tuple, Any

# Ensure project root and src/ are in sys.path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

os.environ["SD_DISABLE_SYSTEM_TRAY"] = "1"
os.environ["SD_DISABLE_STARTUP_TOAST"] = "1"
os.environ["SD_DISABLE_AUTO_UPDATE"] = "1"
os.environ["SD_LANGUAGE"] = "en"
if not os.environ.get("SD_CONFIG_DIR"):
    _sd_test_cfg = os.path.join(tempfile.gettempdir(), "sd_test_isolated_cfg")
    os.makedirs(_sd_test_cfg, exist_ok=True)
    os.environ["SD_CONFIG_DIR"] = _sd_test_cfg

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None  # type: ignore
    ImageTk = None  # type: ignore

from youtube_resolver import (
    is_youtube_url,
    is_social_media_url,
    is_media_url,
    extract_youtube_id,
    extract_media_platform,
    extract_media_id,
    sanitize_filename,
    is_ytdlp_available,
    has_ffmpeg,
    find_ffmpeg_bin,
    update_ytdlp_engine,
    get_ytdlp_version,
    YouTubeResolver,
    MediaResolver,
    YouTubeStreamInfo,
    MediaStreamInfo,
    VideoFormatOption,
    format_filesize,
    SUPPORTED_COOKIE_BROWSERS,
    detect_installed_cookie_browsers,
)
from browser_bridge import BrowserBridgeServer, BrowserBridgeHandler, DEFAULT_BRIDGE_PORT
from native_messaging_host import read_message, send_message, handle_payload
from register_browser import (
    register_native_host,
    unregister_native_host,
    check_and_register_browser,
    register_browser_extensions,
    unregister_browser_extensions,
    is_extension_registered,
    is_registered as is_browser_registered,
    get_status as get_browser_reg_status,
    compute_unpacked_extension_id,
    generate_host_manifest,
    get_default_extension_origins,
)
import installer
from turbo_downloader import (
    TurboDownloadEngine,
    SmartDownloadEngine,
    StreamDownloadCoordinator,
    TokenBucketRateLimiter,
    get_permissive_ssl_context,
    SafeModalDialog,
    ModernFramelessGUI,
    QualitySelectionModal,
    DownloadConfirmationModal,
    FetchingLinkToast,
    validate_refresh_url,
    RefreshLinkModal,
    RefreshLinkDialog,
    DownloadChunk,
    is_downloadable_url,
    get_clipboard_text,
    derive_download_filename,
    COMMON_DOWNLOAD_EXTENSIONS,
    is_startup_enabled,
    enable_startup,
    disable_startup,
    get_startup_command,
    get_startup_entry,
    notify_running_instance,
    WINDOWS_RUN_KEY,
    STARTUP_REG_KEY_NAME,
    SystemTrayManager,
    load_settings,
    save_settings,
    get_setting,
    set_setting,
    parse_speed_limit,
    open_downloaded_file,
    open_containing_folder,
    CATEGORY_SUBFOLDERS,
    resolve_categorized_path,
    DownloadHistoryManager,
    get_app_config_dir,
    resolve_real_download_url,
    StartupWelcomeToast,
    LocalizationManager,
    enable_high_dpi_awareness,
    get_resource_path,
)


def setUpModule():
    os.environ["SD_LANGUAGE"] = "en"
    try:
        set_setting("language", "en")
        LocalizationManager.reset_instance("en")
    except Exception:
        pass


def tearDownModule():
    try:
        LocalizationManager.reset_instance()
    except Exception:
        pass

class TestBilingualLocalization(unittest.TestCase):
    """Verifies LocalizationManager, translation dictionaries, persistence, dynamic switching, and widget updates."""

    def setUp(self):
        from turbo_downloader import LocalizationManager
        self.loc = LocalizationManager.get_instance()
        self.orig_lang = "en"
        self.loc.set_language("en")
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        from turbo_downloader import set_setting
        self.loc.set_language("en")
        set_setting("language", "en")
        try:
            for child in self.root.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_localization_manager_singleton_and_defaults(self):
        """Tests singleton access and language getters/setters."""
        from turbo_downloader import LocalizationManager, get_current_language, set_current_language

        loc1 = LocalizationManager.get_instance()
        loc2 = LocalizationManager.get_instance()
        self.assertIs(loc1, loc2)

        set_current_language("en")
        self.assertEqual(get_current_language(), "en")
        self.assertFalse(loc1.is_rtl())

        set_current_language("ar")
        self.assertEqual(get_current_language(), "ar")
        self.assertTrue(loc1.is_rtl())

        # Verify explicit default_lang override via reset_instance
        loc_ar = LocalizationManager.reset_instance("ar")
        self.assertEqual(loc_ar.get_language(), "ar")
        self.assertTrue(loc_ar.is_rtl())

        loc_en = LocalizationManager.reset_instance("en")
        self.assertEqual(loc_en.get_language(), "en")
        self.assertFalse(loc_en.is_rtl())

    def test_translations_key_symmetry_and_required_coverage(self):
        """Verifies complete key symmetry between Arabic and English dictionaries and coverage of all required keys."""
        from turbo_downloader import TRANSLATIONS

        ar_keys = set(TRANSLATIONS["ar"].keys())
        en_keys = set(TRANSLATIONS["en"].keys())

        # Exact key symmetry: every key in Arabic must exist in English and vice-versa
        diff_ar = ar_keys - en_keys
        diff_en = en_keys - ar_keys
        self.assertEqual(diff_ar, set(), f"Keys in Arabic but missing in English: {diff_ar}")
        self.assertEqual(diff_en, set(), f"Keys in English but missing in Arabic: {diff_en}")

        # Check required key categories from specifications
        required_keys = [
            # App identity
            "app_title", "app_header", "app_subtitle",
            # Notebook tabs
            "tab_chunks", "tab_active", "tab_completed", "tab_logs", "tab_history", "tab_settings",
            # Control buttons
            "btn_add_url", "btn_start", "btn_resume_all", "btn_pause", "btn_pause_all", "btn_cancel",
            "btn_clear_completed", "btn_settings", "btn_sniffer_active", "btn_sniffer_paused",
            "btn_startup_on", "btn_startup_off", "btn_auto_cat_on", "btn_auto_cat_off",
            "btn_cookies_prefix", "btn_browser", "btn_check_updates", "btn_lang_toggle",
            # History tab columns
            "col_hist_category", "col_hist_filename", "col_hist_size", "col_hist_status",
            "col_hist_date", "col_hist_path", "col_hist_actions",
            # History action buttons
            "btn_hist_open", "btn_hist_folder", "btn_hist_redownload", "btn_hist_remove", "btn_hist_clear",
            "lbl_filter", "hist_filter_all",
            # Download Confirmation & Quality Modals
            "modal_file_name", "modal_save_to", "modal_category", "modal_quality", "modal_download_mp3",
            "modal_cookies", "modal_btn_start", "modal_btn_open_in_main", "modal_btn_cancel", "modal_btn_browse",
            "modal_threads", "modal_speed_limiter", "modal_confirm_title", "modal_quality_title",
            # MultipleCandidatesModal
            "multi_modal_title", "multi_modal_source", "multi_modal_subtitle", "multi_col_select",
            "multi_col_filename", "multi_col_type", "multi_col_size", "multi_col_url",
            "multi_select_all", "multi_btn_download_selected", "multi_btn_download_all", "multi_btn_cancel",
            "multi_no_selection_warning", "multi_selection_count",
            # Toasts
            "toast_startup_title", "toast_startup_msg", "toast_fetching_header", "toast_fetching_sub",
            "toast_completed_title", "toast_completed_msg", "toast_error_title", "toast_error_msg",
            # System Tray
            "tray_open", "tray_sniffer_active", "tray_sniffer_paused", "tray_startup_on", "tray_startup_off", "tray_exit"
        ]

        for rk in required_keys:
            self.assertIn(rk, ar_keys, f"Required key '{rk}' missing in Arabic translations")
            self.assertIn(rk, en_keys, f"Required key '{rk}' missing in English translations")

    def test_settings_persistence(self):
        """Verifies changing language persists preference to settings.json."""
        from turbo_downloader import get_setting

        self.loc.set_language("ar")
        self.assertEqual(get_setting("language"), "ar")

        self.loc.set_language("en")
        self.assertEqual(get_setting("language"), "en")

    def test_runtime_language_switching_and_observers(self):
        """Verifies toggle_language switches between 'ar' and 'en' and notifies registered observers."""
        from turbo_downloader import tr

        notifications = []
        def _observer():
            notifications.append(self.loc.get_language())

        self.loc.register_observer(_observer)
        try:
            self.loc.set_language("en")
            self.assertEqual(tr("btn_start"), "▶ Start Download")
            self.assertEqual(self.loc.get_language(), "en")

            # Toggle from en to ar
            new_lang = self.loc.toggle_language()
            self.assertEqual(new_lang, "ar")
            self.assertEqual(tr("btn_start"), "▶ بدء التحميل")
            self.assertEqual(notifications[-1], "ar")

            # Toggle from ar to en
            new_lang2 = self.loc.toggle_language()
            self.assertEqual(new_lang2, "en")
            self.assertEqual(tr("btn_start"), "▶ Start Download")
            self.assertEqual(notifications[-1], "en")
        finally:
            self.loc.unregister_observer(_observer)

    def test_gui_language_toggle_and_widget_updates(self):
        """Verifies clicking btn_lang_toggle dynamically updates all GUI labels, notebook tabs, and headings in place."""
        from turbo_downloader import ModernFramelessGUI, tr

        self.loc.set_language("en")
        app = ModernFramelessGUI(self.root, start_hidden=True)

        try:
            # When language is English:
            # btn_lang_toggle displays '🌐 العربية'
            self.assertEqual(app.btn_lang_toggle.cget("text"), "🌐 العربية")
            self.assertEqual(app.title_lbl.cget("text"), tr("app_header"))
            self.assertEqual(app.btn_start.cget("text"), "▶ Start Download")
            self.assertEqual(app.tree_history.heading("category")["text"], "Category")
            self.assertEqual(app.tree_history.heading("filename")["text"], "File Name")
            self.assertIn("Chunk Segments", app.notebook.tab(0, "text"))

            # Toggle language to Arabic by invoking button
            app.btn_lang_toggle.invoke()

            # Now language is Arabic:
            # btn_lang_toggle displays '🌐 English'
            self.assertEqual(self.loc.get_language(), "ar")
            self.assertEqual(app.btn_lang_toggle.cget("text"), "🌐 English")
            self.assertEqual(app.title_lbl.cget("text"), "التحميل الذكي (SD)")
            self.assertEqual(app.btn_start.cget("text"), "▶ بدء التحميل")
            self.assertEqual(app.tree_history.heading("category")["text"], "التصنيف")
            self.assertEqual(app.tree_history.heading("filename")["text"], "اسم الملف")
            self.assertIn("قطاعات التحميل", app.notebook.tab(0, "text"))

            # Toggle back to English by invoking button again
            app.btn_lang_toggle.invoke()
            self.assertEqual(self.loc.get_language(), "en")
            self.assertEqual(app.btn_lang_toggle.cget("text"), "🌐 العربية")
            self.assertEqual(app.title_lbl.cget("text"), "SMART DOWNLOAD (SD)")
            self.assertEqual(app.btn_start.cget("text"), "▶ Start Download")
            self.assertEqual(app.tree_history.heading("category")["text"], "Category")
            self.assertIn("Chunk Segments", app.notebook.tab(0, "text"))
        finally:
            try:
                app._cleanup_resources()
            except Exception:
                pass

    def test_startup_button_arabic_text_clarity(self):
        """Verifies startup button in Arabic mode displays clear text avoiding confusion with 'Bot'."""
        from turbo_downloader import ModernFramelessGUI
        self.loc.set_language("ar")
        try:
            app = ModernFramelessGUI(self.root, start_hidden=True)
            btn_text = app.btn_startup.cget("text")
            self.assertIn("بدء التشغيل مع ويندوز", btn_text)
            self.assertNotIn("Boot:", btn_text)
            self.assertNotIn("Bot", btn_text)
        finally:
            try:
                app._cleanup_resources()
            except Exception:
                pass
            self.loc.set_language("en")

    def test_magic_bytes_detector(self):
        """Verifies MagicBytesDetector accurately identifies container formats from binary signatures."""
        from turbo_downloader import MagicBytesDetector
        # ZIP
        zip_hdr = b"PK\x03\x04" + b"\x00" * 20
        self.assertEqual(MagicBytesDetector.detect_bytes(zip_hdr)[0], ".zip")
        # 7Z
        sevenz_hdr = b"\x37\x7A\xBC\xAF\x27\x1C" + b"\x00" * 10
        self.assertEqual(MagicBytesDetector.detect_bytes(sevenz_hdr)[0], ".7z")
        # RAR
        rar_hdr = b"Rar!\x1A\x07\x00" + b"\x00" * 10
        self.assertEqual(MagicBytesDetector.detect_bytes(rar_hdr)[0], ".rar")
        # PDF
        pdf_hdr = b"%PDF-1.4\r\n"
        self.assertEqual(MagicBytesDetector.detect_bytes(pdf_hdr)[0], ".pdf")
        # PNG
        png_hdr = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
        self.assertEqual(MagicBytesDetector.detect_bytes(png_hdr)[0], ".png")
        # EXE
        exe_hdr = b"MZ" + b"\x00" * 50
        self.assertEqual(MagicBytesDetector.detect_bytes(exe_hdr)[0], ".exe")
        # MP4
        mp4_hdr = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 20
        self.assertEqual(MagicBytesDetector.detect_bytes(mp4_hdr)[0], ".mp4")

    def test_file_integrity_calculator(self):
        """Verifies calculate_file_integrity calculates accurate CRC-32 and SHA-256."""
        from turbo_downloader import calculate_file_integrity
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"Hello Turbo Downloader Integrity Test!")
            tf_path = tf.name
        try:
            res = calculate_file_integrity(tf_path)
            self.assertTrue("crc32" in res)
            self.assertTrue("sha256" in res)
            expected_sha = hashlib.sha256(b"Hello Turbo Downloader Integrity Test!").hexdigest().lower()
            self.assertEqual(res["sha256"], expected_sha)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_safe_shutdown_preserves_parts(self):
        """Verifies safe_shutdown halts download and serializes state without purging .sd_parts."""
        from turbo_downloader import TurboDownloadEngine, DownloadChunk
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = os.path.join(tmp_dir, "test_file.bin")
            parts_dir = dest + ".sd_parts"
            engine = TurboDownloadEngine(
                url="https://example.com/file.bin",
                destination_path=dest,
                max_connections=2
            )
            # Create simulated chunk & parts dir
            os.makedirs(parts_dir, exist_ok=True)
            chunk_file = os.path.join(parts_dir, "chunk_0.part")
            with open(chunk_file, "wb") as f:
                f.write(b"part data")
            engine.chunks = [DownloadChunk(chunk_id=0, start_byte=0, end_byte=100, part_filepath=chunk_file)]
            engine.chunks[0].downloaded_bytes = 9
            engine.is_running = True

            engine.safe_shutdown()

            self.assertFalse(engine.is_running)
            self.assertTrue(engine.is_paused)
            self.assertTrue(os.path.isdir(parts_dir), ".sd_parts was erroneously purged")
            self.assertTrue(os.path.isfile(chunk_file), "chunk file was erroneously purged")
            self.assertTrue(os.path.isfile(os.path.join(parts_dir, "state.json")), "state.json was not saved")

    def test_history_open_paused_resumes_seamlessly(self):
        """Verifies _history_open_selected_file on incomplete/paused entry prompts to resume."""
        from turbo_downloader import ModernFramelessGUI
        app = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                fake_dest = os.path.join(tmp_dir, "incomplete.zip")
                fake_url = "https://example.com/incomplete.zip"
                # Add paused entry to history
                app.history_manager.add_or_update_entry(
                    url=fake_url,
                    file_path=fake_dest,
                    size_bytes=1024,
                    status="Paused"
                )
                app._refresh_history_table()
                # Select the first entry
                children = app.tree_history.get_children()
                self.assertTrue(len(children) > 0)
                app.tree_history.selection_set(children[0])

                yesno_asked = []
                def _mock_yesno(title, msg, on_yes=None, on_no=None):
                    yesno_asked.append((title, msg))
                    if on_yes:
                        on_yes()

                app.ask_safe_yesno = _mock_yesno
                redownload_called = []
                app._history_redownload_selected = lambda: redownload_called.append(True)

                app._history_open_selected_file()
                self.assertEqual(len(yesno_asked), 1)
                self.assertEqual(len(redownload_called), 1)
        finally:
            try:
                app._cleanup_resources()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
