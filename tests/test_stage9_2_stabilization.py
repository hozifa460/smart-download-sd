"""
Comprehensive verification test suite for Stage 9.2:
- Dual-Queue EXE Freeze Fix & tk.Misc singleton queue across reloads
- Background thread after() and after_idle() safe routing
- Complete removal of VideoPreviewModal and preview_service
- Instant window transitions and clean dismissal
- Expired googlevideo URL protection in history redownload
- Multi-thread connection retention (4 / 8 threads) & card_threads UI display
"""
import os
import sys
import time
import queue
import weakref
import threading
import tempfile
import unittest
from unittest.mock import MagicMock, patch

_sd_test_cfg = os.path.join(tempfile.gettempdir(), "sd_test_isolated_cfg_stage9_2")
os.makedirs(_sd_test_cfg, exist_ok=True)
os.environ["SD_CONFIG_DIR"] = _sd_test_cfg
os.environ["SD_HEADLESS_TEST"] = "1"

import tkinter as tk
from tkinter import ttk

from smart_download.utils.tk_helpers import (
    _BG_TK_CALLBACK_QUEUE,
    _drain_bg_tk_callbacks,
    animate_window_open,
    animate_window_close,
)
from smart_download.core.engine import TurboDownloadEngine
from smart_download.core.stream_coordinator import StreamDownloadCoordinator
from smart_download.services.youtube_models import YouTubeStreamInfo, VideoFormatOption
from smart_download.ui.panels.media_options_bar import MediaOptionsBarMixin
from smart_download.ui.modals.quality_modal import QualitySelectionModal
from smart_download.ui.modals.fetching_toast import FetchingLinkToast
from smart_download.ui.panels.history_panel import HistoryPanelMixin
from smart_download.core.history import DownloadHistoryManager


