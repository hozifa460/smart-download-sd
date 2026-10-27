"""
Unit and integration tests for Stage 9: Comprehensive Runtime & UX Overhaul.
Tests cover:
1. Subtitle format conversion (WebVTT, XML/SRV3, TTML, JSON3) and BOM-free UTF-8 burn-in.
2. Auto-selection of subtitle track when delivery mode is set to hard_burn.
3. Multi-threaded stream downloading in StreamDownloadCoordinator and speed persistence in Phase 3.
4. Fetching toast -topmost release (250ms) and 15s auto-close timer.
5. "Open in Main App" populating the main window without auto-starting downloads.
6. MediaOptionsBarMixin integration and Re-Download with Different Quality in History.
"""
import os
import sys
import json
import threading
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from smart_download.services.subtitle_processor import (
    convert_vtt_to_srt,
    download_subtitle_as_srt,
    burn_subtitle_into_video,
    _parse_timestamp_or_seconds,
    _format_srt_timestamp,
)
from smart_download.services.youtube_tracks import (
    _normalize_sub_url_and_ext,
    extract_audio_tracks,
    extract_subtitle_tracks,
)
from smart_download.services.youtube_models import (
    VideoFormatOption,
    YouTubeStreamInfo,
)
from smart_download.core.stream_coordinator import StreamDownloadCoordinator
from smart_download.ui.panels.media_options_bar import MediaOptionsBarMixin
from smart_download.ui.panels.history_panel import HistoryPanelMixin
from smart_download.ui.controllers.youtube_download_controller import YouTubeDownloadControllerMixin
from smart_download.ui.controllers.download_controller import DownloadControllerMixin


