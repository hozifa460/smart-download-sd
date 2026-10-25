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

class TestBrowserBridgeServer(unittest.TestCase):
    """Verifies BrowserBridgeServer lifecycle, CORS headers, endpoints, and validation."""

    @classmethod
    def setUpClass(cls):
        cls.port = 19288
        cls.received_downloads = []

        def _on_dl(payload):
            cls.received_downloads.append(payload)

        cls.server = BrowserBridgeServer(port=cls.port, on_download=_on_dl)
        cls.server.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        TestBrowserBridgeServer.received_downloads.clear()

    def test_get_ping(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/ping")
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("app"), "Smart Download (SD)")
            self.assertTrue(data.get("active"))

    def test_options_cors(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/download", method="OPTIONS")
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods", ""))

    def test_post_download_valid(self):
        payload = {
            "url": "https://speed.cloudflare.com/test_file.iso",
            "filename": "test_file.iso",
            "referrer": "https://speed.cloudflare.com",
            "start_immediately": True
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/download",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))

        self.assertEqual(len(self.received_downloads), 1)
        received = self.received_downloads[0]
        self.assertEqual(received["url"], "https://speed.cloudflare.com/test_file.iso")
        self.assertEqual(received["filename"], "test_file.iso")
        self.assertTrue(received["start_immediately"])

    def test_post_download_malformed_json(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/download",
            data=b"not valid json {{{",
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 400)

    def test_post_download_missing_url(self):
        payload = {"filename": "test.zip"}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/download",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 400)

    def test_post_download_invalid_scheme(self):
        payload = {"url": "javascript:alert(1)"}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/download",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 400)

    def test_404_not_found(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/nonexistent_endpoint")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 404)

class TestBrowserBridgeConcurrency(unittest.TestCase):
    """Verifies that BrowserBridgeServer can handle rapid concurrent POST requests without drop."""

    @classmethod
    def setUpClass(cls):
        cls.port = 19295
        cls.received_urls = []
        cls.lock = threading.Lock()

        def _on_dl(payload):
            with cls.lock:
                cls.received_urls.append(payload["url"])

        cls.server = BrowserBridgeServer(port=cls.port, on_download=_on_dl)
        cls.server.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_concurrent_downloads(self):
        def _send(idx):
            data = json.dumps({
                "url": f"https://example.com/file_{idx}.zip",
                "filename": f"file_{idx}.zip"
            }).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/download",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)

        threads = []
        for i in range(20):
            t = threading.Thread(target=_send, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        self.assertEqual(len(self.received_urls), 20)

class TestExtensionManifestAndAssets(unittest.TestCase):
    """Validates WebExtension Manifest V3 syntax, compatibility, and file assets."""

    def test_manifest_v3_structure(self):
        ext_dir = os.path.join(PROJECT_ROOT, "extension")
        manifest_path = os.path.join(ext_dir, "manifest.json")
        self.assertTrue(os.path.exists(manifest_path), "manifest.json does not exist")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual(manifest.get("manifest_version"), 3)
        self.assertEqual(manifest.get("name"), "Smart Download (SD) Integration")
        self.assertIn("downloads", manifest.get("permissions", []))
        self.assertIn("contextMenus", manifest.get("permissions", []))
        self.assertIn("storage", manifest.get("permissions", []))

        # Chrome MV3 requires background.service_worker and prohibits background.scripts
        bg = manifest.get("background", {})
        self.assertIn("service_worker", bg, "background.service_worker is required for MV3")
        self.assertNotIn("scripts", bg, "background.scripts is invalid in Manifest V3")

        # Firefox MV3 requires gecko ID for installation
        settings = manifest.get("browser_specific_settings", {})
        self.assertIn("gecko", settings)
        self.assertTrue(settings["gecko"].get("id"))

        # Verify all referenced files exist on disk
        sw_file = os.path.join(ext_dir, bg["service_worker"])
        self.assertTrue(os.path.exists(sw_file), f"Service worker missing: {sw_file}")

        popup_html = os.path.join(ext_dir, manifest.get("action", {}).get("default_popup", ""))
        self.assertTrue(os.path.exists(popup_html), f"Popup HTML missing: {popup_html}")

        for icon_key, icon_rel in manifest.get("icons", {}).items():
            icon_path = os.path.join(ext_dir, icon_rel)
            self.assertTrue(os.path.exists(icon_path), f"Icon {icon_key} missing at {icon_path}")
            self.assertGreater(os.path.getsize(icon_path), 0, f"Icon {icon_key} is 0 bytes")

    def test_extension_origin_includes_unpacked_id(self):
        import register_browser
        origins = register_browser.get_default_extension_origins()
        unpacked_id = register_browser.compute_unpacked_extension_id(
            os.path.join(PROJECT_ROOT, "extension")
        )
        self.assertIn(f"chrome-extension://{unpacked_id}/", origins)

class TestNativeMessagingHostProtocol(unittest.TestCase):
    """Verifies stdio 32-bit length-prefixed Native Messaging Host protocol and commands."""

    def test_read_and_send_message_binary_encoding(self):
        import io
        test_payload = {
            "action": "download",
            "url": "https://speed.cloudflare.com/50mb.bin",
            "filename": "speed_test.bin"
        }

        # Test sending
        out_buf = io.BytesIO()
        ok = send_message(test_payload, stream=out_buf)
        self.assertTrue(ok)

        # Verify length prefix matches JSON payload byte length
        raw_bytes = out_buf.getvalue()
        self.assertGreater(len(raw_bytes), 4)
        length_prefix = struct.unpack("@I", raw_bytes[:4])[0]
        json_bytes = raw_bytes[4:]
        self.assertEqual(length_prefix, len(json_bytes))

        # Test reading
        in_buf = io.BytesIO(raw_bytes)
        received = read_message(stream=in_buf)
        self.assertEqual(received, test_payload)

    def test_handle_payload_ping_offline(self):
        # Ping with port not bound
        res = handle_payload({"action": "ping"}, port=59998)
        self.assertTrue(res.get("success"))
        self.assertFalse(res.get("app_online"))

    def test_handle_payload_missing_url(self):
        res = handle_payload({"action": "download"})
        self.assertFalse(res.get("success"))
        self.assertIn("url", res.get("error", "").lower())

    def test_handle_payload_download_forwarding(self):
        # Start a temporary HTTP server acting as the desktop loopback bridge
        received_data = []

        class MockBridgeHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
            def do_POST(self):
                clen = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(clen)
                received_data.append(json.loads(body.decode("utf-8")))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"success": true, "message": "Dispatched"}')

        server = socketserver.TCPServer(("127.0.0.1", 0), MockBridgeHandler)
        port = server.server_address[1]
        srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
        srv_thread.start()

        try:
            payload = {
                "action": "download",
                "url": "https://example.com/testfile.zip",
                "filename": "testfile.zip"
            }
            res = handle_payload(payload, port=port)
            self.assertTrue(res.get("success"))
            self.assertEqual(len(received_data), 1)
            self.assertEqual(received_data[0]["url"], "https://example.com/testfile.zip")
            self.assertEqual(received_data[0]["filename"], "testfile.zip")
        finally:
            server.shutdown()
            server.server_close()

class TestBrowserRegistryIntegration(unittest.TestCase):
    """Verifies Windows Registry Native Messaging manifest generation and key management."""

    def test_compute_unpacked_extension_id(self):
        test_path = r"C:\Projects\Extensions\TurboExtension"
        ext_id = compute_unpacked_extension_id(test_path)
        self.assertEqual(len(ext_id), 32)
        # Must only contain characters a through p
        for char in ext_id:
            self.assertTrue("a" <= char <= "p", f"Invalid char {char} in extension id {ext_id}")

    def test_generate_host_manifest_structure(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            bat_path = os.path.join(tmp_dir, "launcher.bat")
            with open(bat_path, "w") as f:
                f.write("@echo off\n")

            json_path = os.path.join(tmp_dir, "manifest.json")
            res_path = generate_host_manifest(bat_path, json_path, ["chrome-extension://test/"])

            self.assertTrue(os.path.exists(res_path))
            with open(res_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.assertEqual(data["name"], "com.smartdownload.host")
            self.assertEqual(data["type"], "stdio")
            self.assertIn("chrome-extension://test/", data["allowed_origins"])
            self.assertEqual(data["path"], os.path.abspath(bat_path))

    def test_registry_registration_and_status(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Test registration
            reg_res = register_native_host(target_dir=tmp_dir)
            self.assertTrue(reg_res.get("success"))
            self.assertTrue(os.path.exists(reg_res["manifest_path"]))
            self.assertTrue(os.path.exists(reg_res["launcher_path"]))

            # Verify registry check
            self.assertTrue(is_browser_registered("chrome"))
            self.assertTrue(is_browser_registered("edge"))

            status = get_browser_reg_status()
            self.assertTrue(status["chrome_registered"])
            self.assertTrue(status["edge_registered"])
            self.assertTrue(status["is_registered"])

            # Clean unregistration
            unreg_res = unregister_native_host()
            self.assertTrue(unreg_res.get("success"))
            self.assertFalse(is_browser_registered("chrome"))
            self.assertFalse(is_browser_registered("edge"))

    def test_extension_registry_keys(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile, winreg
        from register_browser import CHROME_EXT_KEY_PREFIX, EDGE_EXT_KEY_PREFIX, STATIC_EXTENSION_ID

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a mock extension folder with manifest
            ext_dir = os.path.join(tmp_dir, "extension")
            os.makedirs(ext_dir, exist_ok=True)
            with open(os.path.join(ext_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "TestExt", "version": "1.0.0"}, f)

            res = register_browser_extensions(extension_dir=ext_dir)
            self.assertTrue(res.get("success"))
            self.assertTrue(is_extension_registered("chrome", STATIC_EXTENSION_ID))
            self.assertTrue(is_extension_registered("edge", STATIC_EXTENSION_ID))

            # Verify registry key contents
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{CHROME_EXT_KEY_PREFIX}\{STATIC_EXTENSION_ID}")
            ver, _ = winreg.QueryValueEx(key, "version")
            path_val, _ = winreg.QueryValueEx(key, "path")
            winreg.CloseKey(key)
            self.assertEqual(ver, "1.0.0")
            self.assertEqual(path_val, os.path.abspath(ext_dir))

            # Unregister
            unreg = unregister_browser_extensions()
            self.assertTrue(unreg.get("success"))
            self.assertFalse(is_extension_registered("chrome", STATIC_EXTENSION_ID))
            self.assertFalse(is_extension_registered("edge", STATIC_EXTENSION_ID))

    def test_idempotent_browser_registration_fast(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            # First run: initial registration
            init_res = check_and_register_browser(target_dir=tmp_dir)
            self.assertTrue(init_res.get("success"))
            self.assertTrue(init_res.get("healed"))

            # Second run: should be completely idempotent and complete in < 5ms
            idempotent_res = check_and_register_browser(target_dir=tmp_dir, force=False)
            self.assertTrue(idempotent_res.get("success"))
            self.assertTrue(idempotent_res.get("idempotent"))
            self.assertFalse(idempotent_res.get("healed"))
            # Must satisfy < 5ms requirement
            self.assertLess(idempotent_res.get("duration_ms", 999.0), 5.0,
                            f"Idempotent check took {idempotent_res.get('duration_ms')}ms (expected < 5ms)")

            # Clean up
            unregister_native_host()

    def test_self_healing_browser_registration(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile, winreg
        with tempfile.TemporaryDirectory() as tmp_dir1, tempfile.TemporaryDirectory() as tmp_dir2:
            # 1. Register with dir1
            r1 = check_and_register_browser(target_dir=tmp_dir1)
            self.assertTrue(r1.get("success"))

            # 2. Simulate path change or relocation to dir2: check_and_register_browser should detect
            # mismatch and self-heal by updating to dir2
            r2 = check_and_register_browser(target_dir=tmp_dir2)
            self.assertTrue(r2.get("success"))
            self.assertTrue(r2.get("healed"))
            self.assertFalse(r2.get("idempotent"))

            # Verify registry key now points to dir2
            from register_browser import CHROME_REG_KEY
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHROME_REG_KEY)
            manifest_val, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            expected_m2 = os.path.normcase(os.path.abspath(os.path.join(tmp_dir2, "com.smartdownload.host.json")))
            self.assertEqual(os.path.normcase(os.path.abspath(manifest_val)), expected_m2)

            # Clean up
            unregister_native_host()

    def test_self_healing_corrupted_or_missing_launcher_in_manifest(self):
        """Verifies that check_and_register_browser heals if manifest points to missing/wrong launcher."""
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            # First register normally
            r1 = check_and_register_browser(target_dir=tmp_dir)
            self.assertTrue(r1.get("success"))

            # Simulate corrupted manifest pointing to non-existent launcher
            manifest_file = os.path.join(tmp_dir, "com.smartdownload.host.json")
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump({"name": "com.smartdownload.host", "path": r"C:\fake\missing\sd_host.bat", "type": "stdio"}, f)

            # Check and register should detect the broken launcher path and heal it
            r2 = check_and_register_browser(target_dir=tmp_dir)
            self.assertTrue(r2.get("success"))
            self.assertTrue(r2.get("healed"), "check_and_register_browser must heal a manifest pointing to a nonexistent launcher")

            # Verify manifest was healed with valid existing launcher path
            with open(manifest_file, "r", encoding="utf-8") as f:
                healed_data = json.load(f)
            self.assertTrue(os.path.isfile(healed_data["path"]))
            self.assertEqual(os.path.normcase(os.path.dirname(os.path.abspath(healed_data["path"]))),
                             os.path.normcase(os.path.abspath(tmp_dir)))

            # Clean up
            unregister_native_host()

    def test_get_default_extension_origins_with_target_dir(self):
        """Verifies that get_default_extension_origins includes unpacked ID for target_dir/extension."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            ext_dir = os.path.join(tmp_dir, "extension")
            os.makedirs(ext_dir, exist_ok=True)
            with open(os.path.join(ext_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "Test"}, f)

            expected_id = compute_unpacked_extension_id(ext_dir)
            origins = get_default_extension_origins(target_dir=tmp_dir)
            self.assertIn(f"chrome-extension://{expected_id}/", origins)

    def test_fast_launcher_batch_executable_priority(self):
        """Verifies launcher batch checks TurboDownloader.exe before searching for python."""
        import tempfile
        from register_browser import generate_launcher_batch
        with tempfile.TemporaryDirectory() as tmp_dir:
            bat_path = os.path.join(tmp_dir, "sd_host.bat")
            generate_launcher_batch(bat_path)
            with open(bat_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Ensure TurboDownloader.exe check appears before where python
            idx_exe = content.find("SmartDownload.exe")
            idx_py = content.find("where py")
            self.assertNotEqual(idx_exe, -1)
            if idx_py != -1:
                self.assertLess(idx_exe, idx_py, "SmartDownload.exe standalone check must precede python search in batch launcher")


if __name__ == "__main__":
    unittest.main()