class TestStage9_2Stabilization(unittest.TestCase):
    """Test suite verifying all Stage 9.2 Critical Stabilization requirements."""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_singleton_callback_queue_across_module_reloads(self):
        """
        Verify that purging and re-importing tk_helpers preserves the EXACT SAME
        queue instance on tk.Misc._sd_bg_callback_queue and correctly routes
        background-thread after() and after_idle() calls into the main-thread drain loop.
        """
        import smart_download.utils.tk_helpers as helpers1

        initial_queue = helpers1._BG_TK_CALLBACK_QUEUE
        self.assertIs(getattr(tk.Misc, "_sd_bg_callback_queue", None), initial_queue)

        # Enqueue from a background thread
        results = []
        def bg_work():
            self.root.after(0, lambda: results.append("bg_after_1"))
            self.root.after_idle(lambda: results.append("bg_idle_1"))

        t = threading.Thread(target=bg_work)
        t.start()
        t.join()

        # Simulate _purge_and_reimport_core()
        if "smart_download.utils.tk_helpers" in sys.modules:
            del sys.modules["smart_download.utils.tk_helpers"]

        import smart_download.utils.tk_helpers as helpers2

        # Verify it reuses the exact same queue instance
        self.assertIs(helpers2._BG_TK_CALLBACK_QUEUE, initial_queue)
        self.assertIs(getattr(tk.Misc, "_sd_bg_callback_queue", None), initial_queue)

        # Enqueue more from background thread using new module's patched methods
        def bg_work_2():
            self.root.after(0, lambda: results.append("bg_after_2"))
            self.root.after_idle(lambda: results.append("bg_idle_2"))

        t2 = threading.Thread(target=bg_work_2)
        t2.start()
        t2.join()

        # Now drain from main thread
        helpers2._drain_bg_tk_callbacks()
        self.assertEqual(results, ["bg_after_1", "bg_idle_1", "bg_after_2", "bg_idle_2"])

    def test_safe_after_idle_background_thread(self):
        """
        Verify that after_idle called from a background thread returns 'bg_queued_idle'
        instead of invoking Tcl directly and crashing with Tcl_AsyncDelete.
        """
        import smart_download.utils.tk_helpers as helpers
        executed = []

        def bg_task():
            res = self.root.after_idle(lambda x: executed.append(x), "hello_idle")
            self.assertEqual(res, "bg_queued_idle")

        t = threading.Thread(target=bg_task)
        t.start()
        t.join()

        self.assertEqual(executed, [])
        helpers._drain_bg_tk_callbacks()
        self.assertEqual(executed, ["hello_idle"])

    def test_complete_removal_of_fake_preview(self):
        """
        Verify that VideoPreviewModal and preview_service.py are completely removed
        and no dead imports or preview buttons remain in modals or toolbars.
        """
        with self.assertRaises((ImportError, ModuleNotFoundError)):
            import smart_download.ui.modals.video_preview_modal  # type: ignore

        with self.assertRaises((ImportError, ModuleNotFoundError)):
            import smart_download.services.preview_service  # type: ignore

        import smart_download.ui.modals as modals
        self.assertFalse(hasattr(modals, "VideoPreviewModal"))

        # Verify QualitySelectionModal has no preview button or method
        self.assertFalse(hasattr(QualitySelectionModal, "_open_live_preview"))
        self.assertFalse(hasattr(QualitySelectionModal, "_open_preview"))

        # Verify MediaOptionsBarMixin has no preview button or method
        self.assertFalse(hasattr(MediaOptionsBarMixin, "_open_media_preview"))
        self.assertFalse(hasattr(MediaOptionsBarMixin, "_on_media_bar_preview_click"))

    def test_instant_window_transitions(self):
        """
        Verify that animate_window_open and animate_window_close execute instantly
        without multi-step alpha animation delays.
        """
        top = tk.Toplevel(self.root)
        top.withdraw()

        animate_window_open(top)
        self.root.update()

        closed = False
        def on_done():
            nonlocal closed
            closed = True

        animate_window_close(top, on_done=on_done)
        self.assertTrue(closed)

    def test_fetching_toast_cancel_and_close(self):
        """
        Verify that FetchingLinkToast immediately dismisses upon Cancel or close.
        """
        cancelled = False
        toast = FetchingLinkToast(
            parent=self.root,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            theme={},
            on_cancel=lambda: globals().update(cancelled=True)
        )
        self.root.update()
        self.assertTrue(toast.winfo_exists())

        # Test cancel click
        toast._on_cancel_click()
        self.root.update()
        self.assertFalse(toast.winfo_exists())

    def test_quality_modal_cancel_clean(self):
        """
        Verify QualitySelectionModal Cancel button closes immediately.
        """
        fake_opt = VideoFormatOption(
            format_id="1080p",
            resolution_label="1080p",
            height=1080,
            ext="mp4",
            filesize_approx=12345678
        )
        theme = {
            "c_bg": "#0f172a",
            "c_panel": "#1e293b",
            "c_panel_light": "#334155",
            "c_border": "#475569",
            "c_accent": "#38bdf8",
            "c_accent_dark": "#0284c7",
            "c_success": "#10b981",
            "c_danger": "#ef4444",
            "c_text_bright": "#f8fafc",
            "c_text_muted": "#94a3b8",
            "c_input_bg": "#090d16"
        }
        cancelled = False
        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Rick Astley - Test",
            duration=212,
            options=[fake_opt],
            default_dest_path="dummy.mp4",
            theme=theme,
            on_confirm=lambda opt, dest: None,
            on_cancel=lambda: globals().update(cancelled=True)
        )
        self.root.update()
        self.assertTrue(modal.winfo_exists())

        modal._on_close()
        self.root.update()
        self.assertFalse(modal.winfo_exists())

    def test_history_redownload_different_quality_googlevideo_protection(self):
        """
        Verify that clicking Redownload with Different Quality on an expired
        googlevideo.com link detects the expired temporary URL and safely aborts
        with user feedback instead of hanging or crashing.
        """
        class DummyApp(HistoryPanelMixin):
            def __init__(self, root):
                self.root = root
                self.tree_history = ttk.Treeview(root)
                self.history_manager = DownloadHistoryManager(history_file=os.path.join(_sd_test_cfg, "history.json"))
                self.c_panel = "#1e293b"
                self.c_text_bright = "#ffffff"
                self.c_accent_dark = "#0284c7"
                self.error_dialog_shown = False
                self._build_history_context_menu()

            def show_error_dialog(self, title, msg):
                self.error_dialog_shown = True

            def _refresh_history_table(self):
                pass

        app = DummyApp(self.root)
        expired_url = "https://rr3---sn-4g5edn6s.googlevideo.com/videoplayback?expire=100000"
        entry = app.history_manager.add_or_update_entry(url=expired_url, file_path="old.mp4", size_bytes=1000, status="Completed")

        # Select the item
        entry_id = entry["id"]
        app.tree_history.insert("", "end", iid=entry_id, values=("Video", "old.mp4", "1 KB", "Completed", "date", "path"))
        app.tree_history.selection_set(entry_id)

        # Trigger redownload different quality
        app._redownload_different_quality()
        self.assertTrue(app.error_dialog_shown)

    def test_multithreading_connection_counts(self):
        """
        Verify that max_connections=4 and max_connections=8 are preserved without clamps.
        """
        for conn in (4, 8):
            engine = TurboDownloadEngine(
                url="https://example.com/testfile.zip",
                destination_path=os.path.join(_sd_test_cfg, f"test_{conn}.zip"),
                max_connections=conn
            )
            self.assertEqual(engine.max_connections, conn)

            stream_info = YouTubeStreamInfo(
                video_id="test_vid",
                title="Test Video",
                clean_filename="test.mp4",
                is_progressive=False,
                video_url="https://example.com/video.mp4",
                audio_url="https://example.com/audio.m4a"
            )
            coord = StreamDownloadCoordinator(
                stream_info=stream_info,
                destination_path=os.path.join(_sd_test_cfg, f"coord_{conn}.mp4"),
                max_connections=conn
            )
            self.assertEqual(coord.max_connections, conn)


if __name__ == "__main__":
    unittest.main()
