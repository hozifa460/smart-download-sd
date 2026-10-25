"""
Unit and stress test suite verifying Stage 7: Enterprise Security Hardening & Heavy Stress Resilience.
Tests:
1. Zip-Slip & Tar-Slip Path Traversal Protection
2. Localhost Bridge CSRF Origin header validation & Concurrency Limiting
3. Windows Reserved Device Names & Content-Disposition Sanitization
4. Blocking of file:// protocol redirect downgrade
5. 500-line activity log cap under rapid insertion
6. Disk space pre-check failure
7. Instant socket interrupt on pause and start double-click guard
"""
import os
import sys
import json
import time
import zipfile
import tarfile
import tempfile
import threading
import urllib.request
import urllib.error
import unittest
from unittest.mock import MagicMock, patch

_tests_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_tests_dir)
_src_dir = os.path.join(_root_dir, "src")
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

try:
    import tkinter as tk
except Exception:
    tk = None  # type: ignore

from smart_download.utils.archive_utils import (
    auto_unpack_archive,
    _safe_extract_zip,
    _safe_extract_tar
)
from smart_download.utils.url_utils import (
    clean_download_filename,
    parse_filename_from_cd_header,
    WINDOWS_RESERVED_NAMES
)
from smart_download.services.browser.bridge_server import (
    BrowserBridgeServer,
    BrowserBridgeHandler
)
from smart_download.core.html_resolver import resolve_real_download_url
from smart_download.core.engine import TurboDownloadEngine
from smart_download.ui.controllers.dispatch_controller import DispatchControllerMixin
from smart_download.ui.controllers.download_controller import DownloadControllerMixin


