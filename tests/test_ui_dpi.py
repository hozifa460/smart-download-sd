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

class TestClipboardNonBlockingInterception(unittest.TestCase):
    """
    Verification of TDM-style non-blocking clipboard interception:
    - Auto-populates URL and destination without locking the main window
    - Auto-starts or queues download without any modal popups or grab_set
    - SafeModalDialog and QualitySelectionModal never lock Tkinter event loop
    """
    def test_clipboard_interception_non_blocking_auto_start(self):
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            test_url = "https://speed.cloudflare.com/__down?bytes=10000000"

            with patch.object(gui, "ask_safe_yesno") as mock_yesno, \
                 patch.object(gui, "_on_start_download") as mock_start:
                gui._on_clipboard_url_detected(test_url)

                self.assertEqual(gui.entry_url.get(), test_url)
                dest_val = gui.entry_dest.get()
                self.assertTrue(len(dest_val) > 0)
                mock_yesno.assert_not_called()
                self.assertIsNotNone(gui._confirm_modal)
                self.assertIsNone(root.grab_current(), "Grab must not be held on root")
                # Open in Main App delegates download to main GUI:
                gui._confirm_modal._on_open_in_main()
                mock_start.assert_called_once()

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_interception_active_download_no_blocking(self):
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            gui.engine = MagicMock()
            gui.engine.is_running = True
            test_url = "https://example.com/queued_file.zip"

            with patch.object(gui, "ask_safe_yesno") as mock_yesno, \
                 patch.object(gui, "_on_start_download") as mock_start:
                gui._on_clipboard_url_detected(test_url)

                self.assertEqual(gui.entry_url.get(), test_url)
                mock_yesno.assert_not_called()
                mock_start.assert_not_called()
                self.assertIsNone(root.grab_current())

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_interception_youtube_smooth_start(self):
        """Verifies intercepted YouTube URLs trigger _start_youtube_download without blocking modal confirmation."""
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

            with patch.object(gui, "_start_youtube_download") as mock_yt_start, \
                 patch.object(gui, "ask_safe_yesno") as mock_yesno:
                gui._on_clipboard_url_detected(yt_url)

                self.assertEqual(gui.entry_url.get(), yt_url)
                dest_val = gui.entry_dest.get()
                self.assertTrue("youtube_video.mp4" in dest_val)
                mock_yesno.assert_not_called()
                mock_yt_start.assert_called_once()
                self.assertIsNone(root.grab_current(), "Main window must remain responsive and grab-free")

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_interception_social_media_smooth_start(self):
        """Verifies intercepted social media URLs (TikTok, Instagram, Facebook, Twitter/X) trigger format analysis."""
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            social_urls = [
                ("https://www.tiktok.com/@creator/video/7123456789012345678", "tiktok_video.mp4"),
                ("https://www.instagram.com/reel/C1234567890/", "instagram_video.mp4"),
                ("https://www.facebook.com/reel/1234567890", "facebook_video.mp4"),
                ("https://x.com/user/status/1234567890123456789", "twitter_video.mp4")
            ]

            for s_url, expected_fn in social_urls:
                with patch.object(gui, "_start_youtube_download") as mock_start, \
                     patch.object(gui, "ask_safe_yesno") as mock_yesno:
                    gui._on_clipboard_url_detected(s_url)

                    self.assertEqual(gui.entry_url.get(), s_url)
                    dest_val = gui.entry_dest.get()
                    self.assertTrue(expected_fn in dest_val, f"Expected {expected_fn} in {dest_val}")
                    mock_yesno.assert_not_called()
                    mock_start.assert_called_once()
                    self.assertIsNone(root.grab_current(), "Main window must remain grab-free")

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_social_media_url_recognition(self):
        """Verifies social media URL detection across TikTok, Instagram, Facebook, Twitter/X, Reddit, Vimeo."""
        test_cases = [
            ("https://www.tiktok.com/@user/video/7123456789012345678", "TikTok"),
            ("https://vt.tiktok.com/ZS1234567/", "TikTok"),
            ("https://www.instagram.com/reel/C1234567890/", "Instagram"),
            ("https://www.instagram.com/p/B1234567890/", "Instagram"),
            ("https://www.facebook.com/watch/?v=1234567890", "Facebook"),
            ("https://fb.watch/aBcDeFgHiJ/", "Facebook"),
            ("https://x.com/user/status/1234567890123456789", "Twitter / X"),
            ("https://twitter.com/user/status/1234567890123456789", "Twitter / X"),
        ]
        for url, expected_plat in test_cases:
            self.assertTrue(is_social_media_url(url), f"Failed is_social_media_url: {url}")
            self.assertTrue(is_media_url(url), f"Failed is_media_url: {url}")
            self.assertEqual(extract_media_platform(url), expected_plat)

    def test_clipboard_interception_one_click_mode(self):
        """Verifies _auto_start_clipboard=False populates fields without starting, ready for one-click manual start."""
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            gui._auto_start_clipboard = False
            test_url = "https://speed.cloudflare.com/__down?bytes=50000000"

            with patch.object(gui, "_on_start_download") as mock_start, \
                 patch.object(gui, "ask_safe_yesno") as mock_yesno:
                gui._on_clipboard_url_detected(test_url)

                self.assertEqual(gui.entry_url.get(), test_url)
                mock_yesno.assert_not_called()
                mock_start.assert_not_called()
                self.assertIsNone(root.grab_current())

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_modal_dialogs_never_trap_win32_input(self):
        root = tk.Tk()
        try:
            dlg = SafeModalDialog(root, "Title", "Message", dialog_type="info")
            self.assertIsNone(root.grab_current(), "SafeModalDialog must not hold active grab")
            dlg.grab_set()
            self.assertIsNone(root.grab_current(), "Explicit grab_set must be a safe no-op")
            dlg.destroy()

            dummy_opt = VideoFormatOption(
                format_id="test", ext="mp4", resolution_label="720p", height=720,
                filesize_approx=5000, fps=30, vcodec="h264", acodec="aac", is_audio_only=False
            )
            gui = ModernFramelessGUI(root)
            q_dlg = QualitySelectionModal(
                parent=root,
                video_title="YT Video",
                duration=120,
                options=[dummy_opt],
                default_dest_path="test_video.mp4",
                theme=gui._theme_dict(),
                on_confirm=lambda opt, p: None
            )
            gui._cleanup_resources()
            self.assertIsNone(root.grab_current(), "QualitySelectionModal must not hold active grab")
            q_dlg.grab_set()
            self.assertIsNone(root.grab_current(), "Explicit grab_set on quality modal must be a safe no-op")
            q_dlg.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

