"""
Unit test suite verifying Stage 4: Strict Single Responsibility Principle (1 File = 1 Responsibility) Architecture.
Verifies all newly decomposed mixins, panels, core engines, and utilities,
their backward compatibility re-exports, and isolated instantiation/behavior.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if os.path.isdir(_src_dir) and _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# 1. UI Controllers
from smart_download.ui.controllers.locale_controller import LocaleControllerMixin
from smart_download.ui.controllers.speed_limiter_controller import SpeedLimiterControllerMixin
from smart_download.ui.controllers.settings_controller import SettingsControllerMixin
from smart_download.ui.controllers.youtube_download_controller import YouTubeDownloadControllerMixin
from smart_download.ui.controllers.batch_download_controller import BatchDownloadControllerMixin
from smart_download.ui.controllers.link_refresh_controller import LinkRefreshControllerMixin
from smart_download.ui.controllers.media_download_controller import MediaDownloadControllerMixin
from smart_download.ui.controllers.dialog_controller import DialogControllerMixin
from smart_download.ui.controllers.lifecycle_controller import WindowLifecycleMixin
from smart_download.ui.controllers.toast_controller import ToastControllerMixin
from smart_download.ui.controllers.update_controller import UpdateControllerMixin
from smart_download.ui.controllers.theme_controller import ThemeControllerMixin
from smart_download.ui.controllers.dispatch_controller import DispatchControllerMixin
from smart_download.ui.controllers.window_controller import WindowChromeMixin

# 2. UI Panels
from smart_download.ui.panels.metrics_panel import MetricsPanelMixin
from smart_download.ui.panels.chunks_panel import ChunksPanelMixin
from smart_download.ui.panels.controls_panel import ControlsPanelMixin
from smart_download.ui.panels.inputs_panel import InputsPanelMixin

# 3. Core & Utils
from smart_download.core.engine_resumer import EngineResumerMixin
from smart_download.core.engine_workers import EngineWorkersMixin
from smart_download.core.engine import TurboDownloadEngine
from smart_download.utils.magic_detector import MagicBytesDetector
from smart_download.utils.archive_utils import calculate_file_integrity, auto_unpack_archive
from smart_download.utils.speed_utils import parse_speed_limit, format_speed
from smart_download.utils.file_ops import (
    CATEGORY_SUBFOLDERS,
    get_file_category_and_icon,
    resolve_categorized_path,
    open_downloaded_file,
    open_containing_folder,
    MagicBytesDetector as ReExportedMagicDetector,
    calculate_file_integrity as ReExportedIntegrity,
    auto_unpack_archive as ReExportedUnpack,
)
from smart_download.utils.url_utils import (
    parse_speed_limit as ReExportedParseSpeed,
    format_speed as ReExportedFormatSpeed,
)
from smart_download.ui.main_window import ModernFramelessGUI
import turbo_downloader as td


class TestUIControllersSRP(unittest.TestCase):
    """Verifies that all 5 decomposed UI controllers adhere to SRP and inheritance requirements."""

    def test_settings_controller_inheritance_and_methods(self):
        """Verify settings_controller inherits LocaleControllerMixin and SpeedLimiterControllerMixin."""
        self.assertTrue(issubclass(SettingsControllerMixin, LocaleControllerMixin))
        self.assertTrue(issubclass(SettingsControllerMixin, SpeedLimiterControllerMixin))

        # Check locale methods
        self.assertTrue(hasattr(LocaleControllerMixin, "toggle_language"))
        self.assertTrue(hasattr(LocaleControllerMixin, "_update_ui_language"))

        # Check speed limiter methods
        self.assertTrue(hasattr(SpeedLimiterControllerMixin, "_on_slider_moved"))
        self.assertTrue(hasattr(SpeedLimiterControllerMixin, "_on_preset_selected"))
        self.assertTrue(hasattr(SpeedLimiterControllerMixin, "_apply_speed_limit"))

        # Check app preferences retained on SettingsControllerMixin
        pref_methods = [
            "toggle_auto_categorize",
            "_update_auto_cat_btn",
            "_update_startup_btn",
            "_get_cookies_btn_text",
            "_update_cookies_btn",
            "cycle_cookies_setting",
            "toggle_startup_setting",
            "toggle_minimize_to_tray_setting",
            "set_minimize_to_tray",
        ]
        for m in pref_methods:
            self.assertTrue(hasattr(SettingsControllerMixin, m), f"Missing {m} in SettingsControllerMixin")

    def test_speed_limiter_isolated_behavior(self):
        """Test SpeedLimiterControllerMixin functions safely without full GUI chrome."""
        class MockLimiter(SpeedLimiterControllerMixin):
            def __init__(self):
                self.speed_limit = 0.0
                self.lbl_slider_val = MagicMock()
                self.lbl_active_limit = MagicMock()
                self.limit_preset_var = MagicMock()
                self.entry_custom_speed = MagicMock()
                self.slider_speed = MagicMock()
                self.engine = MagicMock(is_running=True)

        inst = MockLimiter()
        inst._on_slider_moved("512")
        self.assertEqual(inst.speed_limit, 512 * 1024.0)
        inst.engine.set_speed_limit.assert_called_with(512 * 1024.0)

        inst._on_slider_moved("0")
        self.assertEqual(inst.speed_limit, 0.0)

    def test_media_download_controller_composition(self):
        """Verify MediaDownloadControllerMixin inherits YouTube, Batch, and LinkRefresh mixins."""
        self.assertTrue(issubclass(MediaDownloadControllerMixin, YouTubeDownloadControllerMixin))
        self.assertTrue(issubclass(MediaDownloadControllerMixin, BatchDownloadControllerMixin))
        self.assertTrue(issubclass(MediaDownloadControllerMixin, LinkRefreshControllerMixin))

        self.assertTrue(hasattr(YouTubeDownloadControllerMixin, "_start_youtube_download"))
        self.assertTrue(hasattr(BatchDownloadControllerMixin, "_show_multiple_candidates_dialog"))
        self.assertTrue(hasattr(BatchDownloadControllerMixin, "_queue_multiple_candidate_downloads"))
        self.assertTrue(hasattr(LinkRefreshControllerMixin, "_open_refresh_link_dialog"))
        self.assertTrue(hasattr(LinkRefreshControllerMixin, "_on_link_refreshed_success"))

    def test_lifecycle_and_dialog_controllers(self):
        """Verify WindowLifecycleMixin inherits DialogControllerMixin."""
        self.assertTrue(issubclass(WindowLifecycleMixin, DialogControllerMixin))

        dialog_methods = ["show_safe_error", "show_safe_info", "show_safe_warning", "ask_safe_yesno"]
        for m in dialog_methods:
            self.assertTrue(hasattr(DialogControllerMixin, m), f"Missing {m} in DialogControllerMixin")

        lifecycle_methods = [
            "_on_root_destroyed",
            "_cleanup_resources",
            "_on_close",
            "minimize_to_tray_action",
            "exit_completely",
        ]
        for m in lifecycle_methods:
            self.assertTrue(hasattr(WindowLifecycleMixin, m), f"Missing {m} in WindowLifecycleMixin")

    def test_update_and_toast_controllers(self):
        """Verify UpdateControllerMixin inherits ToastControllerMixin."""
        self.assertTrue(issubclass(UpdateControllerMixin, ToastControllerMixin))

        toast_methods = [
            "_show_background_startup_notification",
            "_show_background_toast",
            "_dismiss_bg_toast",
            "_show_fetching_toast",
            "_close_fetching_toast",
        ]
        for m in toast_methods:
            self.assertTrue(hasattr(ToastControllerMixin, m), f"Missing {m} in ToastControllerMixin")

        update_methods = [
            "_start_auto_update_check",
            "check_for_updates_manual",
            "_show_update_dialog",
        ]
        for m in update_methods:
            self.assertTrue(hasattr(UpdateControllerMixin, m), f"Missing {m} in UpdateControllerMixin")

    def test_window_chrome_composition(self):
        """Verify WindowChromeMixin inherits ThemeControllerMixin and DispatchControllerMixin."""
        self.assertTrue(issubclass(WindowChromeMixin, ThemeControllerMixin))
        self.assertTrue(issubclass(WindowChromeMixin, DispatchControllerMixin))

        self.assertTrue(hasattr(ThemeControllerMixin, "_init_theme"))
        self.assertTrue(hasattr(ThemeControllerMixin, "_theme_dict"))

        self.assertTrue(hasattr(DispatchControllerMixin, "log"))
        self.assertTrue(hasattr(DispatchControllerMixin, "dispatch_to_main_thread"))
        self.assertTrue(hasattr(DispatchControllerMixin, "_drain_dispatch_queue"))

        chrome_methods = [
            "_setup_window",
            "restore_window",
            "_build_title_bar",
            "_on_title_press",
            "_on_title_drag",
            "_on_minimize",
            "is_window_hidden_or_minimized",
        ]
        for m in chrome_methods:
            self.assertTrue(hasattr(WindowChromeMixin, m), f"Missing {m} in WindowChromeMixin")


class TestUIPanelsSRP(unittest.TestCase):
    """Verifies UI Panels decomposition according to SRP."""

    def test_chunks_and_metrics_panels(self):
        """Verify ChunksPanelMixin inherits MetricsPanelMixin."""
        self.assertTrue(issubclass(ChunksPanelMixin, MetricsPanelMixin))

        metric_methods = ["_build_metrics_card", "_create_metric_box", "_draw_main_progress"]
        for m in metric_methods:
            self.assertTrue(hasattr(MetricsPanelMixin, m), f"Missing {m} in MetricsPanelMixin")

        chunk_methods = ["_build_chunk_visualizer_card", "_draw_chunk_segments", "_build_tabs_card"]
        for m in chunk_methods:
            self.assertTrue(hasattr(ChunksPanelMixin, m), f"Missing {m} in ChunksPanelMixin")

    def test_inputs_and_controls_panels(self):
        """Verify InputsPanelMixin inherits ControlsPanelMixin."""
        self.assertTrue(issubclass(InputsPanelMixin, ControlsPanelMixin))

        self.assertTrue(hasattr(ControlsPanelMixin, "_build_limiter_and_actions_card"))

        input_methods = [
            "_build_inputs_card",
            "_paste_url",
            "_browse_destination",
            "_is_downloads_or_category_subfolder",
            "_on_url_change",
        ]
        for m in input_methods:
            self.assertTrue(hasattr(InputsPanelMixin, m), f"Missing {m} in InputsPanelMixin")


class TestCoreAndUtilsSRP(unittest.TestCase):
    """Verifies Core and Utils modules decomposition according to SRP."""

    def test_engine_workers_and_resumer(self):
        """Verify EngineWorkersMixin inherits EngineResumerMixin."""
        self.assertTrue(issubclass(EngineWorkersMixin, EngineResumerMixin))

        resumer_methods = ["update_url", "validate_new_url", "resume_transfer", "refresh_link"]
        for m in resumer_methods:
            self.assertTrue(hasattr(EngineResumerMixin, m), f"Missing {m} in EngineResumerMixin")

        worker_methods = [
            "is_googlevideo_url",
            "_parse_filename_from_cd",
            "_create_request",
            "_spawn_worker",
            "_chunk_worker",
            "_dynamic_split_check",
            "_update_progress_metrics",
            "_stop_workers_for_error",
        ]
        for m in worker_methods:
            self.assertTrue(hasattr(EngineWorkersMixin, m), f"Missing {m} in EngineWorkersMixin")

    def test_magic_bytes_detector(self):
        """Test MagicBytesDetector accurately identifies container formats."""
        self.assertEqual(MagicBytesDetector.detect_bytes(b"PK\x03\x04\x00\x00")[0], ".zip")
        self.assertEqual(MagicBytesDetector.detect_bytes(b"\x37\x7A\xBC\xAF\x27\x1C")[0], ".7z")
        self.assertEqual(MagicBytesDetector.detect_bytes(b"%PDF-1.4")[0], ".pdf")
        self.assertIsNone(MagicBytesDetector.detect_bytes(b"HELLO WORLD"))

    def test_archive_utils(self):
        """Test calculate_file_integrity computes correct hashes."""
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"TurboDownloadEngine Integrity Test")
            temp_path = tf.name
        try:
            res = calculate_file_integrity(temp_path)
            self.assertIn("crc32", res)
            self.assertIn("sha256", res)
            self.assertEqual(len(res["crc32"]), 8)
            self.assertEqual(len(res["sha256"]), 64)
        finally:
            os.remove(temp_path)

    def test_speed_utils(self):
        """Test parse_speed_limit and format_speed."""
        self.assertEqual(parse_speed_limit("Unlimited"), 0.0)
        self.assertEqual(parse_speed_limit("500 KB/s"), 500 * 1024.0)
        self.assertEqual(parse_speed_limit("2 MB/s"), 2 * 1024 * 1024.0)
        self.assertEqual(format_speed(0, allow_unlimited=True), "Unlimited")
        self.assertEqual(format_speed(1024 * 1024), "1.00 MB/s")

    def test_backward_compatibility_re_exports(self):
        """Verify all extracted symbols are re-exported in file_ops, url_utils, and turbo_downloader."""
        self.assertIs(ReExportedMagicDetector, MagicBytesDetector)
        self.assertIs(ReExportedIntegrity, calculate_file_integrity)
        self.assertIs(ReExportedUnpack, auto_unpack_archive)

        self.assertIs(ReExportedParseSpeed, parse_speed_limit)
        self.assertIs(ReExportedFormatSpeed, format_speed)

        # Check turbo_downloader facade
        self.assertIs(td.LocaleControllerMixin, LocaleControllerMixin)
        self.assertIs(td.SpeedLimiterControllerMixin, SpeedLimiterControllerMixin)
        self.assertIs(td.SettingsControllerMixin, SettingsControllerMixin)
        self.assertIs(td.YouTubeDownloadControllerMixin, YouTubeDownloadControllerMixin)
        self.assertIs(td.BatchDownloadControllerMixin, BatchDownloadControllerMixin)
        self.assertIs(td.LinkRefreshControllerMixin, LinkRefreshControllerMixin)
        self.assertIs(td.MediaDownloadControllerMixin, MediaDownloadControllerMixin)
        self.assertIs(td.DialogControllerMixin, DialogControllerMixin)
        self.assertIs(td.WindowLifecycleMixin, WindowLifecycleMixin)
        self.assertIs(td.ToastControllerMixin, ToastControllerMixin)
        self.assertIs(td.UpdateControllerMixin, UpdateControllerMixin)
        self.assertIs(td.ThemeControllerMixin, ThemeControllerMixin)
        self.assertIs(td.DispatchControllerMixin, DispatchControllerMixin)
        self.assertIs(td.WindowChromeMixin, WindowChromeMixin)
        self.assertIs(td.MetricsPanelMixin, MetricsPanelMixin)
        self.assertIs(td.ChunksPanelMixin, ChunksPanelMixin)
        self.assertIs(td.ControlsPanelMixin, ControlsPanelMixin)
        self.assertIs(td.InputsPanelMixin, InputsPanelMixin)
        self.assertIs(td.EngineResumerMixin, EngineResumerMixin)
        self.assertIs(td.EngineWorkersMixin, EngineWorkersMixin)
        self.assertIs(td.MagicBytesDetector, MagicBytesDetector)
        self.assertIs(td.calculate_file_integrity, calculate_file_integrity)
        self.assertIs(td.auto_unpack_archive, auto_unpack_archive)
        self.assertIs(td.parse_speed_limit, parse_speed_limit)
        self.assertIs(td.format_speed, format_speed)

    def test_mro_integrity(self):
        """Verify ModernFramelessGUI and TurboDownloadEngine MRO contain all new mixins."""
        mfg_names = [cls.__name__ for cls in ModernFramelessGUI.__mro__]
        expected_gui_mixins = [
            "LocaleControllerMixin",
            "SpeedLimiterControllerMixin",
            "SettingsControllerMixin",
            "YouTubeDownloadControllerMixin",
            "BatchDownloadControllerMixin",
            "LinkRefreshControllerMixin",
            "MediaDownloadControllerMixin",
            "DialogControllerMixin",
            "WindowLifecycleMixin",
            "ToastControllerMixin",
            "UpdateControllerMixin",
            "ThemeControllerMixin",
            "DispatchControllerMixin",
            "WindowChromeMixin",
            "MetricsPanelMixin",
            "ChunksPanelMixin",
            "ControlsPanelMixin",
            "InputsPanelMixin",
        ]
        for name in expected_gui_mixins:
            self.assertIn(name, mfg_names, f"Expected {name} in ModernFramelessGUI MRO")

        engine_names = [cls.__name__ for cls in TurboDownloadEngine.__mro__]
        self.assertIn("EngineResumerMixin", engine_names)
        self.assertIn("EngineWorkersMixin", engine_names)


if __name__ == "__main__":
    unittest.main()
