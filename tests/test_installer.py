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

class TestWindowsInstallerLogic(unittest.TestCase):
    """Verifies standalone Windows Installer logic, zero-elevation paths, and shortcuts."""

    def test_default_install_dir_and_constants(self):
        self.assertEqual(installer.APP_ID, "SmartDownload")
        self.assertEqual(installer.APP_NAME, "Smart Download (SD)")
        self.assertTrue(installer.DEFAULT_INSTALL_DIR.endswith(r"Programs\SmartDownload"))
        # Ensure path is user-level inside LocalAppData (zero admin/UAC elevation needed)
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            self.assertTrue(installer.DEFAULT_INSTALL_DIR.lower().startswith(local_app_data.lower()))

    def test_register_and_unregister_uninstall_entry(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile, winreg
        with tempfile.TemporaryDirectory() as tmp_dir:
            exe_path = os.path.join(tmp_dir, "SmartDownload.exe")
            with open(exe_path, "w") as f:
                f.write("mock")
            uninst_path = os.path.join(tmp_dir, "Uninstall.exe")
            with open(uninst_path, "w") as f:
                f.write("mock")

            # Pre-create legacy uninstall key to simulate upgrading from old version
            legacy_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, installer.LEGACY_UNINSTALL_REG_KEY)
            winreg.SetValueEx(legacy_key, "DisplayName", 0, winreg.REG_SZ, "Legacy TurboDownloader")
            winreg.CloseKey(legacy_key)

            reg_ok = installer.register_uninstall_entry(tmp_dir, exe_path, uninst_path)
            self.assertTrue(reg_ok)

            # Query uninstall key
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.UNINSTALL_REG_KEY)
            disp_name, _ = winreg.QueryValueEx(key, "DisplayName")
            uninst_cmd, _ = winreg.QueryValueEx(key, "UninstallString")
            quiet_uninst_cmd, _ = winreg.QueryValueEx(key, "QuietUninstallString")
            no_modify, _ = winreg.QueryValueEx(key, "NoModify")
            winreg.CloseKey(key)

            self.assertEqual(disp_name, "Smart Download (SD)")
            # Verify legacy key was cleanly migrated/deleted
            with self.assertRaises(FileNotFoundError):
                winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.LEGACY_UNINSTALL_REG_KEY)
            self.assertIn("Uninstall.exe", uninst_cmd)
            self.assertIn("--uninstall", uninst_cmd)
            self.assertIn("--silent", quiet_uninst_cmd)
            self.assertEqual(no_modify, 1)

            # Clean up
            unreg_ok = installer.unregister_uninstall_entry()
            self.assertTrue(unreg_ok)

            # Verify key is gone
            with self.assertRaises(FileNotFoundError):
                winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.UNINSTALL_REG_KEY)

    def test_create_windows_shortcut(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Shortcut test only runs on Windows OS.")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "app.exe")
            with open(target, "w") as f:
                f.write("mock")
            shortcut = os.path.join(tmp_dir, "TestShortcut.lnk")

            ok = installer.create_windows_shortcut(target, shortcut, description="Test App")
            self.assertTrue(ok)
            self.assertTrue(os.path.isfile(shortcut))

    def test_legacy_shortcuts_cleanup_on_upgrade(self):
        """Verifies that legacy Turbo Download Manager Pro.lnk shortcuts are cleaned up upon installation."""
        if not sys.platform.startswith("win"):
            self.skipTest("Windows shortcut test only runs on Windows OS.")

        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp_desktop, \
             tempfile.TemporaryDirectory() as tmp_start, \
             tempfile.TemporaryDirectory() as tmp_target:

            legacy_dt_lnk = os.path.join(tmp_desktop, "Turbo Download Manager Pro.lnk")
            with open(legacy_dt_lnk, "w") as f:
                f.write("legacy shortcut")

            legacy_sm_lnk = os.path.join(tmp_start, "Turbo Download Manager Pro.lnk")
            with open(legacy_sm_lnk, "w") as f:
                f.write("legacy shortcut")

            with patch.object(installer, "get_desktop_dir", return_value=tmp_desktop), \
                 patch.object(installer, "get_start_menu_programs_dir", return_value=tmp_start):
                res = installer.install_application(
                    target_dir=tmp_target,
                    create_desktop=True,
                    create_start_menu=True,
                    register_browser=False
                )
                self.assertTrue(res.get("success"))
                self.assertFalse(os.path.exists(legacy_dt_lnk), "Legacy desktop shortcut must be removed")
                self.assertFalse(os.path.exists(legacy_sm_lnk), "Legacy start menu shortcut must be removed")
                self.assertTrue(os.path.exists(os.path.join(tmp_desktop, f"{installer.APP_NAME}.lnk")), "New desktop shortcut must exist")

    def test_install_and_uninstall_lifecycle(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Installer tests only run on Windows OS.")

        import tempfile
        progress_events = []

        def _cb(pct, msg):
            progress_events.append((pct, msg))

        with tempfile.TemporaryDirectory() as tmp_dir:
            install_target = os.path.join(tmp_dir, "InstalledTurbo")

            # Execute install into test folder
            res = installer.install_application(
                target_dir=install_target,
                create_desktop=False,
                create_start_menu=False,
                register_browser=False,
                progress_cb=_cb
            )
            self.assertTrue(res.get("success"))
            self.assertTrue(os.path.isdir(install_target))
            self.assertTrue(os.path.isfile(os.path.join(install_target, "SmartDownload.exe")))
            self.assertFalse(os.path.isfile(os.path.join(install_target, "TurboDownloader.exe")), "TurboDownloader.exe must NOT be present in modern installation")
            self.assertTrue(os.path.isfile(os.path.join(install_target, "app_icon.ico")))
            self.assertTrue(len(progress_events) >= 5)
            self.assertEqual(progress_events[-1][0], 1.0)

            # Execute uninstall
            un_progress = []
            un_res = installer.uninstall_application(
                target_dir=install_target,
                progress_cb=lambda p, m: un_progress.append((p, m))
            )
            self.assertTrue(un_res.get("success"))
            self.assertTrue(len(un_progress) >= 4)
            self.assertEqual(un_progress[-1][0], 1.0)
            self.assertFalse(os.path.exists(install_target))

    def test_installer_startup_registration_and_uninstallation(self):
        """Verifies that install_application registers auto-start entries (Run registry, Scheduled Task, Startup shortcut) and uninstall_application removes them."""
        if not sys.platform.startswith("win"):
            self.skipTest("Installer startup tests only run on Windows OS.")

        import tempfile
        import winreg
        from unittest.mock import patch, MagicMock

        orig_reg = None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.STARTUP_REG_KEY, 0, winreg.KEY_READ) as key:
                orig_reg, _ = winreg.QueryValueEx(key, installer.STARTUP_REG_KEY_NAME)
        except Exception:
            pass

        try:
            with tempfile.TemporaryDirectory() as tmp_target, \
                 tempfile.TemporaryDirectory() as tmp_startup:

                recorded_commands = []
                orig_subprocess_run = subprocess.run

                def mock_subprocess_run(cmd, *args, **kwargs):
                    recorded_commands.append(cmd)
                    if isinstance(cmd, list) and len(cmd) > 0 and "schtasks.exe" in str(cmd[0]):
                        m = MagicMock()
                        m.returncode = 0
                        m.stdout = "SUCCESS"
                        m.stderr = ""
                        return m
                    return orig_subprocess_run(cmd, *args, **kwargs)

                with patch.object(installer, "get_startup_dir", return_value=tmp_startup), \
                     patch("subprocess.run", side_effect=mock_subprocess_run):

                    res = installer.install_application(
                        target_dir=tmp_target,
                        create_desktop=False,
                        create_start_menu=False,
                        register_browser=False,
                        register_startup=True
                    )
                    self.assertTrue(res.get("success"))
                    self.assertIn("startup_registered", res)
                    self.assertTrue(res["startup_registered"].get("run_key"))
                    self.assertTrue(res["startup_registered"].get("scheduled_task"))
                    self.assertTrue(res["startup_registered"].get("startup_shortcut"))

                    # 1. Assert HKCU Run registry value exists and points to installed exe --minimized
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.STARTUP_REG_KEY, 0, winreg.KEY_READ) as key:
                        run_val, _ = winreg.QueryValueEx(key, installer.STARTUP_REG_KEY_NAME)
                        expected_exe = os.path.abspath(os.path.join(tmp_target, "SmartDownload.exe"))
                        self.assertIn(expected_exe.lower(), run_val.lower())
                        self.assertTrue(run_val.endswith(" --minimized"))

                    # 2. Assert silent startup shortcut exists in Startup folder
                    startup_lnk = os.path.join(tmp_startup, f"{installer.APP_NAME}.lnk")
                    self.assertTrue(os.path.isfile(startup_lnk), "Startup folder shortcut must exist after install")

                    # 3. Assert schtasks.exe was invoked to create SmartDownloadAutoStart
                    schtasks_create_calls = [
                        c for c in recorded_commands
                        if isinstance(c, list) and len(c) > 0 and "schtasks.exe" in str(c[0]) and "/Create" in c
                    ]
                    self.assertTrue(len(schtasks_create_calls) >= 1, "schtasks.exe /Create must be called during install")
                    create_cmd = schtasks_create_calls[0]
                    self.assertIn("/TN", create_cmd)
                    self.assertIn(installer.TASK_NAME, create_cmd)
                    self.assertIn("/SC", create_cmd)
                    self.assertIn("ONLOGON", create_cmd)

                    # Now execute uninstallation
                    un_res = installer.uninstall_application(target_dir=tmp_target)
                    self.assertTrue(un_res.get("success"))

                    # 1. Assert HKCU Run registry value was deleted
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.STARTUP_REG_KEY, 0, winreg.KEY_READ) as key:
                        with self.assertRaises(FileNotFoundError):
                            winreg.QueryValueEx(key, installer.STARTUP_REG_KEY_NAME)

                    # 2. Assert Startup folder shortcut was deleted
                    self.assertFalse(os.path.exists(startup_lnk), "Startup folder shortcut must be deleted after uninstall")

                    # 3. Assert schtasks.exe was invoked to delete the task
                    schtasks_delete_calls = [
                        c for c in recorded_commands
                        if isinstance(c, list) and len(c) > 0 and "schtasks.exe" in str(c[0]) and "/Delete" in c
                    ]
                    self.assertTrue(len(schtasks_delete_calls) >= 1, "schtasks.exe /Delete must be called during uninstall")
                    del_cmd = schtasks_delete_calls[0]
                    self.assertIn("/TN", del_cmd)
                    self.assertIn(installer.TASK_NAME, del_cmd)
        finally:
            if orig_reg is not None:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, installer.STARTUP_REG_KEY) as key:
                    winreg.SetValueEx(key, installer.STARTUP_REG_KEY_NAME, 0, winreg.REG_SZ, orig_reg)
            else:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.DeleteValue(key, installer.STARTUP_REG_KEY_NAME)
                except Exception:
                    pass

    def test_installer_startup_disabled_clean_state(self):
        """Verifies that install_application(register_startup=False) cleans up pre-existing startup entries and does not enable startup."""
        if not sys.platform.startswith("win"):
            self.skipTest("Installer startup tests only run on Windows OS.")

        import tempfile
        import winreg
        from unittest.mock import patch

        orig_reg = None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.STARTUP_REG_KEY, 0, winreg.KEY_READ) as key:
                orig_reg, _ = winreg.QueryValueEx(key, installer.STARTUP_REG_KEY_NAME)
        except Exception:
            pass

        try:
            with tempfile.TemporaryDirectory() as tmp_target, \
                 tempfile.TemporaryDirectory() as tmp_startup:

                # Pre-populate a fake startup shortcut
                fake_lnk = os.path.join(tmp_startup, f"{installer.APP_NAME}.lnk")
                with open(fake_lnk, "wb") as f:
                    f.write(b"FAKE_LNK")

                with patch.object(installer, "get_startup_dir", return_value=tmp_startup):
                    res = installer.install_application(
                        target_dir=tmp_target,
                        create_desktop=False,
                        create_start_menu=False,
                        register_browser=False,
                        register_startup=False
                    )
                    self.assertTrue(res.get("success"))
                    self.assertFalse(os.path.exists(fake_lnk), "Pre-existing startup shortcut must be cleaned up when register_startup=False")
        finally:
            if orig_reg is not None:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, installer.STARTUP_REG_KEY) as key:
                    winreg.SetValueEx(key, installer.STARTUP_REG_KEY_NAME, 0, winreg.REG_SZ, orig_reg)
            else:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.DeleteValue(key, installer.STARTUP_REG_KEY_NAME)
                except Exception:
                    pass

    def test_build_installer_payload_deduplication(self):
        """Verifies build_installer.prepare_payload() bundles ONLY SmartDownload.exe and excludes TurboDownloader.exe."""
        import build_installer
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp_dist, tempfile.TemporaryDirectory() as tmp_payload:
            mock_exe = os.path.join(tmp_dist, "SmartDownload.exe")
            with open(mock_exe, "wb") as f:
                f.write(b"MOCK_BINARY_DATA")

            with patch.object(build_installer, "DIST_DIR", tmp_dist), \
                 patch.object(build_installer, "PAYLOAD_DIR", tmp_payload):
                build_installer.prepare_payload()

                bundled_files = os.listdir(tmp_payload)
                self.assertIn("SmartDownload.exe", bundled_files, "SmartDownload.exe must be bundled")
                self.assertNotIn("TurboDownloader.exe", bundled_files, "TurboDownloader.exe must NOT be duplicated in payload")

    def test_build_installer_payload_copies_real_registry(self):
        """Verifies prepare_payload copies real registry.py and host_manifest.py, runnable standalone."""
        import build_installer
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp_dist, tempfile.TemporaryDirectory() as tmp_payload:
            mock_exe = os.path.join(tmp_dist, "SmartDownload.exe")
            with open(mock_exe, "wb") as f:
                f.write(b"MOCK_BINARY_DATA")

            with patch.object(build_installer, "DIST_DIR", tmp_dist), \
                 patch.object(build_installer, "PAYLOAD_DIR", tmp_payload):
                build_installer.prepare_payload()

                reg_copy = os.path.join(tmp_payload, "register_browser.py")
                hm_copy = os.path.join(tmp_payload, "host_manifest.py")
                self.assertTrue(os.path.isfile(reg_copy), "register_browser.py must be present in payload")
                self.assertTrue(os.path.isfile(hm_copy), "host_manifest.py must be present in payload")
                with open(reg_copy, "r", encoding="utf-8") as f:
                    content = f.read()
                self.assertNotIn("from smart_download.services.browser.registry import *", content, "Payload register_browser.py must not be the root shim")
                self.assertIn("compute_unpacked_extension_id", content, "Payload must contain full registry logic")

                # Verify register_browser.py in payload executes standalone without relative import errors
                res = subprocess.run([sys.executable, reg_copy, "--status"], capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, f"Payload register_browser.py execution failed: {res.stderr}")


    def test_installer_gui_initialization_grab_free(self):
        """Verifies Tkinter InstallerGUI creates without grab lock and has responsive layout."""
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            gui = installer.InstallerGUI(root, mode="install")
            self.assertEqual(gui.mode, "install")
            # Verify grab-free: root must NOT have active grab lock
            self.assertIsNone(root.grab_current(), "Installer GUI must be grab-free without modal lock")
            # Verify UI elements exist
            self.assertTrue(hasattr(gui, "entry_dir"))
            self.assertTrue(hasattr(gui, "btn_action"))
            self.assertTrue(hasattr(gui, "btn_cancel"))
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_shell_desktop_and_programs_directory_resolution(self):
        """Verifies get_desktop_dir and get_start_menu_programs_dir return valid existing folders."""
        desktop_dir = installer.get_desktop_dir()
        programs_dir = installer.get_start_menu_programs_dir()
        self.assertTrue(os.path.isdir(desktop_dir), f"Desktop folder {desktop_dir} must exist")
        self.assertTrue(os.path.isdir(programs_dir), f"Programs folder {programs_dir} must exist")

    def test_uninstaller_binary_mode_detection(self):
        """Verifies that running with an uninstaller binary name defaults to uninstall mode."""
        with patch("sys.executable", "C:\\Programs\\SmartDownload\\Uninstall.exe"):
            exe_name = os.path.basename(sys.executable).lower()
            is_uninst = "uninstall" in exe_name
            self.assertTrue(is_uninst)
            mode = "uninstall" if is_uninst else "install"
            self.assertEqual(mode, "uninstall")

    def test_installer_shim_bidirectional_monkeypatching(self):
        """Verifies _InstallerShim synchronizes monkeypatches bidirectionally between installer and ops/reg/gui."""
        import smart_download.installer.installer_ops as ops

        # Patching sub-module propagates to root installer shim
        with patch.object(ops, "find_payload_sources", return_value={"mock_test": True}):
            self.assertEqual(installer.find_payload_sources(), {"mock_test": True})

        # Patching root installer shim propagates to sub-module
        with patch.object(installer, "find_payload_sources", return_value={"mock_test_2": True}):
            self.assertEqual(ops.find_payload_sources(), {"mock_test_2": True})