class TestQualitySelectionModalGUI(unittest.TestCase):
    """Verifies Tkinter QualitySelectionModal dialog behavior and edge case handling."""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.update_idletasks()
            cls.root.destroy()
        except Exception:
            pass

    def tearDown(self):
        try:
            for child in self.root.winfo_children():
                child.destroy()
            self.root.update_idletasks()
        except Exception:
            pass

    def test_modal_initialization_and_selection(self):
        from turbo_downloader import QualitySelectionModal, VideoFormatOption
        options = [
            VideoFormatOption(
                format_id="137+140",
                resolution_label="1080p (Full HD)",
                height=1080,
                ext="mp4",
                filesize_approx=55000000,
                fps=60,
                is_progressive=False,
                is_audio_only=False,
                video_url="https://video.com",
                audio_url="https://audio.com",
                note="60 FPS • Lossless Merge (FFmpeg)"
            ),
            VideoFormatOption(
                format_id="140",
                resolution_label="Audio Only (M4A)",
                height=0,
                ext="m4a",
                filesize_approx=5000000,
                fps=0,
                is_progressive=True,
                is_audio_only=True,
                video_url="https://audio.com",
                note="High Quality Audio"
            )
        ]

        confirmed = []
        theme = {
            "c_bg": "#1e293b",
            "c_panel": "#0f172a",
            "c_panel_light": "#334155",
            "c_border": "#475569",
            "c_accent": "#38bdf8",
            "c_accent_dark": "#0284c7",
            "c_success": "#10b981",
            "c_text_bright": "#f8fafc",
            "c_text_muted": "#94a3b8",
            "c_input_bg": "#0f172a"
        }

        modal = QualitySelectionModal(
            parent=self.root,
            video_title="NASA 4K Earth View",
            duration=300,
            options=options,
            default_dest_path="C:/Downloads/Earth.mp4",
            theme=theme,
            on_confirm=lambda opt, dest: confirmed.append((opt, dest))
        )

        # 1. First option is selected by default
        self.assertEqual(modal.selected_option.height, 1080)
        self.assertEqual(modal.entry_dest.get(), "C:/Downloads/Earth.mp4")

        # 2. Select audio option row and verify dynamic extension update
        modal.tree.selection_set("opt_1")
        modal._on_tree_select(None)
        self.assertEqual(modal.selected_option.height, 0)
        self.assertTrue(modal.entry_dest.get().endswith(".m4a"))

        # 3. Simulate confirming download
        modal._on_download()
        self.assertEqual(len(confirmed), 1)
        opt, dest = confirmed[0]
        self.assertEqual(opt.height, 0)
        self.assertTrue(dest.endswith(".m4a"))

    def test_modal_fallback_when_dest_cleared(self):
        from turbo_downloader import QualitySelectionModal, VideoFormatOption
        options = [
            VideoFormatOption(
                format_id="22",
                resolution_label="720p (HD)",
                height=720,
                ext="mp4",
                filesize_approx=20000000,
                fps=30,
                is_progressive=True,
                is_audio_only=False,
                video_url="https://video.com"
            )
        ]
        confirmed = []
        theme = {
            "c_bg": "#000", "c_panel": "#111", "c_panel_light": "#222", "c_border": "#333",
            "c_accent": "#444", "c_accent_dark": "#555", "c_success": "#666",
            "c_text_bright": "#fff", "c_text_muted": "#888", "c_input_bg": "#000"
        }
        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Fallback Test",
            duration=60,
            options=options,
            default_dest_path="C:/Downloads/test.mp4",
            theme=theme,
            on_confirm=lambda opt, dest: confirmed.append((opt, dest))
        )
        # Clear destination box
        modal.entry_dest.delete(0, "end")
        modal._on_download()

        self.assertEqual(len(confirmed), 1)
        _, dest = confirmed[0]
        self.assertTrue(len(dest) > 0, "Destination path must fallback cleanly when input is cleared")

    def test_modal_zorder_and_topmost_attributes(self):
        """Verifies QualitySelectionModal configures topmost and elevation to prevent hiding behind borderless parent."""
        from turbo_downloader import QualitySelectionModal, VideoFormatOption
        options = [
            VideoFormatOption(
                format_id="18",
                resolution_label="360p",
                height=360,
                ext="mp4",
                filesize_approx=1000000,
                fps=30,
                is_progressive=True,
                is_audio_only=False,
                video_url="https://video.com"
            )
        ]
        theme = {
            "c_bg": "#000", "c_panel": "#111", "c_panel_light": "#222", "c_border": "#333",
            "c_accent": "#444", "c_accent_dark": "#555", "c_success": "#666",
            "c_text_bright": "#fff", "c_text_muted": "#888", "c_input_bg": "#000"
        }
        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Topmost Test",
            duration=60,
            options=options,
            default_dest_path="C:/Downloads/test.mp4",
            theme=theme,
            on_confirm=lambda opt, dest: None
        )
        self.assertTrue(modal.attributes("-topmost"))
        self.root.update_idletasks()

    def test_ui_cancellation_and_error_handling_resets_state(self):
        """Verifies cancellation and error callbacks reset card_size, btn_start, and btn_cancel properly."""
        from turbo_downloader import ModernFramelessGUI
        import tkinter as tk

        class DummyUI:
            def __init__(self, root):
                self.root = root
                self._yt_cancel_event = threading.Event()
                self.engine = None
                self.btn_start = tk.Button(root)
                self.btn_pause = tk.Button(root)
                self.btn_cancel = tk.Button(root)
                self.card_size = tk.Label(root)
                self.c_panel_light = "#334155"
                self.logs = []

            def log(self, msg):
                self.logs.append(msg)

        dummy = DummyUI(self.root)
        dummy.btn_start.configure(state="disabled")
        dummy.btn_cancel.configure(state="normal")
        dummy.card_size.configure(text="Fetching available formats...")

        # 1. Trigger cancellation via ModernFramelessGUI method
        ModernFramelessGUI._on_cancel_download(dummy)
        self.assertTrue(dummy._yt_cancel_event.is_set())
        self.assertEqual(str(dummy.btn_start["state"]), "normal")
        self.assertEqual(str(dummy.btn_cancel["state"]), "disabled")
        self.assertEqual(dummy.card_size.cget("text"), "Ready")

        # 2. Trigger error callback via ModernFramelessGUI method
        with patch("tkinter.messagebox.showerror"):
            dummy.card_size.configure(text="Fetching available formats...")
            dummy.btn_start.configure(state="disabled")
            dummy.btn_cancel.configure(state="normal")
            ModernFramelessGUI._engine_error_cb(dummy, "Simulated stream extraction error")
            self.root.update()
            self.assertEqual(str(dummy.btn_start["state"]), "normal")
            self.assertEqual(str(dummy.btn_cancel["state"]), "disabled")
            self.assertEqual(dummy.card_size.cget("text"), "Ready")

    def test_modal_handles_none_inputs(self):
        """Verifies QualitySelectionModal handles video_title=None, duration=None, and default_dest_path=None safely."""
        from turbo_downloader import QualitySelectionModal, VideoFormatOption
        options = [
            VideoFormatOption(
                format_id="18",
                resolution_label="360p",
                height=360,
                ext="mp4",
                filesize_approx=1000000,
                fps=30,
                is_progressive=True,
                is_audio_only=False,
                video_url="https://video.com"
            )
        ]
        theme = {
            "c_bg": "#000", "c_panel": "#111", "c_panel_light": "#222", "c_border": "#333",
            "c_accent": "#444", "c_accent_dark": "#555", "c_success": "#666",
            "c_text_bright": "#fff", "c_text_muted": "#888", "c_input_bg": "#000"
        }
        # Should NOT raise TypeError or crash
        modal = QualitySelectionModal(
            parent=self.root,
            video_title=None,
            duration=None,
            options=options,
            default_dest_path=None,
            theme=theme,
            on_confirm=lambda opt, dest: None
        )
        self.assertEqual(modal.video_title, "YouTube Video")
        self.assertEqual(modal.duration, 0)
        self.assertEqual(modal.dest_path, "")

    def test_modal_fallback_dest_path_with_audio_format(self):
        """Verifies destination path fallback properly retains audio container extension."""
        from turbo_downloader import QualitySelectionModal, VideoFormatOption
        options = [
            VideoFormatOption(
                format_id="140",
                resolution_label="Audio Only (M4A)",
                height=0,
                ext="m4a",
                filesize_approx=5000000,
                fps=0,
                is_progressive=True,
                is_audio_only=True,
                video_url="https://audio.com"
            )
        ]
        confirmed = []
        theme = {
            "c_bg": "#000", "c_panel": "#111", "c_panel_light": "#222", "c_border": "#333",
            "c_accent": "#444", "c_accent_dark": "#555", "c_success": "#666",
            "c_text_bright": "#fff", "c_text_muted": "#888", "c_input_bg": "#000"
        }
        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Song Title",
            duration=120,
            options=options,
            default_dest_path="C:/Downloads/song.mp4",  # initially had .mp4
            theme=theme,
            on_confirm=lambda opt, dest: confirmed.append((opt, dest))
        )
        modal.entry_dest.delete(0, "end")  # clear it out
        modal._on_download()

        self.assertEqual(len(confirmed), 1)
        _, dest = confirmed[0]
        self.assertTrue(dest.lower().endswith(".m4a"), f"Fallback destination must end with .m4a, got {dest}")

    def test_ui_cancellation_dismisses_active_modal(self):
        """Verifies ModernFramelessGUI._on_cancel_download actively destroys and clears _quality_modal."""
        from turbo_downloader import ModernFramelessGUI
        import tkinter as tk

        class DummyUIWithModal:
            def __init__(self, root):
                self.root = root
                self._yt_cancel_event = threading.Event()
                self._quality_modal = tk.Toplevel(root)
                self.engine = None
                self.btn_start = tk.Button(root)
                self.btn_pause = tk.Button(root)
                self.btn_cancel = tk.Button(root)
                self.card_size = tk.Label(root)
                self.c_panel_light = "#334155"

            def log(self, msg):
                pass

        dummy = DummyUIWithModal(self.root)
        self.assertTrue(dummy._quality_modal.winfo_exists())

        ModernFramelessGUI._on_cancel_download(dummy)
        self.assertIsNone(dummy._quality_modal)
        self.assertEqual(dummy.card_size.cget("text"), "Ready")

    def test_engine_and_coordinator_rlock_and_snapshot(self):
        """Verifies TurboDownloadEngine and StreamDownloadCoordinator use re-entrant locks and snapshot methods."""
        from turbo_downloader import DownloadChunk, YouTubeStreamInfo
        engine = TurboDownloadEngine("https://example.com/file.zip", "test.zip")
        self.assertTrue(isinstance(engine._lock, type(threading.RLock())), "TurboDownloadEngine._lock must be threading.RLock")

        # Verify re-entrancy
        with engine._lock:
            with engine._lock:
                snapshot = engine.get_chunks_snapshot()
                self.assertEqual(snapshot, [])

        stream_info = YouTubeStreamInfo(
            video_id="test",
            title="test",
            clean_filename="test.mp4",
            is_progressive=True,
            video_url="https://example.com/stream",
            video_headers={},
            video_ext="mp4",
            video_resolution="720p",
            video_size=1000,
            audio_url=None,
            audio_headers={},
            audio_ext="",
            audio_size=0,
            duration=10,
            thumbnail_url="",
            is_audio_only=False
        )
        coordinator = StreamDownloadCoordinator(stream_info, "out.mp4")
        self.assertTrue(isinstance(coordinator._lock, type(threading.RLock())), "StreamDownloadCoordinator._lock must be threading.RLock")

        # Verify re-entrancy when no current_engine
        with coordinator._lock:
            with coordinator._lock:
                self.assertEqual(coordinator.get_chunks_snapshot(), [])

        # Assign child engine with chunks
        coordinator.current_engine = engine
        c1 = DownloadChunk(0, 0, 499, 200, "downloading", "p0")
        c2 = DownloadChunk(1, 500, 999, 100, "downloading", "p1")
        with engine._lock:
            engine.chunks.extend([c1, c2])

        # Verify coordinator gets chunks under lock without deadlock
        with coordinator._lock:
            snapshot = coordinator.get_chunks_snapshot()
            self.assertEqual(len(snapshot), 2)
            self.assertEqual(snapshot[0].chunk_id, 0)
            self.assertEqual(snapshot[1].chunk_id, 1)

    def test_refresh_chunk_displays_does_not_deadlock(self):
        """Verifies _refresh_chunk_displays does not deadlock when engine is StreamDownloadCoordinator."""
        from turbo_downloader import ModernFramelessGUI, DownloadChunk, YouTubeStreamInfo
        import tkinter as tk
        from tkinter import ttk

        class DummyGUI:
            def __init__(self, root):
                self.root = root
                self.width = 600
                self.height = 400
                self.c_bg = "#000"
                self.c_panel = "#111"
                self.c_border = "#222"
                self.c_input_bg = "#333"
                self.c_text_muted = "#888"
                self.c_text_bright = "#fff"
                self.c_accent = "#38bdf8"
                self.c_success = "#10b981"
                self.engine = None
                self.canvas_chunks = tk.Canvas(root, width=500, height=30)
                self.tree_chunks = ttk.Treeview(root, columns=("id", "range", "size", "downloaded", "pct", "status"))

            def _draw_chunk_segments(self, chunks):
                ModernFramelessGUI._draw_chunk_segments(self, chunks)

        gui = DummyGUI(self.root)
        stream_info = YouTubeStreamInfo(
            video_id="test",
            title="test",
            clean_filename="test.mp4",
            is_progressive=True,
            video_url="https://example.com/stream",
            video_headers={},
            video_ext="mp4",
            video_resolution="720p",
            video_size=1000,
            audio_url=None,
            audio_headers={},
            audio_ext="",
            audio_size=0,
            duration=10,
            thumbnail_url="",
            is_audio_only=False
        )
        coord = StreamDownloadCoordinator(stream_info, "out.mp4")
        child_engine = TurboDownloadEngine("https://example.com/stream", "out.mp4")
        c1 = DownloadChunk(0, 0, 499, 250, "downloading", "p0")
        c2 = DownloadChunk(1, 500, 999, 500, "completed", "p1")
        child_engine.chunks = [c1, c2]
        coord.current_engine = child_engine
        gui.engine = coord

        # Run _refresh_chunk_displays and verify it completes without deadlock
        ModernFramelessGUI._refresh_chunk_displays(gui)

        items = gui.tree_chunks.get_children()
        self.assertEqual(len(items), 2)
        self.assertIn("c_0", items)
        self.assertIn("c_1", items)

