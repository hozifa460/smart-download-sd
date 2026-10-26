"""
Live Tkinter GUI Verification for Stage 8.2 UX & Window Lifecycle Overhaul.
Boots real tk.Tk() instances on Windows to verify:
1. FetchingLinkToast cancellation stops background resolution & prevents re-open loops.
2. QualitySelectionModal close/cancel dismisses URL and stops clipboard loops.
3. Interactive subtitle mode radio buttons switch modes and auto-select real subtitle track.
4. Temporary -topmost elevation releases to 0/False after 250ms across modals.
"""
import os
import sys
import time
import unittest
import tkinter as tk
from unittest.mock import patch

from smart_download.ui.main_window import ModernFramelessGUI
from smart_download.ui.modals.quality_modal import QualitySelectionModal
from smart_download.ui.modals.confirm_modal import DownloadConfirmationModal
from smart_download.ui.modals.refresh_modal import RefreshLinkModal
from smart_download.ui.modals.update_modal import AppUpdateModal
from smart_download.ui.modals.candidates_modal import MultipleCandidatesModal
from smart_download.ui.components.base_modal import SafeModalDialog
from smart_download.services.youtube_models import VideoFormatOption
from smart_download.services.youtube_tracks import extract_audio_tracks, extract_subtitle_tracks