class TestZipTarSlipSecurity(unittest.TestCase):
    """Verifies that zip and tar extraction strictly rejects Zip-Slip path traversal attacks."""

    def test_zip_slip_rejection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = os.path.join(tmp_dir, "malicious.zip")
            out_dir = os.path.join(tmp_dir, "extracted")
            os.makedirs(out_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("../../evil.bat", "@echo off\nevil")

            with zipfile.ZipFile(zip_path, "r") as zf:
                with self.assertRaises(ValueError) as ctx:
                    _safe_extract_zip(zf, out_dir)
                self.assertIn("Zip Slip", str(ctx.exception))

            res = auto_unpack_archive(zip_path, out_dir)
            self.assertIsNone(res)
            evil_path = os.path.abspath(os.path.join(tmp_dir, "..", "evil.bat"))
            self.assertFalse(os.path.exists(evil_path))

    def test_tar_slip_rejection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tar_path = os.path.join(tmp_dir, "malicious.tar")
            out_dir = os.path.join(tmp_dir, "extracted")
            os.makedirs(out_dir, exist_ok=True)

            with tarfile.open(tar_path, "w") as tf:
                ti = tarfile.TarInfo(name="../../evil.sh")
                payload = b"#!/bin/sh\nevil"
                ti.size = len(payload)
                import io
                tf.addfile(ti, io.BytesIO(payload))

            with tarfile.open(tar_path, "r") as tf:
                with self.assertRaises(ValueError) as ctx:
                    _safe_extract_tar(tf, out_dir)
                self.assertIn("Tar Slip", str(ctx.exception))

    def test_tar_slip_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tar_path = os.path.join(tmp_dir, "symlink_evil.tar")
            out_dir = os.path.join(tmp_dir, "extracted")
            os.makedirs(out_dir, exist_ok=True)

            with tarfile.open(tar_path, "w") as tf:
                ti = tarfile.TarInfo(name="evil_link")
                ti.type = tarfile.SYMTYPE
                ti.linkname = "../../evil.sh"
                tf.addfile(ti)

            with tarfile.open(tar_path, "r") as tf:
                with self.assertRaises(ValueError) as ctx:
                    _safe_extract_tar(tf, out_dir)
                self.assertIn("Tar Slip", str(ctx.exception))

            res = auto_unpack_archive(tar_path, out_dir)
            self.assertIsNone(res)

    def test_legitimate_archive_extraction(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = os.path.join(tmp_dir, "safe_archive.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("safe_sub/hello.txt", "hello safe world")

            res = auto_unpack_archive(zip_path, tmp_dir)
            self.assertIsNotNone(res)
            self.assertTrue(os.path.exists(os.path.join(res, "safe_sub", "hello.txt")))


class TestBridgeServerOriginCSRFSecurity(unittest.TestCase):
    """Verifies that the localhost loopback bridge strictly rejects untrusted web Origins with 403."""

    @classmethod
    def setUpClass(cls):
        cls.port = 19298
        cls.server = BrowserBridgeServer(port=cls.port)
        cls.server.start()
        time.sleep(0.15)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_handler_timeout_and_semaphore(self):
        self.assertEqual(BrowserBridgeHandler.timeout, 5.0)
        self.assertEqual(BrowserBridgeHandler._REQUEST_SEMAPHORE._initial_value, 16)

    def test_reject_external_web_origin_download(self):
        url = f"http://127.0.0.1:{self.port}/download"
        data = json.dumps({"url": "https://example.com/file.zip"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://evil-attacker.com"
            }
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 403)

    def test_reject_external_web_origin_show(self):
        url = f"http://127.0.0.1:{self.port}/show"
        req = urllib.request.Request(
            url,
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": "http://malicious.org"
            }
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 403)

    def test_allow_browser_extension_origin(self):
        url = f"http://127.0.0.1:{self.port}/download"
        data = json.dumps({"url": "https://example.com/valid.zip"}).encode("utf-8")
        for ext_origin in (
            "chrome-extension://abcdefghijklmnopabcdefghijklmnop",
            "moz-extension://b1c2d3e4-5678-90ab",
            "edge-extension://abcdefghijklmnopabcdefghijklmnop",
            "safari-web-extension://com.smartdownload.helper"
        ):
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Origin": ext_origin
                }
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                self.assertEqual(resp.status, 200)

    def test_allow_missing_origin_for_local_cli(self):
        url = f"http://127.0.0.1:{self.port}/download"
        data = json.dumps({"url": "https://example.com/cli.zip"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)

    def test_reject_null_origin(self):
        url = f"http://127.0.0.1:{self.port}/download"
        data = json.dumps({"url": "https://example.com/file.zip"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Origin": "null"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 403)

    def test_reject_file_origin(self):
        url = f"http://127.0.0.1:{self.port}/download"
        data = json.dumps({"url": "https://example.com/file.zip"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Origin": "file:///C:/evil.html"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 403)


class TestFilenameSanitizationAndWindowsReserved(unittest.TestCase):
    """Verifies that filenames are sanitized against Windows reserved names and path traversals."""

    def test_windows_reserved_names_prefixed(self):
        for name in ("CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"):
            cleaned = clean_download_filename(f"{name}.txt")
            self.assertEqual(cleaned, f"_{name}.txt")

            cleaned_no_ext = clean_download_filename(name)
            self.assertEqual(cleaned_no_ext, f"_{name}")

            cleaned_lower = clean_download_filename(name.lower() + ".mp4")
            self.assertEqual(cleaned_lower, f"_{name.lower()}.mp4")

    def test_non_reserved_names_unchanged(self):
        self.assertEqual(clean_download_filename("CON_file.txt"), "CON_file.txt")
        self.assertEqual(clean_download_filename("my_document.pdf"), "my_document.pdf")

    def test_strip_path_traversal_and_control_chars(self):
        self.assertEqual(clean_download_filename("../../evil.bat"), "evil.bat")
        self.assertEqual(clean_download_filename("..\\..\\evil.bat"), "evil.bat")
        self.assertEqual(clean_download_filename("file\x00\x1f_test.bin"), "file_test.bin")

    def test_content_disposition_traversal_and_reserved_names(self):
        h1 = 'attachment; filename="../../evil.bat"'
        self.assertEqual(parse_filename_from_cd_header(h1), "evil.bat")

        h2 = 'attachment; filename="..\\..\\win32.exe"'
        self.assertEqual(parse_filename_from_cd_header(h2), "win32.exe")

        h3 = 'attachment; filename="CON.txt"'
        self.assertEqual(parse_filename_from_cd_header(h3), "_CON.txt")

        h4 = "attachment; filename*=UTF-8''..%2F..%2FAUX.iso"
        self.assertEqual(parse_filename_from_cd_header(h4), "_AUX.iso")

    def test_truncation_does_not_create_reserved_name(self):
        cleaned = clean_download_filename("CON_12345.txt", max_length=7)
        self.assertEqual(cleaned, "_CO.txt")
        self.assertNotIn(cleaned.split(".")[0].upper(), WINDOWS_RESERVED_NAMES)

    def test_engine_probe_content_disposition_sanitization(self):
        engine = TurboDownloadEngine(
            url="http://example.com/exploit.bin",
            destination_path=os.path.join(tempfile.gettempdir(), "test_dest.bin")
        )
        mock_resp = MagicMock()
        mock_resp.geturl.return_value = "http://example.com/exploit.bin"
        mock_resp.headers = {
            "Content-Length": "1024",
            "Accept-Ranges": "bytes",
            "Content-Disposition": 'attachment; filename="../../CON.txt"'
        }
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            engine.probe()
        self.assertEqual(engine.filename, "_CON.txt")


class TestFileRedirectSchemeSecurity(unittest.TestCase):
    """Verifies that redirect downgrades to file:// or non-network schemes are blocked."""

    def test_resolve_real_download_url_file_redirect_blocked(self):
        mock_resp = MagicMock()
        mock_resp.geturl.return_value = "file:///C:/Windows/win.ini"
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with self.assertRaises(ValueError) as ctx:
                resolve_real_download_url("http://example.com/exploit", force_refresh=True)
            self.assertIn("Unsupported redirect scheme", str(ctx.exception))

    def test_engine_probe_file_redirect_blocked(self):
        mock_resp = MagicMock()
        mock_resp.geturl.return_value = "file:///etc/shadow"
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        engine = TurboDownloadEngine(
            url="http://example.com/probe_exploit",
            destination_path=os.path.join(tempfile.gettempdir(), "test_file.bin")
        )
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with self.assertRaises(ValueError) as ctx:
                engine.probe()
            self.assertIn("Unsupported redirect scheme", str(ctx.exception))


class TestStressAndHeavyLoadResilience(unittest.TestCase):
    """Verifies heavy stress stability: 500-line activity log cap, disk pre-check, and double-click guard."""

    def test_activity_log_capped_at_500_lines(self):
        if not tk:
            self.skipTest("Tkinter not available")
        root = tk.Tk()
        root.withdraw()

        class DummyUI(DispatchControllerMixin):
            def __init__(self):
                self.root = root
                self._closing = False
                self.txt_log = tk.Text(root)

        ui = DummyUI()
        try:
            for i in range(1000):
                ui.log(f"Stress log message entry #{i}")
            root.update()

            content_lines = len(ui.txt_log.get("1.0", "end-1c").splitlines())
            self.assertLessEqual(content_lines, 500)
            self.assertIn("entry #999", ui.txt_log.get("1.0", "end-1c"))
        finally:
            root.destroy()

    def test_disk_space_pre_check_failure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest_file = os.path.join(tmp_dir, "huge_file.iso")
            error_msg_captured = []

            engine = TurboDownloadEngine(
                url="http://example.com/huge_file.iso",
                destination_path=dest_file,
                on_error=lambda err: error_msg_captured.append(err)
            )
            engine.total_size = 100 * 1024 * 1024 * 1024  # 100 GB

            mock_usage = MagicMock(free=1024 * 1024)  # 1 MB free
            with patch("shutil.disk_usage", return_value=mock_usage):
                with patch.object(engine, "probe"):
                    engine._supervisor_loop()

            self.assertTrue(any("Insufficient disk space" in msg for msg in error_msg_captured))

    def test_pause_aborts_active_connections_instantly(self):
        engine = TurboDownloadEngine(
            url="http://example.com/file.zip",
            destination_path=os.path.join(tempfile.gettempdir(), "test_pause.zip")
        )
        engine.is_running = True
        mock_conn1 = MagicMock()
        mock_conn2 = MagicMock()
        engine._active_connections.extend([mock_conn1, mock_conn2])

        engine.pause()

        self.assertTrue(engine.is_paused)
        self.assertTrue(engine._pause_event.is_set())
        mock_conn1.close.assert_called_once()
        mock_conn2.close.assert_called_once()
        self.assertEqual(len(engine._active_connections), 0)

    def test_double_click_guard_on_start(self):
        class DummyController(DownloadControllerMixin):
            def __init__(self):
                self.engine = None
                self._is_resolving_start = False
                self.btn_start = MagicMock()
                self.entry_url = MagicMock()
                self.entry_dest = MagicMock()
                self.entry_url.get.return_value = "http://example.com/file.zip"
                self.entry_dest.get.return_value = "C:/Downloads/file.zip"
                self.conn_var = MagicMock()
                self.conn_var.get.return_value = "8"
                self.entry_custom_speed = MagicMock()
                self.entry_custom_speed.get.return_value = "0"
                self._resolve_called = 0

            def _resolve_real_url_async(self, url, on_resolved):
                self._resolve_called += 1

        ctrl = DummyController()
        ctrl._on_start_download()
        self.assertEqual(ctrl._resolve_called, 1)
        self.assertTrue(ctrl._is_resolving_start)
        ctrl.btn_start.configure.assert_called_with(state="disabled")

        # Second rapid click must be ignored!
        ctrl._on_start_download()
        self.assertEqual(ctrl._resolve_called, 1)

    def test_disk_space_pre_check_non_existent_dest_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest_file = os.path.join(tmp_dir, "non_existent_subfolder", "file.iso")
            error_msg_captured = []

            engine = TurboDownloadEngine(
                url="http://example.com/file.iso",
                destination_path=dest_file,
                on_error=lambda err: error_msg_captured.append(err)
            )
            engine.total_size = 100 * 1024 * 1024 * 1024  # 100 GB

            mock_usage = MagicMock(free=1024 * 1024)  # 1 MB free
            with patch("shutil.disk_usage", return_value=mock_usage):
                with patch.object(engine, "probe"):
                    engine._supervisor_loop()

            self.assertTrue(any("Insufficient disk space" in msg for msg in error_msg_captured))

    def test_double_click_guard_reset_on_cancel_or_error(self):
        class DummyController(DownloadControllerMixin):
            def __init__(self):
                self.engine = None
                self._is_resolving_start = False
                self.btn_start = MagicMock()
                self.entry_url = MagicMock()
                self.entry_dest = MagicMock()
                self.entry_url.get.return_value = "http://example.com/file.zip"
                self.entry_dest.get.return_value = "C:/Downloads/file.zip"
                self.conn_var = MagicMock()
                self.conn_var.get.return_value = "8"
                self.entry_custom_speed = MagicMock()
                self.entry_custom_speed.get.return_value = "0"
                self.saved_on_resolved = None

            def _resolve_real_url_async(self, url, on_resolved):
                self.saved_on_resolved = on_resolved

            def log(self, msg):
                pass

        ctrl = DummyController()
        ctrl._on_start_download()
        self.assertTrue(ctrl._is_resolving_start)

        # Simulate resolution error: guard must be reset and btn_start re-enabled!
        ctrl.saved_on_resolved({"url": "http://example.com/file.zip", "error": "Network timeout", "resolved": False})
        self.assertFalse(ctrl._is_resolving_start)
        ctrl.btn_start.configure.assert_called_with(state="normal")


if __name__ == "__main__":
    unittest.main()
