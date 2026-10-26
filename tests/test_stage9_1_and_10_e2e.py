"""
Comprehensive Unit & E2E Verification for Smart Download Stages 9.1 & 10.
Covers:
1. YouTube Multi-threading Lock Removal (Dynamic splitting, max_connections retention, no clamp).
2. Clean Original URL Preservation & Instant 0ms Quality Re-selection Cache.
3. 100% Instant Cancel Across All Phases (Download, Merge, Subtitle Burn-in, and UI Metrics Reset).
4. Modernized 2-Row Toolbar & Window Animations.
5. Live Video, Dubbing & Subtitle Preview Player (PreviewSession, SRT parsing, VideoPreviewModal).
"""
import os
import time
import shutil
import unittest
import threading
from unittest.mock import MagicMock, patch

import tkinter as tk

from smart_download.core.engine import TurboDownloadEngine
from smart_download.core.stream_coordinator import StreamDownloadCoordinator
from smart_download.services.youtube_models import YouTubeStreamInfo, VideoFormatOption
from smart_download.services.youtube_service import YouTubeResolver
from smart_download.services.subtitle_processor import embed_subtitle_into_mp4, burn_subtitle_into_video
from smart_download.services.preview_service import (
    SubtitleCue,
    parse_srt_cues,
    fetch_cues_for_track,
    PreviewSession,
)
from smart_download.ui.panels.media_options_bar import MediaOptionsBarMixin
from smart_download.ui.modals.video_preview_modal import VideoPreviewModal


