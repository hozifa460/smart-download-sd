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

class MockRefreshLinkServerHandler(http.server.BaseHTTPRequestHandler):
    """
    Mock HTTP server handler simulating expired links, refreshed URLs,
    size mismatches, missing range support, and HTTP 401/403/410 errors.
    """
    data_store = {}
    expired_urls = set()
    no_range_urls = set()
    request_counts = {}

    def log_message(self, format, *args):
        pass  # Suppress console logging during automated tests

    def do_HEAD(self):
        path = self.path.split('?')[0].lstrip('/')
        if path == "head_forbidden.bin":
            self.send_error(403, "Forbidden: S3 Pre-signed Method Restricted")
            return
        if path in self.expired_urls or path == "forbidden":
            self.send_error(403, "Forbidden - Link Expired")
            return
        if path == "gone":
            self.send_error(410, "Gone")
            return
        if path not in self.data_store:
            self.send_error(404, "Not Found")
            return

        data = self.data_store[path]
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        if path in self.no_range_urls:
            self.send_header("Accept-Ranges", "none")
        else:
            self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0].lstrip('/')
        self.request_counts[path] = self.request_counts.get(path, 0) + 1

        if path in self.expired_urls or path == "forbidden":
            self.send_error(403, "Forbidden - Link Expired")
            return
        if path == "gone":
            self.send_error(410, "Gone")
            return
        if path in ("expire_after_first.bin", "expire_on_get.bin"):
            self.send_error(403, "Forbidden - Link Expired")
            return
        if path not in self.data_store:
            self.send_error(404, "Not Found")
            return

        data = self.data_store[path]
        total_len = len(data)

        range_header = self.headers.get("Range")
        if range_header and path == "fake_accept_ranges_200.bin":
            # Deceptive server: returns 200 OK with full body even when sent Range header!
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total_len))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(data)
            return

        if range_header and path == "no_total_206.bin":
            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", "1")
            self.end_headers()
            self.wfile.write(data[:1])
            return

        if range_header and path in self.no_range_urls:
            # Server does not support range requests: ignore range header and return 200 with full data
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total_len))
            self.send_header("Accept-Ranges", "none")
            self.end_headers()
            self.wfile.write(data)
            return

        if range_header and range_header.startswith("bytes="):
            ranges = range_header[6:].split("-")
            start = int(ranges[0]) if ranges[0] else 0
            end = int(ranges[1]) if ranges[1] else total_len - 1
            if end >= total_len:
                end = total_len - 1
            if start > end or start >= total_len:
                self.send_error(416, "Range Not Satisfiable")
                return

            chunk_len = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Range", f"bytes {start}-{end}/{total_len}")
            self.send_header("Content-Length", str(chunk_len))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            offset = start
            buf_size = 4096
            while offset <= end:
                read_len = min(buf_size, end - offset + 1)
                try:
                    self.wfile.write(data[offset:offset + read_len])
                except Exception:
                    break
                offset += read_len
                time.sleep(0.0005)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total_len))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(data)

