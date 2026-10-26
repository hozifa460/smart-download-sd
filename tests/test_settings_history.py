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

class TestWindowsStartupRegistryIntegration(unittest.TestCase):
    """Verifies Windows Startup Registry helper functions and executable resolution."""

    def setUp(self):
        # Record initial state to restore after test
        self.initial_enabled = is_startup_enabled()
        self.initial_entry = get_startup_entry()

    def tearDown(self):
        # Restore initial state
        if self.initial_enabled and self.initial_entry:
            enable_startup(minimized="--minimized" in self.initial_entry)
        else:
            disable_startup()

    def test_startup_command_script_mode(self):
        # Fallback script mode when standalone exe is absent
        with patch("os.path.isfile", side_effect=lambda p: False if ("SmartDownload.exe" in p or "TurboDownloader.exe" in p) else os.path.exists(p)):
            cmd_min = get_startup_command(minimized=True)
            self.assertIn("--minimized", cmd_min)
            self.assertTrue(cmd_min.endswith(" --minimized"))
            self.assertIn("turbo_downloader.py", cmd_min)

            cmd_full = get_startup_command(minimized=False)
            self.assertNotIn("--minimized", cmd_full)
            self.assertIn("turbo_downloader.py", cmd_full)

    def test_startup_command_prioritizes_standalone_exe(self):
        # Standalone binary dist/TurboDownloader.exe is prioritized when present
        cmd_min = get_startup_command(minimized=True)
        self.assertTrue("SmartDownload.exe" in cmd_min or "TurboDownloader.exe" in cmd_min)
        self.assertNotIn("pythonw.exe", cmd_min)
        self.assertTrue(cmd_min.endswith(" --minimized"))

    def test_startup_command_frozen_mode(self):
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "executable", r"C:\Program Files\SmartDownload\SmartDownload.exe"):
                cmd_min = get_startup_command(minimized=True)
                self.assertEqual(cmd_min, r'"C:\Program Files\SmartDownload\SmartDownload.exe" --minimized')

                cmd_full = get_startup_command(minimized=False)
                self.assertEqual(cmd_full, r'"C:\Program Files\SmartDownload\SmartDownload.exe"')

    def test_startup_lifecycle_enable_disable(self):
        # Enable with minimized=True
        ok = enable_startup(minimized=True)
        self.assertTrue(ok)
        self.assertTrue(is_startup_enabled())
        entry = get_startup_entry()
        self.assertIsNotNone(entry)
        self.assertIn("--minimized", entry)

        # Re-enable with minimized=False
        ok2 = enable_startup(minimized=False)
        self.assertTrue(ok2)
        self.assertTrue(is_startup_enabled())
        entry2 = get_startup_entry()
        self.assertIsNotNone(entry2)
        self.assertNotIn("--minimized", entry2)

        # Disable
        ok3 = disable_startup()
        self.assertTrue(ok3)
        self.assertFalse(is_startup_enabled())
        self.assertIsNone(get_startup_entry())

        # Disabling when already disabled is idempotent
        ok4 = disable_startup()
        self.assertTrue(ok4)
        self.assertFalse(is_startup_enabled())

    def test_registry_error_handling(self):
        with patch("winreg.CreateKey", side_effect=PermissionError("Access denied")):
            self.assertFalse(enable_startup(minimized=True))

        with patch("winreg.OpenKey", side_effect=OSError("Registry error")):
            self.assertFalse(disable_startup())
            self.assertFalse(is_startup_enabled())
            self.assertIsNone(get_startup_entry())

    def test_non_windows_platform_graceful_noops(self):
        with patch("turbo_downloader.IS_WINDOWS", False):
            self.assertFalse(is_startup_enabled())
            self.assertFalse(enable_startup(minimized=True))
            self.assertFalse(disable_startup())
            self.assertIsNone(get_startup_entry())

    def test_startup_command_script_mode_fallback(self):
        with patch("os.path.isfile", return_value=False):
            cmd = get_startup_command(minimized=True)
            self.assertIn("--minimized", cmd)
            self.assertIn("turbo_downloader.py", cmd)

    def test_startup_command_strip_quotes(self):
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "executable", r'"C:\Path With Spaces\SmartDownload.exe"'):
                cmd = get_startup_command(minimized=True)
                self.assertNotIn('""', cmd)
                self.assertEqual(cmd, r'"C:\Path With Spaces\SmartDownload.exe" --minimized')

    def test_is_startup_enabled_whitespace_or_empty(self):
        with patch("winreg.OpenKey"):
            with patch("winreg.QueryValueEx", return_value=("   ", 1)):
                self.assertFalse(is_startup_enabled())
            with patch("winreg.QueryValueEx", return_value=("", 1)):
                self.assertFalse(is_startup_enabled())
            with patch("winreg.QueryValueEx", return_value=(None, 1)):
                self.assertFalse(is_startup_enabled())

    def test_startup_harmonization_and_stale_key_cleanup(self):
        """Verifies that is_startup_enabled detects and cleans up stale/broken entries pointing to missing binaries or missing scripts."""
        import winreg
        import tempfile

        orig_reg = None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ) as key:
                orig_reg, _ = winreg.QueryValueEx(key, STARTUP_REG_KEY_NAME)
        except Exception:
            pass

        try:
            # 1. Inject a broken/stale standalone entry into the Run key
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
                broken_cmd = r'"C:\PathThatDoesNotExist_12345\SmartDownload.exe" --minimized'
                winreg.SetValueEx(key, STARTUP_REG_KEY_NAME, 0, winreg.REG_SZ, broken_cmd)

            # 2. is_startup_enabled must recognize this as broken/stale, delete it, and return False
            enabled = is_startup_enabled()
            self.assertFalse(enabled, "is_startup_enabled must return False for broken/stale binary keys")

            # 3. Verify registry key was cleaned up
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ) as key:
                with self.assertRaises(FileNotFoundError):
                    winreg.QueryValueEx(key, STARTUP_REG_KEY_NAME)

            # 4. Inject a broken Python script entry (interpreter exists, but script does not)
            py_exe = sys.executable
            broken_script = r"C:\PathThatDoesNotExist_12345\missing_script.py"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
                winreg.SetValueEx(key, STARTUP_REG_KEY_NAME, 0, winreg.REG_SZ, f'"{py_exe}" "{broken_script}" --minimized')

            # Must recognize broken script and clean it up
            self.assertFalse(is_startup_enabled(), "is_startup_enabled must return False when python script is missing")
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ) as key:
                with self.assertRaises(FileNotFoundError):
                    winreg.QueryValueEx(key, STARTUP_REG_KEY_NAME)

            # 5. Inject a valid script entry
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tf:
                valid_script = tf.name
            try:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
                    winreg.SetValueEx(key, STARTUP_REG_KEY_NAME, 0, winreg.REG_SZ, f'"{py_exe}" "{valid_script}" --minimized')
                self.assertTrue(is_startup_enabled(), "is_startup_enabled must return True for valid script entry")
            finally:
                if os.path.isfile(valid_script):
                    os.remove(valid_script)

            # 6. enable_startup must successfully register active command
            ok = enable_startup(minimized=True)
            self.assertTrue(ok)
            self.assertTrue(is_startup_enabled())

            # 7. disable_startup cleanly unregisters
            disable_ok = disable_startup()
            self.assertTrue(disable_ok)
            self.assertFalse(is_startup_enabled())
        finally:
            if orig_reg is not None:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
                    winreg.SetValueEx(key, STARTUP_REG_KEY_NAME, 0, winreg.REG_SZ, orig_reg)
            else:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.DeleteValue(key, STARTUP_REG_KEY_NAME)
                except Exception:
                    pass

