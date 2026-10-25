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

class MockHeaderInspectHandler(http.server.BaseHTTPRequestHandler):
    """Echoes received request headers for verification."""
    last_headers = {}

    def do_HEAD(self):
        MockHeaderInspectHandler.last_headers = dict(self.headers)
        self.send_response(200)
        self.send_header("Content-Length", "1024")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        MockHeaderInspectHandler.last_headers = dict(self.headers)
        self.send_response(200)
        self.send_header("Content-Length", "1024")
        self.end_headers()
        self.wfile.write(b"x" * 1024)

    def log_message(self, format, *args):
        pass

class TestEngineCustomHeaders(unittest.TestCase):
    """Verifies TurboDownloadEngine propagates custom headers to probe and workers."""

    @classmethod
    def setUpClass(cls):
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), MockHeaderInspectHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_custom_headers_propagation(self):
        custom_headers = {
            "Authorization": "Bearer secret_test_token_123",
            "X-Custom-Client": "TurboPro/1.0"
        }
        engine = TurboDownloadEngine(
            url=f"http://127.0.0.1:{self.port}/test.bin",
            destination_path="test_headers_out.bin",
            headers=custom_headers
        )
        engine.probe()

        self.assertEqual(
            MockHeaderInspectHandler.last_headers.get("Authorization"),
            "Bearer secret_test_token_123"
        )
        self.assertEqual(
            MockHeaderInspectHandler.last_headers.get("X-Custom-Client"),
            "TurboPro/1.0"
        )