class TestStage9_1_And_10_Verification(unittest.TestCase):
    """Test suite verifying all Stage 9.1 and 10 enhancements."""

    def test_youtube_multithreading_no_locks(self):
        """Verify that googlevideo URLs maintain multi-threading and dynamic chunk splitting."""
        yt_url = "https://rr3---sn-4g5edn6s.googlevideo.com/videoplayback?expire=12345"
        engine = TurboDownloadEngine(
            url=yt_url,
            destination_path="dummy_video.mp4",
            max_connections=8,
            allow_dynamic_split=True
        )

        # 1. Engine should not clamp max_connections to 1 for googlevideo
        self.assertEqual(engine.max_connections, 8)
        self.assertTrue(engine.allow_dynamic_split)
        self.assertTrue(engine.is_googlevideo)

        # 2. Resumer update_url should not clamp connections or disable dynamic split
        new_yt_url = "https://rr1---sn-4g5edn6s.googlevideo.com/videoplayback?expire=67890"
        engine.update_url(new_yt_url)
        self.assertEqual(engine.max_connections, 8)
        self.assertTrue(engine.allow_dynamic_split)

        # 3. Dynamic split check should not be rejected because of is_googlevideo
        self.assertTrue(engine.allow_dynamic_split)
        self.assertFalse(engine.max_connections == 1)

    def test_stream_coordinator_multithreading_and_clean_url(self):
        """Verify StreamDownloadCoordinator assigns multi-thread connections and exposes clean URL."""
        v_url = "https://rr1---sn.googlevideo.com/videoplayback?itag=137"
        a_url = "https://rr1---sn.googlevideo.com/videoplayback?itag=140"
        orig_yt = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        stream_info = YouTubeStreamInfo(
            video_id="dQw4w9WgXcQ",
            title="Rick Roll",
            clean_filename="Rick Roll.mp4",
            is_progressive=False,
            video_url=v_url,
            audio_url=a_url,
            webpage_url=orig_yt
        )

        coordinator = StreamDownloadCoordinator(
            stream_info=stream_info,
            destination_path="rick_roll.mp4",
            max_connections=8
        )

        # 1. Verify clean URL is exposed, not CDN url
        self.assertEqual(coordinator.url, orig_yt)

        # 2. Verify coordinator keeps max_connections = 8 without clamping
        self.assertEqual(coordinator.max_connections, 8)

    def test_media_context_cache_and_instant_reopen(self):
        """Verify _get_cached_media_context and _cache_media_context for 0ms instant quality reopen."""
        bar = MediaOptionsBarMixin()
        bar._media_context_cache = {}

        yt_url = "https://www.youtube.com/watch?v=ABC12345678"
        fake_opt = VideoFormatOption(
            format_id="137",
            resolution_label="1080p",
            height=1080,
            ext="mp4",
            filesize_approx=50000000,
            video_url="https://fake.googlevideo.com/v"
        )
        fake_context = {
            "url": yt_url,
            "info": {"id": "ABC12345678", "title": "Test Video", "duration": 180},
            "options": [fake_opt],
            "audio_tracks": [{"id": "en", "label": "English"}],
            "subtitle_tracks": [{"id": "ar", "label": "Arabic"}],
            "selected_option": fake_opt,
            "final_dest": "test_video.mp4"
        }

        # Cache it
        bar._cache_media_context(yt_url, fake_context)

        # 1. Exact URL lookup
        found = bar._get_cached_media_context(yt_url)
        self.assertIsNotNone(found)
        self.assertEqual(found["info"]["title"], "Test Video")

        # 2. URL with extra query params should still match
        found_with_extra = bar._get_cached_media_context(f"{yt_url}&feature=shared")
        self.assertIsNotNone(found_with_extra)
        self.assertEqual(found_with_extra["info"]["id"], "ABC12345678")

        # 3. Short youtu.be URL lookup
        short_url = "https://youtu.be/ABC12345678"
        found_short = bar._get_cached_media_context(short_url)
        self.assertIsNotNone(found_short)

    def test_instant_cancel_across_all_phases(self):
        """Verify cancel kills active subprocesses in merge, subtitles, and coordinator."""
        cancel_ev = threading.Event()

        # 1. Coordinator cancellation with active subprocess
        stream_info = YouTubeStreamInfo(
            video_id="cancel123",
            title="Cancel Test",
            clean_filename="cancel_test.mp4",
            is_progressive=False,
            video_url="https://fake.url/v",
            audio_url="https://fake.url/a",
            webpage_url="https://youtube.com/watch?v=cancel123"
        )
        coordinator = StreamDownloadCoordinator(
            stream_info=stream_info,
            destination_path="cancel_test.mp4"
        )

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        coordinator._active_subproc = mock_proc

        coordinator.cancel()
        self.assertTrue(coordinator._cancel_event.is_set())
        mock_proc.kill.assert_called_once()
        self.assertIsNone(coordinator._active_subproc)

        # 2. Pre-cancelled merge aborts immediately
        cancel_ev.set()
        res = YouTubeResolver.merge_video_audio(
            "dummy_v.mp4", "dummy_a.mp4", "dummy_out.mp4",
            cancel_event=cancel_ev
        )
        self.assertFalse(res)

        # 3. Pre-cancelled subtitle muxing aborts immediately
        sub_res = embed_subtitle_into_mp4(
            "dummy_v.mp4", "dummy_sub.srt", "en", "ffmpeg",
            cancel_event=cancel_ev
        )
        self.assertFalse(sub_res)

        burn_res = burn_subtitle_into_video(
            "dummy_v.mp4", "dummy_sub.srt", "ffmpeg",
            cancel_event=cancel_ev
        )
        self.assertFalse(burn_res)

    def test_srt_parsing_and_preview_session(self):
        """Verify SRT cue extraction and PreviewSession seeking / subtitle tracking."""
        sample_srt = """1
00:00:01,000 --> 00:00:03,500
Hello, welcome to Smart Download!

2
00:00:04,200 --> 00:00:07,000
<b>High-Speed Multi-Threading</b> in Action.

3
00:00:08,000 --> 00:00:10,000
Enjoy downloading!
"""
        cues = parse_srt_cues(sample_srt)
        self.assertEqual(len(cues), 3)

        # Check first cue
        self.assertAlmostEqual(cues[0].start_sec, 1.0)
        self.assertAlmostEqual(cues[0].end_sec, 3.5)
        self.assertEqual(cues[0].text, "Hello, welcome to Smart Download!")

        # Check second cue (HTML tags stripped)
        self.assertAlmostEqual(cues[1].start_sec, 4.2)
        self.assertAlmostEqual(cues[1].end_sec, 7.0)
        self.assertEqual(cues[1].text, "High-Speed Multi-Threading in Action.")

        # Test PreviewSession
        updates = []

        def on_time(t, cue):
            updates.append((t, cue))

        session = PreviewSession(
            duration=30.0,
            cues=cues,
            on_time_update=on_time,
            use_ffplay=False  # Headless test
        )

        # Query active subtitle at specific times
        self.assertEqual(session.get_active_subtitle(0.5), "")
        self.assertEqual(session.get_active_subtitle(2.0), "Hello, welcome to Smart Download!")
        self.assertEqual(session.get_active_subtitle(3.8), "")
        self.assertEqual(session.get_active_subtitle(5.0), "High-Speed Multi-Threading in Action.")
        self.assertEqual(session.get_active_subtitle(9.0), "Enjoy downloading!")
        self.assertEqual(session.get_active_subtitle(15.0), "")

        # Seek test
        session.seek_to(5.0)
        self.assertEqual(session.current_time, 5.0)
        self.assertEqual(session.get_active_subtitle(), "High-Speed Multi-Threading in Action.")

        # Seek relative
        session.seek(4.0)  # 5.0 + 4.0 = 9.0
        self.assertEqual(session.current_time, 9.0)
        self.assertEqual(session.get_active_subtitle(), "Enjoy downloading!")

        session.stop()
        self.assertEqual(session.current_time, 0.0)
        self.assertFalse(session.is_playing)

    def test_video_preview_modal_instantiation(self):
        """Verify VideoPreviewModal initializes safely with widgets, badges, and clean teardown."""
        root = tk.Tk()
        root.withdraw()
        try:
            cues = [
                SubtitleCue(start_sec=0.0, end_sec=5.0, text="First subtitle cue"),
                SubtitleCue(start_sec=6.0, end_sec=10.0, text="Second subtitle cue")
            ]
            fake_opt = VideoFormatOption(
                format_id="1080p",
                resolution_label="1080p",
                height=1080,
                ext="mp4",
                filesize_approx=12345678
            )
            download_called = False

            def on_dl():
                nonlocal download_called
                download_called = True

            modal = VideoPreviewModal(
                parent=root,
                video_title="Unit Test Video Preview",
                duration=60,
                media_url="",
                selected_option=fake_opt,
                selected_audio={"label": "English Audio"},
                selected_subtitle={"label": "English Subtitles"},
                cues=cues,
                use_ffplay=False,
                on_download_now=on_dl
            )

            # Check widgets exist
            self.assertTrue(modal.winfo_exists())
            self.assertIsNotNone(modal.scale_seek)
            self.assertIsNotNone(modal.lbl_subtitle_cue)
            self.assertIsNotNone(modal.btn_play_pause)
            self.assertIsNotNone(modal.btn_dl_now)

            # Test seek and cue update
            modal.session.seek_to(2.0)
            modal.update_idletasks()
            self.assertEqual(modal.session.get_active_subtitle(), "First subtitle cue")

            # Test download trigger
            modal._on_download_now()
            for _ in range(15):
                root.update()
                time.sleep(0.015)
            self.assertTrue(download_called)

        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_merge_video_audio_pipe_deadlock_free(self):
        """Verify merge_video_audio handles subprocess.TimeoutExpired without deadlocking on pipes."""
        import subprocess
        cancel_ev = threading.Event()
        mock_proc = MagicMock()
        # Simulate 2 timeouts followed by successful finish
        mock_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="ffmpeg", timeout=0.05),
            subprocess.TimeoutExpired(cmd="ffmpeg", timeout=0.05),
            ("", "")
        ]
        mock_proc.returncode = 0

        with patch("smart_download.services.youtube_service.find_ffmpeg_bin", return_value="fake_ffmpeg"):
            with patch("subprocess.Popen", return_value=mock_proc):
                with patch("os.path.exists", return_value=True):
                    with patch("os.path.getsize", return_value=1024):
                        res = YouTubeResolver.merge_video_audio(
                            "dummy_v.mp4", "dummy_a.mp4", "dummy_out.mp4",
                            cancel_event=cancel_ev
                        )
                        self.assertTrue(res)
                        self.assertEqual(mock_proc.communicate.call_count, 3)

    def test_download_controller_cancel_with_dummy_ui(self):
        """Verify _on_cancel_download executes without AttributeError on partial/dummy UI objects."""
        from smart_download.ui.main_window import ModernFramelessGUI

        class MinimalDummyUI:
            def __init__(self):
                self._yt_cancel_event = threading.Event()
                self.engine = None
                self.btn_start = MagicMock()
                self.btn_pause = MagicMock()
                self.btn_cancel = MagicMock()
                self.logs = []
            def log(self, m):
                self.logs.append(m)

        dummy = MinimalDummyUI()
        ModernFramelessGUI._on_cancel_download(dummy)
        self.assertTrue(dummy._yt_cancel_event.is_set())
        dummy.btn_start.configure.assert_called_with(state="normal")
        dummy.btn_cancel.configure.assert_called_with(state="disabled")

    def test_animate_window_fallback_in_test_env(self):
        """Verify animate_window_open and animate_window_close execute callbacks synchronously in test env."""
        from smart_download.utils.tk_helpers import animate_window_open, animate_window_close
        mock_win = MagicMock()
        mock_win.winfo_exists.return_value = True

        animate_window_open(mock_win)
        mock_win.wm_attributes.assert_called_with("-alpha", 1.0)
        # after should not be called to avoid invalid command name Tcl timers
        mock_win.after.assert_not_called()

        closed = False
        def on_done():
            nonlocal closed
            closed = True

        animate_window_close(mock_win, on_done=on_done)
        self.assertTrue(closed)
        mock_win.after.assert_not_called()


if __name__ == "__main__":
    unittest.main()