class TestStage82LiveUX(unittest.TestCase):
    """End-to-end live Tkinter UX test suite executing real GUI widgets."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.gui = ModernFramelessGUI(self.root)
        self.root.update()

    def tearDown(self):
        try:
            self.gui._cleanup_resources()
        except Exception:
            pass
        try:
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_cancel_fetching_toast_stops_resolution_and_no_reopen(self):
        """1. Cancel on FetchingLinkToast stops resolution & does NOT re-open loop."""
        url = "https://www.youtube.com/watch?v=live_test_toast_cancel_82"
        detected_urls = []
        self.gui._on_clipboard_url_detected = lambda u: detected_urls.append(u)

        # Trigger YouTube download flow which shows FetchingLinkToast
        self.gui._start_youtube_download(url, "test_output.mp4")
        self.root.update()

        toast = getattr(self.gui, "_fetching_toast", None)
        self.assertIsNotNone(toast, "FetchingLinkToast must be created and active")
        self.assertTrue(toast.winfo_exists())

        # Click Cancel on the toast
        toast._on_cancel_click()
        self.root.update()

        # Check cancel events
        self.assertTrue(self.gui._yt_cancel_event.is_set(), "_yt_cancel_event must be set on toast cancel")
        self.assertTrue(self.gui._fetch_cancel_event.is_set(), "_fetch_cancel_event must be set on toast cancel")
        self.assertIsNone(getattr(self.gui, "_fetching_toast", None), "Fetching toast must be destroyed/cleared")

        # Simulate clipboard polling 3 times with same URL in clipboard
        with patch("smart_download.ui.controllers.clipboard_controller.get_clipboard_text", return_value=url):
            for _ in range(3):
                self.gui._check_clipboard_now(force=False)
                self.root.update()

        self.assertEqual(len(detected_urls), 0, "Cancelled URL must NOT re-trigger clipboard detection")
        self.assertIsNone(getattr(self.gui, "_fetching_toast", None), "Toast must NOT re-open")
        self.assertIsNone(getattr(self.gui, "_quality_modal", None), "Quality modal must NOT open after cancel")

    def test_cancel_quality_modal_no_reopen_loop(self):
        """2. Cancel / Close on QualitySelectionModal does NOT re-trigger clipboard loop."""
        url = "https://www.youtube.com/watch?v=live_test_modal_cancel_82"
        detected_urls = []
        self.gui._on_clipboard_url_detected = lambda u: detected_urls.append(u)

        sample_info = {
            "title": "Stage 8.2 Live UX Test Video",
            "duration": 180,
            "formats": [{"format_id": "18", "ext": "mp4", "width": 640, "height": 360, "vcodec": "avc1", "acodec": "mp4a"}],
            "subtitles": {"en": [{"url": "https://example.com/en.vtt", "ext": "vtt"}]},
        }
        audio_tracks = extract_audio_tracks(sample_info)
        subtitle_tracks = extract_subtitle_tracks(sample_info)
        opt = VideoFormatOption(
            format_id="18",
            resolution_label="360p",
            height=360,
            ext="mp4",
            filesize_approx=1024 * 1024,
            fps=30,
            vcodec="avc1",
            acodec="mp4a",
            note="Test"
        )

        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Stage 8.2 Live UX Test Video",
            duration=180,
            options=[opt],
            default_dest_path="test_video.mp4",
            theme=self.gui._theme_dict(),
            on_confirm=lambda opt, dest: None,
            on_cancel=None,
            parent_app=self.gui,
            audio_tracks=audio_tracks,
            subtitle_tracks=subtitle_tracks
        )
        self.gui._quality_modal = modal
        self.root.update()

        # Modal is open and active
        self.assertTrue(modal.winfo_exists())

        # User closes the modal via X / Cancel
        modal._on_close()
        self.root.update()

        self.assertIsNone(getattr(self.gui, "_quality_modal", None), "Quality modal reference must be None")

        # Now simulate 3 clipboard ticks with the same URL still in Windows clipboard
        with patch("smart_download.ui.controllers.clipboard_controller.get_clipboard_text", return_value=url):
            for _ in range(3):
                self.gui._check_clipboard_now(force=False)
                self.root.update()

        self.assertEqual(len(detected_urls), 0, "Closed quality modal must NOT cause infinite re-open loop")
        self.assertIsNone(getattr(self.gui, "_quality_modal", None), "Quality modal must remain None")

    def test_interactive_selection_of_all_three_subtitle_modes(self):
        """3. Interactive selection of all 3 subtitle modes (srt_only, hard_burn, soft_embed) + smart auto-select."""
        sample_info = {
            "title": "Subtitle Mode Test Video",
            "duration": 240,
            "subtitles": {
                "en": [{"url": "https://example.com/en.vtt", "ext": "vtt"}],
                "ar": [{"url": "https://example.com/ar.vtt", "ext": "vtt"}]
            }
        }
        audio_tracks = extract_audio_tracks(sample_info)
        subtitle_tracks = extract_subtitle_tracks(sample_info)

        opt = VideoFormatOption(
            format_id="22",
            resolution_label="720p",
            height=720,
            ext="mp4",
            filesize_approx=5 * 1024 * 1024,
            fps=30,
            vcodec="avc1",
            acodec="mp4a",
            note="HD"
        )

        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Subtitle Mode Test Video",
            duration=240,
            options=[opt],
            default_dest_path="test_sub.mp4",
            theme=self.gui._theme_dict(),
            on_confirm=lambda opt, dest: None,
            parent_app=self.gui,
            audio_tracks=audio_tracks,
            subtitle_tracks=subtitle_tracks
        )
        self.root.update()

        cb_sub = modal.cb_sub
        self.assertIsNotNone(cb_sub, "Subtitle dropdown must be present")
        self.assertTrue(hasattr(cb_sub, "_mode_radios"), "Mode radio buttons must be attached to cb_sub")
        self.assertEqual(len(cb_sub._mode_radios), 3, "There must be exactly 3 subtitle mode radio buttons")

        # Initially, subtitle combobox is at index 0 ('None / بدون ترجمة')
        self.assertEqual(cb_sub.current(), 0)

        # Map radio buttons by their value
        radios = {r.cget("value"): r for r in cb_sub._mode_radios}

        # 1. Click 'srt_only' radio button
        radios["srt_only"].invoke()
        self.root.update()
        self.assertEqual(cb_sub.get_selected_mode(), "srt_only")
        # Smart Auto-Select UX: must have advanced past 'none' (index 0) to index 1!
        self.assertGreater(cb_sub.current(), 0, "Clicking subtitle mode must auto-select first subtitle track")
        modal._attach_selected_tracks()
        self.assertEqual(modal.selected_option.subtitle_embed_mode, "srt_only")
        self.assertIsNotNone(modal.selected_option.selected_subtitle_track)
        self.assertNotEqual(modal.selected_option.selected_subtitle_track.get("sub_id"), "none")

        # 2. Click 'hard_burn' radio button
        radios["hard_burn"].invoke()
        self.root.update()
        self.assertEqual(cb_sub.get_selected_mode(), "hard_burn")
        modal._attach_selected_tracks()
        self.assertEqual(modal.selected_option.subtitle_embed_mode, "hard_burn")

        # 3. Click 'soft_embed' radio button
        radios["soft_embed"].invoke()
        self.root.update()
        self.assertEqual(cb_sub.get_selected_mode(), "soft_embed")
        modal._attach_selected_tracks()
        self.assertEqual(modal.selected_option.subtitle_embed_mode, "soft_embed")

        # Cleanup
        modal.destroy()

    def test_topmost_release_check(self):
        """4. Verifies that after 250ms, QualitySelectionModal and other modals release -topmost to 0/False."""
        opt = VideoFormatOption(
            format_id="18",
            resolution_label="360p",
            height=360,
            ext="mp4",
            filesize_approx=1024,
            fps=30,
            vcodec="avc1",
            acodec="mp4a",
            note=""
        )

        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Topmost Test",
            duration=60,
            options=[opt],
            default_dest_path="topmost.mp4",
            theme=self.gui._theme_dict(),
            on_confirm=lambda o, d: None,
            parent_app=self.gui
        )
        self.root.update()

        # Initially -topmost is True
        initial_topmost = bool(modal.attributes("-topmost"))
        self.assertTrue(initial_topmost, "Modal must initially be topmost to appear above main window")

        # Wait 300ms for scheduled timer to release -topmost
        time.sleep(0.35)
        self.root.update()

        released_topmost = bool(modal.attributes("-topmost"))
        self.assertFalse(released_topmost, "Modal must release -topmost after 250ms to prevent window trapping")
        modal.destroy()

    def test_download_confirm_modal_topmost_release(self):
        """Verify DownloadConfirmationModal also releases -topmost after 250ms."""
        cmodal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/topmost_test.zip",
            default_dest_path="topmost_test.zip",
            theme=self.gui._theme_dict(),
            parent_app=self.gui
        )
        self.root.update()
        initial_topmost = bool(cmodal.attributes("-topmost"))
        self.assertTrue(initial_topmost)

        time.sleep(0.35)
        self.root.update()
        self.assertFalse(bool(cmodal.attributes("-topmost")), "DownloadConfirmationModal must release -topmost")
        cmodal.destroy()

    def test_cancel_async_resolver_stops_worker_and_no_dialog(self):
        """5. Cancelling FetchingLinkToast during _resolve_real_url_async aborts completion."""
        url = "https://example.com/slow_probe_page.html"
        resolved_called = []

        def mock_slow_resolve(u, **kw):
            time.sleep(0.2)
            return {"url": u, "candidates": [{"url": "https://example.com/file.zip"}], "is_html": True, "resolved": True}

        with patch("smart_download.ui.controllers.clipboard_controller.resolve_real_download_url", side_effect=mock_slow_resolve):
            self.gui._resolve_real_url_async(url, on_resolved=lambda info: resolved_called.append(info), show_toast=True)
            self.root.update()

            toast = getattr(self.gui, "_fetching_toast", None)
            self.assertIsNotNone(toast, "Fetching toast must appear during async probe")
            toast._on_cancel_click()
            self.root.update()

            self.assertTrue(self.gui._fetch_cancel_event.is_set())
            time.sleep(0.3)
            self.gui._drain_dispatch_queue()
            self.root.update()

            self.assertEqual(len(resolved_called), 0, "Cancelled async probe must NEVER invoke on_resolved")
            self.assertIsNone(getattr(self.gui, "_confirm_modal", None))

    def test_main_btn_cancel_aborts_fetching_and_resets_events(self):
        """6. Clicking main window btn_cancel aborts ongoing fetch operations."""
        url = "https://www.youtube.com/watch?v=live_test_btn_cancel"
        self.gui._start_youtube_download(url, "test.mp4")
        self.root.update()

        toast = getattr(self.gui, "_fetching_toast", None)
        self.assertIsNotNone(toast)

        self.gui._on_cancel_download()
        self.root.update()

        self.assertTrue(self.gui._yt_cancel_event.is_set(), "_yt_cancel_event must be set by _on_cancel_download")
        self.assertTrue(self.gui._fetch_cancel_event.is_set(), "_fetch_cancel_event must be set by _on_cancel_download")
        self.assertIsNone(getattr(self.gui, "_fetching_toast", None))

    def test_force_clipboard_check_processes_even_if_previously_dismissed(self):
        """7. _check_clipboard_now(force=True) re-processes URL even after dismissal."""
        url = "https://example.com/force_test.zip"
        detected = []
        self.gui._on_clipboard_url_detected = lambda u: detected.append(u)

        with patch("smart_download.ui.controllers.clipboard_controller.get_clipboard_text", return_value=url):
            self.gui.clear_last_clipboard_url(url)
            self.gui._check_clipboard_now(force=False)
            self.root.update()
            self.assertEqual(len(detected), 0, "Unforced check on dismissed URL must NOT trigger")

            self.gui._check_clipboard_now(force=True)
            self.root.update()
            self.assertEqual(len(detected), 1, "Forced check on dismissed URL MUST trigger")

    def test_mode_var_programmatic_set_syncs_with_combobox(self):
        """8. Programmatic mode_var.set() updates cb_sub._selected_mode and cb_sub_mode."""
        sample_info = {
            "title": "Sub Trace Video",
            "duration": 60,
            "subtitles": {"en": [{"url": "https://example.com/en.vtt", "ext": "vtt"}]}
        }
        audio_tracks = extract_audio_tracks(sample_info)
        subtitle_tracks = extract_subtitle_tracks(sample_info)
        opt = VideoFormatOption(format_id="18", resolution_label="360p", height=360, ext="mp4", filesize_approx=1024, fps=30, vcodec="avc1", acodec="mp4a", note="")

        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Sub Trace Video",
            duration=60,
            options=[opt],
            default_dest_path="sub.mp4",
            theme=self.gui._theme_dict(),
            on_confirm=lambda o, d: None,
            parent_app=self.gui,
            audio_tracks=audio_tracks,
            subtitle_tracks=subtitle_tracks
        )
        self.root.update()

        cb_sub = modal.cb_sub
        self.assertIsNotNone(cb_sub)
        cb_sub._mode_var.set("srt_only")
        self.root.update()
        self.assertEqual(cb_sub.get_selected_mode(), "srt_only")
        self.assertEqual(cb_sub._mode_combobox.current(), 1)

        cb_sub._mode_var.set("hard_burn")
        self.root.update()
        self.assertEqual(cb_sub.get_selected_mode(), "hard_burn")
        self.assertEqual(cb_sub._mode_combobox.current(), 2)
        modal.destroy()

    def test_candidates_modal_clean_destroy_and_modal_guard(self):
        """9. MultipleCandidatesModal acts as active modal and resets reference on destroy."""
        cands = [
            {"url": "https://example.com/file1.zip", "label": "File 1", "filename": "file1.zip"},
            {"url": "https://example.com/file2.zip", "label": "File 2", "filename": "file2.zip"},
        ]
        modal = MultipleCandidatesModal(
            parent=self.root,
            source_url="https://example.com/landing",
            candidates=cands,
            page_title="Candidates Test",
            theme=self.gui._theme_dict(),
            parent_app=self.gui
        )
        self.gui._candidates_modal = modal
        self.root.update()
        self.assertTrue(modal.winfo_exists())

        # With candidates modal open, check clipboard polling does not trigger
        detected = []
        self.gui._on_clipboard_url_detected = lambda u: detected.append(u)
        with patch("smart_download.ui.controllers.clipboard_controller.get_clipboard_text", return_value="https://example.com/other.zip"):
            self.gui._check_clipboard_now(force=False)
            self.root.update()
        self.assertEqual(len(detected), 0, "Active candidates modal must guard clipboard polling")

        modal.destroy()
        self.root.update()
        self.assertIsNone(getattr(self.gui, "_candidates_modal", None))


if __name__ == "__main__":
    unittest.main()
