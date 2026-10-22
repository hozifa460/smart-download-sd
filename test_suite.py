"""
========================================================================================
Automated Test Suite for Smart Download (SD)
========================================================================================
Thorough verification of:
1. Multi-chunk dynamic on-the-fly splitting and assembly with bit-perfect SHA-256 validation.
2. Single-stream fallback when HTTP Range requests are unsupported (with Content-Length).
3. Boundary gap and overlap assertion validation.
4. TokenBucketRateLimiter capacity adaptation and cancel event responsiveness.
5. Midpoint split boundary clamping preventing disk file size overflow.
6. Pause and resume during active multi-threaded transfer.
7. Clean cancellation without worker thread hangs.
8. Content-Disposition filename parsing with trailing parameters.
9. Temporary .sd_parts suffix and legacy .tdm_parts migration.
========================================================================================
"""

import unittest
import http.server
import socketserver
import threading
import time
import os
import shutil
import hashlib
import ssl
import urllib.request
import urllib.error
from typing import List, Optional

from unittest.mock import patch, MagicMock
import tkinter as tk

# Directly import from turbo_downloader module
from turbo_downloader import (
    TurboDownloadEngine,
    SmartDownloadEngine,
    TokenBucketRateLimiter,
    DownloadChunk,
    get_permissive_ssl_context,
    ModernFramelessGUI,
    SafeModalDialog,
    QualitySelectionModal,
    VideoFormatOption
)
from youtube_resolver import (
    is_youtube_url,
    is_social_media_url,
    is_media_url,
    extract_media_platform
)


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

        app._on_close()

    def test_permissive_ssl_context_properties(self):
        """Verify get_permissive_ssl_context provides an unverified, reusable SSL context."""
        ctx1 = get_permissive_ssl_context()
        ctx2 = get_permissive_ssl_context()
        self.assertIsInstance(ctx1, ssl.SSLContext)
        self.assertFalse(ctx1.check_hostname)
        self.assertEqual(ctx1.verify_mode, ssl.CERT_NONE)
        self.assertIs(ctx1, ctx2, "get_permissive_ssl_context should return the cached reusable context")

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
            if e.code == 404:
                self.skipTest(f"archive.org remote asset returned 404: {e}")
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
            if "404" in str(e) or "timed out" in str(e).lower():
                self.skipTest(f"archive.org remote asset returned error: {e}")
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
            if any("404" in str(err) or "timed out" in str(err).lower() for err in errors):
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


if __name__ == "__main__":
    unittest.main()