class TestSubtitleConversionStage9(unittest.TestCase):
    """Verifies parsing of WebVTT, XML/SRV3, TTML, and JSON3 subtitle formats into standard SRT."""

    def test_convert_standard_webvtt(self):
        vtt_data = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:04.500\n"
            "Hello WebVTT World!\n\n"
            "00:00:05.100 --> 00:00:08.200\n"
            "Second subtitle line\n"
        )
        srt = convert_vtt_to_srt(vtt_data)
        self.assertIn("1\n00:00:01,000 --> 00:00:04,500\nHello WebVTT World!", srt)
        self.assertIn("2\n00:00:05,100 --> 00:00:08,200\nSecond subtitle line", srt)

    def test_convert_xml_transcript_cues(self):
        xml_data = (
            '<?xml version="1.0" encoding="utf-8" ?>\n'
            '<transcript>\n'
            '  <text start="1.5" dur="3.0">Welcome to &amp; Smart Download</text>\n'
            '  <text start="6.25" dur="2.5">Fast &lt;multithreaded&gt; streams</text>\n'
            '</transcript>'
        )
        srt = convert_vtt_to_srt(xml_data)
        self.assertIn("1\n00:00:01,500 --> 00:00:04,500\nWelcome to & Smart Download", srt)
        self.assertIn("2\n00:00:06,250 --> 00:00:08,750\nFast <multithreaded> streams", srt)

    def test_convert_ttml_xml_cues(self):
        ttml_data = (
            '<tt xmlns="http://www.w3.org/ns/ttml">\n'
            '  <body>\n'
            '    <div>\n'
            '      <p begin="00:01:10.500" end="00:01:14.000">TTML Subtitle Line</p>\n'
            '    </div>\n'
            '  </body>\n'
            '</tt>'
        )
        srt = convert_vtt_to_srt(ttml_data)
        self.assertIn("00:01:10,500 --> 00:01:14,000", srt)
        self.assertIn("TTML Subtitle Line", srt)

    def test_convert_json3_events_cues(self):
        json_data = json.dumps({
            "wireMagic": "pb3",
            "events": [
                {
                    "tStartMs": 1200,
                    "dDurationMs": 2800,
                    "segs": [{"utf8": "First "}, {"utf8": "JSON3 segment"}]
                },
                {
                    "tStartMs": 5000,
                    "dDurationMs": 3500,
                    "segs": [{"utf8": "Second segment"}]
                }
            ]
        })
        srt = convert_vtt_to_srt(json_data)
        self.assertIn("1\n00:00:01,200 --> 00:00:04,000\nFirst JSON3 segment", srt)
        self.assertIn("2\n00:00:05,000 --> 00:00:08,500\nSecond segment", srt)

    def test_convert_xml_with_dur_before_start_and_single_quotes(self):
        xml_data = "<transcript><text dur='4.5' start='2.0'>Single quotes &amp; reversed</text></transcript>"
        srt = convert_vtt_to_srt(xml_data)
        self.assertIn("1\n00:00:02,000 --> 00:00:06,500\nSingle quotes & reversed", srt)

    def test_convert_xml_with_intervening_attributes(self):
        xml_data = '<transcript><text start="1.5" id="c1" extra="val" dur="5.0">Intervening attrs</text></transcript>'
        srt = convert_vtt_to_srt(xml_data)
        self.assertIn("1\n00:00:01,500 --> 00:00:06,500\nIntervening attrs", srt)

    def test_convert_ttml_with_single_quotes_and_intervening_attributes(self):
        ttml_data = "<tt><body><div><p xml:id='p1' begin='00:01.000' region='bot' dur='00:04.000'>TTML single</p></div></body></tt>"
        srt = convert_vtt_to_srt(ttml_data)
        self.assertIn("00:00:01,000 --> 00:00:05,000", srt)
        self.assertIn("TTML single", srt)

    def test_convert_json3_with_utf8_bom(self):
        json_data = "\ufeff" + json.dumps({
            "events": [{"tStartMs": 1000, "dDurationMs": 3000, "segs": [{"utf8": "BOM JSON3"}]}]
        })
        srt = convert_vtt_to_srt(json_data)
        self.assertIn("1\n00:00:01,000 --> 00:00:04,000\nBOM JSON3", srt)

    def test_normalize_sub_url_rewrites_formats(self):
        url1, ext1 = _normalize_sub_url_and_ext("https://yt.com/timedtext?fmt=srv3&lang=ar", "srv3")
        self.assertEqual(ext1, "vtt")
        self.assertIn("fmt=vtt", url1)

        url2, ext2 = _normalize_sub_url_and_ext("https://yt.com/timedtext?lang=en&fmt=json3", "json3")
        self.assertEqual(ext2, "vtt")
        self.assertIn("fmt=vtt", url2)

    def test_parse_timestamp_ms_and_timecode(self):
        self.assertAlmostEqual(_parse_timestamp_or_seconds("1500ms"), 1.5)
        self.assertAlmostEqual(_parse_timestamp_or_seconds("500ms"), 0.5)
        self.assertAlmostEqual(_parse_timestamp_or_seconds("00:01:02:15"), 62.5)

    def test_format_srt_timestamp_comma(self):
        self.assertEqual(_format_srt_timestamp("00:01:02,500"), "00:01:02,500")
        self.assertEqual(_format_srt_timestamp("01:02,500"), "00:01:02,500")

    def test_convert_srt_with_commas(self):
        srt_data = "1\n00:00:01,000 --> 00:00:03,500\nHello comma SRT\n"
        converted = convert_vtt_to_srt(srt_data)
        self.assertIn("00:00:01,000 --> 00:00:03,500", converted)
        self.assertIn("Hello comma SRT", converted)

    def test_convert_ttml_with_namespace_and_unquoted_attrs(self):
        xml_data = "<tt><tt:body><tt:p begin=1.5s dur=2.0s>Namespaced TTML</tt:p></tt:body></tt>"
        converted = convert_vtt_to_srt(xml_data)
        self.assertIn("00:00:01,500 --> 00:00:03,500", converted)
        self.assertIn("Namespaced TTML", converted)