class TestRefreshExpiredLinks(unittest.TestCase):
    """
    Automated verification for Feature 4: Refresh Expired Links (تجديد الروابط المنتهية).
    Verifies URL validation, HTTP 401/403/410 handling, state persistence,
    grab-free modal dialog, dynamic split resume, and bit-perfect file assembly.
    """
    server = None
    server_thread = None
    port = 0
    base_url = ""
    test_data = b""
    test_hash = ""

    @classmethod
    def setUpClass(cls):
        cls.test_data = os.urandom(256 * 1024)  # 256 KB
        cls.test_hash = hashlib.sha256(cls.test_data).hexdigest()
        cls.mismatch_data = cls.test_data[: 128 * 1024]  # 128 KB

        MockRefreshLinkServerHandler.data_store = {
            "fresh.bin": cls.test_data,
            "mismatch.bin": cls.mismatch_data,
            "no_range.bin": cls.test_data,
            "expire_on_get.bin": cls.test_data,
            "expire_after_first.bin": cls.test_data,
            "resumable.bin": cls.test_data,
            "head_forbidden.bin": cls.test_data,
            "fake_accept_ranges_200.bin": cls.test_data,
            "no_total_206.bin": cls.test_data,
        }
        MockRefreshLinkServerHandler.no_range_urls = {"no_range.bin"}
        MockRefreshLinkServerHandler.expired_urls = set()
        MockRefreshLinkServerHandler.request_counts = {}

        class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        cls.server = ThreadedHTTPServer(("127.0.0.1", 0), MockRefreshLinkServerHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            try:
                cls.server.shutdown()
                cls.server.server_close()
            except Exception:
                pass

    def setUp(self):
        self.test_dir = os.path.join(TESTS_DIR, "test_temp_refresh")
        os.makedirs(self.test_dir, exist_ok=True)
        self.root = None

    def tearDown(self):
        if getattr(self, "root", None) is not None:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None
        if os.path.isdir(self.test_dir):
            try:
                shutil.rmtree(self.test_dir, ignore_errors=True)
            except Exception:
                pass

    def test_01_validate_refresh_url_success(self):
        fresh_url = f"{self.base_url}/fresh.bin"
        ok, msg, size, ranges = validate_refresh_url(fresh_url, expected_size=len(self.test_data), check_range=True)
        self.assertTrue(ok, f"Expected validation to succeed, got: {msg}")
        self.assertEqual(size, len(self.test_data))
        self.assertTrue(ranges)
        self.assertIn("successfully", msg.lower())

    def test_02_validate_refresh_url_size_mismatch(self):
        mismatch_url = f"{self.base_url}/mismatch.bin"
        ok, msg, size, ranges = validate_refresh_url(mismatch_url, expected_size=len(self.test_data), check_range=True)
        self.assertFalse(ok)
        self.assertEqual(size, len(self.mismatch_data))
        self.assertIn("size mismatch", msg.lower())

    def test_03_validate_refresh_url_http_403_and_410(self):
        url_403 = f"{self.base_url}/forbidden"
        ok_403, msg_403, _, _ = validate_refresh_url(url_403)
        self.assertFalse(ok_403)
        self.assertIn("403", msg_403)

        url_410 = f"{self.base_url}/gone"
        ok_410, msg_410, _, _ = validate_refresh_url(url_410)
        self.assertFalse(ok_410)
        self.assertIn("410", msg_410)

    def test_04_validate_refresh_url_no_range_support(self):
        no_range_url = f"{self.base_url}/no_range.bin"
        ok, msg, size, ranges = validate_refresh_url(no_range_url, expected_size=len(self.test_data), check_range=True)
        self.assertFalse(ok)
        self.assertFalse(ranges)
        self.assertIn("range", msg.lower())

    def test_05_engine_save_and_load_state_persistence(self):
        target = os.path.join(self.test_dir, "persist_test.bin")
        engine = TurboDownloadEngine(
            url="http://example.com/file.bin",
            destination_path=target,
            max_connections=2
        )
        engine.total_size = 200000
        engine.supports_ranges = True
        engine.has_expired_link = True
        c0 = DownloadChunk(0, 0, 99999)
        c0.downloaded_bytes = 45000
        c0.status = "paused"
        c1 = DownloadChunk(1, 100000, 199999)
        c1.downloaded_bytes = 20000
        c1.status = "failed"
        c1.error_msg = "HTTP 403: Forbidden"
        engine.chunks = [c0, c1]

        saved = engine.save_state()
        self.assertTrue(saved)
        state_file = os.path.join(engine.temp_dir, "state.json")
        self.assertTrue(os.path.isfile(state_file))

        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["total_size"], 200000)
        self.assertTrue(data["has_expired_link"])
        self.assertEqual(len(data["chunks"]), 2)

        # Load into fresh engine instance
        engine2 = TurboDownloadEngine(
            url="http://example.com/dummy",
            destination_path=target,
            max_connections=1
        )
        loaded = engine2.load_state()
        self.assertTrue(loaded)
        self.assertEqual(engine2.total_size, 200000)
        self.assertTrue(engine2.has_expired_link)
        self.assertEqual(len(engine2.chunks), 2)
        self.assertEqual(engine2.chunks[0].chunk_id, 0)
        self.assertEqual(engine2.chunks[0].downloaded_bytes, 45000)
        self.assertEqual(engine2.chunks[1].chunk_id, 1)
        self.assertEqual(engine2.chunks[1].downloaded_bytes, 20000)
        self.assertEqual(engine2.chunks[1].error_msg, "HTTP 403: Forbidden")

    def test_06_engine_detects_expired_link_on_403_failure(self):
        target = os.path.join(self.test_dir, "expire_task.bin")
        engine = TurboDownloadEngine(
            url=f"{self.base_url}/expire_on_get.bin",
            destination_path=target,
            max_connections=2
        )
        engine.start()
        for _ in range(60):
            if not engine.is_running:
                break
            time.sleep(0.05)

        self.assertFalse(engine.is_running)
        self.assertTrue(engine.has_expired_link, "Engine must flag has_expired_link on HTTP 403")
        self.assertEqual(engine.last_http_status, 403)
        self.assertTrue(os.path.isdir(engine.temp_dir), "Temporary chunk directory must NOT be deleted on 403 failure")
        state_file = os.path.join(engine.temp_dir, "state.json")
        self.assertTrue(os.path.isfile(state_file), "State file must be saved on failure")

    def test_07_refresh_link_and_resume_bit_perfect(self):
        target = os.path.join(self.test_dir, "resume_task.bin")
        engine = TurboDownloadEngine(
            url=f"{self.base_url}/expire_on_get.bin",
            destination_path=target,
            max_connections=2
        )
        engine.start()
        for _ in range(60):
            if not engine.is_running:
                break
            time.sleep(0.05)

        self.assertTrue(engine.has_expired_link)

        fresh_url = f"{self.base_url}/fresh.bin"
        resumed = engine.refresh_link(fresh_url, auto_resume=True)
        self.assertTrue(resumed)

        for _ in range(100):
            if not engine.is_running:
                break
            time.sleep(0.05)

        self.assertFalse(engine.is_running)
        self.assertFalse(engine.has_expired_link)
        self.assertTrue(os.path.isfile(target), f"Assembled file must exist at {target}")
        self.assertEqual(os.path.getsize(target), len(self.test_data))

        with open(target, "rb") as f:
            downloaded_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(downloaded_hash, self.test_hash, "Resumed download must be 100% bit-perfect with original file")

    def test_08_dynamic_split_with_refresh_link(self):
        target = os.path.join(self.test_dir, "split_resume.bin")
        engine = TurboDownloadEngine(
            url=f"{self.base_url}/resumable.bin",
            destination_path=target,
            max_connections=4
        )
        engine.start()
        time.sleep(0.05)
        engine.pause()
        for _ in range(40):
            if engine.is_paused:
                break
            time.sleep(0.02)

        self.assertTrue(engine.is_paused)
        fresh_url = f"{self.base_url}/fresh.bin"
        engine.refresh_link(fresh_url, auto_resume=True)

        for _ in range(100):
            if not engine.is_running:
                break
            time.sleep(0.05)

        self.assertFalse(engine.is_running)
        self.assertTrue(os.path.isfile(target))
        with open(target, "rb") as f:
            downloaded_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(downloaded_hash, self.test_hash, "Multi-chunk split resume must match SHA-256 hash")

    def test_09_refresh_link_modal_grab_free_and_clipboard_autofill(self):
        self.root = tk.Tk()
        self.root.withdraw()
        modal = RefreshLinkModal(
            parent=self.root,
            old_url=f"{self.base_url}/old.bin",
            total_size=len(self.test_data),
            downloaded_bytes=10000,
            filename="test.bin"
        )
        try:
            modal.grab_set()
            modal.grab_set_global()
            self.root.update()

            fresh_url = f"{self.base_url}/fresh.bin"
            self.root.clipboard_clear()
            self.root.clipboard_append(fresh_url)

            modal._check_clipboard_auto_fill()
            self.assertEqual(modal.entry_new_url.get(), fresh_url, "Modal must auto-populate new URL from clipboard")

            cb_mock = MagicMock()
            modal.on_success = cb_mock
            modal._start_validation()
            if hasattr(modal, "_validating_thread") and modal._validating_thread:
                modal._validating_thread.join(timeout=3.0)
            modal.process_pending_events()
            for _ in range(10):
                self.root.update()
                time.sleep(0.02)
            cb_mock.assert_called_once()
            called_url, called_headers = cb_mock.call_args[0]
            self.assertEqual(called_url, fresh_url)
        finally:
            if modal.winfo_exists():
                modal.destroy()

    def test_10_gui_refresh_link_context_menu_and_action_bar(self):
        self.root = tk.Tk()
        self.root.withdraw()
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(hasattr(gui, "btn_refresh_link"))
            self.assertIn(gui.btn_refresh_link.cget("state"), ("normal", "disabled"))
            self.assertTrue(hasattr(gui, "tree_context_menu"))
            self.assertGreater(gui.tree_context_menu.index(tk.END), 0)

            gui._engine_error_cb("HTTP 403 Forbidden")
            self.root.update()
            self.assertEqual(gui.btn_refresh_link.cget("state"), "normal")
            self.assertEqual(gui.card_size.cget("text"), "Ready")

            gui._open_refresh_link_dialog()
            self.assertIsNotNone(gui._refresh_modal)
            self.assertTrue(gui._refresh_modal.winfo_exists())

            fresh_url = f"{self.base_url}/fresh.bin"
            gui._on_link_refreshed_success(fresh_url)
            self.root.update()
            self.assertEqual(gui.entry_url.get(), fresh_url)
        finally:
            gui._cleanup_resources()

    def test_11_coordinator_refresh_link_delegation(self):
        target = os.path.join(self.test_dir, "coord_test.bin")
        stream_info = YouTubeStreamInfo(
            video_id="dQw4w9WgXcQ",
            title="Test Stream",
            clean_filename="test_stream.mp4",
            is_progressive=True,
            video_url=f"{self.base_url}/fresh.bin"
        )
        coord = StreamDownloadCoordinator(
            stream_info=stream_info,
            destination_path=target,
            max_connections=2
        )
        coord.current_engine = TurboDownloadEngine(
            url=stream_info.video_url,
            destination_path=target,
            max_connections=2
        )
        fresh_url = f"{self.base_url}/fresh.bin"
        coord.update_url(fresh_url)
        self.assertEqual(coord.current_engine.url, fresh_url)

        with patch.object(coord.current_engine, "refresh_link", return_value=True) as mock_ref:
            res = coord.refresh_link(fresh_url, auto_resume=True)
            self.assertTrue(res)
            mock_ref.assert_called_once_with(fresh_url, None, True)

    def test_12_validate_refresh_url_rejects_http_200_on_range(self):
        # Server advertises Accept-Ranges in HEAD, but returns 200 OK to Range request
        fake_url = f"{self.base_url}/fake_accept_ranges_200.bin"
        ok, msg, size, ranges = validate_refresh_url(fake_url, expected_size=len(self.test_data), check_range=True)
        self.assertFalse(ok, "Validation must fail when server returns 200 instead of 206 to Range request")
        self.assertFalse(ranges)
        self.assertIn("range", msg.lower())

    def test_13_validate_refresh_url_handles_head_403_presigned_s3(self):
        # Simulates AWS S3 pre-signed URL where HEAD returns 403 because only GET is signed
        presigned_url = f"{self.base_url}/head_forbidden.bin"
        ok, msg, size, ranges = validate_refresh_url(presigned_url, expected_size=len(self.test_data), check_range=True)
        self.assertTrue(ok, f"Pre-signed GET URL must be verified even when HEAD is 403: {msg}")
        self.assertEqual(size, len(self.test_data))
        self.assertTrue(ranges)

    def test_14_validate_refresh_url_206_without_content_range_total(self):
        # Server returns 206 Partial Content without Content-Range total length
        no_total_url = f"{self.base_url}/no_total_206.bin"
        ok, msg, size, ranges = validate_refresh_url(no_total_url, expected_size=0, check_range=True)
        self.assertTrue(ok)
        self.assertTrue(ranges)
        # Verify resolved_size was NOT mistakenly set to 1 from Content-Length: 1
        self.assertNotEqual(size, 1)

    def test_15_engine_aborts_all_workers_on_403_error(self):
        target = os.path.join(self.test_dir, "abort_workers.bin")
        engine = TurboDownloadEngine(
            url=f"{self.base_url}/expire_on_get.bin",
            destination_path=target,
            max_connections=3
        )
        engine.start()
        for _ in range(60):
            if not engine.is_running:
                break
            time.sleep(0.05)

        self.assertFalse(engine.is_running)
        self.assertTrue(engine.has_expired_link)
        self.assertTrue(engine._error_abort_event.is_set(), "_error_abort_event must be set on 403 error")
        time.sleep(0.3)
        alive_workers = [w for w in engine.active_workers if w.is_alive()]
        self.assertEqual(len(alive_workers), 0, "All worker threads must terminate without lingering zombies")

    def test_16_engine_truncates_excess_chunk_part_file_on_resume(self):
        target = os.path.join(self.test_dir, "trunc_test.bin")
        engine = TurboDownloadEngine(
            url=f"{self.base_url}/fresh.bin",
            destination_path=target,
            max_connections=2
        )
        engine.total_size = len(self.test_data)
        engine.supports_ranges = True
        os.makedirs(engine.temp_dir, exist_ok=True)

        # Create chunk 0 with expected size 100, but file on disk has 200 bytes
        c0 = DownloadChunk(0, 0, 99, part_filepath=os.path.join(engine.temp_dir, "p0"))
        with open(c0.part_filepath, "wb") as f:
            f.write(b"X" * 200)
        c0.downloaded_bytes = 200
        engine.chunks = [c0]

        # Call load_state or let supervisor resume
        engine.save_state()
        engine.load_state()

        # Chunk downloaded_bytes should be clamped to expected span (100)
        self.assertEqual(engine.chunks[0].downloaded_bytes, 100)
        self.assertEqual(engine.chunks[0].status, "completed")

    def test_17_coordinator_polymorphic_properties(self):
        target = os.path.join(self.test_dir, "coord_poly.bin")
        stream_info = YouTubeStreamInfo(
            video_id="test12345",
            title="Poly Stream",
            clean_filename="poly.mp4",
            is_progressive=True,
            video_url=f"{self.base_url}/fresh.bin"
        )
        coord = StreamDownloadCoordinator(
            stream_info=stream_info,
            destination_path=target,
            max_connections=2
        )
        self.assertEqual(coord.url, f"{self.base_url}/fresh.bin")
        self.assertTrue(coord.supports_ranges)
        self.assertFalse(coord.has_expired_link)
        self.assertEqual(coord.last_http_status, 0)