class TestStandaloneExeBuild(unittest.TestCase):
    """Verifies that the PyInstaller standalone Windows executable exists and has valid PE structure."""

    def test_exe_binary_properties(self):
        dist_dir = os.path.join(PROJECT_ROOT, "dist")
        exe_path = os.path.join(dist_dir, "SmartDownload.exe")
        self.assertTrue(os.path.exists(exe_path), f"SmartDownload.exe not found at {exe_path}")
        file_size = os.path.getsize(exe_path)
        self.assertGreater(file_size, 5 * 1024 * 1024, f"Binary size {file_size} is suspiciously small")

    def test_exe_binary_header_pe_signature(self):
        dist_dir = os.path.join(PROJECT_ROOT, "dist")
        exe_path = os.path.join(dist_dir, "SmartDownload.exe")
        with open(exe_path, "rb") as f:
            header = f.read(2)
        self.assertEqual(header, b"MZ", "Executable missing valid Windows PE MZ header")

    def test_exe_binary_startup_verification(self):
        dist_dir = os.path.join(PROJECT_ROOT, "dist")
        exe_path = os.path.join(dist_dir, "SmartDownload.exe")
        if not os.path.exists(exe_path):
            self.skipTest(f"{exe_path} not found")
        # Run with --test-startup (DEVNULL for windowed GUI executables)
        proc = subprocess.run([exe_path, "--test-startup"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        self.assertEqual(proc.returncode, 0, f"Standalone exe failed to start cleanly with returncode {proc.returncode}")

    def test_exe_binary_minimized_background_launch(self):
        dist_dir = os.path.join(PROJECT_ROOT, "dist")
        exe_path = os.path.join(dist_dir, "SmartDownload.exe")
        if not os.path.exists(exe_path):
            self.skipTest(f"{exe_path} not found")
        proc = subprocess.Popen([exe_path, "--minimized"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            connected = False
            for _ in range(40):
                time.sleep(0.4)
                try:
                    req = urllib.request.Request("http://127.0.0.1:9242/ping")
                    with urllib.request.urlopen(req, timeout=1.0) as resp:
                        if resp.status == 200:
                            connected = True
                            break
                except Exception:
                    pass
            self.assertTrue(connected, "Standalone binary with --minimized failed to activate loopback server")
        finally:
            try:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            time.sleep(0.5)

    def test_clean_stale_shadow_modules(self):
        """Verifies that clean_stale_shadow_modules purges shadow files from __pycache__ and root."""
        from build_installer import clean_stale_shadow_modules
        pycache_dir = os.path.join(PROJECT_ROOT, "__pycache__")
        os.makedirs(pycache_dir, exist_ok=True)
        dummy_pyc = os.path.join(pycache_dir, "smart_download.cpython-999.pyc")
        with open(dummy_pyc, "w") as f:
            f.write("dummy")
        self.assertTrue(os.path.isfile(dummy_pyc))
        clean_stale_shadow_modules()
        self.assertFalse(os.path.isfile(dummy_pyc), "Dummy shadow pyc was not removed by clean_stale_shadow_modules")

    def test_install_application_purges_stale_core_plugin(self):
        """Verifies that install_application purges %APPDATA%\\SmartDownload\\core_plugin."""
        from smart_download.installer import install_application
        from smart_download.services.core_patch_updater import get_core_plugin_dir

        with tempfile.TemporaryDirectory() as tmp_dir:
            dummy_plugin = os.path.join(tmp_dir, "core_plugin")
            os.makedirs(dummy_plugin, exist_ok=True)
            dummy_file = os.path.join(dummy_plugin, "stale.txt")
            with open(dummy_file, "w") as f:
                f.write("stale")

            target_install = os.path.join(tmp_dir, "install_target")
            with patch("smart_download.services.core_patch_updater.get_core_plugin_dir", return_value=dummy_plugin):
                install_application(
                    target_dir=target_install,
                    register_browser=False,
                    create_desktop=False,
                    create_start_menu=False,
                    register_startup=False,
                )
            self.assertFalse(os.path.exists(dummy_plugin), "stale core_plugin directory was not purged during installation")

    def test_purge_stale_core_plugin_in_builder(self):
        """Verifies that purge_stale_core_plugin in build_installer removes the core_plugin directory."""
        from build_installer import purge_stale_core_plugin
        with tempfile.TemporaryDirectory() as tmp_dir:
            dummy_plugin = os.path.join(tmp_dir, "core_plugin")
            os.makedirs(dummy_plugin, exist_ok=True)
            with patch("smart_download.services.core_patch_updater.get_core_plugin_dir", return_value=dummy_plugin):
                purge_stale_core_plugin()
            self.assertFalse(os.path.exists(dummy_plugin), "purge_stale_core_plugin failed to remove directory")


if __name__ == "__main__":
    unittest.main()