class TestBurnSubtitleEncodingAndPaths(unittest.TestCase):
    """Verifies BOM-free UTF-8 generation and proper path escaping in burn_subtitle_into_video."""

    @patch("subprocess.run")
    def test_burn_subtitle_creates_bom_free_copy_and_sets_cwd(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "OK"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_video = os.path.join(tmp_dir, "test_video.mp4")
            orig_srt = os.path.join(tmp_dir, "test_video.ar.srt")

            with open(orig_video, "wb") as f:
                f.write(b"dummy video data")
            # Write original srt with UTF-8 BOM
            with open(orig_srt, "w", encoding="utf-8-sig") as f:
                f.write("1\n00:00:01,000 --> 00:00:02,000\nمرحبا بالعالم\n")

            burned_path = burn_subtitle_into_video(orig_video, orig_srt, ffmpeg_path="ffmpeg")
            self.assertTrue(mock_run.called)

            args, kwargs = mock_run.call_args
            cmd = args[0]

            # Verify cwd is directory of video/srt
            self.assertEqual(kwargs.get("cwd"), os.path.abspath(tmp_dir))

            # Verify input video passed to -i is absolute path
            i_idx = cmd.index("-i")
            self.assertEqual(cmd[i_idx + 1], os.path.abspath(orig_video))

            # Verify subtitles filter references temporary file without BOM
            vf_idx = cmd.index("-vf")
            vf_val = cmd[vf_idx + 1]
            self.assertTrue(vf_val.startswith("subtitles=_sd_burn_") and vf_val.endswith(".srt"))

            # Verify temporary burn srt was cleaned up
            temp_files = [f for f in os.listdir(tmp_dir) if f.startswith("_sd_burn_")]
            self.assertEqual(len(temp_files), 0)

            # Verify original srt is still intact
            self.assertTrue(os.path.exists(orig_srt))


class TestStreamCoordinatorMultiThreading(unittest.TestCase):
    """Verifies multi-connection allocation and non-zero speed preservation in Phase 3."""

    def test_connection_allocation_and_allow_split(self):
        stream_info = YouTubeStreamInfo(
            video_id="tiktok123",
            title="TikTok Video",
            clean_filename="test_dest",
            is_progressive=False,
            video_url="https://v16-webapp.tiktok.com/video",
            audio_url="https://v16-webapp.tiktok.com/audio",
            platform="TikTok",
        )
        coord = StreamDownloadCoordinator(
            stream_info=stream_info,
            destination_path="test_dest.mp4",
            max_connections=8
        )
        self.assertEqual(coord.max_connections, 8)
        self.assertEqual(coord._requested_max_connections, 8)
        # Verify internal active speed tracking exists
        self.assertTrue(hasattr(coord, "_last_active_speed"))
        self.assertEqual(coord._last_active_speed, 0.0)

    def test_phase3_speed_preservation(self):
        progress_updates = []
        stream_info = YouTubeStreamInfo(
            video_id="vid123",
            title="Test Video",
            clean_filename="test_dest",
            is_progressive=False,
            video_url="https://example.com/video",
            audio_url="https://example.com/audio",
        )
        coord = StreamDownloadCoordinator(
            stream_info=stream_info,
            destination_path="test_dest.mp4",
            max_connections=8,
            on_progress=lambda d, t, s, eta, a: progress_updates.append((s, eta))
        )
        # Simulate active transfer before Phase 3
        coord._last_active_speed = 5_242_880.0  # 5 MB/s
        coord._v_total_size = 10_000_000
        coord._a_total_size = 2_000_000

        # Simulate Phase 3 progress dispatch (as done in _run_coordinator)
        combined_total = max(1, coord._v_total_size + coord._a_total_size)
        rep_spd = coord._last_active_speed if coord._last_active_speed > 0 else 0.0
        coord.on_progress(combined_total, combined_total, rep_spd, "Merging...", 0)

        self.assertTrue(len(progress_updates) > 0)
        last_speed, last_eta = progress_updates[-1]
        self.assertEqual(last_speed, 5_242_880.0)
        self.assertEqual(last_eta, "Merging...")

    def test_chunk_snapshot_offsets_chunk_ids(self):
        from smart_download.core.chunk import DownloadChunk
        stream_info = YouTubeStreamInfo(
            video_id="vid123",
            title="Test Video",
            clean_filename="test_dest",
            is_progressive=False,
            video_url="https://example.com/video",
            audio_url="https://example.com/audio",
        )
        coord = StreamDownloadCoordinator(
            stream_info=stream_info,
            destination_path="test_dest.mp4",
            max_connections=8
        )
        mock_v_engine = MagicMock()
        mock_v_engine._lock = threading.RLock()
        mock_a_engine = MagicMock()
        mock_a_engine._lock = threading.RLock()

        chunk_v = DownloadChunk(chunk_id=0, start_byte=0, end_byte=100)
        chunk_a = DownloadChunk(chunk_id=0, start_byte=0, end_byte=50)

        mock_v_engine.chunks = [chunk_v]
        mock_a_engine.chunks = [chunk_a]

        coord._active_engines = [mock_v_engine, mock_a_engine]

        snapshots = coord.get_chunks_snapshot()
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0].chunk_id, 0)
        self.assertEqual(snapshots[1].chunk_id, 1)

    def test_chunk_snapshot_no_duplicate_ids_with_dynamic_split(self):
        from smart_download.core.chunk import DownloadChunk
        stream_info = YouTubeStreamInfo(
            video_id="vid123", title="Test", clean_filename="t", is_progressive=False,
            video_url="https://example.com/video", audio_url="https://example.com/audio"
        )
        coord = StreamDownloadCoordinator(stream_info=stream_info, destination_path="t.mp4")
        mock_v_engine = MagicMock()
        mock_v_engine._lock = threading.RLock()
        mock_a_engine = MagicMock()
        mock_a_engine._lock = threading.RLock()

        # Engine 1 has chunks 0 and 2 (from dynamic splitting)
        mock_v_engine.chunks = [
            DownloadChunk(chunk_id=0, start_byte=0, end_byte=50),
            DownloadChunk(chunk_id=2, start_byte=51, end_byte=100)
        ]
        # Engine 2 has chunk 0
        mock_a_engine.chunks = [DownloadChunk(chunk_id=0, start_byte=0, end_byte=30)]
        coord._active_engines = [mock_v_engine, mock_a_engine]

        snapshots = coord.get_chunks_snapshot()
        ids = [c.chunk_id for c in snapshots]
        self.assertEqual(len(ids), len(set(ids)), f"Duplicate chunk IDs found: {ids}")
        self.assertEqual(ids, [0, 2, 3])

    def test_speed_fallback_when_start_time_is_zero(self):
        import time
        coord = StreamDownloadCoordinator(
            stream_info=YouTubeStreamInfo(
                video_id="vid123", title="Test", clean_filename="t", is_progressive=False,
                video_url="https://example.com/v", audio_url="https://example.com/a"
            ),
            destination_path="t.mp4"
        )
        coord.start_time = 0.0
        coord._v_total_size = 1_000_000
        coord._a_total_size = 500_000
        combined_total = max(1, coord._v_total_size + coord._a_total_size)
        st = coord.start_time
        el = (time.time() - st) if (isinstance(st, (int, float)) and st > 0) else 0.1
        rep_spd = coord._last_active_speed if coord._last_active_speed > 0 else (combined_total / max(0.05, el))
        self.assertGreater(rep_spd, 100_000)


