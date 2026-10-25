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

class MockServerHandler(http.server.BaseHTTPRequestHandler):
    data_store = {}
    supports_ranges = True
    delay_per_kb = 0.0
    fail_first_get_bytes = 0

    def do_HEAD(self):
        filename = self.path.lstrip('/')
        if filename not in self.data_store:
            self.send_error(404)
            return
        data = self.data_store[filename]
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        if self.supports_ranges:
            self.send_header("Accept-Ranges", "bytes")
        else:
            self.send_header("Accept-Ranges", "none")
        self.end_headers()

    def do_GET(self):
        filename = self.path.lstrip('/')
        if filename not in self.data_store:
            self.send_error(404)
            return
        data = self.data_store[filename]
        total_len = len(data)

        range_header = self.headers.get("Range")
        if self.supports_ranges and range_header and range_header.startswith("bytes="):
            ranges = range_header[6:].split("-")
            start = int(ranges[0]) if ranges[0] else 0
            end = int(ranges[1]) if ranges[1] else total_len - 1
            if end >= total_len:
                end = total_len - 1
            if start > end or start >= total_len:
                self.send_error(416)
                return

            chunk_len = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Range", f"bytes {start}-{end}/{total_len}")
            self.send_header("Content-Length", str(chunk_len))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            offset = start
            buf_size = 16384
            while offset <= end:
                read_len = min(buf_size, end - offset + 1)
                try:
                    self.wfile.write(data[offset:offset+read_len])
                except Exception:
                    break
                offset += read_len
                if self.delay_per_kb > 0:
                    time.sleep(self.delay_per_kb * (read_len / 1024.0))
                else:
                    time.sleep(0.0005)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total_len))
            if self.supports_ranges:
                self.send_header("Accept-Ranges", "bytes")
            else:
                self.send_header("Accept-Ranges", "none")
            self.end_headers()
            if MockServerHandler.fail_first_get_bytes > 0:
                cut = MockServerHandler.fail_first_get_bytes
                MockServerHandler.fail_first_get_bytes = 0
                try:
                    self.wfile.write(data[:cut])
                except Exception:
                    pass
                self.close_connection = True
                return
            try:
                self.wfile.write(data)
            except Exception:
                pass

    def log_message(self, format, *args):
        pass