class TestClipboardSnifferAndUrlValidation(unittest.TestCase):
    """
    Automated tests verifying the TDM-style Clipboard Sniffer and URL validation:
    1. Validation of direct file download extensions across categories.
    2. YouTube video, short, and music URL recognition.
    3. Query parameter indicators (bytes=, dl=1, export=download, filename=).
    4. Path download endpoints (/download, /__down, /releases/download).
    5. Rejection of regular browsing sites, web document pages, and malformed inputs.
    6. GUI initialization, state defaults, and periodic timer scheduling.
    7. Clean toggle between Active and Paused with button and log updates.
    8. Strict duplicate prevention ensuring identical URLs don't trigger repeat prompts.
    9. Input population and safe confirmation dialog invocation.
    10. Fast YouTube URL dispatch to quality format resolver.
    11. Win32 ctypes clipboard reader resilience and error handling.
    """

    def test_is_downloadable_url_direct_extensions(self):
        """Verifies direct file extensions are recognized as downloadable URLs."""
        test_cases = [
            # Archives
            "https://downloads.example.org/files/archive.zip",
            "https://downloads.example.org/files/data.tar.gz",
            "https://downloads.example.org/files/backup.7z",
            "https://downloads.example.org/files/package.rar",
            # Binaries & Installers
            "https://example.com/releases/installer.exe",
            "https://example.com/packages/setup.msi",
            "https://example.com/os/linux_distro.iso",
            "https://example.com/app/mobile.apk",
            "https://example.com/mac/application.dmg",
            # Media: Video & Audio
            "https://media.example.com/movies/sample.mp4",
            "https://media.example.com/movies/video.mkv",
            "https://media.example.com/music/track.mp3",
            "https://media.example.com/audio/lossless.flac",
            # Documents & Ebooks
            "https://docs.example.org/papers/research.pdf",
            "https://docs.example.org/books/novel.epub",
            "https://docs.example.org/sheets/data.xlsx",
            # Images
            "https://images.example.com/assets/highres.png",
            "https://images.example.com/assets/photo.jpg",
            # Uppercase extensions and query parameters
            "https://example.com/FILES/SETUP.EXE?version=2.0",
            "https://example.com/video.mp4#t=30"
        ]
        for url in test_cases:
            self.assertTrue(is_downloadable_url(url), f"Failed to recognize valid downloadable URL: {url}")

    def test_is_downloadable_url_youtube_links(self):
        """Verifies all recognized YouTube formats are accepted by is_downloadable_url."""
        yt_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/1a2b3c4d5e6",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ"
        ]
        for url in yt_urls:
            self.assertTrue(is_downloadable_url(url), f"Failed to recognize YouTube URL: {url}")

    def test_is_downloadable_url_query_parameters(self):
        """Verifies query parameters signifying downloads are recognized."""
        query_cases = [
            "https://speed.cloudflare.com/__down?bytes=50000000",
            "https://drive.google.com/uc?id=12345&export=download",
            "https://www.dropbox.com/s/abcdef/project_files?dl=1",
            "https://example.com/api/v1/export?download=1",
            "https://example.com/api/v1/export?download=true",
            "https://storage.googleapis.com/bucket/object?response-content-disposition=attachment",
            "https://example.com/download.php?file=archive.zip",
            "https://example.com/handler?action=download&id=99",
            "https://example.com/media/stream?format=mp4&filename=clip.mp4"
        ]
        for url in query_cases:
            self.assertTrue(is_downloadable_url(url), f"Failed to recognize download query param: {url}")

    def test_is_downloadable_url_path_triggers(self):
        """Verifies download path endpoints and CDNs are recognized."""
        path_cases = [
            "https://github.com/user/repo/releases/download/v1.0/binary.bin",
            "https://example.com/downloads/v2/payload",
            "https://example.com/get_file/12345",
            "https://rr---sn-mock.googlevideo.com/videoplayback?expire=123"
        ]
        for url in path_cases:
            self.assertTrue(is_downloadable_url(url), f"Failed to recognize download path trigger: {url}")

    def test_is_downloadable_url_rejected_cases(self):
        """Verifies regular browsing pages, web markup, and invalid inputs are rejected."""
        invalid_cases = [
            # General websites
            "https://www.google.com",
            "https://google.com/",
            "https://en.wikipedia.org/wiki/Main_Page",
            "https://news.ycombinator.com",
            "https://github.com",
            # Web documents without download query params
            "https://example.com/index.html",
            "https://example.com/about.htm",
            "https://example.com/login.php",
            "https://example.com/portal.asp",
            "https://example.com/app.aspx",
            # Non-http schemes
            "mailto:support@example.com",
            "javascript:void(0)",
            "file:///C:/Users/test/file.txt",
            # Local filesystem paths
            "C:\\Downloads\\file.zip",
            "/home/user/downloads/archive.tar.gz",
            # Plain text & whitespace
            "Just some copied text with no url",
            "https://example.com with extra words in clipboard",
            "https://example.com/a\nhttps://example.com/b",
            "   ",
            "",
            None,
            12345,
            ["https://example.com/video.mp4"]
        ]
        for item in invalid_cases:
            self.assertFalse(is_downloadable_url(item), f"False positive on invalid/non-downloadable case: {item}")

    def test_clipboard_sniffer_gui_initialization_and_toggle(self):
        """Verifies ModernFramelessGUI initializes sniffer state and toggles active/paused."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            self.assertTrue(gui._clipboard_sniffer_active, "Clipboard sniffer should default to Active")
            self.assertIsNotNone(gui._clipboard_job, "Clipboard periodic timer job must be scheduled")
            self.assertEqual(gui.btn_clipboard_sniffer.cget("text"), "📋 Sniffer: Active")

            # Toggle to paused
            gui.toggle_clipboard_sniffer()
            self.assertFalse(gui._clipboard_sniffer_active)
            self.assertEqual(gui.btn_clipboard_sniffer.cget("text"), "📋 Sniffer: Paused")

            # Toggle back to active
            gui.toggle_clipboard_sniffer()
            self.assertTrue(gui._clipboard_sniffer_active)
            self.assertEqual(gui.btn_clipboard_sniffer.cget("text"), "📋 Sniffer: Active")

            gui._cleanup_resources()
            self.assertIsNone(gui._clipboard_job, "Clipboard job must be cleared on cleanup")
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_duplicate_prevention(self):
        """Verifies duplicate clipboard content does not re-trigger download interception."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            target_url = "https://example.com/duplicate_test_archive.zip"

            with patch.object(gui, "_on_clipboard_url_detected") as mock_detected:
                with patch("turbo_downloader.get_clipboard_text", return_value=target_url):
                    # First check should detect URL
                    gui._check_clipboard_now(force=True)
                    self.assertEqual(mock_detected.call_count, 1)

                    # Second check with identical clipboard content should be skipped
                    gui._check_clipboard_now(force=True)
                    self.assertEqual(mock_detected.call_count, 1, "Duplicate URL must not re-trigger")

                    # Third check with identical content still skipped
                    gui._check_clipboard_now(force=True)
                    self.assertEqual(mock_detected.call_count, 1, "Duplicate URL must not re-trigger")

                    # Changing clipboard URL triggers a new prompt
                    new_url = "https://example.com/another_archive.7z"
                    with patch("turbo_downloader.get_clipboard_text", return_value=new_url):
                        gui._check_clipboard_now(force=True)
                        self.assertEqual(mock_detected.call_count, 2)

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_populates_entries_and_prompts(self):
        """Verifies _on_clipboard_url_detected populates inputs and opens TDM confirmation modal non-blockingly."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            test_url = "https://speed.cloudflare.com/__down?bytes=50000000"

            with patch.object(gui, "ask_safe_yesno") as mock_yesno, \
                 patch.object(gui, "_on_start_download") as mock_start:
                gui._on_clipboard_url_detected(test_url)

                # Verify URL entry updated
                self.assertEqual(gui.entry_url.get(), test_url)
                # Verify Destination entry populated with a valid file path
                dest_val = gui.entry_dest.get()
                self.assertTrue(len(dest_val) > 0)
                self.assertTrue(dest_val.endswith(".bin") or "__down" in dest_val)

                # Verify legacy blocking modal dialog is not invoked
                mock_yesno.assert_not_called()
                # Verify TDM confirmation dialog was displayed
                self.assertIsNotNone(gui._confirm_modal)
                self.assertTrue(gui._confirm_modal.winfo_exists())
                # Verify no window or widget has trapped the grab
                self.assertIsNone(root.grab_current(), "No widget should hold grab")
                # Download has not started yet until confirmed
                mock_start.assert_not_called()

                # User chooses to open in main app via modal
                gui._confirm_modal._on_open_in_main()
                mock_start.assert_called_once()
                self.assertIsNone(gui._confirm_modal)

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_confirmation_dialog_cancel(self):
        """Verifies cancelling the TDM confirmation modal closes it cleanly without initiating download."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            test_url = "https://example.com/software/tool.zip"

            with patch.object(gui, "_on_start_download") as mock_start:
                gui._on_clipboard_url_detected(test_url)

                self.assertIsNotNone(gui._confirm_modal)
                self.assertTrue(gui._confirm_modal.winfo_exists())
                mock_start.assert_not_called()

                # Cancel via modal close button
                gui._confirm_modal._on_close()
                mock_start.assert_not_called()
                self.assertIsNone(gui._confirm_modal)

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_active_transfer_queues_without_modal(self):
        """Verifies clipboard sniffer populates URL without interrupting running engine or popping modals."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            gui.engine = MagicMock()
            gui.engine.is_running = True
            test_url = "https://speed.cloudflare.com/__down?bytes=25000000"

            with patch.object(gui, "ask_safe_yesno") as mock_yesno, \
                 patch.object(gui, "_on_start_download") as mock_start:
                gui._on_clipboard_url_detected(test_url)

                self.assertEqual(gui.entry_url.get(), test_url)
                self.assertIsNone(gui._confirm_modal)
                mock_yesno.assert_not_called()
                mock_start.assert_not_called()
                self.assertIsNone(root.grab_current())

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_modal_dialogs_never_trap_grab(self):
        """Verifies SafeModalDialog, QualitySelectionModal, and DownloadConfirmationModal never lock application grab."""
        import tkinter as tk
        from turbo_downloader import SafeModalDialog, QualitySelectionModal, DownloadConfirmationModal, VideoFormatOption
        root = tk.Tk()
        try:
            # 1. SafeModalDialog grab test
            dlg = SafeModalDialog(root, "Notice", "Test Message", dialog_type="info")
            self.assertIsNone(root.grab_current(), "SafeModalDialog must not hold active Tk grab")
            dlg.grab_set()  # Attempt explicit grab
            self.assertIsNone(root.grab_current(), "Explicit grab_set must be a safe no-op")
            dlg.destroy()

            # 2. QualitySelectionModal grab test
            dummy_opt = VideoFormatOption(
                format_id="test", ext="mp4", resolution_label="1080p", height=1080,
                filesize_approx=1000, fps=30, vcodec="h264", acodec="aac", is_audio_only=False
            )
            gui = ModernFramelessGUI(root)
            q_dlg = QualitySelectionModal(
                parent=root,
                video_title="Test Video",
                duration=60,
                options=[dummy_opt],
                default_dest_path="test.mp4",
                theme=gui._theme_dict(),
                on_confirm=lambda opt, p: None
            )
            self.assertIsNone(root.grab_current(), "QualitySelectionModal must not hold active Tk grab")
            q_dlg.grab_set()
            self.assertIsNone(root.grab_current(), "Explicit grab_set on quality modal must be a safe no-op")
            q_dlg.destroy()

            # 3. DownloadConfirmationModal grab test
            c_dlg = DownloadConfirmationModal(
                parent=root,
                url="https://example.com/test.zip",
                default_dest_path="test.zip",
                theme=gui._theme_dict(),
                on_confirm=lambda p: None
            )
            self.assertIsNone(root.grab_current(), "DownloadConfirmationModal must not hold active Tk grab")
            c_dlg.grab_set()
            self.assertIsNone(root.grab_current(), "Explicit grab_set on confirmation modal must be a safe no-op")
            c_dlg.destroy()

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_youtube_triggers_start(self):
        """Verifies YouTube URLs from clipboard automatically start resolution & modal flow via _start_youtube_download."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

            with patch.object(gui, "_start_youtube_download") as mock_yt_start:
                gui._on_clipboard_url_detected(yt_url)
                self.assertEqual(gui.entry_url.get(), yt_url)
                dest_val = gui.entry_dest.get()
                self.assertTrue("youtube_video.mp4" in dest_val)
                mock_yt_start.assert_called_once()
                args, _ = mock_yt_start.call_args
                self.assertEqual(args[0], yt_url)
                self.assertEqual(args[1], dest_val)
                self.assertEqual(args[2], 8)
                self.assertEqual(args[3], 0.0)
                self.assertIsNone(root.grab_current(), "Main window must not hold active grab")

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_youtube_active_task_queues(self):
        """Verifies YouTube URLs copied while transfer is active are safely queued in inputs without modal interruption."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            gui.engine = MagicMock()
            gui.engine.is_running = True
            yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

            with patch.object(gui, "_start_youtube_download") as mock_yt_start, \
                 patch.object(gui, "ask_safe_yesno") as mock_yesno:
                gui._on_clipboard_url_detected(yt_url)
                self.assertEqual(gui.entry_url.get(), yt_url)
                mock_yt_start.assert_not_called()
                mock_yesno.assert_not_called()
                self.assertIsNone(root.grab_current())

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_auto_start_disabled(self):
        """Verifies disabling _auto_start_clipboard populates fields for one-click start without auto-downloading."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            gui._auto_start_clipboard = False
            test_url = "https://speed.cloudflare.com/__down?bytes=50000000"
            yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

            with patch.object(gui, "_on_start_download") as mock_start, \
                 patch.object(gui, "_start_youtube_download") as mock_yt_start:
                # 1. Normal file
                gui._on_clipboard_url_detected(test_url)
                self.assertEqual(gui.entry_url.get(), test_url)
                mock_start.assert_not_called()

                # 2. YouTube file
                gui._on_clipboard_url_detected(yt_url)
                self.assertEqual(gui.entry_url.get(), yt_url)
                mock_yt_start.assert_not_called()

                self.assertIsNone(root.grab_current(), "UI controls must remain completely responsive")

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_skips_when_paused(self):
        """Verifies periodic tick does not inspect clipboard when sniffer is paused."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            gui._clipboard_sniffer_active = False

            with patch.object(gui, "_check_clipboard_now") as mock_check:
                gui._check_clipboard_tick()
                mock_check.assert_not_called()

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_win32_clipboard_get_actual_text_retrieval(self):
        """Verifies get_clipboard_text and _win32_clipboard_get retrieve actual text without truncation."""
        import tkinter as tk
        root = tk.Tk()
        try:
            sample_text = "https://example.com/verified_archive_download.zip"
            root.clipboard_clear()
            root.clipboard_append(sample_text)
            root.update()

            res = get_clipboard_text(root)
            self.assertEqual(res, sample_text, "Failed to read clipboard text via Tkinter root")

            # Direct Win32 ctypes fallback test (without root Tkinter handle)
            res_win32 = get_clipboard_text(None)
            if sys.platform.startswith("win"):
                self.assertEqual(res_win32, sample_text, "Win32 direct clipboard API must return matching text")
            else:
                self.assertIsNone(res_win32)
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_derive_download_filename_comprehensive(self):
        """Verifies intelligent destination filename derivation across complex URL formats."""
        test_matrix = [
            # MediaFire / intermediate segment format
            ("https://www.mediafire.com/file/xyz123/myfile.zip/file", "myfile.zip"),
            # Web script with query string parameter
            ("https://example.com/download.php?file=annual_report.pdf", "annual_report.pdf"),
            ("https://example.com/export.aspx?filename=backup_data.sql", "backup_data.sql"),
            # Unicode / percent-encoded Arabic filename
            ("https://example.com/download?file=%D9%81%D9%8A%D8%AF%D9%8A%D9%88.mp4", "فيديو.mp4"),
            # Direct archives with multi-part extensions
            ("https://example.com/dist/archive.tar.gz", "archive.tar.gz"),
            ("https://example.com/dist/archive.tar.xz", "archive.tar.xz"),
            # Cloudflare extensionless endpoint with fallback to .bin
            ("https://speed.cloudflare.com/__down?bytes=50000000", "down.bin"),
            # YouTube URL
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube_video.mp4"),
            # Invalid or empty fallback
            ("", "download.bin"),
            (None, "download.bin")
        ]
        for url, expected_fn in test_matrix:
            derived = derive_download_filename(url)
            self.assertEqual(derived, expected_fn, f"Incorrect derived filename for URL {url}: got {derived}, expected {expected_fn}")

    def test_is_downloadable_url_script_endpoints_and_ports(self):
        """Verifies script endpoints, localhost with ports, and wrapped URLs are properly detected."""
        valid_edge_cases = [
            "http://localhost:8080/test.zip",
            "http://127.0.0.1:8000/download.iso",
            "https://example.com/download.php?file_id=123",
            "https://example.com/download.aspx?id=55",
            "https://example.com/get_file.php?asset=99",
            "https://www.mediafire.com/file/xyz123/myfile.zip/file",
            "https://example.com/dist/package.zst",
            "https://example.com/dist/app.appimage",
            "<https://example.com/enclosed_url.zip>",
            "\"https://example.com/quoted_url.exe\"",
            "https://example.com/sentence_url.mp4."
        ]
        for url in valid_edge_cases:
            self.assertTrue(is_downloadable_url(url), f"Failed to recognize valid edge URL: {url}")

    def test_youtube_cancel_event_on_start_download(self):
        """Verifies starting a new download or YouTube resolution cancels any pending YouTube thread."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            # Create a mock pending resolve event
            gui._yt_cancel_event = threading.Event()
            old_event = gui._yt_cancel_event

            # Starting another YouTube download should signal cancellation of prior event
            with patch.object(threading.Thread, "start"):
                gui._start_youtube_download("https://www.youtube.com/watch?v=12345", "test.mp4", 8, 0.0)
                self.assertTrue(old_event.is_set(), "Old YouTube cancel event must be signaled")
                self.assertIsNot(gui._yt_cancel_event, old_event, "New event instance must be created")

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