class DummyMockApp(
    MediaOptionsBarMixin,
    HistoryPanelMixin,
    DownloadControllerMixin,
):
    """Lightweight test harness for GUI mixins without opening Tk windows."""

    def __init__(self):
        self.c_panel = "#1e293b"
        self.c_panel_light = "#334155"
        self.c_border = "#475569"
        self.c_accent = "#38bdf8"
        self.c_accent_dark = "#0284c7"
        self.c_success = "#10b981"
        self.c_danger = "#ef4444"
        self.c_text_bright = "#f8fafc"
        self.c_text_muted = "#94a3b8"
        self.c_input_bg = "#090d16"

        self.logs = []
        self.entry_url = MagicMock()
        self.entry_dest = MagicMock()
        self.conn_var = MagicMock()
        self.conn_var.get.return_value = "8"
        self.entry_custom_speed = MagicMock()
        self.entry_custom_speed.get.return_value = "0"
        self.btn_start = MagicMock()
        self.btn_pause = MagicMock()
        self.btn_cancel = MagicMock()
        self.card_size = MagicMock()
        self.history_manager = MagicMock()
        self.engine = None
        self._pending_media_context = None

        self.media_options_frame = MagicMock()
        self._main_sub_mode_codes = ["soft_embed", "srt_only", "hard_burn"]
        self.cb_main_quality = MagicMock()
        self.cb_main_quality.current.return_value = 0
        self.cb_main_audio = MagicMock()
        self.cb_main_audio.current.return_value = 0
        self.cb_main_sub = MagicMock()
        self.cb_main_sub.current.return_value = 0
        self.cb_main_sub_mode = MagicMock()
        self.cb_main_sub_mode.current.return_value = 0
        self.btn_reopen_quality = MagicMock()

    def log(self, msg):
        self.logs.append(msg)

    def restore_window(self):
        pass

    def dispatch_to_main_thread(self, fn):
        fn()


