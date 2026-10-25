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
