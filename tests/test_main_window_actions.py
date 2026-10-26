"""
Automated Test Module for Smart Download (SD)
"""
import os, sys, tempfile, time, json, shutil, struct, hashlib, ssl, re, unittest, threading, subprocess
import http.server, socketserver, urllib.request, urllib.error, urllib.parse
from unittest.mock import patch, MagicMock
from typing import List, Dict, Optional, Tuple, Any

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
    tk, ttk = None, None

try:
    from PIL import Image, ImageTk
except Exception:
    Image, ImageTk = None, None

from youtube_resolver import *
from browser_bridge import BrowserBridgeServer, BrowserBridgeHandler, DEFAULT_BRIDGE_PORT
from native_messaging_host import read_message, send_message, handle_payload
from register_browser import *
import installer
from turbo_downloader import *


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
                # Open in Main App delegates download to main GUI without auto-starting:
                gui._confirm_modal._on_open_in_main()
                mock_start.assert_not_called()
                self.assertEqual(gui.btn_start["state"], "normal")
                gui._on_start_download()
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
                mock_start.assert_not_called()
                self.assertIsNone(gui._confirm_modal)
                self.assertEqual(gui.btn_start["state"], "normal")
                gui._on_start_download()
                mock_start.assert_called_once()

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



if __name__ == "__main__":
    unittest.main()