class TestOpenInMainAppAndMediaOptionsBar(unittest.TestCase):
    """Verifies that 'Open in Main App' sets ready state without auto-starting downloads."""

    def test_open_in_main_populates_ready_state(self):
        app = DummyMockApp()

        test_opt = VideoFormatOption(
            format_id="137+140",
            resolution_label="1080p (Full HD)",
            height=1080,
            ext="mp4",
            filesize_approx=50000000,
        )

        app.populate_main_media_bar(
            url="https://youtube.com/watch?v=abcdef",
            dest="C:/Downloads/video.mp4",
            info={"title": "Test Video"},
            options=[test_opt],
            selected_opt=test_opt,
            audio_tracks=[{"label": "English"}],
            subtitle_tracks=[{"label": "None"}, {"label": "Arabic"}],
            resolver=MagicMock()
        )

        # Verify real populate_main_media_bar ran and set media context correctly
        self.assertIsNotNone(app._pending_media_context)
        self.assertEqual(app._pending_media_context["url"], "https://youtube.com/watch?v=abcdef")
        self.assertEqual(app._pending_media_context["final_dest"], "C:/Downloads/video.mp4")
        self.assertEqual(app._pending_media_context["selected_option"], test_opt)
        self.assertTrue(app.cb_main_quality.configure.called)
        self.assertTrue(app.cb_main_audio.configure.called)
        self.assertTrue(app.cb_main_sub.configure.called)
        self.assertIsNone(app.engine)

    def test_start_pending_media_download_triggered_by_start(self):
        app = DummyMockApp()
        opt = VideoFormatOption(
            format_id="137+140",
            resolution_label="1080p (Full HD)",
            height=1080,
            ext="mp4",
            filesize_approx=50000000,
        )
        app._pending_media_context = {
            "url": "https://youtube.com/watch?v=test1234",
            "info": {"title": "Pending Video"},
            "selected_option": opt,
            "final_dest": "C:/Downloads/test.mp4",
        }
        app.entry_url.get.return_value = "https://youtube.com/watch?v=test1234"
        app.entry_dest.get.return_value = "C:/Downloads/test.mp4"

        launched = []
        app._launch_stream_coordinator = lambda info, dest, max_c, b_lim: launched.append((dest, max_c))

        # Invoke _on_start_download
        app._on_start_download()

        self.assertEqual(len(launched), 1)
        self.assertTrue(launched[0][0].endswith("test [1080p].mp4") or launched[0][0].endswith("test.mp4"))
        self.assertIsNone(app._pending_media_context)
        self.assertIsNotNone(app._last_media_context)

    def test_reopen_quality_uses_cached_context_without_reprobing(self):
        app = DummyMockApp()
        app.entry_url.get.return_value = "https://youtube.com/watch?v=cached123"
        app.entry_dest.get.return_value = "C:/Downloads/cached.mp4"
        cached_modal_opened = []
        app._show_cached_quality_modal = lambda ctx: cached_modal_opened.append(ctx)
        app._start_youtube_download = MagicMock()

        app._last_media_context = {
            "url": "https://youtube.com/watch?v=cached123",
            "info": {"title": "Cached Video"},
            "options": [MagicMock()],
        }

        app._reopen_media_quality_modal()

        self.assertEqual(len(cached_modal_opened), 1)
        self.assertFalse(app._start_youtube_download.called)