class TestDownloadHistoryAndCategorization(unittest.TestCase):
    """
    Unit test coverage for:
    1. Smart Auto-Categorization into subfolders (resolve_categorized_path, CATEGORY_SUBFOLDERS).
    2. Persistent Download History Manager (DownloadHistoryManager add, update, deduplication, filtering, reload, remove, clear).
    3. ModernFramelessGUI Download History tab (tree_history, combo_history_filter, btn_auto_cat toggle, auto-recording).
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sd_test_hist_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_category_subfolders_mapping(self):
        """Verify CATEGORY_SUBFOLDERS contains all required category-to-subfolder mappings."""
        self.assertEqual(CATEGORY_SUBFOLDERS.get("Video"), "Video")
        self.assertEqual(CATEGORY_SUBFOLDERS.get("Audio"), "Music")
        self.assertEqual(CATEGORY_SUBFOLDERS.get("Programs"), "Programs")
        self.assertEqual(CATEGORY_SUBFOLDERS.get("Compressed"), "Compressed")
        self.assertEqual(CATEGORY_SUBFOLDERS.get("Documents"), "Documents")
        self.assertEqual(CATEGORY_SUBFOLDERS.get("Images"), "Images")
        self.assertEqual(CATEGORY_SUBFOLDERS.get("General"), "General")

    def test_resolve_categorized_path_extensions(self):
        """Verify resolve_categorized_path correctly maps extensions into designated subfolders."""
        base = os.path.join(self.temp_dir, "Downloads")
        
        # Video (.mp4) -> Video
        p_mp4 = resolve_categorized_path(base, "movie.mp4", auto_categorize=True, create_dir=True)
        self.assertEqual(os.path.normpath(p_mp4), os.path.normpath(os.path.join(base, "Video", "movie.mp4")))
        self.assertTrue(os.path.isdir(os.path.join(base, "Video")))

        # Audio (.mp3, .m4a) -> Music
        p_mp3 = resolve_categorized_path(base, "track.mp3", auto_categorize=True, create_dir=True)
        self.assertEqual(os.path.normpath(p_mp3), os.path.normpath(os.path.join(base, "Music", "track.mp3")))
        p_m4a = resolve_categorized_path(base, "audio.m4a", auto_categorize=True, create_dir=True)
        self.assertEqual(os.path.normpath(p_m4a), os.path.normpath(os.path.join(base, "Music", "audio.m4a")))

        # Programs (.exe) -> Programs
        p_exe = resolve_categorized_path(base, "setup.exe", auto_categorize=True, create_dir=True)
        self.assertEqual(os.path.normpath(p_exe), os.path.normpath(os.path.join(base, "Programs", "setup.exe")))

        # Compressed (.zip) -> Compressed
        p_zip = resolve_categorized_path(base, "archive.zip", auto_categorize=True, create_dir=True)
        self.assertEqual(os.path.normpath(p_zip), os.path.normpath(os.path.join(base, "Compressed", "archive.zip")))

        # Documents (.pdf) -> Documents
        p_pdf = resolve_categorized_path(base, "doc.pdf", auto_categorize=True, create_dir=True)
        self.assertEqual(os.path.normpath(p_pdf), os.path.normpath(os.path.join(base, "Documents", "doc.pdf")))

        # Images (.png) -> Images
        p_png = resolve_categorized_path(base, "photo.png", auto_categorize=True, create_dir=True)
        self.assertEqual(os.path.normpath(p_png), os.path.normpath(os.path.join(base, "Images", "photo.png")))

        # General (.bin, unknown) -> General
        p_bin = resolve_categorized_path(base, "payload.bin", auto_categorize=True, create_dir=True)
        self.assertEqual(os.path.normpath(p_bin), os.path.normpath(os.path.join(base, "General", "payload.bin")))

    def test_resolve_categorized_path_prevents_nested_subfolders(self):
        """Verify resolve_categorized_path prevents nested Video/Video or Video/Music paths."""
        base = os.path.join(self.temp_dir, "Downloads")
        video_dir = os.path.join(base, "Video")

        # Starting inside Video subfolder and saving another video should not nest
        p1 = resolve_categorized_path(video_dir, "clip.mp4", auto_categorize=True, create_dir=False)
        self.assertEqual(os.path.normpath(p1), os.path.normpath(os.path.join(base, "Video", "clip.mp4")))

        # Switching to audio while current base is Video subfolder should route to Music, not Video/Music
        p2 = resolve_categorized_path(video_dir, "song.mp3", auto_categorize=True, create_dir=False)
        self.assertEqual(os.path.normpath(p2), os.path.normpath(os.path.join(base, "Music", "song.mp3")))

    def test_resolve_categorized_path_auto_categorize_false(self):
        """Verify auto_categorize=False preserves base_dir without subfolders."""
        base = os.path.join(self.temp_dir, "Downloads")
        p = resolve_categorized_path(base, "song.mp3", auto_categorize=False, create_dir=False)
        self.assertEqual(os.path.normpath(p), os.path.normpath(os.path.join(base, "song.mp3")))

    def test_resolve_categorized_path_empty_inputs(self):
        """Verify empty base_dir or empty filename fall back safely."""
        p = resolve_categorized_path("", "", auto_categorize=False, create_dir=False)
        expected_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        self.assertEqual(os.path.normpath(p), os.path.normpath(os.path.join(expected_dir, "download.bin")))

    def test_download_history_manager_crud_and_persistence(self):
        """Verify DownloadHistoryManager add, update, deduplication, reload from disk, and remove."""
        hist_file = os.path.join(self.temp_dir, "history.json")
        mgr = DownloadHistoryManager(history_file=hist_file)

        # 1. Add new entries
        file1 = os.path.join(self.temp_dir, "sample.mp4")
        with open(file1, "wb") as f:
            f.write(b"0" * 2048)
        
        entry1 = mgr.add_or_update_entry(
            url="https://example.com/sample.mp4",
            file_path=file1,
            size_bytes=2048,
            status="In Progress",
            elapsed_sec=1.5
        )
        self.assertEqual(entry1["filename"], "sample.mp4")
        self.assertEqual(entry1["category"], "Video")
        self.assertEqual(entry1["status"], "In Progress")
        self.assertEqual(entry1["size_bytes"], 2048)

        file2 = os.path.join(self.temp_dir, "song.mp3")
        with open(file2, "wb") as f:
            f.write(b"0" * 4096)
        
        entry2 = mgr.add_or_update_entry(
            url="https://example.com/song.mp3",
            file_path=file2,
            size_bytes=4096,
            status="Completed",
            elapsed_sec=2.0
        )
        self.assertEqual(entry2["filename"], "song.mp3")
        self.assertEqual(entry2["category"], "Audio")

        # 2. Entries list order (most recent first)
        entries = mgr.get_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["id"], entry2["id"])
        self.assertEqual(entries[1]["id"], entry1["id"])

        # 3. Deduplication / update moves matching incomplete entry to index 0
        updated_entry1 = mgr.add_or_update_entry(
            url="https://example.com/sample.mp4",
            file_path=file1,
            size_bytes=2048,
            status="Completed",
            elapsed_sec=3.2
        )
        entries = mgr.get_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["id"], entry1["id"])
        self.assertAlmostEqual(entries[0]["elapsed_sec"], 3.2)

        # 3b. Re-downloading completed file creates unique new entry without clobbering old completed entry
        redownload_entry = mgr.add_or_update_entry(
            url="https://example.com/sample.mp4",
            file_path=file1,
            size_bytes=2048,
            status="Completed",
            elapsed_sec=4.0
        )
        self.assertEqual(len(mgr.get_entries()), 3)
        self.assertNotEqual(redownload_entry["id"], entry1["id"])
        mgr.remove_entry(redownload_entry["id"])

        # 4. Category filtering
        video_entries = mgr.get_entries(category_filter="Video")
        self.assertEqual(len(video_entries), 1)
        self.assertEqual(video_entries[0]["category"], "Video")

        audio_entries = mgr.get_entries(category_filter="Audio")
        self.assertEqual(len(audio_entries), 1)
        self.assertEqual(audio_entries[0]["category"], "Audio")

        all_entries = mgr.get_entries(category_filter="All Categories")
        self.assertEqual(len(all_entries), 2)

        # 5. Persistence across reload from disk
        mgr_reloaded = DownloadHistoryManager(history_file=hist_file)
        reloaded_entries = mgr_reloaded.get_entries()
        self.assertEqual(len(reloaded_entries), 2)
        self.assertEqual(reloaded_entries[0]["filename"], "sample.mp4")
        self.assertEqual(reloaded_entries[1]["filename"], "song.mp3")

        # 6. Remove entry
        rem_ok = mgr_reloaded.remove_entry(entry1["id"], delete_file=False)
        self.assertTrue(rem_ok)
        self.assertEqual(len(mgr_reloaded.get_entries()), 1)
        self.assertTrue(os.path.exists(file1))

        # Remove entry with delete_file=True
        rem_del_ok = mgr_reloaded.remove_entry(entry2["id"], delete_file=True)
        self.assertTrue(rem_del_ok)
        self.assertEqual(len(mgr_reloaded.get_entries()), 0)
        self.assertFalse(os.path.exists(file2))

        # 7. Clear history
        mgr_reloaded.add_or_update_entry("https://example.com/temp.txt", os.path.join(self.temp_dir, "temp.txt"))
        self.assertEqual(len(mgr_reloaded.get_entries()), 1)
        mgr_reloaded.clear_history()
        self.assertEqual(len(mgr_reloaded.get_entries()), 0)

    def test_gui_history_tab_and_widgets(self):
        """Verify ModernFramelessGUI initializes history tab, widgets, filter, and auto-sort button."""
        root = tk.Tk()
        hist_file = os.path.join(self.temp_dir, "gui_history.json")
        try:
            gui = ModernFramelessGUI(root, start_hidden=True)
            gui.history_manager = DownloadHistoryManager(history_file=hist_file)

            # Check widgets exist
            self.assertTrue(hasattr(gui, "notebook"))
            self.assertTrue(hasattr(gui, "tree_history"))
            self.assertTrue(hasattr(gui, "combo_history_filter"))
            self.assertTrue(hasattr(gui, "btn_auto_cat"))
            self.assertTrue(hasattr(gui, "btn_hist_open"))
            self.assertTrue(hasattr(gui, "btn_hist_folder"))
            self.assertTrue(hasattr(gui, "btn_hist_redownload"))
            self.assertTrue(hasattr(gui, "btn_hist_remove"))
            self.assertTrue(hasattr(gui, "btn_hist_clear"))

            # Check combo_history_filter default
            self.assertEqual(gui.combo_history_filter.get(), "All Categories")

            # Check btn_auto_cat toggle
            initial_state = gui.auto_categorize_folders
            gui.toggle_auto_categorize()
            self.assertEqual(gui.auto_categorize_folders, not initial_state)
            if gui.auto_categorize_folders:
                self.assertIn("ON", gui.btn_auto_cat.cget("text"))
            else:
                self.assertIn("OFF", gui.btn_auto_cat.cget("text"))
            # Toggle back
            gui.toggle_auto_categorize()
            self.assertEqual(gui.auto_categorize_folders, initial_state)

            # Simulate completion callback and verify tree_history populated
            test_file = os.path.join(self.temp_dir, "downloaded_test.mp4")
            with open(test_file, "wb") as f:
                f.write(b"data" * 100)

            gui.entry_url.delete(0, tk.END)
            gui.entry_url.insert(0, "https://example.com/downloaded_test.mp4")
            gui._engine_complete_cb(test_file, 400, 1.2, suppress_dialog=True)

            gui._drain_dispatch_queue()
            root.update()

            # Verify recorded in history manager
            hist_items = gui.history_manager.get_entries()
            self.assertEqual(len(hist_items), 1)
            self.assertEqual(hist_items[0]["filename"], "downloaded_test.mp4")
            self.assertEqual(hist_items[0]["status"], "Completed")

            # Verify populated into tree_history
            tree_children = gui.tree_history.get_children()
            self.assertEqual(len(tree_children), 1)
            vals = gui.tree_history.item(tree_children[0], "values")
            self.assertIn("downloaded_test.mp4", vals[1])

            # Select and test redownload
            gui.tree_history.selection_set(tree_children[0])
            with patch.object(gui, "_on_start_download") as mock_start:
                gui._history_redownload_selected()
                self.assertEqual(gui.entry_url.get(), "https://example.com/downloaded_test.mp4")
                mock_start.assert_called_once()
        finally:
            gui._cleanup_resources()
            root.update_idletasks()
            root.destroy()

    def test_history_manager_corrupted_json(self):
        """Verify DownloadHistoryManager gracefully handles corrupt or non-list JSON files."""
        corrupt_file = os.path.join(self.temp_dir, "corrupt.json")
        with open(corrupt_file, "w", encoding="utf-8") as f:
            f.write("NOT_A_JSON{{{")
        mgr = DownloadHistoryManager(history_file=corrupt_file)
        self.assertEqual(mgr.get_entries(), [])

        # Non-list JSON (e.g. dict)
        with open(corrupt_file, "w", encoding="utf-8") as f:
            f.write('{"hello": "world"}')
        mgr2 = DownloadHistoryManager(history_file=corrupt_file)
        self.assertEqual(mgr2.get_entries(), [])

    def test_history_manager_max_entries_truncation(self):
        """Verify history entries list is strictly capped at max_entries."""
        hist_file = os.path.join(self.temp_dir, "capped.json")
        mgr = DownloadHistoryManager(history_file=hist_file, max_entries=5)
        for i in range(10):
            mgr.add_or_update_entry(f"https://example.com/file_{i}.zip", f"C:/file_{i}.zip")
        entries = mgr.get_entries()
        self.assertEqual(len(entries), 5)
        self.assertEqual(entries[0]["filename"], "file_9.zip")

    def test_resolve_categorized_path_case_insensitivity(self):
        """Verify extensions in uppercase (.MP4, .ZIP, .EXE) are mapped correctly."""
        base = os.path.join(self.temp_dir, "Downloads")
        p_up = resolve_categorized_path(base, "CLIP.MP4", auto_categorize=True, create_dir=False)
        self.assertEqual(os.path.normpath(p_up), os.path.normpath(os.path.join(base, "Video", "CLIP.MP4")))

    def test_quality_selection_modal_categorization_switch(self):
        """Verify QualitySelectionModal updates subfolder between Video and Music if parent is categorized."""
        root = tk.Tk()
        try:
            from turbo_downloader import VideoFormatOption
            options = [
                VideoFormatOption(format_id="137", ext="mp4", height=1080, resolution_label="1080p", filesize_approx=1000000),
                VideoFormatOption(format_id="140", ext="m4a", height=0, is_audio_only=True, resolution_label="Audio", filesize_approx=500000),
                VideoFormatOption(format_id="mp3", ext="mp3", height=0, is_audio_only=True, resolution_label="MP3", filesize_approx=500000),
            ]
            theme = {
                "c_bg": "#121212", "c_panel": "#1e1e1e", "c_panel_light": "#2a2a2a",
                "c_border": "#333", "c_accent": "#0ea5e9", "c_accent_dark": "#0284c7",
                "c_success": "#10b981", "c_text_bright": "#fff", "c_text_muted": "#888",
                "c_input_bg": "#111"
            }
            # 1. Auto-categorized in Video subfolder
            cat_dest = os.path.join(self.temp_dir, "Downloads", "Video", "clip.mp4")
            confirmed1 = []
            modal = QualitySelectionModal(
                root, "Test Title", 120, options, cat_dest, theme, lambda opt, dest: confirmed1.append((opt, dest))
            )
            modal._on_download_mp3()
            self.assertEqual(len(confirmed1), 1)
            self.assertIn("Music", confirmed1[0][1])
            self.assertTrue(confirmed1[0][1].endswith(".mp3"))

            # 2. Non-categorized custom directory (e.g. C:/Downloads/clip.mp4)
            uncat_dest = os.path.join("C:", os.sep, "Downloads", "clip.mp4")
            confirmed2 = []
            modal2 = QualitySelectionModal(
                root, "Test Title", 120, options, uncat_dest, theme, lambda opt, dest: confirmed2.append((opt, dest))
            )
            modal2._on_download_mp3()
            self.assertEqual(len(confirmed2), 1)
            self.assertEqual(os.path.dirname(os.path.normpath(confirmed2[0][1])), os.path.normpath("C:/Downloads"))
            self.assertTrue(confirmed2[0][1].endswith(".mp3"))
        finally:
            try:
                root.update_idletasks()
                root.destroy()
            except Exception:
                pass

    def test_windows_path_case_insensitivity_deduplication(self):
        """Verify Windows path case differences deduplicate rather than creating duplicate entries."""
        hist_file = os.path.join(self.temp_dir, "case_test.json")
        mgr = DownloadHistoryManager(history_file=hist_file)

        path_upper = os.path.join(self.temp_dir, "Clip.mp4")
        path_lower = os.path.join(self.temp_dir, "clip.mp4")

        mgr.add_or_update_entry(url="https://example.com/Clip.mp4", file_path=path_upper, size_bytes=1000, status="In Progress")
        mgr.add_or_update_entry(url="https://example.com/Clip.mp4", file_path=path_lower, size_bytes=2000, status="Completed")

        entries = mgr.get_entries()
        self.assertEqual(len(entries), 1, "Differing path case must deduplicate on Windows")
        self.assertEqual(entries[0]["size_bytes"], 2000)

    def test_open_containing_folder_missing_file_opens_parent_folder(self):
        """Verify open_containing_folder opens existing parent directory if the file itself is missing."""
        from turbo_downloader import open_containing_folder
        missing_file = os.path.join(self.temp_dir, "missing_movie.mp4")
        self.assertFalse(os.path.exists(missing_file))
        self.assertTrue(os.path.isdir(self.temp_dir))

        with patch("os.startfile", create=True) as mock_startfile, \
             patch("subprocess.Popen") as mock_popen:
            open_containing_folder(missing_file)
            # Either startfile(self.temp_dir) or Popen(["explorer", self.temp_dir])
            called_with_temp_dir = False
            for call in mock_startfile.call_args_list:
                if call[0] and os.path.normpath(call[0][0]) == os.path.normpath(self.temp_dir):
                    called_with_temp_dir = True
            for call in mock_popen.call_args_list:
                args = call[0][0] if call[0] else []
                if isinstance(args, list) and len(args) >= 2 and os.path.normpath(str(args[1])) == os.path.normpath(self.temp_dir):
                    called_with_temp_dir = True
            self.assertTrue(called_with_temp_dir, "Must open parent directory, not home directory")

    def test_get_entries_aliases_and_plurals(self):
        """Verify get_entries supports 'Music' for 'Audio' and plural aliases like 'Videos'."""
        hist_file = os.path.join(self.temp_dir, "alias_test.json")
        mgr = DownloadHistoryManager(history_file=hist_file)
        mgr.add_or_update_entry("https://example.com/song.mp3", "C:/song.mp3")
        mgr.add_or_update_entry("https://example.com/movie.mp4", "C:/movie.mp4")

        # "Music" alias for "Audio"
        music_entries = mgr.get_entries("Music")
        self.assertEqual(len(music_entries), 1)
        self.assertEqual(music_entries[0]["category"], "Audio")

        # "Videos" plural alias for "Video"
        video_entries = mgr.get_entries("Videos")
        self.assertEqual(len(video_entries), 1)
        self.assertEqual(video_entries[0]["category"], "Video")

    def test_add_or_update_entry_none_inputs(self):
        """Verify add_or_update_entry gracefully accepts None for size_bytes and elapsed_sec."""
        hist_file = os.path.join(self.temp_dir, "none_test.json")
        mgr = DownloadHistoryManager(history_file=hist_file)
        entry = mgr.add_or_update_entry(
            url="https://example.com/file.bin",
            file_path="",
            size_bytes=None,
            elapsed_sec=None
        )
        self.assertEqual(entry["size_bytes"], 0)
        self.assertEqual(entry["elapsed_sec"], 0.0)

    def test_resolve_categorized_path_url_query_and_fragments(self):
        """Verify resolve_categorized_path cleans query parameters and hash fragments."""
        base = os.path.join(self.temp_dir, "Downloads")
        res = resolve_categorized_path(base, "video.mp4?token=123#frag", auto_categorize=True, create_dir=False)
        self.assertTrue(res.endswith("video.mp4"))
        self.assertNotIn("?", res)
        self.assertNotIn("#", res)
        self.assertIn("Video", res)

    def test_multi_selection_remove_in_gui(self):
        """Verify GUI _history_remove_selected removes all selected entries when multiple rows are selected."""
        root = tk.Tk()
        hist_file = os.path.join(self.temp_dir, "multi_rem.json")
        try:
            gui = ModernFramelessGUI(root, start_hidden=True)
            gui.history_manager = DownloadHistoryManager(history_file=hist_file)

            e1 = gui.history_manager.add_or_update_entry("https://example.com/1.mp4", "C:/1.mp4")
            e2 = gui.history_manager.add_or_update_entry("https://example.com/2.mp4", "C:/2.mp4")
            gui._refresh_history_table()

            # Select both items
            gui.tree_history.selection_set([e1["id"], e2["id"]])
            self.assertEqual(len(gui.tree_history.selection()), 2)

            gui._history_remove_selected(delete_file=False)
            self.assertEqual(len(gui.history_manager.get_entries()), 0)
            self.assertEqual(len(gui.tree_history.get_children()), 0)
        finally:
            gui._cleanup_resources()
            root.update_idletasks()
            root.destroy()

    def test_tree_history_corrupt_ids_graceful(self):
        """Verify _refresh_history_table handles missing or empty entry IDs without TclError."""
        root = tk.Tk()
        hist_file = os.path.join(self.temp_dir, "empty_id.json")
        try:
            gui = ModernFramelessGUI(root, start_hidden=True)
            gui.history_manager = DownloadHistoryManager(history_file=hist_file)
            # Inject entry with empty id
            gui.history_manager._entries.append({
                "id": "",
                "filename": "corrupt_id.bin",
                "file_path": "C:/corrupt_id.bin",
                "url": "https://example.com/corrupt_id.bin",
                "size_bytes": 100,
                "category": "General",
                "status": "Completed"
            })
            gui._refresh_history_table()
            self.assertEqual(len(gui.tree_history.get_children()), 1)
        finally:
            gui._cleanup_resources()
            root.update_idletasks()
            root.destroy()

    def test_confirmation_dialog_completion_records_history(self):
        """Verify DownloadConfirmationModal records completion into DownloadHistoryManager."""
        root = tk.Tk()
        hist_file = os.path.join(self.temp_dir, "modal_hist.json")
        try:
            with patch("turbo_downloader.get_config_dir", return_value=self.temp_dir):
                mgr = DownloadHistoryManager(history_file=hist_file)
                modal = DownloadConfirmationModal(
                    parent=root,
                    url="https://example.com/modal_file.zip",
                    default_dest_path=os.path.join(self.temp_dir, "modal_file.zip"),
                    theme={"c_bg": "#121212", "c_panel": "#1e1e1e"},
                    history_manager=mgr
                )
                modal.show_progress_view()
                modal.on_download_complete(os.path.join(self.temp_dir, "modal_file.zip"), 5000, 1.0)
                root.update()

                entries = mgr.get_entries()
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]["filename"], "modal_file.zip")
                self.assertEqual(entries[0]["status"], "Completed")
                modal.destroy()
        finally:
            root.update_idletasks()
            root.destroy()


if __name__ == "__main__":
    unittest.main()