class TestSpeedFormatting(unittest.TestCase):
    """Verifies format_speed across units, edge cases, clamping, and error handling."""

    def test_format_speed_clamping_and_zero(self):
        from smart_download.utils import format_speed
        self.assertEqual(format_speed(0), "0 B/s")
        self.assertEqual(format_speed(-1), "0 B/s")
        self.assertEqual(format_speed(-999999), "0 B/s")
        self.assertEqual(format_speed(0, allow_unlimited=True), "Unlimited")
        self.assertEqual(format_speed(-10, allow_unlimited=True), "Unlimited")

    def test_format_speed_units_bytes_kb_mb_gb(self):
        from smart_download.utils import format_speed
        self.assertEqual(format_speed(500), "500 B/s")
        self.assertEqual(format_speed(1024), "1.0 KB/s")
        self.assertEqual(format_speed(1536), "1.5 KB/s")
        self.assertEqual(format_speed(1048576), "1.00 MB/s")
        self.assertEqual(format_speed(5242880), "5.00 MB/s")
        self.assertEqual(format_speed(1073741824), "1.00 GB/s")
        self.assertEqual(format_speed(2.5 * 1073741824), "2.50 GB/s")

    def test_format_speed_invalid_and_non_numeric_types(self):
        from smart_download.utils import format_speed
        self.assertEqual(format_speed(None), "0 B/s")
        self.assertEqual(format_speed("invalid"), "0 B/s")
        self.assertEqual(format_speed(""), "0 B/s")
        self.assertEqual(format_speed("2048"), "2.0 KB/s")


if __name__ == "__main__":
    unittest.main()
