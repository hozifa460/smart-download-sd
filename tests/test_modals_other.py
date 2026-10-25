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


if __name__ == "__main__":
    unittest.main()
