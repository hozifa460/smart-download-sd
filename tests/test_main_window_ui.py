"""
Automated Test Module for Smart Download (SD)
"""
import os, sys, tempfile, time, json, shutil, struct, hashlib, ssl, re, unittest, threading, subprocess
import http.server, socketserver, urllib.request, urllib.error, urllib.parse
from unittest.mock import patch, MagicMock
from typing import List, Dict, Optional, Tuple, Any

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
    tk, ttk = None, None

try:
    from PIL import Image, ImageTk
except Exception:
    Image, ImageTk = None, None

from youtube_resolver import *
from browser_bridge import BrowserBridgeServer, BrowserBridgeHandler, DEFAULT_BRIDGE_PORT
from native_messaging_host import read_message, send_message, handle_payload
from register_browser import *
import installer
from turbo_downloader import *


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

class TestBackgroundAndMinimizedLaunch(unittest.TestCase):
    """Verifies silent background launch, IPC/sniffer preservation, and window restore on intercept."""

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_start_hidden_flag_withdraws_root(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            self.assertFalse(self.root.winfo_viewable(), "Window must be hidden/withdrawn on start_hidden=True")
            self.assertTrue(gui.bridge_server.is_running, "Loopback IPC bridge server must remain active")
            self.assertTrue(gui._clipboard_sniffer_active, "Clipboard URL sniffer must remain active")
            self.assertIsNotNone(gui._clipboard_job, "Periodic clipboard sniffer job must be scheduled")

            # Verify restore_window
            gui.restore_window()
            self.assertFalse(gui._start_hidden)
            self.root.update_idletasks()
            self.assertTrue(self.root.winfo_viewable(), "Window must be visible after restore_window()")
        finally:
            gui._cleanup_resources()

    def test_cli_flags_detection(self):
        flags = [
            (["turbo_downloader.py", "--minimized"], True),
            (["turbo_downloader.py", "--background"], True),
            (["turbo_downloader.py"], False)
        ]
        for argv, expected_hidden in flags:
            with patch.object(sys, "argv", argv):
                sub_root = tk.Tk()
                sub_root.withdraw()
                try:
                    gui = ModernFramelessGUI(sub_root)
                    self.assertEqual(gui._start_hidden, expected_hidden)
                    gui._cleanup_resources()
                finally:
                    try:
                        sub_root.update_idletasks()
                        sub_root.destroy()
                    except Exception:
                        pass

    def test_clipboard_detection_suppresses_window_and_shows_modal(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            target_url = "https://speed.cloudflare.com/__down?bytes=25000000"
            gui._on_clipboard_url_detected(target_url)

            # Main window must remain hidden (suppressed)
            self.assertTrue(gui._start_hidden)
            self.assertEqual(self.root.state(), "withdrawn")
            # Confirmation modal must be created and active
            self.assertIsNotNone(gui._confirm_modal)
            self.assertTrue(gui._confirm_modal.winfo_exists())
            self.assertEqual(gui.entry_url.get().strip(), target_url)

            # User chooses 'Open in Main App': restores window
            with patch.object(gui, "_on_start_download") as mock_start:
                gui._confirm_modal._on_open_in_main()
                mock_start.assert_called_once()
            self.assertFalse(gui._start_hidden)
            self.assertEqual(self.root.state(), "normal")
        finally:
            if gui._confirm_modal:
                try:
                    gui._confirm_modal.destroy()
                except Exception:
                    pass
            gui._cleanup_resources()

    def test_browser_download_suppresses_window_and_shows_modal(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            target_url = "https://speed.cloudflare.com/files/archive_bundle.zip"
            payload = {
                "url": target_url,
                "filename": "archive_bundle.zip",
                "start_immediately": False
            }
            gui._apply_browser_download(payload)

            # Main window must remain hidden (suppressed)
            self.assertTrue(gui._start_hidden)
            self.assertEqual(self.root.state(), "withdrawn")
            # Confirmation modal must be displayed
            self.assertIsNotNone(gui._confirm_modal)
            self.assertTrue(gui._confirm_modal.winfo_exists())
            self.assertEqual(gui.entry_url.get().strip(), target_url)

            # User chooses 'Open in Main App': restores window
            with patch.object(gui, "_on_start_download") as mock_start:
                gui._confirm_modal._on_open_in_main()
                mock_start.assert_called_once()
            self.assertFalse(gui._start_hidden)
            self.assertEqual(self.root.state(), "normal")
        finally:
            if gui._confirm_modal:
                try:
                    gui._confirm_modal.destroy()
                except Exception:
                    pass
            gui._cleanup_resources()

    def test_gui_startup_toggle_button(self):
        gui = ModernFramelessGUI(self.root, start_hidden=False)
        try:
            self.assertTrue(hasattr(gui, "btn_startup"))
            # Initial state
            init_state = is_startup_enabled()
            if init_state:
                self.assertEqual(gui.btn_startup.cget("text"), "🚀 Boot: ON")
            else:
                self.assertEqual(gui.btn_startup.cget("text"), "🚀 Boot: OFF")

            # Toggle state
            toggled = gui.toggle_startup_setting()
            self.assertEqual(toggled, not init_state)
            if toggled:
                self.assertEqual(gui.btn_startup.cget("text"), "🚀 Boot: ON")
            else:
                self.assertEqual(gui.btn_startup.cget("text"), "🚀 Boot: OFF")

            # Toggle back to restore
            gui.toggle_startup_setting()
            self.assertEqual(is_startup_enabled(), init_state)
        finally:
            gui._cleanup_resources()

    def test_browser_integration_dialog_startup_card(self):
        gui = ModernFramelessGUI(self.root, start_hidden=False)
        try:
            gui._open_browser_integration_dialog()
            self.assertTrue(hasattr(gui, "_update_dlg_startup_ui"))
            # Test triggering update callback
            gui._update_dlg_startup_ui()
        finally:
            gui._cleanup_resources()

    def test_cli_flags_case_insensitivity_and_variants(self):
        variants = [
            ["turbo_downloader.py", "-minimized"],
            ["turbo_downloader.py", "--MINIMIZED"],
            ["turbo_downloader.py", "/minimized"],
            ["turbo_downloader.py", "-background"],
            ["turbo_downloader.py", "--BACKGROUND"],
            ["turbo_downloader.py", "/background"],
        ]
        for v in variants:
            with patch.object(sys, "argv", v):
                sub_root = tk.Tk()
                sub_root.withdraw()
                try:
                    gui = ModernFramelessGUI(sub_root)
                    self.assertTrue(gui._start_hidden, f"Flag {v} failed to activate _start_hidden")
                    self.assertTrue(gui._was_started_hidden, f"Flag {v} failed to set _was_started_hidden")
                    gui._cleanup_resources()
                finally:
                    try:
                        sub_root.update_idletasks()
                        sub_root.destroy()
                    except Exception:
                        pass

    def test_was_started_hidden_preserves_confirmation_modal(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            gui._auto_start_clipboard = False
            payload = {
                "url": "https://speed.cloudflare.com/__down?bytes=50000000",
                "filename": "big_file.bin",
                "start_immediately": True
            }
            gui._apply_browser_download(payload)
            self.assertIsNotNone(gui._confirm_modal)
            self.assertTrue(gui._confirm_modal.winfo_exists())
        finally:
            if gui._confirm_modal:
                try:
                    gui._confirm_modal.destroy()
                except Exception:
                    pass
            gui._cleanup_resources()

    def test_single_instance_show_endpoint(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            self.assertFalse(self.root.winfo_viewable())

            # Request /show via loopback HTTP bridge
            req = urllib.request.Request("http://127.0.0.1:9242/show")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(body.get("status"), "ok")

            for _ in range(50):
                gui._drain_dispatch_queue()
                self.root.update()
                if not gui._start_hidden:
                    break
                time.sleep(0.03)

            self.assertFalse(gui._start_hidden)
            self.assertTrue(self.root.winfo_viewable())
        finally:
            gui._cleanup_resources()

    def test_notify_running_instance_helper(self):
        # 1. When GUI is active and listening
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            handled = notify_running_instance(show=True)
            self.assertTrue(handled, "notify_running_instance should succeed when instance is listening")
            for _ in range(50):
                gui._drain_dispatch_queue()
                self.root.update()
                if not gui._start_hidden:
                    break
                time.sleep(0.03)
            self.assertFalse(gui._start_hidden)
        finally:
            gui._cleanup_resources()

        # 2. When no GUI is listening
        handled_stopped = notify_running_instance(show=True)
        self.assertFalse(handled_stopped, "notify_running_instance should return False when no server is running")

    def test_clipboard_detection_youtube_url_keeps_window_hidden(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            with patch.object(gui, "_start_youtube_download") as mock_yt:
                gui._on_clipboard_url_detected("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
                self.assertTrue(gui._start_hidden)
                self.assertEqual(self.root.state(), "withdrawn")
                mock_yt.assert_called_once()
        finally:
            gui._cleanup_resources()


class TestSystemTrayAndBackgroundMinimization(unittest.TestCase):
    """
    Automated test suite verifying Windows System Tray Icon & Background Minimization:
    1. Settings persistence: load_settings, save_settings, get_setting, set_setting defaults & round-trip.
    2. SystemTrayManager initialization & 4-item right-click context menu structure.
    3. Tray menu dynamic labels (Clipboard Sniffer & Start with Windows).
    4. Tray menu callbacks: Restore window, Toggle sniffer, Toggle startup, Exit completely.
    5. Window Close (✕) action minimizes to tray when minimize_to_tray is True (default).
    6. Window Close (✕) action exits completely when minimize_to_tray is False.
    7. GUI Settings toggle: toggle_minimize_to_tray_setting updates preference and UI.
    8. Seamless wakeup from tray on clipboard URL interception with DownloadConfirmationModal.
    9. Seamless wakeup from tray on browser extension download with DownloadConfirmationModal.
    10. Clean exit: stops tray icon, cancels timers, stops loopback server, and destroys window.
    """

    def setUp(self):
        self.root = None

    def tearDown(self):
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None

    def test_settings_persistence(self):
        cur = get_setting("minimize_to_tray", True)
        self.assertIn(cur, (True, False))
        set_setting("minimize_to_tray", False)
        self.assertFalse(get_setting("minimize_to_tray", True))
        set_setting("minimize_to_tray", True)
        self.assertTrue(get_setting("minimize_to_tray", False))

    def test_tray_manager_menu_structure(self):
        class MockApp:
            def __init__(self):
                self._clipboard_sniffer_active = True
                self.restored = False
                self.exited = False
            def restore_window(self):
                self.restored = True
            def toggle_clipboard_sniffer(self):
                self._clipboard_sniffer_active = not self._clipboard_sniffer_active
            def toggle_startup_setting(self):
                return True
            def exit_completely(self):
                self.exited = True
            def dispatch_to_main_thread(self, fn, *args, **kwargs):
                fn(*args, **kwargs)

        app = MockApp()
        tray = SystemTrayManager(app)
        menu = tray._build_menu()
        self.assertIsNotNone(menu)
        items = list(menu.items)
        self.assertEqual(len(items), 4)

        # 1. Open Turbo Downloader (default action for single / double click)
        self.assertEqual(items[0].text, "🖥️ Open Smart Download")
        self.assertTrue(items[0].default)

        # 2. Clipboard Sniffer
        self.assertIn("Clipboard Sniffer: Active", items[1].text)

        # 3. Start with Windows
        self.assertIn("Start with Windows", items[2].text)

        # 4. Exit Completely
        self.assertEqual(items[3].text, "❌ Exit Completely")

    def test_tray_manager_menu_callbacks(self):
        class MockApp:
            def __init__(self):
                self._clipboard_sniffer_active = True
                self.restored = False
                self.exited = False
                self.sniffer_toggled = False
                self.startup_toggled = False
            def restore_window(self):
                self.restored = True
            def toggle_clipboard_sniffer(self):
                self._clipboard_sniffer_active = not self._clipboard_sniffer_active
                self.sniffer_toggled = True
            def toggle_startup_setting(self):
                self.startup_toggled = True
                return True
            def exit_completely(self):
                self.exited = True
            def dispatch_to_main_thread(self, fn, *args, **kwargs):
                fn(*args, **kwargs)

        app = MockApp()
        tray = SystemTrayManager(app)
        menu = tray._build_menu()

        # Invoke default (single/double click) or item 0
        menu(None)
        self.assertTrue(app.restored)

        # Invoke sniffer toggle
        menu.items[1](None)
        self.assertTrue(app.sniffer_toggled)
        self.assertFalse(app._clipboard_sniffer_active)
        self.assertIn("Clipboard Sniffer: Paused", menu.items[1].text)

        # Invoke startup toggle
        menu.items[2](None)
        self.assertTrue(app.startup_toggled)

        # Invoke exit
        menu.items[3](None)
        self.assertTrue(app.exited)

    def test_close_button_minimizes_to_tray_when_enabled(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        try:
            gui.set_minimize_to_tray(True)
            self.assertTrue(gui.minimize_to_tray)
            self.assertEqual(self.root.state(), "normal")

            # Click close button
            gui._on_close()

            # Window must be withdrawn (minimized to tray)
            self.assertEqual(self.root.state(), "withdrawn")
            # Loopback server and clipboard sniffer must remain active
            self.assertTrue(gui.bridge_server.is_running)
            self.assertTrue(gui._clipboard_sniffer_active)
        finally:
            gui.exit_completely()

    def test_close_button_exits_when_disabled(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        gui.set_minimize_to_tray(False)
        self.assertFalse(gui.minimize_to_tray)

        # Click close button
        gui._on_close()

        # Root must be destroyed
        try:
            exists = bool(self.root and self.root.winfo_exists())
        except Exception:
            exists = False
        self.assertFalse(exists)
        self.root = None

    def test_gui_settings_tray_card_and_toggle(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        try:
            gui.set_minimize_to_tray(True)
            self.assertTrue(gui.minimize_to_tray)

            # Toggle setting
            res = gui.toggle_minimize_to_tray_setting()
            self.assertFalse(res)
            self.assertFalse(gui.minimize_to_tray)
            self.assertFalse(get_setting("minimize_to_tray", True))

            # Open settings dialog
            gui._open_browser_integration_dialog()
            self.assertTrue(hasattr(gui, "_update_dlg_tray_ui"))
            gui._update_dlg_tray_ui()

            # Toggle back to True
            res2 = gui.toggle_minimize_to_tray_setting()
            self.assertTrue(res2)
            self.assertTrue(gui.minimize_to_tray)
            self.assertTrue(get_setting("minimize_to_tray", False))
        finally:
            gui.exit_completely()

    def test_clipboard_detection_keeps_tray_state_and_shows_modal(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        try:
            gui.set_minimize_to_tray(True)
            gui._on_close()
            self.assertEqual(self.root.state(), "withdrawn")

            # Intercept download URL from clipboard
            target_url = "https://speed.cloudflare.com/__down?bytes=15000000"
            gui._on_clipboard_url_detected(target_url)

            # Main window must remain withdrawn in tray
            self.assertEqual(self.root.state(), "withdrawn")
            # TDM confirmation modal must be open
            self.assertIsNotNone(gui._confirm_modal)
            self.assertTrue(gui._confirm_modal.winfo_exists())
            self.assertEqual(gui.entry_url.get().strip(), target_url)

            # Clicking 'Open in Main App' restores the main window
            gui._confirm_modal._on_open_in_main()
            self.assertEqual(self.root.state(), "normal")
        finally:
            if gui._confirm_modal:
                try:
                    gui._confirm_modal.destroy()
                except Exception:
                    pass
            gui.exit_completely()

    def test_browser_download_keeps_tray_state_and_shows_modal(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        try:
            gui.set_minimize_to_tray(True)
            gui._on_close()
            self.assertEqual(self.root.state(), "withdrawn")

            # Browser extension pushes download payload
            target_url = "https://speed.cloudflare.com/files/release_pkg.zip"
            gui._apply_browser_download({
                "url": target_url,
                "filename": "release_pkg.zip",
                "start_immediately": False
            })

            # Main window must remain withdrawn in tray
            self.assertEqual(self.root.state(), "withdrawn")
            # TDM confirmation modal must be open
            self.assertIsNotNone(gui._confirm_modal)
            self.assertTrue(gui._confirm_modal.winfo_exists())
            self.assertEqual(gui.entry_url.get().strip(), target_url)

            # Clicking 'Open in Main App' restores the main window
            gui._confirm_modal._on_open_in_main()
            self.assertEqual(self.root.state(), "normal")
        finally:
            if gui._confirm_modal:
                try:
                    gui._confirm_modal.destroy()
                except Exception:
                    pass
            gui.exit_completely()

    def test_clean_exit_completely_teardown(self):
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        self.assertTrue(gui.bridge_server.is_running)
        gui.exit_completely()

        # Bridge server stopped
        self.assertIsNone(gui.bridge_server)
        # Root destroyed
        try:
            exists = bool(self.root and self.root.winfo_exists())
        except Exception:
            exists = False
        self.assertFalse(exists)
        self.root = None


class TestClipboardSequenceRecopying(unittest.TestCase):
    """Verifies that re-copying the same link (clipboard sequence increment) re-triggers URL processing."""

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_recopy_same_url_detected_when_sequence_changes(self):
        gui = ModernFramelessGUI(self.root)
        try:
            url = "https://example.com/recopy_test.zip"
            detected_urls = []
            gui._on_clipboard_url_detected = lambda u: detected_urls.append(u)

            with patch("turbo_downloader.IS_WINDOWS", True):
                with patch("turbo_downloader.get_clipboard_text", return_value=url):
                    # 1. First copy event at seq=100
                    with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=100):
                        gui._check_clipboard_now()
                        self.assertEqual(len(detected_urls), 1)

                    # 2. Subsequent tick without copying (seq still 100) -> ignored
                    with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=100):
                        gui._check_clipboard_now()
                        self.assertEqual(len(detected_urls), 1)

                    # 3. User explicitly re-copies the exact same link (seq increments to 101)
                    with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=101):
                        gui._check_clipboard_now()
                        self.assertEqual(len(detected_urls), 2, "Re-copying identical link with sequence change must trigger")

                    # 4. Another tick with seq=101 -> ignored
                    with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=101):
                        gui._check_clipboard_now()
                        self.assertEqual(len(detected_urls), 2)
        finally:
            gui._cleanup_resources()

    def test_startup_clipboard_not_permanently_blocked(self):
        url = "https://example.com/startup_existing.zip"
        # Sniffer starts up with URL already in clipboard
        with patch("turbo_downloader.IS_WINDOWS", True):
            with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=50):
                with patch("turbo_downloader.get_clipboard_text", return_value=url):
                    gui = ModernFramelessGUI(self.root)
                    try:
                        detected_urls = []
                        gui._on_clipboard_url_detected = lambda u: detected_urls.append(u)

                        # Tick 1: sequence unchanged -> no trigger
                        gui._check_clipboard_now()
                        self.assertEqual(len(detected_urls), 0)

                        # User copies the same URL after launch -> seq=51 -> triggers!
                        with patch("ctypes.windll.user32.GetClipboardSequenceNumber", return_value=51):
                            gui._check_clipboard_now()
                            self.assertEqual(len(detected_urls), 1, "User copying startup clipboard URL after launch must trigger")
                    finally:
                        gui._cleanup_resources()

    def test_modal_cancellation_clears_last_clipboard_url(self):
        gui = ModernFramelessGUI(self.root)
        try:
            url = "https://example.com/cancel_and_recopy.zip"
            gui._last_clipboard_url = url
            gui.clear_last_clipboard_url()
            self.assertIsNone(gui._last_clipboard_url)
        finally:
            gui._cleanup_resources()

    def test_clear_last_clipboard_url_allows_reprocessing(self):
        gui = ModernFramelessGUI(self.root)
        try:
            url = "https://example.com/clear_recopy_test.zip"
            detected_urls = []
            gui._on_clipboard_url_detected = lambda u: detected_urls.append(u)
            gui._last_clipboard_url = url

            with patch("turbo_downloader.get_clipboard_text", return_value=url):
                # Duplicate is initially suppressed
                gui._check_clipboard_now(force=True)
                self.assertEqual(len(detected_urls), 0)

                # Clear last clipboard url (as done when closing/cancelling a modal)
                gui.clear_last_clipboard_url()

                # Now checking clipboard processes the URL
                gui._check_clipboard_now(force=True)
                self.assertEqual(len(detected_urls), 1, "Clearing last clipboard URL must allow re-processing")
        finally:
            gui._cleanup_resources()

    def test_quality_modal_close_clears_last_clipboard_url(self):
        gui = ModernFramelessGUI(self.root)
        try:
            url = "https://www.youtube.com/watch?v=cancel_modal_test"
            gui._last_clipboard_url = url
            modal = QualitySelectionModal(
                parent=self.root,
                video_title="Cancel Test Video",
                duration=120,
                options=[],
                default_dest_path="test.mp4",
                theme=gui._theme_dict(),
                on_confirm=lambda opt, dest: None,
                on_cancel=None,
                parent_app=gui
            )
            modal._on_close()
            self.assertIsNone(gui._last_clipboard_url, "Closing QualitySelectionModal must clear _last_clipboard_url")
        finally:
            gui._cleanup_resources()

    def test_download_confirmation_modal_close_clears_last_clipboard_url(self):
        gui = ModernFramelessGUI(self.root)
        try:
            url = "https://example.com/confirm_cancel.zip"
            gui._last_clipboard_url = url
            modal = DownloadConfirmationModal(
                parent=self.root,
                url=url,
                default_dest_path="confirm_cancel.zip",
                theme=gui._theme_dict(),
                parent_app=gui
            )
            modal._on_close()
            self.assertIsNone(gui._last_clipboard_url, "Closing DownloadConfirmationModal must clear _last_clipboard_url")
        finally:
            gui._cleanup_resources()


class TestBackgroundStartupNotificationAndTray(unittest.TestCase):
    """Verifies that launching with --minimized or --background displays notification and sleek toast."""

    def setUp(self):
        import tkinter as tk
        self._orig_toast_env = os.environ.pop("SD_DISABLE_STARTUP_TOAST", None)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        if self._orig_toast_env is not None:
            os.environ["SD_DISABLE_STARTUP_TOAST"] = self._orig_toast_env
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_background_notification_toast_creation_and_auto_dismiss(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui._start_hidden)
            gui._show_background_startup_notification()

            # Root window must remain hidden/withdrawn
            self.assertFalse(self.root.winfo_viewable())

            # Background toast must be displayed
            self.assertIsNotNone(gui._bg_toast)
            self.assertTrue(gui._bg_toast.winfo_exists())

            # Text content validation
            found_text = False
            for w in gui._bg_toast.winfo_children():
                for sub in w.winfo_children():
                    if isinstance(sub, tk.Frame):
                        for lbl in sub.winfo_children():
                            if "active in the background" in str(lbl.cget("text")):
                                found_text = True
            self.assertTrue(found_text, "Background notification must display 'active in the background'")

            # Dismissal
            gui._dismiss_bg_toast()
            self.assertIsNone(gui._bg_toast)
        finally:
            gui._cleanup_resources()

    def test_update_ui_language_with_active_speed_limit(self):
        """Verifies _update_ui_language formats active speed limit without NameError."""
        from smart_download.locales.i18n import set_current_language
        set_current_language("en")
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            # Active speed limit
            gui.speed_limit = 5.0 * 1024 * 1024
            gui._update_ui_language()
            active_text = gui.lbl_active_limit.cget("text")
            self.assertIn("5.00 MB/s", active_text)

            # Unlimited speed limit
            gui.speed_limit = 0.0
            gui._update_ui_language()
            active_text_unlimited = gui.lbl_active_limit.cget("text")
            self.assertIn("Unlimited", active_text_unlimited)
        finally:
            gui._cleanup_resources()

    def test_build_title_bar_icon_dim_scaling(self):
        """Verifies _build_title_bar scales icon_dim based on dpi_scale without NameError."""
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(hasattr(gui, "_title_icon_photo"))
            self.assertIsNotNone(gui._title_icon_photo)
        finally:
            gui._cleanup_resources()


if __name__ == "__main__":
    unittest.main()