class TestTurboDownloader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), MockServerHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_dynamic_splitting_and_sha256_integrity(self):
        """Test multi-chunk dynamic on-the-fly splitting with bit-perfect SHA-256 match."""
        test_size = 4 * 1024 * 1024  # 4MB
        test_data = os.urandom(test_size)
        orig_hash = hashlib.sha256(test_data).hexdigest()
        MockServerHandler.data_store["dynamic_test.bin"] = test_data
        MockServerHandler.supports_ranges = True
        MockServerHandler.delay_per_kb = 0.0002

        dest = "test_dynamic_out.bin"
        if os.path.exists(dest):
            os.remove(dest)

        completed = threading.Event()
        errors = []

        engine = TurboDownloadEngine(
            url=f"http://127.0.0.1:{self.port}/dynamic_test.bin",
            destination_path=dest,
            max_connections=6,
            min_split_threshold=128 * 1024,
            rate_limit_bytes_per_sec=0,
            on_complete=lambda path, size, elapsed: completed.set(),
            on_error=lambda err: errors.append(err)
        )
        engine.start()

        finished = completed.wait(timeout=15.0)
        self.assertTrue(finished, f"Download timed out! Errors: {errors}")
        self.assertEqual(len(errors), 0, f"Encountered unexpected errors: {errors}")

        self.assertGreater(len(engine.chunks), 1, "Expected multiple chunks created via dynamic split")

        with open(dest, "rb") as f:
            downloaded_hash = hashlib.sha256(f.read()).hexdigest()

        self.assertEqual(downloaded_hash, orig_hash)
        os.remove(dest)

    def test_single_stream_fallback_with_content_length(self):
        """
        Verify single-stream fallback when server does NOT support HTTP Range requests.
        Ensures entire file is downloaded, not just 1 byte.
        """
        test_size = 300 * 1024  # 300 KB
        test_data = os.urandom(test_size)
        orig_hash = hashlib.sha256(test_data).hexdigest()
        MockServerHandler.data_store["norange_full.bin"] = test_data
        MockServerHandler.supports_ranges = False
        MockServerHandler.delay_per_kb = 0.0

        dest = "test_norange_out.bin"
        if os.path.exists(dest):
            os.remove(dest)

        completed = threading.Event()
        errors = []

        engine = TurboDownloadEngine(
            url=f"http://127.0.0.1:{self.port}/norange_full.bin",
            destination_path=dest,
            max_connections=4,
            on_complete=lambda p, s, e: completed.set(),
            on_error=lambda err: errors.append(err)
        )
        engine.start()

        finished = completed.wait(timeout=10.0)
        self.assertTrue(finished, f"Single stream download timed out! Errors: {errors}")
        self.assertEqual(len(errors), 0, f"Errors: {errors}")

        self.assertEqual(len(engine.chunks), 1, "Should not split when ranges are unsupported")
        self.assertTrue(os.path.exists(dest))
        self.assertEqual(os.path.getsize(dest), test_size, "Downloaded size must equal full file size!")

        with open(dest, "rb") as f:
            downloaded_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(downloaded_hash, orig_hash)
        os.remove(dest)

    def test_boundary_gap_assertion_catches_corruption(self):
        """Verify strict sequential assembly asserts against gaps or corruptions."""
        engine = TurboDownloadEngine("http://dummy", "dummy.bin", max_connections=2)
        engine.total_size = 1000
        engine.supports_ranges = True
        # Create chunk with gap (ends at 499, next starts at 502)
        c1 = DownloadChunk(0, 0, 499, 500, "completed", "dummy0.part")
        c2 = DownloadChunk(1, 502, 999, 498, "completed", "dummy1.part")
        engine.chunks = [c1, c2]

        with self.assertRaises(AssertionError) as ctx:
            engine.assemble()
        self.assertIn("Boundary Gap/Overlap", str(ctx.exception))

    def test_token_bucket_large_buffer_adaptation(self):
        """Test that TokenBucketRateLimiter adapts capacity for buffers larger than initial capacity."""
        limiter = TokenBucketRateLimiter(rate_limit_bytes_per_sec=10000)
        self.assertEqual(limiter.capacity, 65536.0)

        # Request 100,000 bytes (larger than initial 65,536 capacity)
        # Should dynamically expand capacity without hanging infinitely
        start = time.monotonic()
        limiter.acquire(100000)
        # Verify capacity expanded
        self.assertGreaterEqual(limiter.capacity, 100000)

    def test_token_bucket_cancel_responsiveness(self):
        """Test that TokenBucketRateLimiter aborts waiting immediately when cancel_event is set."""
        limiter = TokenBucketRateLimiter(rate_limit_bytes_per_sec=1000) # 1 KB/s
        cancel = threading.Event()

        start = time.monotonic()
        # Schedule cancel in 50ms
        threading.Timer(0.05, cancel.set).start()
        # Request 50,000 bytes (at 1KB/s this would normally sleep for 50s)
        limiter.acquire(50000, cancel_event=cancel)
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 0.5, "TokenBucket must abort promptly on cancel event!")

    def test_pause_and_resume_integrity(self):
        """Test pause during active multi-threaded download and resume to completion."""
        test_size = 2 * 1024 * 1024  # 2MB
        test_data = os.urandom(test_size)
        orig_hash = hashlib.sha256(test_data).hexdigest()
        MockServerHandler.data_store["pause_resume.bin"] = test_data
        MockServerHandler.supports_ranges = True
        MockServerHandler.delay_per_kb = 0.001

        dest = "test_pause_resume.bin"
        if os.path.exists(dest):
            os.remove(dest)

        completed = threading.Event()
        errors = []

        engine = TurboDownloadEngine(
            url=f"http://127.0.0.1:{self.port}/pause_resume.bin",
            destination_path=dest,
            max_connections=4,
            min_split_threshold=64 * 1024,
            on_complete=lambda p, s, e: completed.set(),
            on_error=lambda err: errors.append(err)
        )
        engine.start()

        # Download some data
        time.sleep(0.3)
        self.assertTrue(engine.is_running)

        # Pause
        engine.pause()
        self.assertTrue(engine.is_paused)
        time.sleep(0.4)

        # Resume
        engine.resume()
        self.assertFalse(engine.is_paused)

        finished = completed.wait(timeout=15.0)
        self.assertTrue(finished, f"Pause/Resume download timed out! Errors: {errors}")
        self.assertEqual(len(errors), 0)

        with open(dest, "rb") as f:
            downloaded_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(downloaded_hash, orig_hash)
        os.remove(dest)

    def test_content_disposition_filename_parsing(self):
        """Test filename extraction from complex Content-Disposition headers."""
        engine = TurboDownloadEngine("http://dummy", "dummy.bin")
        # Complex header with trailing parameters
        cd1 = 'attachment; filename="archive_backup_2026.zip"; modification-date="Wed, 12 Feb 1997 16:29:51 -0500"'
        self.assertEqual(engine._parse_filename_from_cd(cd1), "archive_backup_2026.zip")

        # Unquoted filename
        cd2 = 'attachment; filename=document.pdf'
        self.assertEqual(engine._parse_filename_from_cd(cd2), "document.pdf")

        # Empty
        self.assertIsNone(engine._parse_filename_from_cd(""))

    def test_aggressive_dynamic_split(self):
        """Test aggressive dynamic split with small threshold to provoke race conditions."""
        size = 3 * 1024 * 1024  # 3MB
        payload = os.urandom(size)
        expected_hash = hashlib.sha256(payload).hexdigest()
        MockServerHandler.data_store["agg_split.bin"] = payload
        MockServerHandler.supports_ranges = True
        MockServerHandler.delay_per_kb = 0.0005

        out_path = "test_agg_split.bin"
        if os.path.exists(out_path):
            os.remove(out_path)

        completed = threading.Event()
        error_holder = []

        engine = TurboDownloadEngine(
            url=f"http://127.0.0.1:{self.port}/agg_split.bin",
            destination_path=out_path,
            max_connections=8,
            min_split_threshold=64 * 1024,
            on_complete=lambda path, total, elapsed: completed.set(),
            on_error=lambda err: error_holder.append(err)
        )
        engine.start()

        finished = completed.wait(timeout=15.0)
        self.assertTrue(finished, f"Download timed out! Errors: {error_holder}")
        self.assertEqual(len(error_holder), 0, f"Encountered errors: {error_holder}")

        with open(out_path, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(actual_hash, expected_hash)
        os.remove(out_path)

    def test_cancel_and_cleanup(self):
        """Test cancel cleanly stops workers and cleans up."""
        size = 5 * 1024 * 1024  # 5MB
        payload = os.urandom(size)
        MockServerHandler.data_store["cancel_test.bin"] = payload
        MockServerHandler.supports_ranges = True
        MockServerHandler.delay_per_kb = 0.005

        out_path = "test_cancel.bin"
        if os.path.exists(out_path):
            os.remove(out_path)

        engine = TurboDownloadEngine(
            url=f"http://127.0.0.1:{self.port}/cancel_test.bin",
            destination_path=out_path,
            max_connections=4
        )
        engine.start()
        time.sleep(0.3)
        self.assertTrue(engine.is_running)

        engine.cancel()
        time.sleep(0.3)
        self.assertFalse(engine.is_running)
        if os.path.exists(engine.temp_dir):
            shutil.rmtree(engine.temp_dir, ignore_errors=True)

    def test_rate_limiter_throttling(self):
        """Test that TokenBucketRateLimiter throttles throughput accurately."""
        limiter = TokenBucketRateLimiter(rate_limit_bytes_per_sec=200 * 1024)
        start = time.monotonic()
        total_bytes = 0
        chunk = 32 * 1024
        for _ in range(5):
            limiter.acquire(chunk)
            total_bytes += chunk
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.4)

    def test_small_file_single_chunk(self):
        """Test downloading a file smaller than min_split_threshold."""
        size = 15 * 1024  # 15 KB
        payload = os.urandom(size)
        expected_hash = hashlib.sha256(payload).hexdigest()
        MockServerHandler.data_store["small.bin"] = payload
        MockServerHandler.supports_ranges = True
        MockServerHandler.delay_per_kb = 0.0

        out_path = "test_small.bin"
        if os.path.exists(out_path):
            os.remove(out_path)

        completed = threading.Event()
        engine = TurboDownloadEngine(
            url=f"http://127.0.0.1:{self.port}/small.bin",
            destination_path=out_path,
            max_connections=4,
            min_split_threshold=64 * 1024,
            on_complete=lambda p, t, e: completed.set()
        )
        engine.start()
        finished = completed.wait(timeout=5.0)
        self.assertTrue(finished)

        with open(out_path, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(actual_hash, expected_hash)
        self.assertEqual(len(engine.chunks), 1)
        os.remove(out_path)

    def test_gui_initialization_and_slider_synchronization(self):
        """Test ModernFramelessGUI instantiation, slider, and preset sync."""
        import tkinter as tk
        from turbo_downloader import ModernFramelessGUI

        root = tk.Tk()
        app = ModernFramelessGUI(root)

        # Test slider movement updates entry box
        app.slider_speed.set(2048)
        app._on_slider_moved("2048")
        self.assertEqual(app.entry_custom_speed.get(), "2048")

        # Test preset selection updates slider and entry
        app.limit_preset_var.set("5.0 MB/s")
        app._on_preset_selected()
        self.assertEqual(app.entry_custom_speed.get(), "5120")
        self.assertEqual(app.slider_speed.get(), 5120)

        # Test progress bar drawing
        app._draw_main_progress(50.0)

        # Test visual chunk segment drawing and treeview update
        c0 = DownloadChunk(0, 0, 500000, 250000, "active")
        c1 = DownloadChunk(1, 500001, 1000000, 500000, "completed")
        class DummyEngine:
            total_size = 1000000
            chunks = [c0, c1]
            _lock = threading.Lock()
            is_running = False
            is_paused = False

        app.engine = DummyEngine()
        app._draw_chunk_segments([c0, c1])
        app._refresh_chunk_displays()
        self.assertEqual(len(app.tree_chunks.get_children()), 2)

        app.exit_completely()

    def test_permissive_ssl_context_properties(self):
        """Verify get_permissive_ssl_context provides an unverified, reusable SSL context."""
        ctx1 = get_permissive_ssl_context()
        ctx2 = get_permissive_ssl_context()
        self.assertIsInstance(ctx1, ssl.SSLContext)
        self.assertFalse(ctx1.check_hostname)
        self.assertEqual(ctx1.verify_mode, ssl.CERT_NONE)
        self.assertIs(ctx1, ctx2, "get_permissive_ssl_context should return the cached reusable context")

    def test_app_auto_updater_verified_ssl_context(self):
        """Verify AppAutoUpdater enforces a strictly verified SSL context by default instead of CERT_NONE."""
        from updater import AppAutoUpdater, _get_verified_ssl_context
        updater = AppAutoUpdater(current_version="2.0.0")
        self.assertIsInstance(updater.ssl_context, ssl.SSLContext)
        self.assertTrue(updater.ssl_context.check_hostname, "AppAutoUpdater must verify hostname by default")
        self.assertEqual(updater.ssl_context.verify_mode, ssl.CERT_REQUIRED, "AppAutoUpdater must use CERT_REQUIRED by default")
        verified_ctx = _get_verified_ssl_context()
        self.assertTrue(verified_ctx.check_hostname)
        self.assertEqual(verified_ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_engine_custom_and_default_ssl_context(self):
        """Verify TurboDownloadEngine accepts custom SSL context and falls back to permissive."""
        default_engine = TurboDownloadEngine("http://dummy", "dummy.bin")
        self.assertIs(default_engine.ssl_context, get_permissive_ssl_context())
        self.assertIsNotNone(default_engine.opener)

        custom_ctx = ssl.create_default_context()
        custom_engine = TurboDownloadEngine("http://dummy", "dummy.bin", ssl_context=custom_ctx)
        self.assertIs(custom_engine.ssl_context, custom_ctx)

    def test_archive_org_ssl_connectivity_and_redirect(self):
        """
        Verify real-world SSL connectivity against archive.org expired/CDN cert endpoint:
        1. Default SSL context is tested against archive.org.
        2. Permissive SSL context successfully probes, follows redirect, and detects ranges.
        """
        archive_url = "https://archive.org/download/8k_ISS_flythru_to_cupola/8k_ISS_flythru_to_cupola.mp4"

        # 1. Test default SSL context on archive.org (may fail if cert expired or succeed if renewed)
        default_ctx = ssl.create_default_context()
        default_req = urllib.request.Request(archive_url, headers={"User-Agent": "Mozilla/5.0"})
        failed_with_ssl = False
        try:
            with urllib.request.urlopen(default_req, context=default_ctx, timeout=15):
                pass
        except urllib.error.HTTPError as e:
            if e.code in (404, 500, 502, 503, 504):
                self.skipTest(f"archive.org remote asset returned HTTP {e.code}: {e}")
            failed_with_ssl = True
        except urllib.error.URLError as e:
            failed_with_ssl = (
                "CERTIFICATE_VERIFY_FAILED" in str(e)
                or "certificate has expired" in str(e)
                or isinstance(getattr(e, "reason", None), ssl.SSLError)
            )
        except Exception:
            failed_with_ssl = True

        # 2. Confirm TurboDownloadEngine probe succeeds and follows redirect under permissive SSL
        test_dest = "test_iss_probe.mp4"
        engine = TurboDownloadEngine(archive_url, test_dest)
        try:
            engine.probe()
        except RuntimeError as e:
            err_lower = str(e).lower()
            if any(k in err_lower for k in ("404", "500", "502", "503", "504", "bad gateway", "internal server error", "service unavailable", "timed out", "connection reset")):
                self.skipTest(f"archive.org remote server temporarily unavailable: {e}")
            raise
        except Exception as e:
            self.skipTest(f"archive.org remote asset unreachable: {e}")

        self.assertGreater(engine.total_size, 0)
        self.assertEqual(engine.total_size, 4448426)
        self.assertTrue(engine.supports_ranges)
        self.assertIn("archive.org", engine.url)
        # Ensure redirected URL was recorded
        self.assertTrue(engine.url.startswith("https://"))

    def test_archive_org_download_execution(self):
        """Verify downloading from archive.org with permissive SSL context completes without error."""
        archive_url = "https://archive.org/download/8k_ISS_flythru_to_cupola/8k_ISS_flythru_to_cupola.mp4"
        test_dest = "test_archive_verify.mp4"
        if os.path.exists(test_dest):
            os.remove(test_dest)

        completed = threading.Event()
        errors = []

        engine = TurboDownloadEngine(
            url=archive_url,
            destination_path=test_dest,
            max_connections=4,
            on_complete=lambda p, s, e: completed.set(),
            on_error=lambda err: errors.append(err)
        )
        engine.start()

        finished = completed.wait(timeout=45.0)
        if not finished:
            engine.cancel()
            self.skipTest("archive.org download timed out due to slow external CDN network latency")

        if errors:
            err_lower = " ".join(str(err).lower() for err in errors)
            if any(k in err_lower for k in ("404", "500", "502", "503", "504", "bad gateway", "internal server error", "service unavailable", "timed out", "connection reset")):
                self.skipTest(f"archive.org remote asset returned error: {errors}")
        self.assertEqual(len(errors), 0, f"Encountered errors: {errors}")
        self.assertTrue(os.path.exists(test_dest))
        self.assertEqual(os.path.getsize(test_dest), 4448426)
        os.remove(test_dest)

    def test_non_range_retry_does_not_corrupt_data(self):
        """Verify that when a non-range server drops mid-stream, retry resets buffer and avoids data duplication."""
        size = 128 * 1024  # 128 KB
        payload = os.urandom(size)
        expected_hash = hashlib.sha256(payload).hexdigest()
        filename = "retry_test_nonrange.bin"
        MockServerHandler.data_store[filename] = payload
        MockServerHandler.supports_ranges = False
        # Drop socket after sending 32KB on first GET
        MockServerHandler.fail_first_get_bytes = 32 * 1024

        out_path = "test_non_range_retry.bin"
        if os.path.exists(out_path):
            os.remove(out_path)

        completed = threading.Event()
        errors = []

        engine = TurboDownloadEngine(
            url=f"http://127.0.0.1:{self.port}/{filename}",
            destination_path=out_path,
            max_connections=1,
            on_complete=lambda p, s, e: completed.set(),
            on_error=lambda err: errors.append(err)
        )
        engine.start()

        finished = completed.wait(timeout=10.0)
        self.assertTrue(finished, f"Download timed out! Errors: {errors}")
        self.assertEqual(len(errors), 0)
        self.assertTrue(os.path.exists(out_path))

        with open(out_path, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(actual_hash, expected_hash, "Retry must not duplicate/corrupt non-range file content")
        self.assertEqual(os.path.getsize(out_path), size)
        os.remove(out_path)

    def test_directory_destination_filename_resolution(self):
        """Verify that supplying a directory as destination_path resolves the filename from URL when CD is absent."""
        MockServerHandler.data_store["test_file_resolve.bin"] = b"resolved payload content"
        test_dir = "test_dest_dir"
        os.makedirs(test_dir, exist_ok=True)
        try:
            engine = TurboDownloadEngine(
                url=f"http://127.0.0.1:{self.port}/test_file_resolve.bin",
                destination_path=test_dir
            )
            engine.probe()
            self.assertEqual(engine.filename, "test_file_resolve.bin")
            self.assertEqual(engine.destination_path, os.path.join(test_dir, "test_file_resolve.bin"))
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_engine_custom_opener_injection(self):
        """Verify TurboDownloadEngine accepts a custom urllib OpenerDirector."""
        custom_opener = urllib.request.build_opener()
        engine = TurboDownloadEngine("http://dummy", "dummy.bin", opener=custom_opener)
        self.assertIs(engine.opener, custom_opener)

class TestSmartDownloadBrandingAndParts(unittest.TestCase):
    """Verifies rebranding aliases and .sd_parts / legacy .tdm_parts migration."""

    def test_smart_download_engine_alias(self):
        self.assertIs(SmartDownloadEngine, TurboDownloadEngine)

    def test_sd_parts_default_temporary_directory(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = os.path.join(tmp_dir, "archive.zip")
            engine = SmartDownloadEngine(
                url="https://example.com/archive.zip",
                destination_path=dest
            )
            self.assertEqual(engine.temp_dir, dest + ".sd_parts")
            self.assertTrue(engine.temp_dir.endswith(".sd_parts"))

    def test_legacy_tdm_parts_automatic_migration(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = os.path.join(tmp_dir, "legacy_file.bin")
            legacy_dir = dest + ".tdm_parts"
            os.makedirs(legacy_dir, exist_ok=True)
            marker_file = os.path.join(legacy_dir, "part_0.data")
            with open(marker_file, "w") as f:
                f.write("in_progress_data")

            # Creating engine must automatically migrate .tdm_parts -> .sd_parts
            engine = SmartDownloadEngine(
                url="https://example.com/legacy_file.bin",
                destination_path=dest
            )
            self.assertEqual(engine.temp_dir, dest + ".sd_parts")
            self.assertTrue(os.path.isdir(dest + ".sd_parts"), "Migrated .sd_parts directory must exist")
            self.assertFalse(os.path.exists(legacy_dir), "Old .tdm_parts directory must be removed after migration")
            migrated_marker = os.path.join(dest + ".sd_parts", "part_0.data")
            self.assertTrue(os.path.isfile(migrated_marker), "In-progress partial download data must be preserved")

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
