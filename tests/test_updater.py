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

class TestVersionComparisonAndUnification(unittest.TestCase):
    """Verifies version parsing/comparison edge cases, APP_VERSION='2.0.0' unification, and dist/ cleanup."""

    def test_parse_version_and_is_newer_version_standard_and_edge_cases(self):
        from updater import parse_version, is_newer_version

        # Standard semantic versions
        self.assertTrue(is_newer_version("2.1.0", "2.0.0"))
        self.assertTrue(is_newer_version("v2.1.0", "2.0.0"))
        self.assertTrue(is_newer_version("v2.0.1", "v2.0.0"))
        self.assertTrue(is_newer_version("3.0", "2.9.9"))
        self.assertFalse(is_newer_version("2.0.0", "2.0.0"))
        self.assertFalse(is_newer_version("v2.0.0", "2.0.0"))
        self.assertFalse(is_newer_version("1.9.9", "2.0.0"))
        self.assertFalse(is_newer_version("2.0", "2.0.0"))

        # Date-based yt-dlp versions (with leading zeros like 2026.03.13)
        self.assertTrue(is_newer_version("2026.10.23", "2026.03.13"))
        self.assertFalse(is_newer_version("2026.03.13", "2026.03.13"))
        self.assertFalse(is_newer_version("2025.12.31", "2026.01.01"))

        # Pre-release vs final release and multi-digit SemVer pre-release ordering
        self.assertTrue(is_newer_version("2.0.0", "2.0.0-beta.1"))
        self.assertFalse(is_newer_version("2.0.0-alpha.1", "2.0.0"))
        self.assertTrue(is_newer_version("2.1.0-rc1", "2.0.0"))
        self.assertTrue(is_newer_version("2.0.0-alpha.10", "2.0.0-alpha.2"))
        self.assertFalse(is_newer_version("2.0.0-alpha.2", "2.0.0-alpha.10"))
        self.assertTrue(is_newer_version("2.0.0-rc10", "2.0.0-rc2"))
        self.assertFalse(is_newer_version("2.0.0-rc2", "2.0.0-rc10"))

        # Edge cases: empty, None, malformed, trailing hyphen/plus, non-string -> always False
        self.assertEqual(parse_version(""), ())
        self.assertEqual(parse_version(None), ())
        self.assertEqual(parse_version("   "), ())
        self.assertEqual(parse_version("not_a_version"), ())
        self.assertEqual(parse_version("2.0.0-"), ())
        self.assertEqual(parse_version("2.0.0+"), ())
        self.assertFalse(is_newer_version("", "2.0.0"))
        self.assertFalse(is_newer_version(None, "2.0.0"))
        self.assertFalse(is_newer_version("invalid", "2.0.0"))
        self.assertFalse(is_newer_version("", ""))
        self.assertFalse(is_newer_version("2.0.0", ""))
        self.assertFalse(is_newer_version("2.0.0", None))
        self.assertFalse(is_newer_version("2.0.0", "2.0.0-"))

    def test_unified_app_version_across_all_modules(self):
        import updater
        import turbo_downloader
        import youtube_resolver
        import browser_bridge
        import installer
        import register_browser
        import native_messaging_host

        expected = "2.0.0"
        self.assertEqual(updater.APP_VERSION, expected)
        self.assertEqual(turbo_downloader.APP_VERSION, expected)
        self.assertEqual(youtube_resolver.APP_VERSION, expected)
        self.assertEqual(browser_bridge.APP_VERSION, expected)
        self.assertEqual(installer.APP_VERSION, expected)
        self.assertEqual(register_browser.APP_VERSION, expected)
        self.assertEqual(native_messaging_host.APP_VERSION, expected)

        ext_manifest = os.path.join(PROJECT_ROOT, "extension", "manifest.json")
        with open(ext_manifest, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        self.assertEqual(manifest_data.get("version"), expected)

    def test_browser_bridge_ping_and_status_return_unified_version(self):
        import urllib.request
        from browser_bridge import BrowserBridgeServer

        srv = BrowserBridgeServer(port=45791)
        srv.start()
        try:
            for endpoint in ("/ping", "/status"):
                url = f"http://127.0.0.1:{srv.port}{endpoint}"
                with urllib.request.urlopen(url, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(data.get("version"), "2.0.0")
        finally:
            srv.stop()

    def test_dist_directory_has_no_stale_turbodownloader_artifacts(self):
        dist_dir = os.path.join(PROJECT_ROOT, "dist")
        if os.path.isdir(dist_dir):
            files = set(os.listdir(dist_dir))
            for stale in (
                "TurboDownloader.exe",
                "TurboDownloader-Setup.exe",
                "com.turbodownloader.host.json",
                "turbo_host.bat",
            ):
                self.assertNotIn(stale, files, f"Stale artifact {stale} must not exist in dist/")
            dist_ext_manifest = os.path.join(dist_dir, "extension", "manifest.json")
            if os.path.isfile(dist_ext_manifest):
                with open(dist_ext_manifest, "r", encoding="utf-8") as f:
                    ext_data = json.load(f)
                self.assertEqual(ext_data.get("version"), "2.0.0")
                self.assertEqual(ext_data.get("name"), "Smart Download (SD) Integration")

class TestYtDlpAutoUpdater(unittest.TestCase):
    """Verifies YtDlpAutoUpdater check, wheel/zip extraction, in-process sys.meta_path reload, and fallback safety."""

    def _create_mock_ytdlp_wheel_bytes(self, version_str: str = "2099.12.31", corrupt: bool = False) -> bytes:
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if not corrupt:
                zf.writestr(
                    "yt_dlp/__init__.py",
                    "from . import version, extractor\n__version__ = version.__version__\nclass YoutubeDL:\n    def __init__(self, params=None):\n        self.params = params or {}\n    def __enter__(self):\n        return self\n    def __exit__(self, *args):\n        pass\n"
                )
                zf.writestr(
                    "yt_dlp/version.py",
                    f"__version__ = '{version_str}'\nRELEASE_GIT_head = 'mock'\n"
                )
                zf.writestr(
                    "yt_dlp/extractor/__init__.py",
                    "def gen_extractors():\n    return []\n"
                )
                zf.writestr(
                    "yt_dlp/utils.py",
                    "class DownloadError(Exception):\n    pass\n"
                )
            else:
                zf.writestr("unrelated_folder/dummy.txt", "no yt_dlp package here")
        return buf.getvalue()

    def test_check_for_update_pypi_and_github_fallback(self):
        from updater import YtDlpAutoUpdater

        mock_pypi_payload = json.dumps({
            "info": {"version": "2099.11.22"},
            "urls": [
                {
                    "filename": "yt_dlp-2099.11.22-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "url": "https://files.pythonhosted.org/packages/yt_dlp-2099.11.22-py3-none-any.whl",
                }
            ]
        }).encode("utf-8")

        class _MockResp:
            def __init__(self, data: bytes, status: int = 200):
                self._data = data
                self.status = status
            def read(self):
                return self._data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        updater = YtDlpAutoUpdater()
        with patch.object(updater, "get_current_version", return_value="2026.03.13"), \
             patch("urllib.request.urlopen", return_value=_MockResp(mock_pypi_payload)):
            info = updater.check_for_update()
            self.assertTrue(info["success"])
            self.assertTrue(info["update_available"])
            self.assertEqual(info["latest_version"], "2099.11.22")
            self.assertTrue(info["download_url"].endswith(".whl"))

        with patch.object(updater, "get_current_version", return_value="2099.11.22"), \
             patch("urllib.request.urlopen", return_value=_MockResp(mock_pypi_payload)):
            info_same = updater.check_for_update()
            self.assertTrue(info_same["success"])
            self.assertFalse(info_same["update_available"])

        # Fallback to GitHub API when PyPI fails
        mock_gh_payload = json.dumps({
            "tag_name": "2099.12.01",
            "assets": [
                {
                    "name": "yt-dlp",
                    "browser_download_url": "https://github.com/yt-dlp/yt-dlp/releases/download/2099.12.01/yt-dlp"
                }
            ]
        }).encode("utf-8")

        def _side_effect(req, timeout=10, context=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "pypi.org" in url:
                raise OSError("PyPI unreachable")
            return _MockResp(mock_gh_payload)

        with patch.object(updater, "get_current_version", return_value="2026.03.13"), \
             patch("urllib.request.urlopen", side_effect=_side_effect):
            info_gh = updater.check_for_update()
            self.assertTrue(info_gh["success"])
            self.assertTrue(info_gh["update_available"])
            self.assertEqual(info_gh["latest_version"], "2099.12.01")
            self.assertEqual(info_gh["source"], "github")

    def test_update_extracts_wheel_and_dynamically_reloads_ytdlp_in_process(self):
        import tempfile
        import yt_dlp as orig_ytdlp
        from updater import YtDlpAutoUpdater, _ExternalYtDlpFinder

        orig_version = orig_ytdlp.version.__version__
        orig_sys_path = list(sys.path)
        orig_meta_path = list(sys.meta_path)
        orig_modules = {k: v for k, v in sys.modules.items() if k == "yt_dlp" or k.startswith("yt_dlp.")}

        try:
            with tempfile.TemporaryDirectory() as tmp_root:
                plugin_dir = os.path.join(tmp_root, "yt_dlp_plugin")
                updater = YtDlpAutoUpdater(plugin_dir=plugin_dir)
                wheel_bytes = self._create_mock_ytdlp_wheel_bytes("2099.12.31")

                class _MockStreamResp:
                    def __init__(self, data: bytes):
                        import io
                        self._buf = io.BytesIO(data)
                        self.headers = {"Content-Length": str(len(data))}
                    def read(self, sz: int = -1):
                        return self._buf.read(sz)
                    def __enter__(self):
                        return self
                    def __exit__(self, *args):
                        pass

                with patch.object(updater, "check_for_update", return_value={
                    "success": True,
                    "update_available": True,
                    "current_version": orig_version,
                    "latest_version": "2099.12.31",
                    "download_url": "https://example.com/yt_dlp-2099.12.31-py3-none-any.whl",
                }), patch("urllib.request.urlopen", return_value=_MockStreamResp(wheel_bytes)):
                    res = updater.update()
                    self.assertTrue(res["updated"], f"Expected update to succeed, got: {res}")
                    self.assertEqual(res["version"], "2099.12.31")
                    self.assertTrue(os.path.isfile(os.path.join(plugin_dir, "yt_dlp", "__init__.py")))

                    # Verify in-process reload updated yt_dlp and installed _ExternalYtDlpFinder at sys.meta_path[0]
                    import yt_dlp as reloaded_ytdlp
                    self.assertEqual(reloaded_ytdlp.version.__version__, "2099.12.31")
                    self.assertEqual(updater.get_current_version(), "2099.12.31")
                    self.assertIsInstance(sys.meta_path[0], _ExternalYtDlpFinder)

                # Now test corrupt archive rollback: existing valid plugin in plugin_dir must remain intact!
                corrupt_bytes = self._create_mock_ytdlp_wheel_bytes(corrupt=True)
                with patch.object(updater, "check_for_update", return_value={
                    "success": True,
                    "update_available": True,
                    "current_version": "2099.12.31",
                    "latest_version": "2100.01.01",
                    "download_url": "https://example.com/yt_dlp-2100.01.01-py3-none-any.whl",
                }), patch("urllib.request.urlopen", return_value=_MockStreamResp(corrupt_bytes)):
                    res_bad = updater.update()
                    self.assertFalse(res_bad["updated"])
                    self.assertIsNotNone(res_bad.get("error"))
                    # Previous valid plugin must still be intact
                    self.assertTrue(os.path.isfile(os.path.join(plugin_dir, "yt_dlp", "__init__.py")))
                    self.assertEqual(updater.get_current_version(), "2099.12.31")
        finally:
            # Restore original yt_dlp modules, sys.path, and sys.meta_path
            sys.path[:] = orig_sys_path
            sys.meta_path[:] = orig_meta_path
            for k in list(sys.modules.keys()):
                if k == "yt_dlp" or k.startswith("yt_dlp."):
                    sys.modules.pop(k, None)
            sys.modules.update(orig_modules)

    def test_corrupt_external_plugin_falls_back_to_bundled_ytdlp(self):
        import tempfile
        import yt_dlp as orig_ytdlp
        from updater import YtDlpAutoUpdater

        orig_sys_path = list(sys.path)
        orig_meta_path = list(sys.meta_path)
        orig_modules = {k: v for k, v in sys.modules.items() if k == "yt_dlp" or k.startswith("yt_dlp.")}

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                bad_pkg = os.path.join(tmp_dir, "yt_dlp")
                os.makedirs(os.path.join(bad_pkg, "extractor"), exist_ok=True)
                with open(os.path.join(bad_pkg, "__init__.py"), "w", encoding="utf-8") as f:
                    f.write("raise RuntimeError('corrupted external plugin')\n")
                with open(os.path.join(bad_pkg, "version.py"), "w", encoding="utf-8") as f:
                    f.write("__version__ = '2099.99.99'\n")
                with open(os.path.join(bad_pkg, "extractor", "__init__.py"), "w", encoding="utf-8") as f:
                    f.write("")

                updater = YtDlpAutoUpdater(plugin_dir=tmp_dir)
                activated = updater.activate_plugin(force=True)
                self.assertFalse(activated, "Corrupted external plugin must fail activation gracefully")
                # Bundled yt_dlp must still be active and importable
                import yt_dlp as current_ytdlp
                self.assertEqual(current_ytdlp.version.__version__, orig_ytdlp.version.__version__)
        finally:
            sys.path[:] = orig_sys_path
            sys.meta_path[:] = orig_meta_path
            for k in list(sys.modules.keys()):
                if k == "yt_dlp" or k.startswith("yt_dlp."):
                    sys.modules.pop(k, None)
            sys.modules.update(orig_modules)

    def test_youtube_resolver_auto_updates_ytdlp_and_retries_on_failure(self):
        import yt_dlp
        from youtube_resolver import YouTubeResolver, YtDlpAutoUpdater

        resolver = YouTubeResolver(auto_update_on_failure=True)
        attempt_count = {"n": 0}

        class _FakeYDL:
            def __init__(self, opts=None):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract_info(self, url, download=False):
                attempt_count["n"] += 1
                if attempt_count["n"] == 1:
                    raise RuntimeError("Extractor Error: Signature extraction failed")
                return {
                    "title": "Recovered Video After Self-Update",
                    "duration": 95,
                    "webpage_url": url,
                    "formats": [
                        {
                            "format_id": "18",
                            "url": "https://example.com/video.mp4",
                            "ext": "mp4",
                            "height": 360,
                            "width": 640,
                            "filesize": 5000000,
                            "vcodec": "avc1",
                            "acodec": "mp4a",
                            "protocol": "https",
                        }
                    ],
                }

        with patch.object(yt_dlp, "YoutubeDL", _FakeYDL), \
             patch.object(YtDlpAutoUpdater, "update", return_value={
                 "success": True,
                 "updated": True,
                 "version": "2099.12.31",
                 "plugin_dir": "mock_dir",
             }) as mock_update:
            info, options = resolver.extract_format_options("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            self.assertEqual(info["title"], "Recovered Video After Self-Update")
            self.assertEqual(attempt_count["n"], 2)
            self.assertGreaterEqual(len(options), 1)
            mock_update.assert_called_once()

    def test_swap_failure_restores_backup_and_concurrent_updates(self):
        import tempfile
        from updater import YtDlpAutoUpdater

        orig_sys_path = list(sys.path)
        orig_meta_path = list(sys.meta_path)
        orig_modules = {k: v for k, v in sys.modules.items() if k == "yt_dlp" or k.startswith("yt_dlp.")}

        class _MockStreamResp:
            def __init__(self, data: bytes):
                import io
                self._buf = io.BytesIO(data)
                self.headers = {"Content-Length": str(len(data))}
            def read(self, sz: int = -1):
                return self._buf.read(sz)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        try:
            with tempfile.TemporaryDirectory() as tmp_root:
                plugin_dir = os.path.join(tmp_root, "yt_dlp_plugin")
                updater = YtDlpAutoUpdater(plugin_dir=plugin_dir)
                wheel_v1 = self._create_mock_ytdlp_wheel_bytes("2099.10.01")
                wheel_v2 = self._create_mock_ytdlp_wheel_bytes("2099.11.01")

                # Install initial v1 plugin
                with patch("urllib.request.urlopen", return_value=_MockStreamResp(wheel_v1)):
                    res1 = updater.download_and_extract_archive("https://example.com/v1.whl", target_version="2099.10.01")
                    self.assertTrue(res1["updated"])
                    self.assertEqual(updater.get_plugin_version(), "2099.10.01")

                # Simulate failure on second _safe_replace_dir call (moving staging_dir -> plugin_dir)
                real_replace = YtDlpAutoUpdater._safe_replace_dir
                call_idx = {"n": 0}
                def _failing_second_replace(src, dst, retries=5, delay=0.06):
                    call_idx["n"] += 1
                    if call_idx["n"] == 2:
                        raise PermissionError("Simulated Windows file lock during staging->plugin swap")
                    return real_replace(src, dst, retries=retries, delay=delay)

                with patch("urllib.request.urlopen", return_value=_MockStreamResp(wheel_v2)), \
                     patch.object(YtDlpAutoUpdater, "_safe_replace_dir", side_effect=_failing_second_replace):
                    res_fail = updater.download_and_extract_archive("https://example.com/v2.whl", target_version="2099.11.01")
                    self.assertFalse(res_fail["updated"])
                    # Previous v1 plugin MUST have been restored from backup!
                    self.assertTrue(updater.is_plugin_valid(plugin_dir))
                    self.assertEqual(updater.get_plugin_version(), "2099.10.01")

                # Verify concurrent threads updating simultaneously do not collide on temp files
                results = []
                def _thread_worker():
                    results.append(updater.download_and_extract_archive("https://example.com/v2.whl", target_version="2099.11.01"))

                with patch("urllib.request.urlopen", side_effect=lambda *a, **kw: _MockStreamResp(wheel_v2)):
                    t1 = threading.Thread(target=_thread_worker)
                    t2 = threading.Thread(target=_thread_worker)
                    t1.start()
                    t2.start()
                    t1.join(timeout=10)
                    t2.join(timeout=10)
                self.assertEqual(len(results), 2)
                self.assertTrue(all(r.get("updated") for r in results), f"Expected both threads to succeed, got: {results}")
                self.assertEqual(updater.get_plugin_version(), "2099.11.01")
        finally:
            sys.path[:] = orig_sys_path
            sys.meta_path[:] = orig_meta_path
            for k in list(sys.modules.keys()):
                if k == "yt_dlp" or k.startswith("yt_dlp."):
                    sys.modules.pop(k, None)
            sys.modules.update(orig_modules)

class TestAppAutoUpdaterAndModal(unittest.TestCase):
    """Verifies AppAutoUpdater GitHub Release check, download, silent installer launch, and AppUpdateModal UI."""

    def test_app_auto_updater_check_for_update(self):
        from updater import AppAutoUpdater

        mock_release = json.dumps({
            "tag_name": "v2.1.0",
            "html_url": "https://github.com/hozifa460/smart-download-sd/releases/tag/v2.1.0",
            "body": "### What's New in v2.1.0\n- Faster downloads\n- Auto-updater improvements",
            "published_at": "2026-10-23T00:00:00Z",
            "assets": [
                {
                    "name": "SmartDownload.exe",
                    "browser_download_url": "https://github.com/hozifa460/smart-download-sd/releases/download/v2.1.0/SmartDownload.exe",
                    "size": 46000000
                },
                {
                    "name": "SmartDownload-Setup.exe",
                    "browser_download_url": "https://github.com/hozifa460/smart-download-sd/releases/download/v2.1.0/SmartDownload-Setup.exe",
                    "size": 60000000
                }
            ]
        }).encode("utf-8")

        class _MockResp:
            def __init__(self, data: bytes, status: int = 200):
                self._data = data
                self.status = status
            def read(self):
                return self._data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with patch("urllib.request.urlopen", return_value=_MockResp(mock_release)):
            res = AppAutoUpdater(current_version="2.0.0").check_for_update()
            self.assertTrue(res["update_available"])
            self.assertEqual(res["latest_version"], "2.1.0")
            self.assertEqual(res["asset_name"], "SmartDownload-Setup.exe")
            self.assertTrue(res["download_url"].endswith("SmartDownload-Setup.exe"))
            self.assertIn("What's New in v2.1.0", res["release_notes"])
            self.assertIsNone(res["error"])

            # Same version -> update_available is False
            res_same = AppAutoUpdater(current_version="2.1.0").check_for_update()
            self.assertFalse(res_same["update_available"])

            # Newer local version -> update_available is False
            res_newer = AppAutoUpdater(current_version="2.2.0").check_for_update()
            self.assertFalse(res_newer["update_available"])

        # Network error handling -> never raises
        with patch("urllib.request.urlopen", side_effect=OSError("Offline")):
            res_err = AppAutoUpdater(current_version="2.0.0").check_for_update()
            self.assertFalse(res_err["update_available"])
            self.assertIn("Offline", res_err["error"])

    def test_app_auto_updater_download_and_apply_update(self):
        import tempfile
        from updater import AppAutoUpdater

        payload_bytes = b"MZ_MOCK_INSTALLER_BINARY_" * 200  # > 1024 bytes

        class _MockDownloadResp:
            def __init__(self, data: bytes):
                import io
                self._buf = io.BytesIO(data)
                self.headers = {"Content-Length": str(len(data))}
            def read(self, sz: int = -1):
                return self._buf.read(sz)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        updater = AppAutoUpdater(current_version="2.0.0")
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest_file = os.path.join(tmp_dir, "SmartDownload-Setup.exe")
            progress_calls = []

            with patch("urllib.request.urlopen", return_value=_MockDownloadResp(payload_bytes)):
                downloaded_path = updater.download_update(
                    "https://github.com/hozifa460/smart-download-sd/releases/download/v2.1.0/SmartDownload-Setup.exe",
                    dest_path=dest_file,
                    progress_cb=lambda cur, tot: progress_calls.append((cur, tot))
                )
                self.assertEqual(downloaded_path, os.path.abspath(dest_file))
                self.assertTrue(os.path.isfile(dest_file))
                self.assertGreater(len(progress_calls), 0)
                self.assertEqual(progress_calls[-1][0], len(payload_bytes))

            # Test apply_update launches installer with --silent --launch and calls exit_callback
            exited = {"called": False}
            with patch("subprocess.Popen") as mock_popen:
                ap_ok = updater.apply_update(
                    dest_file,
                    silent=True,
                    launch_after=True,
                    exit_callback=lambda: exited.__setitem__("called", True)
                )
                self.assertTrue(ap_ok)
                self.assertTrue(exited["called"])
                mock_popen.assert_called_once()
                called_cmd = mock_popen.call_args[0][0]
                self.assertEqual(called_cmd[0], os.path.abspath(dest_file))
                self.assertIn("--silent", called_cmd)
                self.assertIn("--launch", called_cmd)

    def test_app_update_modal_and_manual_update_check_ui(self):
        import tkinter as tk
        from turbo_downloader import ModernFramelessGUI, AppUpdateModal

        root = tk.Tk()
        root.withdraw()
        gui = ModernFramelessGUI(root)
        try:
            self.assertTrue(hasattr(gui, "btn_check_updates"))
            self.assertEqual(gui.btn_check_updates.cget("text"), "🔄 Check for Updates")

            update_info = {
                "update_available": True,
                "current_version": "2.0.0",
                "latest_version": "2.1.0",
                "installer_url": "https://github.com/hozifa460/smart-download-sd/releases/download/v2.1.0/SmartDownload-Setup.exe",
                "download_url": "https://github.com/hozifa460/smart-download-sd/releases/download/v2.1.0/SmartDownload-Setup.exe",
                "release_url": "https://github.com/hozifa460/smart-download-sd/releases/tag/v2.1.0",
                "release_notes": "### Release v2.1.0\n- Self-updating yt-dlp engine\n- 1-click installer update",
                "asset_name": "SmartDownload-Setup.exe",
                "installer_size": 60405009,
            }
            modal = gui._show_update_dialog(update_info)
            self.assertIsNotNone(modal)
            self.assertIsInstance(modal, AppUpdateModal)
            self.assertTrue(modal.winfo_exists())
            # Must be grab-free
            self.assertIsNone(modal.grab_current())
            self.assertIn("⬇ Update Now", modal.btn_update.cget("text"))
            modal._on_close()
            self.assertFalse(modal.winfo_exists())
        finally:
            gui._cleanup_resources()
            try:
                root.update_idletasks()
                root.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