class TestStreamCoordinatorIntegration(unittest.TestCase):
    """Verifies StreamDownloadCoordinator end-to-end integration."""

    @classmethod
    def setUpClass(cls):
        cls.data_store = {}

        class MediaMockHandler(http.server.BaseHTTPRequestHandler):
            def do_HEAD(self):
                fn = self.path.lstrip('/')
                if fn not in TestStreamCoordinatorIntegration.data_store:
                    self.send_error(404)
                    return
                data = TestStreamCoordinatorIntegration.data_store[fn]
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

            def do_GET(self):
                fn = self.path.lstrip('/')
                if fn not in TestStreamCoordinatorIntegration.data_store:
                    self.send_error(404)
                    return
                data = TestStreamCoordinatorIntegration.data_store[fn]
                total = len(data)
                range_header = self.headers.get("Range")
                if range_header and range_header.startswith("bytes="):
                    rng = range_header[6:].split("-")
                    start = int(rng[0]) if rng[0] else 0
                    end = int(rng[1]) if rng[1] else total - 1
                    if end >= total:
                        end = total - 1
                    chunk_len = end - start + 1
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
                    self.send_header("Content-Length", str(chunk_len))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    self.wfile.write(data[start:end+1])
                else:
                    self.send_response(200)
                    self.send_header("Content-Length", str(total))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    self.wfile.write(data)

            def log_message(self, format, *args):
                pass

        cls.server = socketserver.TCPServer(("127.0.0.1", 0), MediaMockHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_coordinator_progressive_download(self):
        """Verifies progressive stream download through coordinator with bit-perfect validation."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = os.urandom(512 * 1024)
            expected_hash = hashlib.sha256(payload).hexdigest()
            self.data_store["prog_video.mp4"] = payload

            stream_info = YouTubeStreamInfo(
                video_id="test1234567",
                title="Progressive Test",
                clean_filename="Progressive_Test.mp4",
                is_progressive=True,
                video_url=f"http://127.0.0.1:{self.port}/prog_video.mp4",
                video_size=len(payload)
            )

            out_path = os.path.join(tmp_dir, "test_coord_prog_out.mp4")

            completed = threading.Event()
            errors = []

            coord = StreamDownloadCoordinator(
                stream_info=stream_info,
                destination_path=out_path,
                max_connections=4,
                on_complete=lambda path, size, elapsed: completed.set(),
                on_error=lambda err: (errors.append(err), completed.set())
            )
            coord.start()
            self.assertTrue(completed.wait(timeout=10), "Coordinator timed out")
            self.assertEqual(len(errors), 0, f"Coordinator failed: {errors}")
            self.assertTrue(os.path.exists(out_path))

            with open(out_path, "rb") as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            self.assertEqual(actual_hash, expected_hash)

    def test_coordinator_dual_stream_with_merge(self):
        """Verifies dual-stream coordinator downloading video and audio separately and merging via FFmpeg."""
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            self.skipTest("FFmpeg not installed")

        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_v_path = os.path.join(temp_dir, "raw_v.mp4")
            raw_a_path = os.path.join(temp_dir, "raw_a.m4a")

            subprocess.run([
                ffmpeg_bin, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1",
                "-c:v", "libx264", raw_v_path
            ], check=True, capture_output=True)

            subprocess.run([
                ffmpeg_bin, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
                "-c:a", "aac", raw_a_path
            ], check=True, capture_output=True)

            with open(raw_v_path, "rb") as f:
                v_data = f.read()
            with open(raw_a_path, "rb") as f:
                a_data = f.read()

            self.data_store["dual_video.mp4"] = v_data
            self.data_store["dual_audio.m4a"] = a_data

            stream_info = YouTubeStreamInfo(
                video_id="dual_test_123",
                title="Dual Test Video",
                clean_filename="Dual_Test_Video.mp4",
                is_progressive=False,
                video_url=f"http://127.0.0.1:{self.port}/dual_video.mp4",
                video_size=len(v_data),
                video_ext="mp4",
                video_resolution="1080p",
                audio_url=f"http://127.0.0.1:{self.port}/dual_audio.m4a",
                audio_size=len(a_data),
                audio_ext="m4a"
            )

            out_merged = os.path.join(temp_dir, "test_coord_merged_out.mp4")

            completed = threading.Event()
            errors = []
            progress_history = []

            def _track_progress(dl, total, spd, eta, active):
                pct = (dl / total * 100.0) if total > 0 else 0
                progress_history.append(pct)

            coord = StreamDownloadCoordinator(
                stream_info=stream_info,
                destination_path=out_merged,
                max_connections=2,
                on_progress=_track_progress,
                on_complete=lambda path, size, elapsed: completed.set(),
                on_error=lambda err: (errors.append(err), completed.set())
            )
            coord.start()

            self.assertTrue(completed.wait(timeout=15), "Dual stream coordinator timed out")
            self.assertEqual(len(errors), 0, f"Dual stream coordinator failed: {errors}")
            self.assertTrue(os.path.exists(out_merged), "Merged output file was not created")
            self.assertGreater(os.path.getsize(out_merged), 0, "Merged output file is empty")

            # Verify that temporary video and audio files were cleaned up
            self.assertFalse(os.path.exists(out_merged + ".video.tmp"), "video.tmp was not cleaned up")
            self.assertFalse(os.path.exists(out_merged + ".audio.tmp"), "audio.tmp was not cleaned up")

            # Verify progress history is monotonically non-decreasing (no jump back to 0%)
            for i in range(1, len(progress_history)):
                self.assertGreaterEqual(
                    progress_history[i],
                    progress_history[i - 1] - 0.01,
                    f"Progress jumped backwards at index {i}: {progress_history[i-1]}% -> {progress_history[i]}%"
                )

    def test_coordinator_cancel_cleanup(self):
        """Verifies that cancelling StreamDownloadCoordinator cleans up part files cleanly."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = os.urandom(1024 * 1024)
            self.data_store["cancel_v.mp4"] = payload
            self.data_store["cancel_a.m4a"] = payload

            stream_info = YouTubeStreamInfo(
                video_id="cancel_test",
                title="Cancel Test",
                clean_filename="Cancel_Test.mp4",
                is_progressive=False,
                video_url=f"http://127.0.0.1:{self.port}/cancel_v.mp4",
                video_size=len(payload),
                audio_url=f"http://127.0.0.1:{self.port}/cancel_a.m4a",
                audio_size=len(payload)
            )

            out_path = os.path.join(tmp_dir, "test_coord_cancel_out.mp4")
            coord = StreamDownloadCoordinator(
                stream_info=stream_info,
                destination_path=out_path,
                max_connections=2
            )
            coord.start()
            time.sleep(0.05)
            coord.cancel()
            time.sleep(0.3)

            self.assertFalse(coord.is_running)
            self.assertFalse(os.path.exists(out_path + ".video.tmp"))
            self.assertFalse(os.path.exists(out_path + ".audio.tmp"))

class TestSmartDownloadPartsDirectory(unittest.TestCase):
    """Verifies that temporary download chunks use .sd_parts and seamlessly migrate legacy .tdm_parts."""

    def test_parts_directory_default_suffix(self):
        import tempfile
        from turbo_downloader import TurboDownloadEngine
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = os.path.join(tmp_dir, "test_download.iso")
            engine = TurboDownloadEngine("https://example.com/test_download.iso", dest)
            self.assertEqual(engine.temp_dir, dest + ".sd_parts")
            self.assertTrue(engine.temp_dir.endswith(".sd_parts"))

    def test_parts_directory_migration_from_tdm_parts(self):
        import tempfile
        from turbo_downloader import TurboDownloadEngine
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = os.path.join(tmp_dir, "legacy_download.mp4")
            legacy_parts = dest + ".tdm_parts"
            os.makedirs(legacy_parts, exist_ok=True)
            chunk_file = os.path.join(legacy_parts, "legacy_download.mp4.part_0")
            with open(chunk_file, "wb") as f:
                f.write(b"partially_downloaded_data_content")

            engine = TurboDownloadEngine("https://example.com/legacy_download.mp4", dest)
            self.assertEqual(engine.temp_dir, dest + ".sd_parts")
            self.assertTrue(os.path.isdir(dest + ".sd_parts"), ".sd_parts directory must exist after migration")
            self.assertFalse(os.path.exists(legacy_parts), ".tdm_parts directory must have been moved")
            migrated_chunk = os.path.join(dest + ".sd_parts", "legacy_download.mp4.part_0")
            self.assertTrue(os.path.isfile(migrated_chunk), "Part file must be preserved in .sd_parts")
            with open(migrated_chunk, "rb") as f:
                self.assertEqual(f.read(), b"partially_downloaded_data_content")


class TestHeadlessDecoupling(unittest.TestCase):
    """Verifies that core modules and utilities can be imported without Tkinter in headless environments."""

    def test_headless_package_and_utils_import(self):
        cmd = [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.path.insert(0, 'src'); "
                "sys.modules['tkinter'] = None; "
                "import smart_download; "
                "import smart_download.utils; "
                "import smart_download.core.engine; "
                "import smart_download.utils.url_utils; "
                "assert smart_download.ModernFramelessGUI is None; "
                "assert callable(smart_download.utils._detach_photo_tk); "
                "assert smart_download.utils.format_speed(1024) == '1.0 KB/s'; "
                "print('HEADLESS_OK')"
            )
        ]
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Headless import failed: {res.stderr}")
        self.assertIn("HEADLESS_OK", res.stdout)


if __name__ == "__main__":
    unittest.main()