class TestTDMDownloadConfirmationDialog(unittest.TestCase):
    """Verifies the TDM-style Download Confirmation Dialog GUI, categories, and actions."""

    def test_get_file_category_and_icon(self):
        from turbo_downloader import get_file_category_and_icon
        test_cases = [
            ("archive.zip", ("Compressed", "📦")),
            ("archive.tar.gz", ("Compressed", "📦")),
            ("package.7z", ("Compressed", "📦")),
            ("disk.iso", ("Compressed", "📦")),
            ("setup.exe", ("Programs", "⚙️")),
            ("installer.msi", ("Programs", "⚙️")),
            ("app.apk", ("Programs", "⚙️")),
            ("movie.mp4", ("Video", "🎬")),
            ("stream.mkv", ("Video", "🎬")),
            ("clip.webm", ("Video", "🎬")),
            ("song.mp3", ("Audio", "🎵")),
            ("audio.flac", ("Audio", "🎵")),
            ("manual.pdf", ("Documents", "📄")),
            ("notes.docx", ("Documents", "📄")),
            ("data.csv", ("Documents", "📄")),
            ("photo.png", ("Images", "🖼️")),
            ("graphic.webp", ("Images", "🖼️")),
            ("unknown_data.bin", ("Programs", "⚙️")),
            ("stream_data.xyz", ("General", "📥")),
            ("https://example.com/file.rar?token=123", ("Compressed", "📦")),
        ]
        for item, expected in test_cases:
            cat, icon = get_file_category_and_icon(item)
            self.assertEqual((cat, icon), expected, f"Failed for {item}")

    def test_confirmation_dialog_initialization_and_fields(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            url = "https://example.com/releases/v1.0.0/AppSetup.exe"
            default_dest = os.path.join(os.path.expanduser("~"), "Downloads", "AppSetup.exe")
            dlg = DownloadConfirmationModal(
                parent=root,
                url=url,
                default_dest_path=default_dest,
                theme={"c_bg": "#121212", "c_panel": "#1e1e1e"}
            )
            self.assertEqual(dlg.entry_url.get(), url)
            self.assertEqual(dlg.entry_dest.get(), default_dest)
            self.assertEqual(dlg.lbl_filename_val.cget("text"), "AppSetup.exe")
            self.assertIn("Programs", dlg.lbl_category_val.cget("text"))
            self.assertIn("⚙️", dlg.lbl_category_val.cget("text"))
            self.assertIsNone(root.grab_current(), "Modal must never capture window grab")
            dlg.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_browse_action(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            url = "https://example.com/files/document.pdf"
            default_dest = "document.pdf"
            dlg = DownloadConfirmationModal(
                parent=root,
                url=url,
                default_dest_path=default_dest
            )
            new_target = "C:/Users/test/Documents/new_report.zip"
            with patch("tkinter.filedialog.asksaveasfilename", return_value=new_target):
                dlg._on_browse()
                self.assertEqual(dlg.entry_dest.get(), new_target)
                self.assertEqual(dlg.lbl_filename_val.cget("text"), "new_report.zip")
                self.assertIn("Compressed", dlg.lbl_category_val.cget("text"))
                self.assertIn("📦", dlg.lbl_category_val.cget("text"))
            dlg.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_keyrelease_updates_meta(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            url = "https://example.com/files/download"
            dlg = DownloadConfirmationModal(
                parent=root,
                url=url,
                default_dest_path="download.bin"
            )
            dlg.entry_dest.delete(0, tk.END)
            dlg.entry_dest.insert(0, "C:/Music/favorite_track.mp3")
            dlg._on_dest_key_release()
            self.assertEqual(dlg.lbl_filename_val.cget("text"), "favorite_track.mp3")
            self.assertIn("Audio", dlg.lbl_category_val.cget("text"))
            self.assertIn("🎵", dlg.lbl_category_val.cget("text"))
            dlg.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_confirm_callback(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            confirmed_path = []
            def _on_confirm(p):
                confirmed_path.append(p)

            dlg = DownloadConfirmationModal(
                parent=root,
                url="https://example.com/file.zip",
                default_dest_path="C:/Downloads/file.zip",
                on_confirm=_on_confirm
            )
            dlg.entry_dest.delete(0, tk.END)
            dlg.entry_dest.insert(0, "C:/CustomPath/my_file.zip")
            dlg._on_start()
            self.assertTrue(dlg._confirmed)
            self.assertEqual(confirmed_path, ["C:/CustomPath/my_file.zip"])
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_cancel_callback(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            cancelled = []
            def _on_cancel():
                cancelled.append(True)

            dlg = DownloadConfirmationModal(
                parent=root,
                url="https://example.com/file.zip",
                default_dest_path="C:/Downloads/file.zip",
                on_cancel=_on_cancel
            )
            dlg._on_close()
            self.assertFalse(dlg._confirmed)
            self.assertEqual(cancelled, [True])
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_null_and_empty_inputs(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            dlg = DownloadConfirmationModal(
                parent=None,
                url="",
                default_dest_path="",
                theme=None
            )
            self.assertIsNotNone(dlg.entry_url)
            self.assertIsNotNone(dlg.entry_dest)
            dlg.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

class TestBackgroundAndMinimizedLaunch(unittest.TestCase):
    """Verifies silent background launch, IPC/sniffer preservation, and window restore on intercept."""

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_start_hidden_flag_withdraws_root(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            self.assertFalse(self.root.winfo_viewable(), "Window must be hidden/withdrawn on start_hidden=True")
            self.assertTrue(gui.bridge_server.is_running, "Loopback IPC bridge server must remain active")
            self.assertTrue(gui._clipboard_sniffer_active, "Clipboard URL sniffer must remain active")
            self.assertIsNotNone(gui._clipboard_job, "Periodic clipboard sniffer job must be scheduled")

            # Verify restore_window
            gui.restore_window()
            self.assertFalse(gui._start_hidden)
            self.root.update_idletasks()
            self.assertTrue(self.root.winfo_viewable(), "Window must be visible after restore_window()")
        finally:
            gui._cleanup_resources()

    def test_cli_flags_detection(self):
        flags = [
            (["turbo_downloader.py", "--minimized"], True),
            (["turbo_downloader.py", "--background"], True),
            (["turbo_downloader.py"], False)
        ]
        for argv, expected_hidden in flags:
            with patch.object(sys, "argv", argv):
                sub_root = tk.Tk()
                sub_root.withdraw()
                try:
                    gui = ModernFramelessGUI(sub_root)
                    self.assertEqual(gui._start_hidden, expected_hidden)
                    gui._cleanup_resources()
                finally:
                    try:
                        sub_root.update_idletasks()
                        sub_root.destroy()
                    except Exception:
                        pass

    def test_clipboard_detection_suppresses_window_and_shows_modal(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            target_url = "https://speed.cloudflare.com/__down?bytes=25000000"
            gui._on_clipboard_url_detected(target_url)

            # Main window must remain hidden (suppressed)
            self.assertTrue(gui._start_hidden)
            self.assertEqual(self.root.state(), "withdrawn")
            # Confirmation modal must be created and active
            self.assertIsNotNone(gui._confirm_modal)
            self.assertTrue(gui._confirm_modal.winfo_exists())
            self.assertEqual(gui.entry_url.get().strip(), target_url)

            # User chooses 'Open in Main App': restores window
            with patch.object(gui, "_on_start_download") as mock_start:
                gui._confirm_modal._on_open_in_main()
                mock_start.assert_called_once()
            self.assertFalse(gui._start_hidden)
            self.assertEqual(self.root.state(), "normal")
        finally:
            if gui._confirm_modal:
                try:
                    gui._confirm_modal.destroy()
                except Exception:
                    pass
            gui._cleanup_resources()

    def test_browser_download_suppresses_window_and_shows_modal(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            target_url = "https://speed.cloudflare.com/files/archive_bundle.zip"
            payload = {
                "url": target_url,
                "filename": "archive_bundle.zip",
                "start_immediately": False
            }
            gui._apply_browser_download(payload)

            # Main window must remain hidden (suppressed)
            self.assertTrue(gui._start_hidden)
            self.assertEqual(self.root.state(), "withdrawn")
            # Confirmation modal must be displayed
            self.assertIsNotNone(gui._confirm_modal)
            self.assertTrue(gui._confirm_modal.winfo_exists())
            self.assertEqual(gui.entry_url.get().strip(), target_url)

            # User chooses 'Open in Main App': restores window
            with patch.object(gui, "_on_start_download") as mock_start:
                gui._confirm_modal._on_open_in_main()
                mock_start.assert_called_once()
            self.assertFalse(gui._start_hidden)
            self.assertEqual(self.root.state(), "normal")
        finally:
            if gui._confirm_modal:
                try:
                    gui._confirm_modal.destroy()
                except Exception:
                    pass
            gui._cleanup_resources()

    def test_gui_startup_toggle_button(self):
        gui = ModernFramelessGUI(self.root, start_hidden=False)
        try:
            self.assertTrue(hasattr(gui, "btn_startup"))
            # Initial state
            init_state = is_startup_enabled()
            if init_state:
                self.assertEqual(gui.btn_startup.cget("text"), "🚀 Boot: ON")
            else:
                self.assertEqual(gui.btn_startup.cget("text"), "🚀 Boot: OFF")

            # Toggle state
            toggled = gui.toggle_startup_setting()
            self.assertEqual(toggled, not init_state)
            if toggled:
                self.assertEqual(gui.btn_startup.cget("text"), "🚀 Boot: ON")
            else:
                self.assertEqual(gui.btn_startup.cget("text"), "🚀 Boot: OFF")

            # Toggle back to restore
            gui.toggle_startup_setting()
            self.assertEqual(is_startup_enabled(), init_state)
        finally:
            gui._cleanup_resources()

    def test_browser_integration_dialog_startup_card(self):
        gui = ModernFramelessGUI(self.root, start_hidden=False)
        try:
            gui._open_browser_integration_dialog()
            self.assertTrue(hasattr(gui, "_update_dlg_startup_ui"))
            # Test triggering update callback
            gui._update_dlg_startup_ui()
        finally:
            gui._cleanup_resources()

    def test_cli_flags_case_insensitivity_and_variants(self):
        variants = [
            ["turbo_downloader.py", "-minimized"],
            ["turbo_downloader.py", "--MINIMIZED"],
            ["turbo_downloader.py", "/minimized"],
            ["turbo_downloader.py", "-background"],
            ["turbo_downloader.py", "--BACKGROUND"],
            ["turbo_downloader.py", "/background"],
        ]
        for v in variants:
            with patch.object(sys, "argv", v):
                sub_root = tk.Tk()
                sub_root.withdraw()
                try:
                    gui = ModernFramelessGUI(sub_root)
                    self.assertTrue(gui._start_hidden, f"Flag {v} failed to activate _start_hidden")
                    self.assertTrue(gui._was_started_hidden, f"Flag {v} failed to set _was_started_hidden")
                    gui._cleanup_resources()
                finally:
                    try:
                        sub_root.update_idletasks()
                        sub_root.destroy()
                    except Exception:
                        pass

    def test_was_started_hidden_preserves_confirmation_modal(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            gui._auto_start_clipboard = False
            payload = {
                "url": "https://speed.cloudflare.com/__down?bytes=50000000",
                "filename": "big_file.bin",
                "start_immediately": True
            }
            gui._apply_browser_download(payload)
            self.assertIsNotNone(gui._confirm_modal)
            self.assertTrue(gui._confirm_modal.winfo_exists())
        finally:
            if gui._confirm_modal:
                try:
                    gui._confirm_modal.destroy()
                except Exception:
                    pass
            gui._cleanup_resources()

    def test_single_instance_show_endpoint(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            self.assertFalse(self.root.winfo_viewable())

            # Request /show via loopback HTTP bridge
            req = urllib.request.Request("http://127.0.0.1:9242/show")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(body.get("status"), "ok")

            for _ in range(50):
                gui._drain_dispatch_queue()
                self.root.update()
                if not gui._start_hidden:
                    break
                time.sleep(0.03)

            self.assertFalse(gui._start_hidden)
            self.assertTrue(self.root.winfo_viewable())
        finally:
            gui._cleanup_resources()

    def test_notify_running_instance_helper(self):
        # 1. When GUI is active and listening
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            handled = notify_running_instance(show=True)
            self.assertTrue(handled, "notify_running_instance should succeed when instance is listening")
            for _ in range(50):
                gui._drain_dispatch_queue()
                self.root.update()
                if not gui._start_hidden:
                    break
                time.sleep(0.03)
            self.assertFalse(gui._start_hidden)
        finally:
            gui._cleanup_resources()

        # 2. When no GUI is listening
        handled_stopped = notify_running_instance(show=True)
        self.assertFalse(handled_stopped, "notify_running_instance should return False when no server is running")

    def test_clipboard_detection_youtube_url_keeps_window_hidden(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            with patch.object(gui, "_start_youtube_download") as mock_yt:
                gui._on_clipboard_url_detected("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
                self.assertTrue(gui._start_hidden)
                self.assertEqual(self.root.state(), "withdrawn")
                mock_yt.assert_called_once()
        finally:
            gui._cleanup_resources()

class TestSystemTrayAndBackgroundMinimization(unittest.TestCase):
    """
    Automated test suite verifying Windows System Tray Icon & Background Minimization:
    1. Settings persistence: load_settings, save_settings, get_setting, set_setting defaults & round-trip.
    2. SystemTrayManager initialization & 4-item right-click context menu structure.
    3. Tray menu dynamic labels (Clipboard Sniffer & Start with Windows).
    4. Tray menu callbacks: Restore window, Toggle sniffer, Toggle startup, Exit completely.
    5. Window Close (✕) action minimizes to tray when minimize_to_tray is True (default).
    6. Window Close (✕) action exits completely when minimize_to_tray is False.
    7. GUI Settings toggle: toggle_minimize_to_tray_setting updates preference and UI.
    8. Seamless wakeup from tray on clipboard URL interception with DownloadConfirmationModal.
    9. Seamless wakeup from tray on browser extension download with DownloadConfirmationModal.
    10. Clean exit: stops tray icon, cancels timers, stops loopback server, and destroys window.
    """

    def setUp(self):
        self.root = None

    def tearDown(self):
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None

    def test_settings_persistence(self):
        cur = get_setting("minimize_to_tray", True)
        self.assertIn(cur, (True, False))
        set_setting("minimize_to_tray", False)
        self.assertFalse(get_setting("minimize_to_tray", True))
        set_setting("minimize_to_tray", True)
        self.assertTrue(get_setting("minimize_to_tray", False))

    def test_tray_manager_menu_structure(self):
        class MockApp:
            def __init__(self):
                self._clipboard_sniffer_active = True
                self.restored = False
                self.exited = False
            def restore_window(self):
                self.restored = True
            def toggle_clipboard_sniffer(self):
                self._clipboard_sniffer_active = not self._clipboard_sniffer_active
            def toggle_startup_setting(self):
                return True
            def exit_completely(self):
                self.exited = True
            def dispatch_to_main_thread(self, fn, *args, **kwargs):
                fn(*args, **kwargs)

        app = MockApp()
        tray = SystemTrayManager(app)
        menu = tray._build_menu()
        self.assertIsNotNone(menu)
        items = list(menu.items)
        self.assertEqual(len(items), 4)

        # 1. Open Turbo Downloader (default action for single / double click)
        self.assertEqual(items[0].text, "🖥️ Open Smart Download")
        self.assertTrue(items[0].default)

        # 2. Clipboard Sniffer
        self.assertIn("Clipboard Sniffer: Active", items[1].text)

        # 3. Start with Windows
        self.assertIn("Start with Windows", items[2].text)

        # 4. Exit Completely
        self.assertEqual(items[3].text, "❌ Exit Completely")

    def test_tray_manager_menu_callbacks(self):
        class MockApp:
            def __init__(self):
                self._clipboard_sniffer_active = True
                self.restored = False
                self.exited = False
                self.sniffer_toggled = False
                self.startup_toggled = False
            def restore_window(self):
                self.restored = True
            def toggle_clipboard_sniffer(self):
                self._clipboard_sniffer_active = not self._clipboard_sniffer_active
                self.sniffer_toggled = True
            def toggle_startup_setting(self):
                self.startup_toggled = True
                return True
            def exit_completely(self):
                self.exited = True
            def dispatch_to_main_thread(self, fn, *args, **kwargs):
                fn(*args, **kwargs)

        app = MockApp()
        tray = SystemTrayManager(app)
        menu = tray._build_menu()

        # Invoke default (single/double click) or item 0
        menu(None)
        self.assertTrue(app.restored)

        # Invoke sniffer toggle
        menu.items[1](None)
        self.assertTrue(app.sniffer_toggled)
        self.assertFalse(app._clipboard_sniffer_active)
        self.assertIn("Clipboard Sniffer: Paused", menu.items[1].text)

        # Invoke startup toggle
        menu.items[2](None)
        self.assertTrue(app.startup_toggled)

        # Invoke exit
        menu.items[3](None)
        self.assertTrue(app.exited)

    def test_close_button_minimizes_to_tray_when_enabled(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        try:
            gui.set_minimize_to_tray(True)
            self.assertTrue(gui.minimize_to_tray)
            self.assertEqual(self.root.state(), "normal")

            # Click close button
            gui._on_close()

            # Window must be withdrawn (minimized to tray)
            self.assertEqual(self.root.state(), "withdrawn")
            # Loopback server and clipboard sniffer must remain active
            self.assertTrue(gui.bridge_server.is_running)
            self.assertTrue(gui._clipboard_sniffer_active)
        finally:
            gui.exit_completely()

    def test_close_button_exits_when_disabled(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        gui.set_minimize_to_tray(False)
        self.assertFalse(gui.minimize_to_tray)

        # Click close button
        gui._on_close()

        # Root must be destroyed
        try:
            exists = bool(self.root and self.root.winfo_exists())
        except Exception:
            exists = False
        self.assertFalse(exists)
        self.root = None

    def test_gui_settings_tray_card_and_toggle(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        try:
            gui.set_minimize_to_tray(True)
            self.assertTrue(gui.minimize_to_tray)

            # Toggle setting
            res = gui.toggle_minimize_to_tray_setting()
            self.assertFalse(res)
            self.assertFalse(gui.minimize_to_tray)
            self.assertFalse(get_setting("minimize_to_tray", True))

            # Open settings dialog
            gui._open_browser_integration_dialog()
            self.assertTrue(hasattr(gui, "_update_dlg_tray_ui"))
            gui._update_dlg_tray_ui()

            # Toggle back to True
            res2 = gui.toggle_minimize_to_tray_setting()
            self.assertTrue(res2)
            self.assertTrue(gui.minimize_to_tray)
            self.assertTrue(get_setting("minimize_to_tray", False))
        finally:
            gui.exit_completely()

    def test_clipboard_detection_keeps_tray_state_and_shows_modal(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        try:
            gui.set_minimize_to_tray(True)
            gui._on_close()
            self.assertEqual(self.root.state(), "withdrawn")

            # Intercept download URL from clipboard
            target_url = "https://speed.cloudflare.com/__down?bytes=15000000"
            gui._on_clipboard_url_detected(target_url)

            # Main window must remain withdrawn in tray
            self.assertEqual(self.root.state(), "withdrawn")
            # TDM confirmation modal must be open
            self.assertIsNotNone(gui._confirm_modal)
            self.assertTrue(gui._confirm_modal.winfo_exists())
            self.assertEqual(gui.entry_url.get().strip(), target_url)

            # Clicking 'Open in Main App' restores the main window
            gui._confirm_modal._on_open_in_main()
            self.assertEqual(self.root.state(), "normal")
        finally:
            if gui._confirm_modal:
                try:
                    gui._confirm_modal.destroy()
                except Exception:
                    pass
            gui.exit_completely()

    def test_browser_download_keeps_tray_state_and_shows_modal(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        try:
            gui.set_minimize_to_tray(True)
            gui._on_close()
            self.assertEqual(self.root.state(), "withdrawn")

            # Browser extension pushes download payload
            target_url = "https://speed.cloudflare.com/files/release_pkg.zip"
            gui._apply_browser_download({
                "url": target_url,
                "filename": "release_pkg.zip",
                "start_immediately": False
            })

            # Main window must remain withdrawn in tray
            self.assertEqual(self.root.state(), "withdrawn")
            # TDM confirmation modal must be open
            self.assertIsNotNone(gui._confirm_modal)
            self.assertTrue(gui._confirm_modal.winfo_exists())
            self.assertEqual(gui.entry_url.get().strip(), target_url)

            # Clicking 'Open in Main App' restores the main window
            gui._confirm_modal._on_open_in_main()
            self.assertEqual(self.root.state(), "normal")
        finally:
            if gui._confirm_modal:
                try:
                    gui._confirm_modal.destroy()
                except Exception:
                    pass
            gui.exit_completely()

    def test_clean_exit_completely_teardown(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        self.assertTrue(gui.bridge_server.is_running)
        gui.exit_completely()

        # Bridge server stopped
        self.assertIsNone(gui.bridge_server)
        # Root destroyed
        try:
            exists = bool(self.root and self.root.winfo_exists())
        except Exception:
            exists = False
        self.assertFalse(exists)
        self.root = None

class TestTDMConfirmationAndStandaloneProgress(unittest.TestCase):
    """
    Verifies TDM-style confirmation modal features and standalone progress handling:
    1. Speed limiter parsing across various units (Unlimited, KB/s, MB/s, custom numbers).
    2. Connection count selector (1, 2, 4, 8, 16, 32) and speed selector in DownloadConfirmationModal.
    3. Three action buttons: 'Start Download', 'Open in Main App', and 'Cancel'.
    4. Transition to standalone compact progress view and canvas progress bar rendering.
    5. Standalone download controls: Pause / Resume toggling and Cancel aborting engine.
    6. Completion state actions: 'Open File', 'Open Folder', and 'Close'.
    7. QualitySelectionModal 'Open in Main App' action.
    """

    def setUp(self):
        self.root = tk.Tk()
        self.theme = {
            "c_bg": "#121214",
            "c_panel": "#1b1b1f",
            "c_panel_light": "#25252b",
            "c_border": "#2c2c34",
            "c_accent": "#6366f1",
            "c_accent_dark": "#4f46e5",
            "c_success": "#10b981",
            "c_warning": "#f59e0b",
            "c_error": "#ef4444",
            "c_text_bright": "#ffffff",
            "c_text_muted": "#9ca3af",
            "c_input_bg": "#18181b",
        }

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_speed_limit_parser(self):
        """Tests parsing of speed limit presets and custom strings to bytes per second."""
        self.assertEqual(parse_speed_limit("Unlimited"), 0.0)
        self.assertEqual(parse_speed_limit("none"), 0.0)
        self.assertEqual(parse_speed_limit("256 KB/s"), 256 * 1024.0)
        self.assertEqual(parse_speed_limit("512 KB/s"), 512 * 1024.0)
        self.assertEqual(parse_speed_limit("1 MB/s"), 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("2 MB/s"), 2 * 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("5 MB/s"), 5 * 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("10 MB/s"), 10 * 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("20 MB/s"), 20 * 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("1024"), 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("500000"), 500000.0)
        self.assertEqual(parse_speed_limit(""), 0.0)
        self.assertEqual(parse_speed_limit("invalid_limit"), 0.0)

    def test_confirmation_dialog_controls_and_options(self):
        """Verifies DownloadConfirmationModal thread and speed options and helper getters."""
        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/testfile.iso",
            default_dest_path="C:\\Downloads\\testfile.iso",
            theme=self.theme,
            on_confirm=lambda *a: None,
            default_connections=8,
            default_speed_limit=0.0
        )
        try:
            # Check thread count combobox values
            thread_values = list(modal.combo_threads["values"])
            for t in ["1", "2", "4", "8", "16", "32"]:
                self.assertIn(t, thread_values)
            self.assertEqual(modal.get_max_connections(), 8)

            modal.combo_threads.set("16")
            self.assertEqual(modal.get_max_connections(), 16)

            modal.combo_threads.set("invalid")
            self.assertEqual(modal.get_max_connections(), 8)  # Fallback

            # Check speed limiter combobox values
            speed_values = list(modal.combo_speed["values"])
            self.assertIn("Unlimited", speed_values)
            self.assertIn("1 MB/s", speed_values)
            self.assertEqual(modal.get_speed_limit_bytes(), 0.0)

            modal.combo_speed.set("2 MB/s")
            self.assertEqual(modal.get_speed_limit_bytes(), 2 * 1024 * 1024.0)

            # Check that grab is not held
            self.assertIsNone(self.root.grab_current())
        finally:
            try:
                modal.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_three_action_buttons(self):
        """Verifies presence of Start Download, Open in Main App, and Cancel buttons."""
        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/software.zip",
            default_dest_path="C:\\Downloads\\software.zip",
            theme=self.theme,
            on_confirm=lambda *a: None
        )
        try:
            self.assertTrue(hasattr(modal, "btn_start"))
            self.assertTrue(hasattr(modal, "btn_open_app"))
            self.assertTrue(hasattr(modal, "btn_cancel"))
            self.assertIn("Start Download", modal.btn_start.cget("text"))
            self.assertIn("Open in Main App", modal.btn_open_app.cget("text"))
            self.assertIn("Cancel", modal.btn_cancel.cget("text"))
        finally:
            try:
                modal.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_transition_to_progress_view(self):
        """Verifies transitioning modal into standalone progress view and updating progress."""
        started = []
        def mock_start_in_window(dest, conns, speed, modal_ref):
            started.append((dest, conns, speed, modal_ref))

        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/data.tar.gz",
            default_dest_path="C:\\Downloads\\data.tar.gz",
            theme=self.theme,
            on_confirm=lambda *a: None,
            on_start_in_window=mock_start_in_window
        )
        try:
            self.assertFalse(modal.is_in_progress_view)
            modal._on_start_in_window()
            self.assertTrue(modal.is_in_progress_view)
            self.assertEqual(len(started), 1)

            # Check progress view widgets exist
            self.assertTrue(hasattr(modal, "canvas_prog"))
            self.assertTrue(hasattr(modal, "lbl_prog_size"))
            self.assertTrue(hasattr(modal, "lbl_prog_speed"))
            self.assertTrue(hasattr(modal, "lbl_prog_eta"))
            self.assertTrue(hasattr(modal, "lbl_prog_threads"))
            self.assertTrue(hasattr(modal, "btn_pause_resume"))
            self.assertTrue(hasattr(modal, "btn_cancel_prog"))

            # Update progress
            modal.update_progress(5000000, 10000000, 1048576, "00:00:05", 8)
            self.root.update()
            self.assertIn("50.0%", modal.lbl_prog_size.cget("text"))
            self.assertIn("00:00:05", modal.lbl_prog_eta.cget("text"))
            self.assertIn("8 Active", modal.lbl_prog_threads.cget("text"))
        finally:
            try:
                modal.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_pause_resume_and_cancel_standalone(self):
        """Verifies pause/resume toggling and cancellation in standalone modal view."""
        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/archive.7z",
            default_dest_path="C:\\Downloads\\archive.7z",
            theme=self.theme,
            on_confirm=lambda *a: None
        )
        try:
            modal.show_progress_view()
            mock_engine = MagicMock()
            mock_engine.is_running = True
            mock_engine.is_paused = False
            modal.engine = mock_engine

            # Pause
            modal._on_pause_resume()
            mock_engine.pause.assert_called_once()
            self.assertIn("Resume", modal.btn_pause_resume.cget("text"))

            # Resume
            mock_engine.is_paused = True
            modal._on_pause_resume()
            mock_engine.resume.assert_called_once()
            self.assertIn("Pause", modal.btn_pause_resume.cget("text"))

            # Cancel
            modal._on_close()
            mock_engine.cancel.assert_called_once()
        finally:
            try:
                if modal.winfo_exists():
                    modal.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_completion_actions(self):
        """Verifies completion state actions: Open File, Open Folder, and Close."""
        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/app.exe",
            default_dest_path="C:\\Downloads\\app.exe",
            theme=self.theme,
            on_confirm=lambda *a: None
        )
        try:
            modal.show_progress_view()
            test_file = "C:\\Downloads\\app.exe"
            modal.on_download_complete(test_file, 1048576, 2.5)
            self.root.update()

            self.assertTrue(modal.is_completed)
            self.assertTrue(hasattr(modal, "btn_open_file"))
            self.assertTrue(hasattr(modal, "btn_open_folder"))
            self.assertTrue(hasattr(modal, "btn_close_prog"))

            with patch("turbo_downloader.open_downloaded_file") as mock_open_file, \
                 patch("turbo_downloader.open_containing_folder") as mock_open_folder:
                modal._on_open_file()
                mock_open_file.assert_called_once_with(test_file)

                modal._on_open_folder()
                mock_open_folder.assert_called_once_with(test_file)
        finally:
            try:
                modal.destroy()
            except Exception:
                pass

    def test_quality_selection_modal_open_in_main(self):
        """Verifies QualitySelectionModal 'Open in Main App' button invokes the on_open_in_main callback."""
        opened_in_main = []
        def mock_open_in_main(opt, dest):
            opened_in_main.append((opt, dest))

        opt1 = VideoFormatOption(
            format_id="137+140",
            resolution_label="1080p (Full HD)",
            height=1080,
            ext="mp4",
            filesize_approx=50000000,
            fps=30,
            vcodec="avc1",
            acodec="mp4a"
        )
        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Test Video Title",
            duration=120,
            options=[opt1],
            default_dest_path="C:\\Downloads\\Test Video Title.mp4",
            theme=self.theme,
            on_confirm=lambda *a: None,
            on_open_in_main=mock_open_in_main
        )
        try:
            self.assertTrue(hasattr(modal, "btn_open_app"))
            self.assertIn("Open in Main App", modal.btn_open_app.cget("text"))
            modal._on_open_in_main()
            self.assertEqual(len(opened_in_main), 1)
            self.assertEqual(opened_in_main[0][0], opt1)
            self.assertEqual(opened_in_main[0][1], "C:\\Downloads\\Test Video Title.mp4")
        finally:
            try:
                if modal.winfo_exists():
                    modal.destroy()
            except Exception:
                pass

    def test_modal_viewable_when_parent_is_iconic_or_withdrawn(self):
        """Verifies DownloadConfirmationModal and QualitySelectionModal remain viewable when parent is iconic/withdrawn."""
        self.root.withdraw()
        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/file.bin",
            default_dest_path="C:\\Downloads\\file.bin",
            theme=self.theme
        )
        try:
            self.root.update()
            modal.update()
            self.assertEqual(modal.state(), "normal")
            self.assertEqual(modal.winfo_viewable(), 1, "DownloadConfirmationModal must be viewable on screen when parent is hidden")
        finally:
            try:
                modal.destroy()
            except Exception:
                pass

        opt = VideoFormatOption(
            format_id="137",
            resolution_label="1080p",
            height=1080,
            ext="mp4",
            filesize_approx=5000,
            fps=30,
            vcodec="h264",
            acodec="aac"
        )
        qmodal = QualitySelectionModal(
            parent=self.root,
            video_title="Test YT",
            duration=60,
            options=[opt],
            default_dest_path="C:\\Downloads\\Test.mp4",
            theme=self.theme,
            on_confirm=lambda *a: None
        )
        try:
            self.root.update()
            qmodal.update()
            self.assertEqual(qmodal.state(), "normal")
            self.assertEqual(qmodal.winfo_viewable(), 1, "QualitySelectionModal must be viewable on screen when parent is hidden")
        finally:
            try:
                qmodal.destroy()
            except Exception:
                pass

    def test_open_in_main_while_download_active_transitions_cleanly_without_restart(self):
        """Verifies clicking 'Open in Main App' while download is active restores main window without restarting transfer."""
        gui = ModernFramelessGUI(self.root)
        try:
            mock_engine = MagicMock()
            mock_engine.is_running = True
            mock_engine.is_paused = False
            gui.engine = mock_engine

            modal = DownloadConfirmationModal(
                parent=self.root,
                url="https://example.com/large.iso",
                default_dest_path="C:\\Downloads\\large.iso",
                theme=self.theme,
                parent_app=gui
            )
            modal.engine = mock_engine
            modal.show_progress_view()
            self.assertTrue(modal.is_in_progress_view)

            with patch.object(gui, "_on_start_download") as mock_start_dl:
                modal._on_open_in_main()
                mock_start_dl.assert_not_called()

            self.assertEqual(self.root.state(), "normal")
            self.assertEqual(gui.btn_start.cget("state"), "disabled")
            self.assertEqual(gui.btn_cancel.cget("state"), "normal")
            self.assertEqual(gui.btn_pause.cget("text"), "⏸ Pause")
        finally:
            gui.exit_completely()

    def test_standalone_modal_cancellation_restores_main_window_controls(self):
        """Verifies cancelling active download in standalone modal restores main GUI btn_start to normal."""
        gui = ModernFramelessGUI(self.root)
        try:
            mock_engine = MagicMock()
            mock_engine.is_running = True
            gui.engine = mock_engine
            gui.btn_start.configure(state="disabled")
            gui.btn_cancel.configure(state="normal")

            modal = DownloadConfirmationModal(
                parent=self.root,
                url="https://example.com/test.zip",
                default_dest_path="C:\\Downloads\\test.zip",
                theme=self.theme,
                parent_app=gui
            )
            gui._confirm_modal = modal
            modal.engine = mock_engine
            modal.show_progress_view()

            modal._on_close()

            mock_engine.cancel.assert_called_once()
            self.assertIsNone(gui.engine)
            self.assertEqual(gui.btn_start.cget("state"), "normal", "Main GUI btn_start must be re-enabled on modal cancel")
            self.assertEqual(gui.btn_cancel.cget("state"), "disabled")
            self.assertIn("Cancelled", gui.card_size.cget("text"))
        finally:
            gui.exit_completely()

    def test_duplicate_completion_dialog_suppressed_when_modal_present(self):
        """Verifies _engine_complete_cb suppresses redundant popup dialog when standalone modal is present."""
        gui = ModernFramelessGUI(self.root)
        try:
            with patch.object(gui, "show_safe_info") as mock_safe_info:
                # With suppress_dialog=True (standalone modal active)
                gui._engine_complete_cb("C:\\Downloads\\file.bin", 1024, 1.0, suppress_dialog=True)
                self.root.update()
                mock_safe_info.assert_not_called()

                # Without suppress_dialog (normal main window completion)
                gui._engine_complete_cb("C:\\Downloads\\file.bin", 1024, 1.0, suppress_dialog=False)
                self.root.update()
                mock_safe_info.assert_called_once()
        finally:
            gui.exit_completely()

    def test_subsequent_clipboard_url_does_not_destroy_active_modal(self):
        """Verifies copying a new URL while modal is actively downloading does not destroy it."""
        gui = ModernFramelessGUI(self.root)
        try:
            modal = DownloadConfirmationModal(
                parent=self.root,
                url="https://example.com/active.zip",
                default_dest_path="C:\\Downloads\\active.zip",
                theme=self.theme,
                parent_app=gui
            )
            gui._confirm_modal = modal
            modal.show_progress_view()
            self.assertTrue(modal.is_in_progress_view)

            # A subsequent download confirmation request arrives
            gui._show_download_confirmation_dialog("https://example.com/second.zip", "C:\\Downloads\\second.zip")

            # The original active modal must still be alive!
            self.assertTrue(modal.winfo_exists())
            self.assertIs(gui._confirm_modal, modal)
        finally:
            gui.exit_completely()

    def test_pause_resume_synchronizes_parent_app_button(self):
        """Verifies toggling pause/resume in standalone modal synchronizes parent_app btn_pause text."""
        gui = ModernFramelessGUI(self.root)
        try:
            mock_engine = MagicMock()
            mock_engine.is_running = True
            mock_engine.is_paused = False
            gui.engine = mock_engine

            modal = DownloadConfirmationModal(
                parent=self.root,
                url="https://example.com/sync.zip",
                default_dest_path="C:\\Downloads\\sync.zip",
                theme=self.theme,
                parent_app=gui
            )
            modal.engine = mock_engine
            modal.show_progress_view()

            # Pause in modal
            modal._on_pause_resume()
            self.assertIn("Resume", gui.btn_pause.cget("text"))

            # Resume in modal
            mock_engine.is_paused = True
            modal._on_pause_resume()
            self.assertIn("Pause", gui.btn_pause.cget("text"))
        finally:
            gui.exit_completely()

class TestInstantFetchingLinkToast(unittest.TestCase):
    """Verifies instant (< 50ms) fetching link toast indicator, dark styling, grab-free architecture, and smooth modal transition."""

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        # Warm up Windows font cache and Tkinter window subsystem
        try:
            _w = FetchingLinkToast(self.root, url="https://example.com/warmup", theme={
                "c_bg": "#0f172a", "c_panel": "#1e293b", "c_panel_light": "#334155",
                "c_border": "#475569", "c_accent": "#38bdf8", "c_accent_dark": "#0284c7",
                "c_success": "#10b981", "c_danger": "#ef4444", "c_text_bright": "#f8fafc",
                "c_text_muted": "#94a3b8", "c_input_bg": "#0b1220"
            })
            _w.close()
        except Exception:
            pass
        self.theme = {
            "c_bg": "#0f172a",
            "c_panel": "#1e293b",
            "c_panel_light": "#334155",
            "c_border": "#475569",
            "c_accent": "#38bdf8",
            "c_accent_dark": "#0284c7",
            "c_success": "#10b981",
            "c_danger": "#ef4444",
            "c_text_bright": "#f8fafc",
            "c_text_muted": "#94a3b8",
            "c_input_bg": "#0b1220"
        }

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_toast_creation_under_50ms_and_properties(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        t0 = time.perf_counter()
        toast = FetchingLinkToast(self.root, url=url, theme=self.theme)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        try:
            self.assertLess(elapsed_ms, 200.0, f"Fetching toast took {elapsed_ms:.1f}ms, must be < 200ms")
            self.assertTrue(toast.winfo_exists())
            self.assertIn("جاري جلب وتحليل الرابط", toast.lbl_ar.cget("text"))
            self.assertIn("Fetching link information", toast.lbl_en.cget("text"))
            self.assertIn("youtube.com", toast.lbl_domain.cget("text"))
            # Grab-free verification
            toast.grab_set()
            toast.grab_set_global()
        finally:
            toast.close()

    def test_toast_animations_and_clean_close(self):
        toast = FetchingLinkToast(self.root, url="https://example.com/test_video.mp4", theme=self.theme)
        try:
            toast._animate_pulse()
            toast._animate_dots()
            self.assertTrue(toast.winfo_exists())
        finally:
            toast.close()
            self.assertFalse(toast.winfo_exists())

    def test_toast_cancel_callback_invoked(self):
        cancelled = []
        toast = FetchingLinkToast(
            self.root,
            url="https://www.youtube.com/watch?v=test",
            theme=self.theme,
            on_cancel=lambda: cancelled.append(True)
        )
        toast._on_cancel_click()
        self.assertEqual(cancelled, [True])
        self.assertFalse(toast.winfo_exists())

    def test_integration_fetching_toast_in_hidden_youtube_download(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui.is_window_hidden_or_minimized())
            sample_opt = VideoFormatOption(
                format_id="137",
                resolution_label="1080p",
                height=1080,
                ext="mp4",
                filesize_approx=50000000,
                fps=30,
                vcodec="avc1",
                acodec="none"
            )
            fake_info = {"title": "Test Video Title", "duration": 120}

            with patch("turbo_downloader.YouTubeResolver.extract_format_options", return_value=(fake_info, [sample_opt])):
                with patch("youtube_resolver.YouTubeResolver.extract_format_options", return_value=(fake_info, [sample_opt])):
                    gui._start_youtube_download("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "output.mp4")
                    # Immediately, fetching toast must be created (< 50ms)
                    self.assertIsNotNone(gui._fetching_toast)
                    self.assertTrue(gui._fetching_toast.winfo_exists())

                    # Wait for resolver thread to complete and post _show_modal
                    for _ in range(35):
                        time.sleep(0.04)
                        gui._drain_dispatch_queue()
                        gui.root.update()
                        if gui._quality_modal:
                            break

                    # Fetching toast must now be smoothly closed and quality modal presented
                    self.assertIsNone(gui._fetching_toast)
                    self.assertIsNotNone(gui._quality_modal)
                    self.assertTrue(gui._quality_modal.winfo_exists())
        finally:
            if getattr(gui, "_quality_modal", None):
                try:
                    gui._quality_modal.destroy()
                except Exception:
                    pass
            gui._cleanup_resources()

    def test_integration_fetching_toast_cancelled_by_user(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            with patch("turbo_downloader.YouTubeResolver.extract_format_options", side_effect=lambda url: time.sleep(0.5)):
                with patch("youtube_resolver.YouTubeResolver.extract_format_options", side_effect=lambda url: time.sleep(0.5)):
                    gui._start_youtube_download("https://www.youtube.com/watch?v=slow_fetch", "output.mp4")
                    self.assertIsNotNone(gui._fetching_toast)

                    # Cancel fetching toast
                    gui._fetching_toast._on_cancel_click()
                    self.assertTrue(gui._yt_cancel_event.is_set())
                    self.assertIsNone(gui._fetching_toast)
                    self.assertIsNone(gui._last_clipboard_url, "Cancelling fetching toast must clear last clipboard URL")
                    self.assertEqual(gui.btn_start.cget("state"), "normal", "btn_start must be restored to normal")
                    self.assertEqual(gui.card_size.cget("text"), "Ready", "card_size must be restored to Ready")
                    time.sleep(0.1)
                    gui.root.update()
                    self.assertIsNone(gui._quality_modal)
        finally:
            gui._cleanup_resources()

    def test_toast_direct_destroy_cancels_jobs_cleanly(self):
        toast = FetchingLinkToast(self.root, url="https://example.com/test_destroy.mp4", theme=self.theme)
        self.assertTrue(toast.winfo_exists())
        self.assertIsNotNone(toast._pulse_job)
        self.assertIsNotNone(toast._dot_job)
        toast.destroy()
        self.assertFalse(toast.winfo_exists())
        self.assertIsNone(toast._pulse_job)
        self.assertIsNone(toast._dot_job)

    def test_toast_empty_url_graceful_fallback(self):
        toast = FetchingLinkToast(self.root, url="", theme=self.theme)
        try:
            self.assertTrue(toast.winfo_exists())
            self.assertIn("remote", toast.lbl_domain.cget("text"))
        finally:
            toast.destroy()

class TestClipboardSequenceRecopying(unittest.TestCase):
    """Verifies that re-copying the same link (clipboard sequence increment) re-triggers URL processing."""

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_recopy_same_url_detected_when_sequence_changes(self):
        gui = ModernFramelessGUI(self.root)
        try:
            url = "https://example.com/recopy_test.zip"
            detected_urls = []
            gui._on_clipboard_url_detected = lambda u: detected_urls.append(u)

            with patch("turbo_downloader.IS_WINDOWS", True):
                with patch("turbo_downloader.get_clipboard_text", return_value=url):
                    # 1. First copy event at seq=100
                    with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=100):
                        gui._check_clipboard_now()
                        self.assertEqual(len(detected_urls), 1)

                    # 2. Subsequent tick without copying (seq still 100) -> ignored
                    with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=100):
                        gui._check_clipboard_now()
                        self.assertEqual(len(detected_urls), 1)

                    # 3. User explicitly re-copies the exact same link (seq increments to 101)
                    with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=101):
                        gui._check_clipboard_now()
                        self.assertEqual(len(detected_urls), 2, "Re-copying identical link with sequence change must trigger")

                    # 4. Another tick with seq=101 -> ignored
                    with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=101):
                        gui._check_clipboard_now()
                        self.assertEqual(len(detected_urls), 2)
        finally:
            gui._cleanup_resources()

    def test_startup_clipboard_not_permanently_blocked(self):
        url = "https://example.com/startup_existing.zip"
        # Sniffer starts up with URL already in clipboard
        with patch("turbo_downloader.IS_WINDOWS", True):
            with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=50):
                with patch("turbo_downloader.get_clipboard_text", return_value=url):
                    gui = ModernFramelessGUI(self.root)
                    try:
                        detected_urls = []
                        gui._on_clipboard_url_detected = lambda u: detected_urls.append(u)

                        # Tick 1: sequence unchanged -> no trigger
                        gui._check_clipboard_now()
                        self.assertEqual(len(detected_urls), 0)

                        # User copies the same URL after launch -> seq=51 -> triggers!
                        with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=51):
                            gui._check_clipboard_now()
                            self.assertEqual(len(detected_urls), 1, "User copying startup clipboard URL after launch must trigger")
                    finally:
                        gui._cleanup_resources()

    def test_modal_cancellation_clears_last_clipboard_url(self):
        gui = ModernFramelessGUI(self.root)
        try:
            url = "https://example.com/cancel_and_recopy.zip"
            gui._last_clipboard_url = url
            gui.clear_last_clipboard_url()
            self.assertIsNone(gui._last_clipboard_url)
        finally:
            gui._cleanup_resources()

    def test_clear_last_clipboard_url_allows_reprocessing(self):
        gui = ModernFramelessGUI(self.root)
        try:
            url = "https://example.com/clear_recopy_test.zip"
            detected_urls = []
            gui._on_clipboard_url_detected = lambda u: detected_urls.append(u)
            gui._last_clipboard_url = url

            with patch("turbo_downloader.get_clipboard_text", return_value=url):
                # Duplicate is initially suppressed
                gui._check_clipboard_now(force=True)
                self.assertEqual(len(detected_urls), 0)

                # Clear last clipboard url (as done when closing/cancelling a modal)
                gui.clear_last_clipboard_url()

                # Now checking clipboard processes the URL
                gui._check_clipboard_now(force=True)
                self.assertEqual(len(detected_urls), 1, "Clearing last clipboard URL must allow re-processing")
        finally:
            gui._cleanup_resources()

    def test_quality_modal_close_clears_last_clipboard_url(self):
        gui = ModernFramelessGUI(self.root)
        try:
            url = "https://www.youtube.com/watch?v=cancel_modal_test"
            gui._last_clipboard_url = url
            modal = QualitySelectionModal(
                parent=self.root,
                video_title="Cancel Test Video",
                duration=120,
                options=[],
                default_dest_path="test.mp4",
                theme=gui._theme_dict(),
                on_confirm=lambda opt, dest: None,
                on_cancel=None,
                parent_app=gui
            )
            modal._on_close()
            self.assertIsNone(gui._last_clipboard_url, "Closing QualitySelectionModal must clear _last_clipboard_url")
        finally:
            gui._cleanup_resources()

    def test_download_confirmation_modal_close_clears_last_clipboard_url(self):
        gui = ModernFramelessGUI(self.root)
        try:
            url = "https://example.com/confirm_cancel.zip"
            gui._last_clipboard_url = url
            modal = DownloadConfirmationModal(
                parent=self.root,
                url=url,
                default_dest_path="confirm_cancel.zip",
                theme=gui._theme_dict(),
                parent_app=gui
            )
            modal._on_close()
            self.assertIsNone(gui._last_clipboard_url, "Closing DownloadConfirmationModal must clear _last_clipboard_url")
        finally:
            gui._cleanup_resources()

class TestBackgroundStartupNotificationAndTray(unittest.TestCase):
    """Verifies that launching with --minimized or --background displays notification and sleek toast."""

    def setUp(self):
        import tkinter as tk
        self._orig_toast_env = os.environ.pop("SD_DISABLE_STARTUP_TOAST", None)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        if self._orig_toast_env is not None:
            os.environ["SD_DISABLE_STARTUP_TOAST"] = self._orig_toast_env
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_background_notification_toast_creation_and_auto_dismiss(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            gui._show_background_startup_notification()

            # Root window must remain hidden/withdrawn
            self.assertFalse(self.root.winfo_viewable())

            # Background toast must be displayed
            self.assertIsNotNone(gui._bg_toast)
            self.assertTrue(gui._bg_toast.winfo_exists())

            # Text content validation
            found_text = False
            for w in gui._bg_toast.winfo_children():
                for sub in w.winfo_children():
                    if isinstance(sub, tk.Frame):
                        for lbl in sub.winfo_children():
                            if "active in the background" in str(lbl.cget("text")):
                                found_text = True
            self.assertTrue(found_text, "Background notification must display 'active in the background'")

            # Dismissal
            gui._dismiss_bg_toast()
            self.assertIsNone(gui._bg_toast)
        finally:
            gui._cleanup_resources()

    def test_update_ui_language_with_active_speed_limit(self):
        """Verifies _update_ui_language formats active speed limit without NameError."""
        from smart_download.locales.i18n import set_current_language
        set_current_language("en")
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            # Active speed limit
            gui.speed_limit = 5.0 * 1024 * 1024
            gui._update_ui_language()
            active_text = gui.lbl_active_limit.cget("text")
            self.assertIn("5.00 MB/s", active_text)

            # Unlimited speed limit
            gui.speed_limit = 0.0
            gui._update_ui_language()
            active_text_unlimited = gui.lbl_active_limit.cget("text")
            self.assertIn("Unlimited", active_text_unlimited)
        finally:
            gui._cleanup_resources()

    def test_build_title_bar_icon_dim_scaling(self):
        """Verifies _build_title_bar scales icon_dim based on dpi_scale without NameError."""
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(hasattr(gui, "_title_icon_photo"))
            self.assertIsNotNone(gui._title_icon_photo)
        finally:
            gui._cleanup_resources()


if __name__ == "__main__":
    unittest.main()
