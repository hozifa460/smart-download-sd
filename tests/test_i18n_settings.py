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
            status="Completed",
            elapsed_sec=1.5
        )
        self.assertEqual(entry1["filename"], "sample.mp4")
        self.assertEqual(entry1["category"], "Video")
        self.assertEqual(entry1["status"], "Completed")
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

        # 3. Deduplication / update moves matching entry to index 0
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

        mgr.add_or_update_entry(url="https://example.com/Clip.mp4", file_path=path_upper, size_bytes=1000)
        mgr.add_or_update_entry(url="https://example.com/Clip.mp4", file_path=path_lower, size_bytes=2000)

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
