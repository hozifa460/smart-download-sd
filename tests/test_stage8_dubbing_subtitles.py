"""
Unit tests for Stage 8: YouTube Multi-Language Audio Dubbing & Subtitle Selection/Embedding.
Tests extract_audio_tracks, extract_subtitle_tracks, convert_vtt_to_srt, download_subtitle_as_srt,
embed_subtitle_into_mp4, build_stream_info overrides, and QualitySelectionModal track integration.
"""
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from smart_download.services.youtube_models import (
    VideoFormatOption,
    YouTubeStreamInfo,
)
from smart_download.services.youtube_format_builder import YouTubeFormatBuilderMixin
from smart_download.services.youtube_tracks import (
    extract_audio_tracks,
    extract_subtitle_tracks,
    convert_vtt_to_srt,
    download_subtitle_as_srt,
    embed_subtitle_into_mp4,
    burn_subtitle_into_video,
    handle_subtitles_post_download,
)


class DummyBuilder(YouTubeFormatBuilderMixin):
    pass


class TestYouTubeTracks(unittest.TestCase):
    """Test suite for audio dubbing and subtitle track extraction and processing."""

    def setUp(self):
        self.builder = DummyBuilder()

    def test_extract_audio_tracks_sorting_and_selection(self):
        """Verifies multi-language audio formats grouping, m4a preference, and sort order."""
        info = {
            "formats": [
                # Video only - must be ignored
                {
                    "format_id": "137",
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "url": "https://googlevideo.com/video137",
                },
                # Original English track (m4a, 128kbps)
                {
                    "format_id": "140-orig",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "abr": 128.0,
                    "ext": "m4a",
                    "language": "en",
                    "format_note": "original",
                    "url": "https://googlevideo.com/audio140_orig",
                    "http_headers": {"User-Agent": "Test"},
                },
                # Original webm track (higher bitrate, but m4a preferred)
                {
                    "format_id": "251-orig",
                    "vcodec": "none",
                    "acodec": "opus",
                    "abr": 160.0,
                    "ext": "webm",
                    "language": "en",
                    "format_note": "original",
                    "url": "https://googlevideo.com/audio251_orig",
                },
                # Spanish dub
                {
                    "format_id": "140-es",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "abr": 128.0,
                    "ext": "m4a",
                    "language": "es",
                    "format_note": "Spanish dub",
                    "url": "https://googlevideo.com/audio140_es",
                },
                # Arabic dub
                {
                    "format_id": "140-ar",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "abr": 128.0,
                    "ext": "m4a",
                    "language": "ar",
                    "format_note": "Arabic dub",
                    "url": "https://googlevideo.com/audio140_ar",
                },
                # French dub
                {
                    "format_id": "140-fr",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "abr": 128.0,
                    "ext": "m4a",
                    "language": "fr",
                    "format_note": "French dub",
                    "url": "https://googlevideo.com/audio140_fr",
                },
            ]
        }

        tracks = extract_audio_tracks(info)
        self.assertGreaterEqual(len(tracks), 4)

        # 1. Original/Default must be first
        self.assertTrue(tracks[0]["is_original"])
        self.assertEqual(tracks[0]["track_id"], "original")
        self.assertEqual(tracks[0]["ext"], "m4a")  # preferred over webm
        self.assertEqual(tracks[0]["url"], "https://googlevideo.com/audio140_orig")
        self.assertIn("Original", tracks[0]["label"])

        # 2. Arabic must precede Spanish and French (en, ar, others)
        lang_order = [t["language"] for t in tracks[1:]]
        self.assertIn("ar", lang_order)
        self.assertIn("es", lang_order)
        self.assertIn("fr", lang_order)
        ar_idx = lang_order.index("ar")
        es_idx = lang_order.index("es")
        fr_idx = lang_order.index("fr")
        self.assertLess(ar_idx, es_idx)
        self.assertLess(ar_idx, fr_idx)

    def test_extract_audio_tracks_empty(self):
        """Verifies fallback original track when formats list has no audio-only streams."""
        info = {"formats": [{"format_id": "18", "vcodec": "avc1", "acodec": "mp4a"}]}
        tracks = extract_audio_tracks(info)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]["track_id"], "original")
        self.assertTrue(tracks[0]["is_original"])

    def test_extract_subtitle_tracks_manual_and_auto(self):
        """Verifies subtitle priority, None option first, and format selection."""
        info = {
            "subtitles": {
                "en": [
                    {"ext": "srv3", "url": "https://example.com/en.srv3"},
                    {"ext": "vtt", "url": "https://example.com/en.vtt"},
                ],
                "ar": [
                    {"ext": "vtt", "url": "https://example.com/ar.vtt"},
                    {"ext": "srt", "url": "https://example.com/ar.srt"},
                ],
                "de": [
                    {"ext": "vtt", "url": "https://example.com/de.vtt"},
                ]
            },
            "automatic_captions": {
                "es": [
                    {"ext": "vtt", "url": "https://example.com/es_auto.vtt"},
                ],
                "unsupported_rare_lang": [
                    {"ext": "vtt", "url": "https://example.com/rare.vtt"},
                ]
            }
        }

        subs = extract_subtitle_tracks(info)

        # Index 0 must be 'none'
        self.assertEqual(subs[0]["sub_id"], "none")
        self.assertIn("None", subs[0]["label"])

        # Arabic manual picked SRT over VTT
        ar_track = next(s for s in subs if s["language"] == "ar" and not s["is_auto"])
        self.assertEqual(ar_track["ext"], "srt")
        self.assertEqual(ar_track["url"], "https://example.com/ar.srt")
        self.assertIn("Official", ar_track["label"])

        # English manual picked VTT over SRV3
        en_track = next(s for s in subs if s["language"] == "en" and not s["is_auto"])
        self.assertEqual(en_track["ext"], "vtt")
        self.assertEqual(en_track["url"], "https://example.com/en.vtt")

        # Spanish auto caption is present
        es_auto = next((s for s in subs if s["language"] == "es" and s["is_auto"]), None)
        self.assertIsNotNone(es_auto)
        self.assertTrue(es_auto["is_auto"])

        # Rare unsupported auto caption excluded
        rare = next((s for s in subs if s["language"] == "unsupported_rare_lang"), None)
        self.assertIsNone(rare)

    def test_convert_vtt_to_srt(self):
        """Verifies clean conversion of WebVTT timestamps, tags, and indices into SRT."""
        vtt_input = """WEBVTT
Kind: captions
Language: en

01:05.250 --> 01:08.500 align:start position:0%
Hello world from <i>smart</i> download!

00:02:15.100 --> 00:02:18.200
<c.yellow>Second subtitle line</c>
"""
        srt = convert_vtt_to_srt(vtt_input)
        self.assertIn("1\n00:01:05,250 --> 00:01:08,500\nHello world from smart download!", srt)
        self.assertIn("2\n00:02:15,100 --> 00:02:18,200\nSecond subtitle line", srt)
        self.assertNotIn("WEBVTT", srt)
        self.assertNotIn("align:start", srt)
        self.assertNotIn("<c.yellow>", srt)

    def test_download_subtitle_as_srt_mock(self):
        """Verifies downloading subtitle and writing UTF-8-SIG encoded .srt file."""
        sub_track = {
            "sub_id": "ar",
            "language": "ar",
            "url": "https://example.com/ar.vtt",
            "ext": "vtt"
        }
        mock_vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nمرحبا بك في Smart Download\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            video_file = os.path.join(tmpdir, "test_video.mp4")
            with open(video_file, "wb") as vf:
                vf.write(b"fake_mp4_bytes")

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = mock_vtt.encode("utf-8")

            with patch("requests.get", return_value=mock_resp):
                out_srt = download_subtitle_as_srt(sub_track, video_file)

            self.assertIsNotNone(out_srt)
            self.assertTrue(os.path.isfile(out_srt))
            self.assertTrue(out_srt.endswith("test_video.ar.srt"))
            # Both <video_stem>.<lang>.srt and <video_stem>.srt must be written
            default_srt = os.path.join(tmpdir, "test_video.srt")
            self.assertTrue(os.path.isfile(default_srt))

            # Check UTF-8-SIG encoding (BOM)
            with open(out_srt, "rb") as f:
                content_bytes = f.read()
                self.assertTrue(content_bytes.startswith(b"\xef\xbb\xbf"))

            with open(out_srt, "r", encoding="utf-8-sig") as f:
                content = f.read()
                self.assertIn("00:00:01,000 --> 00:00:04,000", content)
                self.assertIn("مرحبا بك في Smart Download", content)

    def test_download_subtitle_none_returns_none(self):
        """Verifies None or 'none' sub_id returns None without network call."""
        res1 = download_subtitle_as_srt(None, "dummy.mp4")
        res2 = download_subtitle_as_srt({"sub_id": "none"}, "dummy.mp4")
        self.assertIsNone(res1)
        self.assertIsNone(res2)

    def test_build_stream_info_with_audio_dub(self):
        """Verifies build_stream_info overrides audio URL and ext when dubbing is chosen."""
        info = {
            "id": "vid123",
            "title": "Multilingual Video",
            "duration": 300,
            "webpage_url": "https://www.youtube.com/watch?v=vid123",
        }
        option = VideoFormatOption(
            format_id="137+140",
            resolution_label="1080p (Full HD)",
            height=1080,
            ext="mp4",
            filesize_approx=150000000,
            is_progressive=False,
            video_url="https://googlevideo.com/video137",
            audio_url="https://googlevideo.com/audio140_en",
            audio_ext="m4a",
            audio_size=10000000,
        )

        # Select Arabic dub
        option.selected_audio_track = {
            "track_id": "ar",
            "language": "ar",
            "url": "https://googlevideo.com/audio_dub_ar",
            "ext": "m4a",
            "filesize": 12000000,
            "is_original": False,
        }
        # Select English subtitle
        option.selected_subtitle_track = {
            "sub_id": "en",
            "language": "en",
            "url": "https://example.com/sub_en.vtt",
            "ext": "vtt",
        }

        stream_info = self.builder.build_stream_info(info, option)
        self.assertEqual(stream_info.audio_url, "https://googlevideo.com/audio_dub_ar")
        self.assertEqual(stream_info.audio_language, "ar")
        self.assertFalse(stream_info.is_progressive)
        self.assertEqual(stream_info.subtitle_track, option.selected_subtitle_track)

    def test_build_stream_info_progressive_upgraded_for_dub(self):
        """Verifies progressive stream is upgraded to dual-stream merge if non-original dub is picked."""
        info = {
            "id": "prog123",
            "title": "Progressive Video",
            "duration": 180,
            "webpage_url": "https://www.youtube.com/watch?v=prog123",
        }
        option = VideoFormatOption(
            format_id="22",
            resolution_label="720p (HD)",
            height=720,
            ext="mp4",
            filesize_approx=50000000,
            is_progressive=True,
            video_url="https://googlevideo.com/prog22",
        )

        option.selected_audio_track = {
            "track_id": "ar",
            "language": "ar",
            "url": "https://googlevideo.com/audio_ar",
            "ext": "m4a",
            "is_original": False,
        }

        stream_info = self.builder.build_stream_info(info, option)
        # Should now be split dual-stream for merging with dubbed audio
        self.assertFalse(stream_info.is_progressive)
        self.assertEqual(stream_info.audio_url, "https://googlevideo.com/audio_ar")
        self.assertEqual(stream_info.audio_language, "ar")

    def test_embed_subtitle_into_mp4_mock(self):
        """Verifies FFmpeg command construction and atomic replacement for soft-embedding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "movie.mp4")
            srt_path = os.path.join(tmpdir, "movie.ara.srt")
            with open(video_path, "wb") as vf:
                vf.write(b"mp4_sample")
            with open(srt_path, "wb") as sf:
                sf.write(b"1\n00:00:01,000 --> 00:00:02,000\nSub\n")

            captured_cmd = []
            def mock_run(cmd, **kwargs):
                captured_cmd.extend(cmd)
                # Simulate creating target file
                out_path = cmd[-1]
                with open(out_path, "wb") as out_f:
                    out_f.write(b"mp4_with_subtitles")
                res = MagicMock()
                res.returncode = 0
                return res

            with patch("subprocess.run", side_effect=mock_run):
                ok = embed_subtitle_into_mp4(video_path, srt_path, "ar", "ffmpeg")
                self.assertTrue(ok)
                self.assertTrue(os.path.isfile(video_path))
                self.assertTrue(os.path.isfile(srt_path))  # External srt preserved
                # Verify .submux.mp4, -f mp4, and -disposition:s:0 default
                self.assertTrue(captured_cmd[-1].endswith(".submux.mp4"))
                self.assertIn("-f", captured_cmd)
                self.assertEqual(captured_cmd[captured_cmd.index("-f") + 1], "mp4")
                self.assertIn("-disposition:s:0", captured_cmd)
                self.assertEqual(captured_cmd[captured_cmd.index("-disposition:s:0") + 1], "default")

    def test_quality_modal_tracks_selection(self):
        """Verifies QualitySelectionModal displays audio/sub comboboxes and attaches selections."""
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
        except Exception:
            return  # Headless environment
        try:
            from smart_download.ui.modals.quality_modal import QualitySelectionModal
            audio_tracks = [
                {"track_id": "original", "language": "en", "label": "Original (Default)", "url": "http://audio_orig", "is_original": True},
                {"track_id": "ar", "language": "ar", "label": "العربية (ar) - 128kbps", "url": "http://audio_ar", "is_original": False},
            ]
            sub_tracks = [
                {"sub_id": "none", "language": "none", "label": "None / بدون ترجمة", "url": "", "is_auto": False},
                {"sub_id": "ar", "language": "ar", "label": "العربية (Official)", "url": "http://sub_ar", "is_auto": False},
            ]
            opt = VideoFormatOption(
                format_id="22",
                resolution_label="720p (HD)",
                height=720,
                ext="mp4",
                filesize_approx=1000000,
                is_progressive=True,
                video_url="http://vid22"
            )
            confirmed_opt = []
            def on_confirm(selected_opt, dest):
                confirmed_opt.append(selected_opt)

            theme = {
                "c_bg": "#0f172a", "c_panel": "#1e293b", "c_panel_light": "#334155",
                "c_border": "#475569", "c_accent": "#38bdf8", "c_accent_dark": "#0284c7",
                "c_success": "#10b981", "c_text_bright": "#f8fafc", "c_text_muted": "#94a3b8",
                "c_input_bg": "#090d16"
            }
            modal = QualitySelectionModal(
                parent=root,
                video_title="Test Video",
                duration=120,
                options=[opt],
                default_dest_path="test.mp4",
                theme=theme,
                on_confirm=on_confirm,
                audio_tracks=audio_tracks,
                subtitle_tracks=sub_tracks
            )
            self.assertIsNotNone(modal.cb_audio)
            self.assertIsNotNone(modal.cb_sub)
            self.assertEqual(modal.cb_audio.get(), "Original (Default)")
            self.assertEqual(modal.cb_sub.get(), "None / بدون ترجمة")

            modal.cb_audio.current(1)
            modal.cb_sub.current(1)
            modal.cb_sub._mode_combobox.current(1)  # "srt_only"

            modal._on_download()
            self.assertEqual(len(confirmed_opt), 1)
            self.assertEqual(confirmed_opt[0].selected_audio_track["track_id"], "ar")
            self.assertEqual(confirmed_opt[0].selected_subtitle_track["sub_id"], "ar")
            self.assertEqual(confirmed_opt[0].subtitle_embed_mode, "srt_only")
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_extract_audio_tracks_no_duplicate_original(self):
        """Verifies no duplicate original language track is created when multiple formats exist."""
        info = {
            "formats": [
                {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a", "abr": 128, "language": "en", "format_note": "original", "url": "http://140"},
                {"format_id": "251", "vcodec": "none", "acodec": "opus", "ext": "webm", "abr": 160, "language": "en", "format_note": "medium", "url": "http://251"},
                {"format_id": "dub-ar", "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a", "abr": 128, "language": "ar", "format_note": "Arabic dub", "url": "http://ar"},
            ]
        }
        tracks = extract_audio_tracks(info)
        track_ids = [t["track_id"] for t in tracks]
        self.assertEqual(track_ids, ["original", "ar"])
        self.assertEqual(tracks[0]["format_id"], "140")  # m4a preferred for original
        self.assertTrue(tracks[0]["is_original"])

    def test_convert_vtt_to_srt_variable_ms_and_html_unescape(self):
        """Verifies VTT conversion supports 1/2 digit ms timestamps and unescapes HTML entities."""
        vtt = (
            "WEBVTT\n\n"
            "00:00:01.5 --> 00:00:03.50 align:start\n"
            "Tom &amp; Jerry &quot;quote&#39;s&quot; &lt;show&gt;\n"
        )
        srt = convert_vtt_to_srt(vtt)
        self.assertIn("1\n00:00:01,500 --> 00:00:03,500\nTom & Jerry \"quote's\" <show>", srt)

    def test_embed_subtitle_into_mp4_regional_lang_code(self):
        """Verifies regional language codes like 'en-US' and 'ar-EG' map to 3-letter ISO tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            v_path = os.path.join(tmpdir, "vid.mp4")
            s_path = os.path.join(tmpdir, "sub.srt")
            with open(v_path, "wb") as f: f.write(b"mp4")
            with open(s_path, "wb") as f: f.write(b"srt")

            captured_cmds = []
            def mock_run(cmd, **kwargs):
                captured_cmds.append(cmd)
                out = cmd[-1]
                with open(out, "wb") as out_f: out_f.write(b"out")
                res = MagicMock()
                res.returncode = 0
                return res

            with patch("subprocess.run", side_effect=mock_run):
                embed_subtitle_into_mp4(v_path, s_path, "en-US", "ffmpeg")
                embed_subtitle_into_mp4(v_path, s_path, "ar-EG", "ffmpeg")

            self.assertEqual(len(captured_cmds), 2)
            self.assertIn("language=eng", captured_cmds[0])
            self.assertIn("language=ara", captured_cmds[1])
            self.assertIn("-map", captured_cmds[0])

    def test_progressive_merge_stream_mapping(self):
        """Verifies merge_video_audio uses explicit stream mapping (-map 0:v:0 -map 1:a:0)."""
        from smart_download.services.youtube_service import YouTubeResolver
        with tempfile.TemporaryDirectory() as tmpdir:
            v_path = os.path.join(tmpdir, "v.mp4")
            a_path = os.path.join(tmpdir, "a.m4a")
            out_path = os.path.join(tmpdir, "out.mp4")
            with open(v_path, "wb") as f: f.write(b"v")
            with open(a_path, "wb") as f: f.write(b"a")

            captured_cmd = []
            def mock_run(cmd, **kwargs):
                captured_cmd.extend(cmd)
                with open(out_path, "wb") as f: f.write(b"merged")
                res = MagicMock()
                res.returncode = 0
                return res

            with patch("smart_download.services.youtube_service.find_ffmpeg_bin", return_value="ffmpeg"), \
                 patch("subprocess.run", side_effect=mock_run):
                YouTubeResolver.merge_video_audio(v_path, a_path, out_path)

            self.assertIn("-map", captured_cmd)
            v_map_idx = captured_cmd.index("-map")
            self.assertEqual(captured_cmd[v_map_idx + 1], "0:v:0")
            a_map_idx = captured_cmd.index("-map", v_map_idx + 2)
            self.assertEqual(captured_cmd[a_map_idx + 1], "1:a:0")

    def test_build_stream_info_progressive_no_ffmpeg(self):
        """Verifies progressive stream is NOT upgraded to dual stream if FFmpeg is unavailable."""
        info = {"id": "1", "title": "Prog", "duration": 60}
        option = VideoFormatOption(
            format_id="22", resolution_label="720p", height=720,
            ext="mp4", filesize_approx=1000, is_progressive=True, video_url="http://vid"
        )
        option.selected_audio_track = {
            "track_id": "ar", "language": "ar", "url": "http://audio_ar", "is_original": False
        }
        with patch("smart_download.services.youtube_format_builder.has_ffmpeg", return_value=False):
            stream_info = self.builder.build_stream_info(info, option)
            self.assertTrue(stream_info.is_progressive)

    def test_handle_subtitles_post_download_srt_only(self):
        """Verifies srt_only mode downloads .srt but skips FFmpeg entirely."""
        stream_info = MagicMock()
        stream_info.subtitle_track = {
            "sub_id": "ar", "language": "ar", "url": "http://sub_ar", "ext": "vtt"
        }
        stream_info.subtitle_embed_mode = "srt_only"
        logs = []

        with tempfile.TemporaryDirectory() as tmpdir:
            v_path = os.path.join(tmpdir, "test.mp4")
            srt_path = os.path.join(tmpdir, "test.ar.srt")
            with open(v_path, "wb") as f: f.write(b"fake_video")
            with open(srt_path, "wb") as sf: sf.write(b"fake_srt")

            with patch("smart_download.services.subtitle_processor.download_subtitle_as_srt", return_value=srt_path), \
                 patch("smart_download.services.subtitle_processor.find_ffmpeg_bin") as mock_ffmpeg, \
                 patch("smart_download.services.subtitle_processor.embed_subtitle_into_mp4") as mock_embed, \
                 patch("smart_download.services.subtitle_processor.burn_subtitle_into_video") as mock_burn:
                handle_subtitles_post_download(stream_info, v_path, on_log=logs.append)
                mock_ffmpeg.assert_not_called()
                mock_embed.assert_not_called()
                mock_burn.assert_not_called()
                self.assertTrue(any("SRT-only mode selected" in l for l in logs))

    def test_handle_subtitles_post_download_soft_embed(self):
        """Verifies soft_embed mode downloads .srt and calls embed_subtitle_into_mp4."""
        stream_info = MagicMock()
        stream_info.subtitle_track = {
            "sub_id": "ar", "language": "ar", "url": "http://sub_ar", "ext": "vtt"
        }
        stream_info.subtitle_embed_mode = "soft_embed"

        with tempfile.TemporaryDirectory() as tmpdir:
            v_path = os.path.join(tmpdir, "test.mp4")
            srt_path = os.path.join(tmpdir, "test.ar.srt")
            with open(v_path, "wb") as f: f.write(b"fake_video")
            with open(srt_path, "wb") as sf: sf.write(b"fake_srt")

            with patch("smart_download.services.subtitle_processor.download_subtitle_as_srt", return_value=srt_path), \
                 patch("smart_download.services.subtitle_processor.find_ffmpeg_bin", return_value="ffmpeg"), \
                 patch("smart_download.services.subtitle_processor.embed_subtitle_into_mp4", return_value=True) as mock_embed, \
                 patch("smart_download.services.subtitle_processor.burn_subtitle_into_video") as mock_burn:
                handle_subtitles_post_download(stream_info, v_path)
                mock_embed.assert_called_once_with(v_path, srt_path, "ar", "ffmpeg", on_log=None)
                mock_burn.assert_not_called()

    def test_handle_subtitles_post_download_hard_burn_success(self):
        """Verifies hard_burn mode downloads .srt and calls burn_subtitle_into_video."""
        stream_info = MagicMock()
        stream_info.subtitle_track = {
            "sub_id": "ar", "language": "ar", "url": "http://sub_ar", "ext": "vtt"
        }
        stream_info.subtitle_embed_mode = "hard_burn"

        with tempfile.TemporaryDirectory() as tmpdir:
            v_path = os.path.join(tmpdir, "test.mp4")
            srt_path = os.path.join(tmpdir, "test.ar.srt")
            with open(v_path, "wb") as f: f.write(b"fake_video")
            with open(srt_path, "wb") as sf: sf.write(b"fake_srt")

            with patch("smart_download.services.subtitle_processor.download_subtitle_as_srt", return_value=srt_path), \
                 patch("smart_download.services.subtitle_processor.find_ffmpeg_bin", return_value="ffmpeg"), \
                 patch("smart_download.services.subtitle_processor.burn_subtitle_into_video", return_value=True) as mock_burn, \
                 patch("smart_download.services.subtitle_processor.embed_subtitle_into_mp4") as mock_embed:
                handle_subtitles_post_download(stream_info, v_path)
                mock_burn.assert_called_once_with(v_path, srt_path, "ffmpeg", on_log=None)
                mock_embed.assert_not_called()

    def test_handle_subtitles_post_download_hard_burn_fallback(self):
        """Verifies hard_burn mode falls back to soft_embed if burn_subtitle_into_video fails."""
        stream_info = MagicMock()
        stream_info.subtitle_track = {
            "sub_id": "ar", "language": "ar", "url": "http://sub_ar", "ext": "vtt"
        }
        stream_info.subtitle_embed_mode = "hard_burn"
        logs = []

        with tempfile.TemporaryDirectory() as tmpdir:
            v_path = os.path.join(tmpdir, "test.mp4")
            srt_path = os.path.join(tmpdir, "test.ar.srt")
            with open(v_path, "wb") as f: f.write(b"fake_video")
            with open(srt_path, "wb") as sf: sf.write(b"fake_srt")

            with patch("smart_download.services.subtitle_processor.download_subtitle_as_srt", return_value=srt_path), \
                 patch("smart_download.services.subtitle_processor.find_ffmpeg_bin", return_value="ffmpeg"), \
                 patch("smart_download.services.subtitle_processor.burn_subtitle_into_video", return_value=False) as mock_burn, \
                 patch("smart_download.services.subtitle_processor.embed_subtitle_into_mp4", return_value=True) as mock_embed:
                handle_subtitles_post_download(stream_info, v_path, on_log=logs.append)
                mock_burn.assert_called_once()
                mock_embed.assert_called_once_with(v_path, srt_path, "ar", "ffmpeg", on_log=logs.append)
                self.assertTrue(any("falling back" in l for l in logs))

    def test_burn_subtitle_into_video_command(self):
        """Verifies burn_subtitle_into_video constructs correct FFmpeg args and replaces file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "movie.mp4")
            srt_path = os.path.join(tmpdir, "movie.ara.srt")
            with open(video_path, "wb") as vf: vf.write(b"mp4_raw")
            with open(srt_path, "wb") as sf: sf.write(b"1\n00:00:01,000 --> 00:00:02,000\nSub\n")

            captured_cmd = []
            captured_cwd = []
            def mock_run(cmd, **kwargs):
                captured_cmd.extend(cmd)
                captured_cwd.append(kwargs.get("cwd"))
                out_path = cmd[-1]
                with open(out_path, "wb") as out_f:
                    out_f.write(b"mp4_burned")
                res = MagicMock()
                res.returncode = 0
                return res

            with patch("subprocess.run", side_effect=mock_run):
                ok = burn_subtitle_into_video(video_path, srt_path, "ffmpeg")
                self.assertTrue(ok)
                self.assertTrue(captured_cmd[-1].endswith(".burn.mp4"))
                self.assertIn("-vf", captured_cmd)
                vf_idx = captured_cmd.index("-vf")
                self.assertIn("subtitles=", captured_cmd[vf_idx + 1])
                self.assertIn("_sd_burn_sub.srt", captured_cmd[vf_idx + 1])
                self.assertIn("-c:v", captured_cmd)
                self.assertIn("libx264", captured_cmd)
                self.assertIn("-preset", captured_cmd)
                self.assertIn("veryfast", captured_cmd)
                self.assertIn("-crf", captured_cmd)
                self.assertIn("22", captured_cmd)
                self.assertIn("-f", captured_cmd)
                self.assertEqual(captured_cmd[captured_cmd.index("-f") + 1], "mp4")
                self.assertEqual(captured_cwd[0], tmpdir)

    def test_build_audio_subtitle_row_sub_mode(self):
        """Verifies build_audio_subtitle_row creates mode selector and toggles state."""
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
        except Exception:
            return
        try:
            from smart_download.services.youtube_tracks import build_audio_subtitle_row
            audio = [{"track_id": "original", "language": "en", "label": "Original", "url": "u1", "is_original": True}]
            subs = [
                {"sub_id": "none", "language": "none", "label": "None", "url": "", "is_auto": False},
                {"sub_id": "ar", "language": "ar", "label": "Arabic", "url": "u2", "is_auto": False},
            ]
            theme = {"c_bg": "#0f172a", "c_panel": "#1e293b", "c_border": "#475569", "c_text_bright": "#fff"}
            cb_audio, cb_sub = build_audio_subtitle_row(root, theme, audio, subs)
            self.assertIsNotNone(cb_sub)
            self.assertTrue(hasattr(cb_sub, "_mode_combobox"))
            mode_cb = cb_sub._mode_combobox
            self.assertIsNotNone(mode_cb)
            # Initially disabled because sub is 'none' (idx 0)
            self.assertEqual(str(mode_cb.cget("state")), "disabled")
            # Select Arabic (idx 1)
            cb_sub.current(1)
            cb_sub._update_mode_state()
            self.assertEqual(str(mode_cb.cget("state")), "readonly")
            # Select hard_burn (idx 2)
            mode_cb.current(2)
            self.assertEqual(cb_sub.get_selected_mode(), "hard_burn")
        finally:
            try: root.destroy()
            except Exception: pass

    def test_burn_subtitle_into_video_special_chars(self):
        """Verifies burn_subtitle_into_video creates safe temp copy for filenames with quotes/spaces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "Don't Stop [1080p].mp4")
            srt_path = os.path.join(tmpdir, "Don't Stop [1080p].ar.srt")
            with open(video_path, "wb") as vf: vf.write(b"mp4_raw")
            with open(srt_path, "wb") as sf: sf.write(b"1\n00:00:01,000 --> 00:00:02,000\nSub\n")

            captured_cmd = []
            def mock_run(cmd, **kwargs):
                captured_cmd.extend(cmd)
                out_path = cmd[-1]
                with open(out_path, "wb") as out_f:
                    out_f.write(b"mp4_burned")
                res = MagicMock()
                res.returncode = 0
                return res

            with patch("subprocess.run", side_effect=mock_run):
                ok = burn_subtitle_into_video(video_path, srt_path, "ffmpeg")
                self.assertTrue(ok)
                vf_arg = captured_cmd[captured_cmd.index("-vf") + 1]
                self.assertIn("subtitles=_sd_burn_sub.srt:charenc=UTF-8", vf_arg)
                # Temporary srt copy must be cleaned up in finally block
                temp_files = [f for f in os.listdir(tmpdir) if f.startswith("_sd_burn_")]
                self.assertEqual(len(temp_files), 0)

    def test_build_stream_info_fallback_sub_mode_setting(self):
        """Verifies build_stream_info falls back to get_setting when option mode is None."""
        info = {"id": "vid_mode", "title": "Mode Test", "duration": 100}
        option = VideoFormatOption(
            format_id="22", resolution_label="720p", height=720,
            ext="mp4", filesize_approx=5000, is_progressive=True, video_url="http://vid"
        )
        option.subtitle_embed_mode = None  # Explicitly None
        with patch("smart_download.config.get_setting", return_value="hard_burn"):
            stream_info = self.builder.build_stream_info(info, option)
            self.assertEqual(stream_info.subtitle_embed_mode, "hard_burn")


if __name__ == "__main__":
    unittest.main()

