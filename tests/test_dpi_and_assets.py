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

class TestDPIAndAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        enable_high_dpi_awareness()

    def test_enable_high_dpi_awareness_idempotent(self):
        """Verify calling enable_high_dpi_awareness multiple times does not raise or crash."""
        try:
            enable_high_dpi_awareness()
            enable_high_dpi_awareness()
        except Exception as e:
            self.fail(f"enable_high_dpi_awareness raised unexpectedly: {e}")

    def test_app_icon_ico_exists_and_multiresolution(self):
        """Verify app_icon.ico contains all required Windows standard & high-DPI resolutions."""
        ico_path = get_resource_path("app_icon.ico")
        self.assertTrue(os.path.isfile(ico_path), f"app_icon.ico missing at {ico_path}")
        with Image.open(ico_path) as im:
            self.assertEqual(im.format, "ICO")
            sizes = im.info.get("sizes")
            self.assertIsNotNone(sizes)
            expected = {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}
            self.assertTrue(expected.issubset(sizes), f"Expected sizes {expected} not in {sizes}")

    def test_app_icon_png_exists_and_hires(self):
        """Verify app_icon.png is 256x256 RGBA."""
        png_path = get_resource_path("app_icon.png")
        self.assertTrue(os.path.isfile(png_path), f"app_icon.png missing at {png_path}")
        with Image.open(png_path) as im:
            self.assertEqual(im.size, (256, 256))
            self.assertEqual(im.mode, "RGBA")

    def test_extension_icons_exist(self):
        """Verify extension icons (16, 48, 128) are present and valid."""
        for sz in [16, 48, 128]:
            p = os.path.join(PROJECT_ROOT, "extension", "icons", f"icon{sz}.png")
            self.assertTrue(os.path.isfile(p), f"Extension icon missing: {p}")
            with Image.open(p) as im:
                self.assertEqual(im.size, (sz, sz))

    def test_gui_dpi_scaling_attributes(self):
        """Verify ModernFramelessGUI calculates dpi and dpi_scale properly."""
        root = tk.Tk()
        gui = ModernFramelessGUI(root)
        try:
            self.assertTrue(hasattr(gui, "dpi"))
            self.assertTrue(hasattr(gui, "dpi_scale"))
            self.assertGreaterEqual(gui.dpi, 72.0)
            self.assertGreaterEqual(gui.dpi_scale, 1.0)
            self.assertGreaterEqual(gui.width, 850)
            self.assertGreaterEqual(gui.height, 650)
            # Verify canvas heights scaled
            self.assertGreaterEqual(int(gui.canvas_prog.cget("height")), 22)
            self.assertGreaterEqual(int(gui.canvas_chunks.cget("height")), 30)
        finally:
            gui._cleanup_resources()
            try:
                root.destroy()
            except Exception:
                pass

    def test_safe_modal_dpi_scaling(self):
        """Verify SafeModalDialog dimensions scale with DPI."""
        root = tk.Tk()
        try:
            dlg = SafeModalDialog(root, title="Test Modal", message="Test Message", dialog_type="info")
            root.update()
            self.assertTrue(dlg.winfo_exists())
            self.assertGreater(dlg.winfo_width(), 0)
            self.assertGreater(dlg.winfo_height(), 0)
            dlg._on_ok()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_quality_modal_dpi_scaling_and_icon(self):
        """Verify QualitySelectionModal geometry and icon setup."""
        from turbo_downloader import VideoFormatOption
        root = tk.Tk()
        options = [
            VideoFormatOption(format_id="18", resolution_label="360p", height=360, ext="mp4", filesize_approx=1000000)
        ]
        theme = {
            "c_bg": "#0f172a",
            "c_panel": "#1e293b",
            "c_panel_light": "#334155",
            "c_border": "#475569",
            "c_accent": "#38bdf8",
            "c_accent_dark": "#0284c7",
            "c_success": "#10b981",
            "c_text_bright": "#f8fafc",
            "c_text_muted": "#94a3b8",
            "c_input_bg": "#090d16"
        }
        try:
            modal = QualitySelectionModal(root, "Test Video", 120, options, "test.mp4", theme, lambda opt, dest: None)
            root.update()
            self.assertTrue(modal.winfo_exists())
            self.assertGreaterEqual(modal.winfo_width(), 500)
            self.assertGreaterEqual(modal.winfo_height(), 400)
            modal._on_close()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_browser_integration_dialog_dpi_scaling_and_icon(self):
        """Verify _open_browser_integration_dialog opens with scaled geometry and closes cleanly."""
        root = tk.Tk()
        gui = ModernFramelessGUI(root)
        try:
            gui._open_browser_integration_dialog()
            root.update()
            # Find the toplevel
            top = None
            for child in root.winfo_children():
                if isinstance(child, tk.Toplevel):
                    top = child
                    break
            self.assertIsNotNone(top, "Browser integration dialog toplevel not found")
            self.assertTrue(top.winfo_exists())
            self.assertGreaterEqual(top.winfo_width(), 550)
            self.assertGreaterEqual(top.winfo_height(), 450)
            top.destroy()
        finally:
            gui._cleanup_resources()
            try:
                root.destroy()
            except Exception:
                pass

    def test_treeview_column_scaling_and_typography(self):
        """Verify treeview columns scale with dpi_scale."""
        root = tk.Tk()
        gui = ModernFramelessGUI(root)
        try:
            expected_range_w = max(200, int(250 * gui.dpi_scale))
            actual_w = gui.tree_chunks.column("range", "width")
            self.assertEqual(actual_w, expected_range_w)
            self.assertEqual(gui.txt_log.cget("font"), "Consolas 9")
        finally:
            gui._cleanup_resources()
            try:
                root.destroy()
            except Exception:
                pass

    def test_throttle_slider_scaling(self):
        """Verify dynamic slider length and width scale with DPI."""
        root = tk.Tk()
        gui = ModernFramelessGUI(root)
        try:
            expected_len = max(20, int(22 * gui.dpi_scale))
            expected_w = max(14, int(16 * gui.dpi_scale))
            self.assertEqual(int(gui.slider_speed.cget("sliderlength")), expected_len)
            self.assertEqual(int(gui.slider_speed.cget("width")), expected_w)
        finally:
            gui._cleanup_resources()
            try:
                root.destroy()
            except Exception:
                pass

    def test_resource_cleanup_on_destroy_event(self):
        """Verify destroying root directly automatically triggers _cleanup_resources and closes bridge server."""
        root = tk.Tk()
        gui = ModernFramelessGUI(root)
        server = gui.bridge_server
        self.assertTrue(server.is_running)
        root.destroy()
        self.assertTrue(gui._closing)
        self.assertIsNone(gui._refresh_job)
        self.assertFalse(server.is_running)


if __name__ == "__main__":
    unittest.main()
