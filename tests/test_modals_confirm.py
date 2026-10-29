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
            self.assertEqual(opened_in_main[0][1], "C:\\Downloads\\Test Video Title [1080p].mp4")
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
            self.assertIn("Pause", gui.btn_pause.cget("text"))
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


if __name__ == "__main__":
    unittest.main()
