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

class MockHtmlResolverHandler(http.server.BaseHTTPRequestHandler):
    """Local HTTP mock server for testing resolve_real_download_url and HTML download protection."""
    def log_message(self, format, *args):
        pass

    def do_HEAD(self):
        self._handle_req(send_body=False)

    def do_GET(self):
        self._handle_req(send_body=True)

    def _handle_req(self, send_body=True):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path

        if path in ("/file.bin", "/file.exe"):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", "1024")
            self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
            self.end_headers()
            if send_body:
                self.wfile.write(b"b" * 1024)

        elif path.startswith("/page-with-link"):
            body = (
                b"<!doctype html><html><head><title>Thanks</title></head><body>"
                b"<h1>Thank you for downloading ZadLoop</h1>"
                b"<p>Your download should start automatically. If not, "
                b"<a href=\"/download/windows\">click here for Windows</a>.</p>"
                b"</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        elif path == "/download/windows":
            # 302 redirect to /files/App-1.0-x64.exe
            self.send_response(302)
            self.send_header("Location", "/files/App-1.0-x64.exe")
            self.end_headers()

        elif path == "/files/App-1.0-x64.exe":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", "2048")
            self.send_header("Content-Disposition", 'attachment; filename="App-1.0-x64.exe"')
            self.end_headers()
            if send_body:
                self.wfile.write(b"e" * 2048)

        elif path == "/nav-only":
            body = (
                b"<!doctype html><html><head><title>Nav Only</title></head><body>"
                b"<a href=\"/about\">About Us</a>"
                b"<a href=\"/style.css\">Stylesheet</a>"
                b"<a href=\"/script.js\">Javascript</a>"
                b"</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        elif path == "/about":
            body = b"<!doctype html><html><body>About Page Content</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        elif path == "/meta-refresh":
            body = (
                b"<!doctype html><html><head>"
                b"<meta http-equiv=\"refresh\" content=\"0;url=/f/setup.msi\">"
                b"</head><body>Please wait...</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        elif path == "/f/setup.msi":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-msi")
            self.send_header("Content-Length", "4096")
            self.send_header("Content-Disposition", 'attachment; filename="setup.msi"')
            self.end_headers()
            if send_body:
                self.wfile.write(b"m" * 4096)

        elif path in ("/html-trap.bin", "/thanks.bin", "/webpage"):
            body = b"<!doctype html><html><body>Server returned web page</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        else:
            self.send_error(404)

class TestHtmlLinkResolverAndStartupToast(unittest.TestCase):
    """Verifies resolve_real_download_url, HTML download protection safety net, and StartupWelcomeToast."""

    @classmethod
    def setUpClass(cls):
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), MockHtmlResolverHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sd_resolver_test_")
        self._orig_toast_env = os.environ.pop("SD_DISABLE_STARTUP_TOAST", None)

    def tearDown(self):
        if self._orig_toast_env is not None:
            os.environ["SD_DISABLE_STARTUP_TOAST"] = self._orig_toast_env
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_non_html_file_url_returned_unchanged(self):
        """Non-HTML file URL is returned unchanged with is_html=False."""
        url = f"http://127.0.0.1:{self.port}/file.exe"
        info = resolve_real_download_url(url)
        self.assertFalse(info["is_html"])
        self.assertFalse(info["resolved"])
        self.assertTrue(info["url"].endswith("/file.exe"))
        self.assertEqual(info["filename"], "file.exe")
        self.assertEqual(info["error"], "")

    def test_html_page_with_redirect_resolved_to_real_download(self):
        """HTML page with <a href="/download/windows"> 302-redirecting to .exe is resolved."""
        url = f"http://127.0.0.1:{self.port}/page-with-link?platform=windows"
        info = resolve_real_download_url(url)
        self.assertFalse(info["is_html"])
        self.assertTrue(info["resolved"])
        self.assertTrue(info["url"].endswith("App-1.0-x64.exe"))
        self.assertEqual(info["filename"], "App-1.0-x64.exe")
        self.assertEqual(info["size"], 2048)
        self.assertEqual(info["error"], "")

    def test_html_page_with_only_nav_links_unresolved(self):
        """HTML page with only nav links returns is_html=True, resolved=False."""
        url = f"http://127.0.0.1:{self.port}/nav-only"
        info = resolve_real_download_url(url)
        self.assertTrue(info["is_html"])
        self.assertFalse(info["resolved"])

    def test_meta_refresh_resolved(self):
        """<meta http-equiv="refresh" content="0;url=/f/setup.msi"> is resolved."""
        url = f"http://127.0.0.1:{self.port}/meta-refresh"
        info = resolve_real_download_url(url)
        self.assertFalse(info["is_html"])
        self.assertTrue(info["resolved"])
        self.assertTrue(info["url"].endswith("/f/setup.msi"))
        self.assertEqual(info["filename"], "setup.msi")

    def test_gui_clipboard_flow_with_unresolvable_html_does_not_start(self):
        """Unresolvable HTML page clipboard flow does not create _confirm_modal and does not start engine."""
        root = tk.Tk()
        root.withdraw()
        try:
            gui = ModernFramelessGUI(root, start_hidden=True)
            gui._start_hidden = True
            gui._clipboard_sniffer_active = False
            url = f"http://127.0.0.1:{self.port}/nav-only"
            gui._on_clipboard_url_detected(url)

            # Wait for background thread and queue drain
            for _ in range(50):
                gui._drain_dispatch_queue()
                root.update()
                time.sleep(0.04)

            self.assertIsNone(getattr(gui, "_confirm_modal", None))
            self.assertTrue(gui.engine is None or not gui.engine.is_running)

            # Test direct _on_start_download aborts as well
            gui.entry_url.delete(0, tk.END)
            gui.entry_url.insert(0, url)
            gui.entry_dest.delete(0, tk.END)
            gui.entry_dest.insert(0, os.path.join(self.temp_dir, "nav.bin"))
            gui._on_start_download()

            for _ in range(50):
                gui._drain_dispatch_queue()
                root.update()
                time.sleep(0.04)

            self.assertTrue(gui.engine is None or not gui.engine.is_running)
            self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "nav.bin")))

            gui._cleanup_resources()
        finally:
            root.destroy()

    def test_gui_clipboard_flow_with_resolvable_html_creates_modal_with_real_file(self):
        """Resolvable HTML landing page resolves to real binary and shows confirmation modal with .exe in Programs."""
        root = tk.Tk()
        root.withdraw()
        try:
            gui = ModernFramelessGUI(root, start_hidden=True)
            gui._start_hidden = True
            gui._clipboard_sniffer_active = False
            url = f"http://127.0.0.1:{self.port}/page-with-link?platform=windows"
            gui._on_clipboard_url_detected(url)

            # Wait for background thread and queue drain
            for _ in range(50):
                gui._drain_dispatch_queue()
                root.update()
                time.sleep(0.04)
                if getattr(gui, "_confirm_modal", None) is not None:
                    break

            gui._drain_dispatch_queue()
            root.update()

            self.assertIsNotNone(gui._confirm_modal)
            self.assertTrue(gui._confirm_modal.winfo_exists())
            self.assertTrue(gui.entry_url.get().endswith("App-1.0-x64.exe"))
            self.assertIn("Programs", gui.entry_dest.get())
            self.assertTrue(gui.entry_dest.get().endswith("App-1.0-x64.exe"))
            gui._confirm_modal.destroy()
            gui._cleanup_resources()
        finally:
            root.destroy()

    def test_gui_browser_download_unresolvable_html_aborts(self):
        """Browser download received with unresolvable HTML does not create _confirm_modal and does not start engine."""
        root = tk.Tk()
        root.withdraw()
        try:
            gui = ModernFramelessGUI(root, start_hidden=True)
            gui._start_hidden = True
            gui._clipboard_sniffer_active = False
            url = f"http://127.0.0.1:{self.port}/nav-only"
            gui._apply_browser_download({"url": url, "filename": "thanks.bin", "start_immediately": True})

            for _ in range(50):
                gui._drain_dispatch_queue()
                root.update()
                time.sleep(0.04)

            gui._drain_dispatch_queue()
            root.update()

            self.assertIsNone(getattr(gui, "_confirm_modal", None))
            self.assertTrue(gui.engine is None or not gui.engine.is_running)
            gui._cleanup_resources()
        finally:
            root.destroy()

    def test_engine_safety_net_html_to_bin_errors(self):
        """TurboDownloadEngine aborts with clear error when server returns text/html for a .bin destination."""
        url = f"http://127.0.0.1:{self.port}/html-trap.bin"
        dest = os.path.join(self.temp_dir, "thanks.bin")
        engine = TurboDownloadEngine(url, destination_path=dest)
        with self.assertRaises(RuntimeError) as cm:
            engine.probe()
        self.assertIn("Server returned a web page (HTML), not a file", str(cm.exception))
        self.assertFalse(os.path.exists(dest))

    def test_startup_welcome_toast(self):
        """StartupWelcomeToast creates, positions within screen bounds, and auto-destroys."""
        root = tk.Tk()
        root.withdraw()
        try:
            toast = StartupWelcomeToast(root, duration_ms=250)
            self.assertTrue(toast.winfo_exists())
            root.update()

            x = toast.winfo_x()
            y = toast.winfo_y()
            w = toast.winfo_width()
            h = toast.winfo_height()
            sw = toast.winfo_screenwidth()
            sh = toast.winfo_screenheight()

            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + w, sw + 10)
            self.assertLessEqual(y + h, sh + 10)

            # Auto-destruction
            for _ in range(30):
                root.update()
                time.sleep(0.02)
                if not toast.winfo_exists():
                    break

            self.assertFalse(toast.winfo_exists())
        finally:
            try:
                root.destroy()
            except Exception:
                pass