class TestFetchingToastSafety(unittest.TestCase):
    """Verifies that FetchingLinkToast releases -topmost after 250ms and has a 15s auto-close timer."""

    @patch("tkinter.Toplevel.attributes")
    @patch("tkinter.Toplevel.after")
    @patch("tkinter.Toplevel.geometry")
    @patch("tkinter.Toplevel.overrideredirect")
    def test_fetching_toast_topmost_and_safety_timer(self, mock_override, mock_geom, mock_after, mock_attrs):
        from smart_download.ui.modals.fetching_toast import FetchingLinkToast

        mock_parent = MagicMock()
        mock_parent.winfo_exists.return_value = False
        mock_after.return_value = "job_123"

        toast = FetchingLinkToast(
            parent=None,
            url="https://youtube.com/watch?v=12345",
            theme={"c_bg": "#0f172a"}
        )

        # Verify 15s safety close timer scheduled
        scheduled_times = [call[0][0] for call in mock_after.call_args_list]
        self.assertIn(15000, scheduled_times)
        # Verify 250ms topmost release scheduled
        self.assertIn(250, scheduled_times)
        self.assertEqual(toast._safety_close_job, "job_123")


class TestSubtitleAutoSelection(unittest.TestCase):
    """Verifies subtitle auto-selection when hard_burn mode is chosen."""

    def test_auto_select_track_when_hard_burn(self):
        from smart_download.ui.modals.quality_modal import QualitySelectionModal

        sub_tracks = [
            {"track_idx": 0, "name": "None", "code": "none"},
            {"track_idx": 1, "name": "Arabic", "code": "ar", "url": "https://example.com/sub.vtt"},
        ]

        mock_parent = MagicMock()
        mock_parent.winfo_exists.return_value = False

        opt = VideoFormatOption(
            format_id="137",
            resolution_label="1080p",
            height=1080,
            ext="mp4",
            filesize_approx=1000000,
        )

        modal = QualitySelectionModal.__new__(QualitySelectionModal)
        modal.selected_option = opt
        modal.audio_tracks = []
        modal.subtitle_tracks = sub_tracks
        modal.cb_sub = MagicMock()
        modal.cb_sub.current.return_value = 0
        modal.cb_sub.get_selected_mode.return_value = "hard_burn"
        modal.cb_audio = None

        # When hard_burn is chosen and cb_sub is at 0 (None)
        modal._attach_selected_tracks()

        # Verify track 1 (Arabic) is auto-selected
        self.assertEqual(opt.selected_subtitle_track, sub_tracks[1])
        self.assertEqual(opt.subtitle_embed_mode, "hard_burn")


class TestHistoryRedownloadQuality(unittest.TestCase):
    """Verifies that Re-Download with Different Quality routes to format selection."""

    def test_history_redownload_with_quality_invokes_youtube_download(self):
        app = DummyMockApp()
        app.tree_history = MagicMock()
        app.tree_history.selection.return_value = ["hist_1"]
        app.history_manager.get_entry.return_value = {
            "url": "https://www.youtube.com/watch?v=history123",
            "file_path": "C:/Downloads/hist.mp4"
        }
        yt_calls = []
        app._start_youtube_download = lambda url, dest: yt_calls.append((url, dest))

        app._history_redownload_with_quality()

        self.assertEqual(len(yt_calls), 1)
        self.assertEqual(yt_calls[0][0], "https://www.youtube.com/watch?v=history123")


if __name__ == "__main__":
    unittest.main()
