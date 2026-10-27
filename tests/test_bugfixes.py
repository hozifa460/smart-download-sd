"""
Automated unit and integration tests for Part 1 (Subtitle Hard-Burn fixes & GTX translation fallback)
and Part 2 (In-App VidMate-Style Video Preview Modal).
"""
import os
import sys
import json
import base64
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from smart_download.services.subtitle_downloader import (
    _strip_tlang_param,
    _translate_srt_cues_via_gtx,
    _parse_timedtext_to_cues,
    _format_cues_to_srt,
    download_subtitle_as_srt,
)
from smart_download.services.subtitle_processor import (
    burn_subtitle_into_video,
    handle_subtitles_post_download,
    strip_burn_tag_from_filename,
)
from smart_download.services.youtube_models import find_ffmpeg_bin
from smart_download.ui.modals.video_preview_modal import (
    generate_preview_html,
    _convert_srt_to_vtt_data_uri,
    _find_progressive_mp4_url,
    open_video_preview,
)


class TestSubtitleProcessorAndGTXFallback(unittest.TestCase):
    """Verifies YouTube timedtext fallback, GTX cue translation, and hard-burn retry matrix."""

    def test_strip_tlang_param(self):
        """Verifies stripping tlang parameter from YouTube timedtext URLs."""
        url1 = "https://www.youtube.com/api/timedtext?v=abc&lang=en&tlang=ar&fmt=vtt"
        self.assertEqual(
            _strip_tlang_param(url1),
            "https://www.youtube.com/api/timedtext?v=abc&lang=en&fmt=vtt"
        )
        url2 = "https://www.youtube.com/api/timedtext?tlang=ar&v=abc"
        self.assertEqual(
            _strip_tlang_param(url2),
            "https://www.youtube.com/api/timedtext?v=abc"
        )

    def test_translate_srt_cues_via_gtx(self):
        """Verifies batch translation of subtitle cues using Google GTX API."""
        cues = [
            (1.0, 3.0, "Hello World"),
            (4.0, 6.0, "Welcome to Smart Download"),
        ]
        mock_gtx_resp = MagicMock()
        mock_gtx_resp.__enter__.return_value = mock_gtx_resp
        mock_gtx_resp.read.return_value = json.dumps([
            [
                ["مرحبا بالعالم\n ||| \nأهلا بكم في سمارت داونلود", "Hello World\n ||| \nWelcome to Smart Download", None, None]
            ]
        ]).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_gtx_resp):
            translated = _translate_srt_cues_via_gtx(cues, target_lang="ar")
            self.assertEqual(len(translated), 2)
            self.assertEqual(translated[0][0], 1.0)
            self.assertEqual(translated[0][1], 3.0)
            self.assertEqual(translated[0][2], "مرحبا بالعالم")
            self.assertEqual(translated[1][2], "أهلا بكم في سمارت داونلود")

    def test_download_subtitle_as_srt_tlang_fallback(self):
        """
        Verifies that when &tlang=ar candidate URL fails (HTTP 429), download_subtitle_as_srt
        deterministically fetches untranslated base URL and translates via GTX.
        """
        sub_track = {
            "sub_id": "ar-auto",
            "language": "ar",
            "url": "https://www.youtube.com/api/timedtext?v=xyz&lang=en&tlang=ar&fmt=vtt",
            "base_url": "https://www.youtube.com/api/timedtext?v=xyz&lang=en",
            "is_auto": True,
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            video_file = os.path.join(tmp_dir, "test_video.mp4")
            with open(video_file, "wb") as f:
                f.write(b"fake mp4")

            # Mock _fetch_url_direct:
            # - candidate with tlang=ar returns None (simulating HTTP 429)
            # - base url returns English VTT
            def mock_fetch(url, headers, timeout=15):
                if "tlang=ar" in url:
                    return None  # HTTP 429 Too Many Requests
                if "lang=en" in url:
                    return "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello from base timedtext\n"
                return None

            # Mock GTX translation
            mock_gtx_resp = MagicMock()
            mock_gtx_resp.__enter__.return_value = mock_gtx_resp
            mock_gtx_resp.read.return_value = json.dumps([
                [["مرحبا من النص الأصلي", "Hello from base timedtext", None, None]]
            ]).encode("utf-8")

            with patch("smart_download.services.subtitle_downloader._fetch_url_direct", side_effect=mock_fetch):
                with patch("urllib.request.urlopen", return_value=mock_gtx_resp):
                    srt_path = download_subtitle_as_srt(sub_track, video_file)
                    self.assertIsNotNone(srt_path)
                    self.assertTrue(os.path.isfile(srt_path))
                    with open(srt_path, "r", encoding="utf-8-sig") as sf:
                        content = sf.read()
                    self.assertIn("-->", content)
                    self.assertIn("مرحبا من النص الأصلي", content)

    def test_burn_subtitle_candidate_matrix_retry(self):
        """
        Verifies that burn_subtitle_into_video retries Candidate 2 with -c:a aac -b:a 192k
        when Candidate 1 (charenc=UTF-8) fails with non-zero exit code.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_file = os.path.join(tmp_dir, "sample.mp4")
            srt_file = os.path.join(tmp_dir, "sample.srt")
            with open(video_file, "wb") as f:
                f.write(b"mp4 content")
            with open(srt_file, "w", encoding="utf-8-sig") as f:
                f.write("1\n00:00:01,000 --> 00:00:02,000\nSubtitle\n")

            commands_run = []

            def mock_run(cmd, **kwargs):
                commands_run.append(list(cmd))
                res = MagicMock()
                vf_arg = cmd[cmd.index("-vf") + 1]
                if "charenc=UTF-8" in vf_arg:
                    # Candidate 1 fails
                    res.returncode = 1
                    res.stderr = "Error initializing filter 'subtitles': option 'charenc' not found"
                else:
                    # Candidate 2 succeeds and creates output temp file
                    out_path = cmd[-1]
                    with open(out_path, "wb") as out_f:
                        out_f.write(b"burned video output")
                    res.returncode = 0
                    res.stderr = ""
                return res

            with patch("subprocess.run", side_effect=mock_run):
                ok = burn_subtitle_into_video(video_file, srt_file, ffmpeg_path="ffmpeg")
                self.assertTrue(ok)
                self.assertEqual(len(commands_run), 2)

                cand1 = commands_run[0]
                self.assertIn("charenc=UTF-8", cand1[cand1.index("-vf") + 1])
                self.assertIn("-c:a", cand1)
                self.assertIn("aac", cand1)

                cand2 = commands_run[1]
                self.assertNotIn("charenc=UTF-8", cand2[cand2.index("-vf") + 1])
                self.assertIn("-c:a", cand2)
                self.assertIn("aac", cand2)

    def test_handle_subtitles_post_download_strip_tag_on_burn_failure(self):
        """
        Verifies that if hard_burn fails, strip_burn_tag_from_filename removes [Sub]
        or [Sub-Burned] tag from the output filename so users are never misled.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tagged_path = os.path.join(tmp_dir, "My Video [1080p] [Sub].mp4")
            with open(tagged_path, "wb") as f:
                f.write(b"video data")

            stream_info = MagicMock()
            stream_info.subtitle_track = {
                "sub_id": "ar", "url": "https://example.com/fail.vtt", "language": "ar"
            }
            stream_info.subtitle_embed_mode = "hard_burn"

            # Mock download_subtitle_as_srt to return None (download failure)
            with patch("smart_download.services.subtitle_processor.download_subtitle_as_srt", return_value=None):
                handle_subtitles_post_download(stream_info, tagged_path)
                # The file on disk should have had [Sub] stripped
                self.assertFalse(os.path.exists(tagged_path))
                untagged_path = os.path.join(tmp_dir, "My Video [1080p].mp4")
                self.assertTrue(os.path.exists(untagged_path))

    def test_handle_subtitles_post_download_burn_failure_embeds_into_untagged_file(self):
        """
        Verifies that if hard_burn fails on 'Video [Sub-Burned].mp4', strip_burn_tag_from_filename
        renames the file and embed_subtitle_into_mp4 receives the updated (untagged) path.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tagged_path = os.path.join(tmp_dir, "My Video [1080p] [Sub-Burned].mp4")
            srt_path = os.path.join(tmp_dir, "My Video [1080p].ar.srt")
            with open(tagged_path, "wb") as f:
                f.write(b"video data")
            with open(srt_path, "wb") as f:
                f.write(b"1\n00:00:01,000 --> 00:00:02,000\nSub\n")

            stream_info = MagicMock()
            stream_info.subtitle_track = {
                "sub_id": "ar", "url": "https://example.com/sub.vtt", "language": "ar"
            }
            stream_info.subtitle_embed_mode = "hard_burn"

            embed_calls = []

            def mock_embed(v_path, s_path, lang, ffmpeg, **kwargs):
                embed_calls.append(v_path)
                return True

            with patch("smart_download.services.subtitle_processor.download_subtitle_as_srt", return_value=srt_path), \
                 patch("smart_download.services.subtitle_processor.find_ffmpeg_bin", return_value="ffmpeg"), \
                 patch("smart_download.services.subtitle_processor.burn_subtitle_into_video", return_value=False), \
                 patch("smart_download.services.subtitle_processor.embed_subtitle_into_mp4", side_effect=mock_embed):
                handle_subtitles_post_download(stream_info, tagged_path)

                self.assertEqual(len(embed_calls), 1)
                # Verify embed received the untagged path, NOT the non-existent tagged path
                expected_untagged = os.path.join(tmp_dir, "My Video [1080p].mp4")
                self.assertEqual(embed_calls[0], expected_untagged)
                self.assertTrue(os.path.isfile(expected_untagged))

    def test_strip_burn_tag_from_filename(self):
        """Verifies strip_burn_tag_from_filename renames [Sub-Burned] and [Sub] on disk."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = os.path.join(tmp_dir, "Tutorial [Sub-Burned].mp4")
            with open(f1, "wb") as f: f.write(b"data")
            res1 = strip_burn_tag_from_filename(f1)
            self.assertEqual(os.path.basename(res1), "Tutorial.mp4")
            self.assertTrue(os.path.exists(res1))


class TestVideoPreviewModal(unittest.TestCase):
    """Verifies HTML5 preview generation, live WebVTT subtitles, and chromeless launcher."""

    def test_convert_srt_to_vtt_data_uri(self):
        """Verifies SRT conversion to WebVTT base64 data URI."""
        srt = "1\n00:00:01,500 --> 00:00:04,200\nHello World\n"
        uri = _convert_srt_to_vtt_data_uri(srt)
        self.assertIsNotNone(uri)
        self.assertTrue(uri.startswith("data:text/vtt;charset=utf-8;base64,"))
        b64_part = uri.split(",", 1)[1]
        decoded = base64.b64decode(b64_part).decode("utf-8")
        self.assertTrue(decoded.startswith("WEBVTT"))
        self.assertIn("00:00:01.500 --> 00:00:04.200", decoded)
        self.assertIn("Hello World", decoded)

    def test_find_progressive_mp4_url(self):
        """Verifies detection of fast-buffering progressive MP4 stream (format 18 / 22)."""
        info_dict = {
            "formats": [
                {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "height": 1080, "url": "http://v1080"},
                {"format_id": "22", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "height": 720, "url": "http://prog720"},
                {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "height": 360, "url": "http://prog360"},
            ]
        }
        res = _find_progressive_mp4_url(None, info_dict)
        self.assertEqual(res, "http://prog720")

    def test_find_progressive_mp4_from_stream_info(self):
        """Verifies detection of progressive MP4 stream directly on stream_info with is_progressive=True."""
        stream_info = MagicMock()
        stream_info.video_url = "https://rr1---sn.googlevideo.com/videoplayback?id=123"
        stream_info.is_progressive = True
        stream_info.ext = "mp4"

        res = _find_progressive_mp4_url(stream_info, {})
        self.assertEqual(res, "https://rr1---sn.googlevideo.com/videoplayback?id=123")

    def test_generate_preview_html_with_subtitles(self):
        """Verifies HTML5 output includes direct stream and WebVTT subtitle track."""
        vtt_uri = "data:text/vtt;charset=utf-8;base64,V0VCVlRUCg=="
        html_code = generate_preview_html(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            video_title="Test Video Preview",
            stream_url="https://stream.example.com/video.mp4",
            vtt_data_uri=vtt_uri,
            video_id="dQw4w9WgXcQ",
            sub_label="Arabic Subtitles",
            quality_label="720p (HD)",
            sub_lang="ar"
        )
        self.assertIn("<title>Test Video Preview — Smart Download Preview</title>", html_code)
        self.assertIn('video id="videoEl" src="https://stream.example.com/video.mp4"', html_code)
        self.assertIn(f'track label="Arabic Subtitles" kind="subtitles" srclang="ar" src="{vtt_uri}" default', html_code)
        self.assertIn("https://www.youtube.com/embed/dQw4w9WgXcQ", html_code)
        self.assertIn("Switch to Web Player", html_code)

    def test_open_video_preview_launches_browser(self):
        """Verifies open_video_preview writes HTML and invokes chromeless browser."""
        with patch("smart_download.ui.modals.video_preview_modal._find_chromeless_browser", return_value="msedge.exe"):
            with patch("subprocess.Popen") as mock_popen:
                html_path = open_video_preview(
                    parent=None,
                    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    video_title="Unit Test Preview",
                    stream_info=None,
                    info_dict={"id": "dQw4w9WgXcQ", "formats": []},
                    selected_sub_track=None
                )
                self.assertTrue(os.path.isfile(html_path))
                mock_popen.assert_called_once()
                cmd = mock_popen.call_args[0][0]
                self.assertEqual(cmd[0], "msedge.exe")
                self.assertTrue(any(arg.startswith("--app=file:///") for arg in cmd))
                self.assertIn("--window-size=860,560", cmd)
                try: os.remove(html_path)
                except Exception: pass

    def test_quality_modal_preview_passes_selected_subtitle_track(self):
        """Verifies QualitySelectionModal._on_preview_video passes selected_subtitle_track to open_video_preview."""
        from smart_download.ui.modals.quality_modal import QualitySelectionModal
        from smart_download.services.youtube_models import VideoFormatOption
        import tkinter as tk

        try:
            root = tk.Tk()
            root.withdraw()
        except Exception:
            self.skipTest("Tkinter GUI display not available")

        try:
            opt = VideoFormatOption(
                format_id="22", resolution_label="720p", height=720,
                ext="mp4", filesize_approx=1000, is_progressive=True,
                video_url="https://example.com/video.mp4"
            )
            sub_track = {
                "sub_id": "ar", "language": "ar", "label": "العربية", "url": "https://example.com/ar.vtt"
            }
            theme = {
                "c_bg": "#000", "c_panel": "#111", "c_panel_light": "#222",
                "c_border": "#333", "c_accent": "#444", "c_accent_dark": "#555",
                "c_text_bright": "#fff", "c_text_muted": "#aaa", "c_input_bg": "#000", "c_success": "#0f0"
            }
            modal = QualitySelectionModal(
                parent=root,
                video_title="Modal Test",
                duration=60,
                options=[opt],
                default_dest_path="test.mp4",
                theme=theme,
                on_confirm=lambda o, d: None,
                subtitle_tracks=[{"sub_id": "none", "label": "None"}, sub_track],
                video_url="https://example.com/watch"
            )

            # Select subtitle track
            if modal.cb_sub:
                modal.cb_sub.current(1)

            with patch("smart_download.ui.modals.video_preview_modal.open_video_preview") as mock_preview:
                modal._on_preview_video()
                mock_preview.assert_called_once()
                call_kwargs = mock_preview.call_args[1]
                self.assertEqual(call_kwargs.get("selected_sub_track"), sub_track)

            modal.destroy()
        finally:
            try: root.destroy()
            except Exception: pass

    def test_extract_subtitle_tracks_synthesizes_ar_auto(self):
        """Verifies extract_subtitle_tracks creates ar_auto fallback with base_url when Arabic is missing."""
        from smart_download.services.youtube_tracks import extract_subtitle_tracks

        info = {
            "webpage_url": "https://www.youtube.com/watch?v=123",
            "automatic_captions": {
                "en": [{"url": "https://www.youtube.com/api/timedtext?v=123&lang=en", "ext": "vtt"}]
            }
        }
        tracks = extract_subtitle_tracks(info)
        ar_track = next((t for t in tracks if t.get("sub_id") == "ar_auto"), None)
        self.assertIsNotNone(ar_track)
        self.assertEqual(ar_track["language"], "ar")
        self.assertTrue(ar_track["is_auto"])
        self.assertEqual(ar_track["base_url"], "https://www.youtube.com/api/timedtext?v=123&lang=en&fmt=vtt")
        self.assertIn("tlang=ar", ar_track["url"])


class TestHardenedFFmpeg(unittest.TestCase):
    """Verifies hardened find_ffmpeg_bin search order."""

    def test_find_ffmpeg_bin_prefers_shutil_which(self):
        with patch("shutil.which", return_value=os.path.abspath(__file__)):
            bin_path = find_ffmpeg_bin()
            self.assertIsNotNone(bin_path)
            self.assertEqual(bin_path, os.path.abspath(__file__))

    def test_find_ffmpeg_bin_imageio_fallback(self):
        with patch("shutil.which", return_value=None):
            fake_imageio = MagicMock()
            fake_imageio.get_ffmpeg_exe.return_value = os.path.abspath(__file__)
            with patch.dict("sys.modules", {"imageio_ffmpeg": fake_imageio}):
                bin_path = find_ffmpeg_bin()
                self.assertEqual(bin_path, os.path.abspath(__file__))


if __name__ == "__main__":
    unittest.main()