class MockMultiCandidateServer(http.server.BaseHTTPRequestHandler):
    """Local mock server for testing resolve_all_download_candidates."""
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path

        if path == "/file.exe":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", "1024")
            self.end_headers()
            self.wfile.write(b"x" * 1024)

        elif path == "/multi-candidates":
            body = (
                b"<!doctype html><html><head><title>ZadLoop Multi Downloads</title></head><body>"
                b"<h1>Choose your package</h1>"
                b"<a href=\"/files/App-2.0-x64.exe\">Windows 64-bit Installer</a>"
                b"<a href=\"/files/App-2.0-x86.exe\">Windows 32-bit Installer</a>"
                b"<a href=\"/files/App-2.0-arm64.exe\">Windows ARM64 Installer</a>"
                b"<a href=\"/files/App-2.0-portable.zip\">Portable Zip (50 MB)</a>"
                b"<a href=\"/about-us\">About Us</a>"
                b"<a href=\"/privacy\">Privacy Policy</a>"
                b"<a href=\"https://twitter.com/example\">Twitter</a>"
                b"</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/single-candidate":
            body = (
                b"<!doctype html><html><head><title>Download Ready</title></head><body>"
                b"<a href=\"/files/Tool-Setup.exe\">Click here to download Tool</a>"
                b"<a href=\"/contact\">Contact Us</a>"
                b"</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/zero-candidates":
            body = (
                b"<!doctype html><html><head><title>Articles</title></head><body>"
                b"<a href=\"/blog/post-1\">Read Post 1</a>"
                b"<a href=\"/terms\">Terms of Use</a>"
                b"</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

class TestMultipleDownloadCandidates(unittest.TestCase):
    """Verifies resolve_all_download_candidates HTML parsing, filtering, deduplication, and MultipleCandidatesModal GUI."""

    @classmethod
    def setUpClass(cls):
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), MockMultiCandidateServer)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            for child in self.root.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_resolve_all_download_candidates_multiple_html(self):
        """Extracts all valid download candidates while filtering out navigation, policy, and social links."""
        from turbo_downloader import resolve_all_download_candidates

        html = """
        <!DOCTYPE html>
        <html>
        <head><title>App Downloads</title></head>
        <body>
        <h1>Download Packages</h1>
        <a href="/downloads/App-2.0.0-x64.exe">Windows 64-bit Installer</a>
        <a href="/downloads/App-2.0.0-x86.exe">Windows 32-bit Installer</a>
        <a href="/downloads/App-2.0.0-arm64.exe">Windows ARM64 Installer</a>
        <a href="/downloads/App-2.0.0-portable.zip">Portable Archive (30 MB)</a>
        <a href="/about-us">About Us</a>
        <a href="/privacy-policy">Privacy Policy</a>
        <a href="/terms-of-service">Terms</a>
        <a href="https://twitter.com/example">Twitter</a>
        <a href="https://facebook.com/example">Facebook</a>
        <a href="#top">Back to Top</a>
        </body>
        </html>
        """
        candidates = resolve_all_download_candidates(html, base_url="https://example.com/downloads/thanks")
        self.assertEqual(len(candidates), 4)

        fns = [c["filename"] for c in candidates]
        self.assertIn("App-2.0.0-x64.exe", fns)
        self.assertIn("App-2.0.0-x86.exe", fns)
        self.assertIn("App-2.0.0-arm64.exe", fns)
        self.assertIn("App-2.0.0-portable.zip", fns)

        # Verify each candidate dictionary structure
        for c in candidates:
            self.assertIn("url", c)
            self.assertTrue(c["url"].startswith("https://example.com/downloads/App-2.0.0-"))
            self.assertIn("filename", c)
            self.assertIn("ext", c)
            self.assertIn(c["ext"], (".exe", ".zip"))
            self.assertIn("size_bytes", c)
            self.assertIn("title", c)
            self.assertIn("score", c)
            self.assertGreater(c["score"], 0)

        # Check size parsing on portable archive
        portable_cand = [c for c in candidates if c["filename"] == "App-2.0.0-portable.zip"][0]
        self.assertEqual(portable_cand["size_bytes"], 30 * 1024 * 1024)

    def test_resolve_all_download_candidates_deduplication(self):
        """Deduplicates multiple identical links or anchor variations pointing to the same file."""
        from turbo_downloader import resolve_all_download_candidates

        html = """
        <html><body>
        <a href="/builds/release.exe">Download Executable</a>
        <a href="/builds/release.exe#download">Direct Link</a>
        <a href="https://example.com/builds/release.exe">Mirror Link</a>
        </body></html>
        """
        candidates = resolve_all_download_candidates(html, base_url="https://example.com/page")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["filename"], "release.exe")

    def test_resolve_all_download_candidates_zero_candidates(self):
        """Returns empty list for regular web pages with zero downloadable files."""
        from turbo_downloader import resolve_all_download_candidates

        html = """
        <html><body>
        <a href="/home">Home</a>
        <a href="/news">News</a>
        <a href="/contact">Contact</a>
        <a href="/privacy">Privacy</a>
        </body></html>
        """
        candidates = resolve_all_download_candidates(html, base_url="https://example.com/news")
        self.assertEqual(len(candidates), 0)

    def test_resolve_all_download_candidates_single_candidate(self):
        """Returns exactly 1 candidate when page contains only a single download link."""
        from turbo_downloader import resolve_all_download_candidates

        html = """
        <html><body>
        <h1>Thank you!</h1>
        <p>If download didn't start, <a href="/setup.msi">click here</a>.</p>
        <a href="/">Home</a>
        </body></html>
        """
        candidates = resolve_all_download_candidates(html, base_url="https://example.com/thanks")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["filename"], "setup.msi")
        self.assertEqual(candidates[0]["ext"], ".msi")

    def test_resolve_all_download_candidates_from_live_mock_url(self):
        """Fetches and extracts candidates over HTTP network connection."""
        from turbo_downloader import resolve_all_download_candidates

        url = f"http://127.0.0.1:{self.port}/multi-candidates"
        candidates = resolve_all_download_candidates(url)
        self.assertEqual(len(candidates), 4)
        fns = [c["filename"] for c in candidates]
        self.assertIn("App-2.0-x64.exe", fns)
        self.assertIn("App-2.0-portable.zip", fns)

    def test_resolve_all_download_candidates_direct_binary_url(self):
        """Returns empty candidate list when target URL returns direct octet-stream."""
        from turbo_downloader import resolve_all_download_candidates

        url = f"http://127.0.0.1:{self.port}/file.exe"
        candidates = resolve_all_download_candidates(url)
        self.assertEqual(len(candidates), 0)

    def test_multiple_candidates_modal_grab_free_and_ui(self):
        """Verifies MultipleCandidatesModal initialization, grab-free architecture, and geometry."""
        from turbo_downloader import MultipleCandidatesModal

        candidates = [
            {"url": "https://example.com/app-x64.exe", "filename": "app-x64.exe", "ext": ".exe", "size_bytes": 1024, "title": "64-bit Installer", "score": 1000},
            {"url": "https://example.com/app-x86.exe", "filename": "app-x86.exe", "ext": ".exe", "size_bytes": 1024, "title": "32-bit Installer", "score": 900},
            {"url": "https://example.com/app-portable.zip", "filename": "app-portable.zip", "ext": ".zip", "size_bytes": 2048, "title": "Portable ZIP", "score": 800},
        ]

        modal = MultipleCandidatesModal(
            parent=self.root,
            source_url="https://example.com/downloads",
            candidates=candidates,
            page_title="App Downloads"
        )

        self.assertIsNone(self.root.grab_current(), "Modal must never capture grab")
        self.assertEqual(len(modal.candidate_vars), 3)
        self.assertTrue(modal.var_select_all.get())
        self.assertEqual(modal.candidates[0]["filename"], "app-x64.exe")
        self.assertEqual(len(modal.candidates), 3)
        modal.destroy()

    def test_multiple_candidates_modal_select_all_toggle(self):
        """Tests master checkbox toggles all candidates on and off."""
        from turbo_downloader import MultipleCandidatesModal

        candidates = [
            {"url": "https://example.com/file1.exe", "filename": "file1.exe", "ext": ".exe", "size_bytes": None, "title": "File 1", "score": 500},
            {"url": "https://example.com/file2.zip", "filename": "file2.zip", "ext": ".zip", "size_bytes": None, "title": "File 2", "score": 400},
        ]

        modal = MultipleCandidatesModal(
            parent=self.root,
            source_url="https://example.com/page",
            candidates=candidates
        )

        # Uncheck master select all
        modal.select_all(False)
        self.assertFalse(modal.var_select_all.get())
        self.assertEqual(len(modal.get_selected_candidates()), 0)

        # Re-check master select all
        modal.select_all(True)
        self.assertTrue(modal.var_select_all.get())
        self.assertEqual(len(modal.get_selected_candidates()), 2)
        modal.destroy()

    def test_multiple_candidates_modal_select_specific(self):
        """Tests selecting or deselecting a specific candidate updates selection state."""
        from turbo_downloader import MultipleCandidatesModal

        candidates = [
            {"url": "https://example.com/f1.exe", "filename": "f1.exe", "ext": ".exe", "size_bytes": None, "title": "F1", "score": 500},
            {"url": "https://example.com/f2.exe", "filename": "f2.exe", "ext": ".exe", "size_bytes": None, "title": "F2", "score": 400},
            {"url": "https://example.com/f3.exe", "filename": "f3.exe", "ext": ".exe", "size_bytes": None, "title": "F3", "score": 300},
        ]

        modal = MultipleCandidatesModal(
            parent=self.root,
            source_url="https://example.com/page",
            candidates=candidates
        )

        # Deselect index 1
        modal.select_candidate(1, False)
        self.assertFalse(modal.var_select_all.get())
        selected = modal.get_selected_candidates()
        self.assertEqual(len(selected), 2)
        self.assertEqual([s["filename"] for s in selected], ["f1.exe", "f3.exe"])
        modal.destroy()

    def test_multiple_candidates_modal_action_download_selected(self):
        """Tests Download Selected button dispatches selected items to callback."""
        from turbo_downloader import MultipleCandidatesModal

        candidates = [
            {"url": "https://example.com/f1.exe", "filename": "f1.exe", "ext": ".exe", "size_bytes": None, "title": "F1", "score": 500},
            {"url": "https://example.com/f2.exe", "filename": "f2.exe", "ext": ".exe", "size_bytes": None, "title": "F2", "score": 400},
        ]

        dispatched = []
        modal = MultipleCandidatesModal(
            parent=self.root,
            source_url="https://example.com/page",
            candidates=candidates,
            on_download_selected=lambda items: dispatched.append(items)
        )

        modal.select_candidate(0, False)
        modal.btn_download_selected.invoke()
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(len(dispatched[0]), 1)
        self.assertEqual(dispatched[0][0]["filename"], "f2.exe")
        self.assertFalse(modal.winfo_exists())

    def test_multiple_candidates_modal_action_download_all(self):
        """Tests Download All button dispatches all candidates regardless of unchecked boxes."""
        from turbo_downloader import MultipleCandidatesModal

        candidates = [
            {"url": "https://example.com/f1.exe", "filename": "f1.exe", "ext": ".exe", "size_bytes": None, "title": "F1", "score": 500},
            {"url": "https://example.com/f2.exe", "filename": "f2.exe", "ext": ".exe", "size_bytes": None, "title": "F2", "score": 400},
        ]

        dispatched = []
        modal = MultipleCandidatesModal(
            parent=self.root,
            source_url="https://example.com/page",
            candidates=candidates,
            on_download_all=lambda items: dispatched.append(items)
        )

        # Uncheck one item, then invoke Download All
        modal.select_candidate(0, False)
        modal.btn_download_all.invoke()
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(len(dispatched[0]), 2)
        self.assertFalse(modal.winfo_exists())

    def test_multiple_candidates_modal_action_cancel(self):
        """Tests Cancel button invokes on_cancel and closes modal."""
        from turbo_downloader import MultipleCandidatesModal

        cancelled = []
        modal = MultipleCandidatesModal(
            parent=self.root,
            source_url="https://example.com/page",
            candidates=[{"url": "https://example.com/f.exe", "filename": "f.exe", "ext": ".exe", "size_bytes": None, "title": "F", "score": 100}],
            on_cancel=lambda: cancelled.append(True)
        )

        modal.btn_cancel.invoke()
        self.assertEqual(len(cancelled), 1)
        self.assertFalse(modal.winfo_exists())



if __name__ == "__main__":
    unittest.main()
