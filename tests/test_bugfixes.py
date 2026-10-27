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


class TestPreviewStreamBridgeAndUnifiedVidMatePlayer(unittest.TestCase):
    """
    Comprehensive verification for:
    - preview_stream_bridge.py loopback endpoints (/player, /subtitle.vtt, /api/update_filename, /api/action)
    - header-forwarding media stream proxy (/stream_video Range request handling with custom headers)
    - generate_preview_html live audio dubbing synchronization and Bottom Settings controls
    - QualitySelectionModal embedded header banner and unified preview integration
    """

    def setUp(self):
        from smart_download.services.preview_stream_bridge import start_preview_bridge, get_preview_bridge_port
        self.port = get_preview_bridge_port()
        self.base_url = f"http://127.0.0.1:{self.port}"

    def test_preview_stream_bridge_endpoints(self):
        """Verifies /player, /subtitle.vtt, /api/update_filename, and /api/action over 127.0.0.1."""
        from smart_download.services.preview_stream_bridge import (
            register_preview_session,
            get_preview_session,
            unregister_preview_session,
        )
        from smart_download.services.youtube_models import VideoFormatOption
        import urllib.request
        import json

        on_confirm_mock = MagicMock()
        on_open_in_main_mock = MagicMock()
        on_cancel_mock = MagicMock()

        opt = VideoFormatOption(
            format_id="best_1080",
            resolution_label="1080p (Full HD)",
            height=1080,
            ext="mp4",
            filesize_approx=15_000_000,
            is_progressive=True,
            video_url="https://v16-webapp.tiktok.com/video.mp4",
            video_headers={"Referer": "https://www.tiktok.com/", "User-Agent": "TikTok 1.0"}
        )
        audio_tracks = [
            {"track_id": "original", "label": "Original Audio", "url": ""},
            {"track_id": "dub-ar", "label": "Arabic Dub", "url": "https://cdn.example.com/audio_ar.m4a", "language": "ar"},
        ]
        subtitle_tracks = [
            {"sub_id": "none", "label": "None"},
            {"sub_id": "ar-sub", "label": "Arabic [ar]", "url": "https://cdn.example.com/sub_ar.vtt", "language": "ar"},
        ]

        sid = register_preview_session(
            url="https://www.tiktok.com/@user/video/9876543210",
            video_title="TikTok Viral Clip",
            options=[opt],
            audio_tracks=audio_tracks,
            subtitle_tracks=subtitle_tracks,
            default_dest_path="C:\\Downloads\\video.mp4",
            on_confirm=on_confirm_mock,
            on_open_in_main=on_open_in_main_mock,
            on_cancel=on_cancel_mock,
        )

        try:
            # 1. GET /player?sid=<sid>
            player_url = f"{self.base_url}/player?sid={sid}"
            with urllib.request.urlopen(player_url, timeout=5) as resp:
                self.assertEqual(resp.getcode(), 200)
                ct = resp.headers.get("Content-Type", "")
                self.assertIn("text/html", ct)
                content = resp.read().decode("utf-8")
                self.assertIn("TikTok Viral Clip", content)
                self.assertIn("1080p (Full HD)", content)
                self.assertIn("Download Selected Quality", content)
                self.assertIn("TikTok", content)

            # 2. GET /subtitle.vtt?sid=<sid>&s_idx=1
            sub_url = f"{self.base_url}/subtitle.vtt?sid={sid}&s_idx=1"
            # Mock subtitle download
            def mock_sub_download(track, out_path):
                srt_path = out_path.replace(".mp4", ".srt")
                with open(srt_path, "w", encoding="utf-8") as f:
                    f.write("1\n00:00:01,000 --> 00:00:03,000\nمرحبا بكم في المعاينة\n")
                return srt_path

            with patch("smart_download.services.preview_stream_bridge.download_subtitle_as_srt", side_effect=mock_sub_download):
                with urllib.request.urlopen(sub_url, timeout=5) as resp:
                    self.assertEqual(resp.getcode(), 200)
                    self.assertIn("text/vtt", resp.headers.get("Content-Type", ""))
                    vtt_text = resp.read().decode("utf-8")
                    self.assertTrue(vtt_text.startswith("WEBVTT"))
                    self.assertIn("00:00:01.000 --> 00:00:03.000", vtt_text)
                    self.assertIn("مرحبا بكم في المعاينة", vtt_text)

            # Verify in-memory cache
            sess = get_preview_session(sid)
            self.assertIsNotNone(sess)
            self.assertIn(1, sess.cached_subtitles)

            # 3. POST /api/update_filename?sid=<sid>
            update_url = f"{self.base_url}/api/update_filename?sid={sid}"
            req_data = json.dumps({"q_idx": 0, "sub_mode": "hard_burn", "current_dest": "C:\\Downloads\\video.mp4"}).encode("utf-8")
            req = urllib.request.Request(update_url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.getcode(), 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("dest_path", data)
                self.assertIn("[Sub]", data["dest_path"])

            # 4. POST /api/action?sid=<sid> with action="download"
            action_url = f"{self.base_url}/api/action?sid={sid}"
            act_data = json.dumps({
                "action": "download",
                "q_idx": 0,
                "a_idx": 1,
                "s_idx": 1,
                "sub_mode": "hard_burn",
                "dest_path": "C:\\Downloads\\video.mp4"
            }).encode("utf-8")
            req = urllib.request.Request(action_url, data=act_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.getcode(), 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data.get("status"), "ok")
                self.assertEqual(data.get("action"), "download")

            on_confirm_mock.assert_called_once()
            call_opt, call_dest = on_confirm_mock.call_args[0]
            self.assertEqual(call_opt.selected_audio_track, audio_tracks[1])
            self.assertEqual(call_opt.selected_subtitle_track, subtitle_tracks[1])
            self.assertEqual(call_opt.subtitle_embed_mode, "hard_burn")
            self.assertIn("[Sub]", call_dest)

            # 5. POST /api/action?sid=<sid> with action="open_in_main"
            act_data_main = json.dumps({
                "action": "open_in_main",
                "q_idx": 0,
                "a_idx": 0,
                "s_idx": 0,
                "sub_mode": "soft_embed",
                "dest_path": "C:\\Downloads\\video.mp4"
            }).encode("utf-8")
            req = urllib.request.Request(action_url, data=act_data_main, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.getcode(), 200)
            on_open_in_main_mock.assert_called_once()
        finally:
            unregister_preview_session(sid)

    def test_preview_stream_bridge_header_forwarding_proxy(self):
        """Verifies Range requests and HTTP headers (User-Agent, Referer, Cookie) are forwarded upstream."""
        from smart_download.services.preview_stream_bridge import register_preview_session, unregister_preview_session
        from smart_download.services.youtube_models import VideoFormatOption
        import urllib.request

        opt = VideoFormatOption(
            format_id="ig_reel",
            resolution_label="1080p",
            height=1080,
            ext="mp4",
            filesize_approx=4_000_000,
            is_progressive=True,
            video_url="https://scontent.cdninstagram.com/v/t50/reel.mp4",
            video_headers={
                "User-Agent": "InstagramBot 21.0",
                "Referer": "https://www.instagram.com/reel/xyz/",
                "Cookie": "sessionid=test_cookie_123"
            }
        )

        sid = register_preview_session(
            url="https://www.instagram.com/reel/xyz/",
            video_title="Instagram Reel",
            options=[opt]
        )

        try:
            stream_url = f"{self.base_url}/stream_video?sid={sid}&q_idx=0"
            _real_urlopen = urllib.request.urlopen
            captured_requests = []

            def mock_upstream_urlopen(req, **kwargs):
                url_str = req.full_url if hasattr(req, "full_url") else str(req)
                if "127.0.0.1" in url_str:
                    return _real_urlopen(req, **kwargs)
                captured_requests.append(req)
                resp = MagicMock()
                resp.getcode.return_value = 206
                resp.headers = {
                    "Content-Type": "video/mp4",
                    "Content-Range": "bytes 0-1023/4000000",
                    "Content-Length": "1024",
                    "Accept-Ranges": "bytes"
                }
                resp.read.side_effect = [b"A" * 1024, b""]
                return resp

            with patch("urllib.request.urlopen", side_effect=mock_upstream_urlopen):
                client_req = urllib.request.Request(stream_url, headers={"Range": "bytes=0-1023"})
                with urllib.request.urlopen(client_req, timeout=5) as resp:
                    self.assertEqual(resp.getcode(), 206)
                    self.assertEqual(resp.headers.get("Accept-Ranges"), "bytes")
                    self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
                    body = resp.read()
                    self.assertEqual(len(body), 1024)

            self.assertEqual(len(captured_requests), 1)
            up_req = captured_requests[0]
            self.assertEqual(up_req.full_url, "https://scontent.cdninstagram.com/v/t50/reel.mp4")
            self.assertEqual(up_req.get_header("Range"), "bytes=0-1023")
            self.assertEqual(up_req.get_header("Referer"), "https://www.instagram.com/reel/xyz/")
            self.assertEqual(up_req.get_header("Cookie"), "sessionid=test_cookie_123")
            self.assertEqual(up_req.get_header("User-agent"), "InstagramBot 21.0")
        finally:
            unregister_preview_session(sid)

    def test_generate_preview_html_audio_dubbing_sync_and_settings(self):
        """Verifies generate_preview_html renders dub audio element, sync JS, badges, and settings panel."""
        from smart_download.ui.modals.preview_html_builder import generate_preview_html
        from smart_download.services.youtube_models import VideoFormatOption

        opt1 = VideoFormatOption(
            format_id="137", resolution_label="1080p (Full HD)", height=1080,
            ext="mp4", filesize_approx=25_000_000, fps=60, note="60 FPS • Lossless"
        )
        opt2 = VideoFormatOption(
            format_id="22", resolution_label="720p (HD)", height=720,
            ext="mp4", filesize_approx=10_000_000, fps=30, note="Standard Progressive"
        )

        audio_track = {
            "track_id": "ar-dub",
            "language": "ar",
            "label": "العربية (مدبلج)",
            "url": "https://stream.example.com/dub_ar.m4a"
        }

        html_out = generate_preview_html(
            url="https://twitter.com/user/status/123456789",
            video_title="Twitter X Video",
            stream_url="https://video.twimg.com/vid.mp4",
            selected_audio_track=audio_track,
            options=[opt1, opt2],
            audio_tracks=[{"track_id": "original", "label": "Original Audio"}, audio_track],
            subtitle_tracks=[{"sub_id": "none", "label": "No Subtitles"}, {"sub_id": "ar", "label": "Arabic"}],
            default_dest_path="C:\\Downloads\\tweet.mp4",
            platform_name="Twitter / X"
        )

        # 1. Elements verification
        self.assertIn('<audio id="dubAudioEl"', html_out)
        self.assertIn('<video id="videoEl"', html_out)
        self.assertIn('Twitter / X', html_out)
        self.assertIn('🔊 العربية (مدبلج)', html_out)

        # 2. Synchronization JS logic verification
        self.assertIn("dubAudioEl.currentTime = videoEl.currentTime", html_out)
        self.assertIn("videoEl.muted = true", html_out)
        self.assertIn("0.28", html_out)  # Snap threshold
        self.assertIn("dubAudioEl.play()", html_out)
        self.assertIn("dubAudioEl.pause()", html_out)
        self.assertIn("videoEl.addEventListener(\"volumechange\"", html_out)
        self.assertIn("videoEl.addEventListener(\"play\"", html_out)
        self.assertIn("videoEl.addEventListener(\"pause\"", html_out)
        self.assertIn("videoEl.addEventListener(\"seeking\"", html_out)
        self.assertIn("videoEl.addEventListener(\"seeked\"", html_out)
        self.assertIn("videoEl.addEventListener(\"waiting\"", html_out)
        self.assertIn("videoEl.addEventListener(\"playing\"", html_out)
        self.assertIn("videoEl.addEventListener(\"ratechange\"", html_out)
        self.assertIn("videoEl.addEventListener(\"timeupdate\"", html_out)

        # 3. Settings panel verification
        self.assertIn("table class=\"format-table\"", html_out)
        self.assertIn("1080p (Full HD)", html_out)
        self.assertIn("720p (HD)", html_out)
        self.assertIn("select id=\"audioSelect\"", html_out)
        self.assertIn("select id=\"subSelect\"", html_out)
        self.assertIn("select id=\"modeSelect\"", html_out)
        self.assertIn("input type=\"text\" id=\"destInput\"", html_out)
        self.assertIn("Download Selected Quality", html_out)
        self.assertIn("Open in Main Window", html_out)

    def test_quality_modal_embedded_preview_banner(self):
        """Verifies QualitySelectionModal renders the compact embedded Preview Header Banner and preview button."""
        from smart_download.ui.modals.quality_modal import QualitySelectionModal
        from smart_download.services.youtube_models import VideoFormatOption
        import tkinter as tk

        try:
            root = tk.Tk()
            root.withdraw()
        except Exception:
            self.skipTest("Tkinter display not available")

        try:
            opt = VideoFormatOption(
                format_id="22", resolution_label="720p", height=720,
                ext="mp4", filesize_approx=5000, is_progressive=True,
                video_url="https://example.com/video.mp4"
            )
            theme = {
                "c_bg": "#000", "c_panel": "#111", "c_panel_light": "#222",
                "c_border": "#333", "c_accent": "#444", "c_accent_dark": "#555",
                "c_text_bright": "#fff", "c_text_muted": "#aaa", "c_input_bg": "#000", "c_success": "#0f0"
            }
            modal = QualitySelectionModal(
                parent=root,
                video_title="Banner Test Video",
                duration=120,
                options=[opt],
                default_dest_path="banner_test.mp4",
                theme=theme,
                on_confirm=lambda o, d: None,
                video_url="https://www.tiktok.com/@user/video/111"
            )

            # Check banner exists
            self.assertTrue(hasattr(modal, "card_info"))
            self.assertTrue(hasattr(modal, "btn_banner_preview"))
            self.assertIsInstance(modal.btn_banner_preview, tk.Button)
            self.assertTrue(hasattr(modal, "btn_preview_video"))

            # Test preview launch passes options and callbacks
            with patch("smart_download.ui.modals.video_preview_modal.open_video_preview") as mock_prev:
                modal._on_preview_video()
                mock_prev.assert_called_once()
                kwargs = mock_prev.call_args[1]
                self.assertEqual(kwargs.get("options"), [opt])
                self.assertEqual(kwargs.get("url"), "https://www.tiktok.com/@user/video/111")
                self.assertEqual(kwargs.get("modal_ref"), modal)

            modal.destroy()
        finally:
            try: root.destroy()
            except Exception: pass

    def test_preview_stream_audio_dubbing_proxy(self):
        """Verifies /stream_audio proxies dubbed audio chunks with upstream headers and Range."""
        from smart_download.services.preview_stream_bridge import register_preview_session, unregister_preview_session
        import urllib.request

        audio_track = {
            "track_id": "ar-dub",
            "language": "ar",
            "label": "العربية (مدبلج)",
            "url": "https://cdn.example.com/dub_audio.m4a",
            "http_headers": {"User-Agent": "AudioClient/2.0", "Referer": "https://example.com/audio"}
        }
        sid = register_preview_session(
            url="https://www.youtube.com/watch?v=dub_test",
            video_title="Dub Test",
            audio_tracks=[{"track_id": "original", "label": "Original"}, audio_track]
        )
        try:
            audio_url = f"{self.base_url}/stream_audio?sid={sid}&a_idx=1"
            _real_urlopen = urllib.request.urlopen
            captured = []

            def mock_urlopen(req, **kwargs):
                url_s = req.full_url if hasattr(req, "full_url") else str(req)
                if "127.0.0.1" in url_s:
                    return _real_urlopen(req, **kwargs)
                captured.append(req)
                resp = MagicMock()
                resp.getcode.return_value = 206
                resp.headers = {
                    "Content-Type": "audio/mp4",
                    "Content-Range": "bytes 0-511/200000",
                    "Content-Length": "512",
                    "Accept-Ranges": "bytes"
                }
                resp.read.side_effect = [b"B" * 512, b""]
                return resp

            with patch("urllib.request.urlopen", side_effect=mock_urlopen):
                req = urllib.request.Request(audio_url, headers={"Range": "bytes=0-511"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.getcode(), 206)
                    self.assertEqual(resp.headers.get("Content-Type"), "audio/mp4")
                    self.assertEqual(len(resp.read()), 512)

            self.assertEqual(len(captured), 1)
            up_req = captured[0]
            self.assertEqual(up_req.full_url, "https://cdn.example.com/dub_audio.m4a")
            self.assertEqual(up_req.get_header("Range"), "bytes=0-511")
            self.assertEqual(up_req.get_header("Referer"), "https://example.com/audio")
            self.assertEqual(up_req.get_header("User-agent"), "AudioClient/2.0")
        finally:
            unregister_preview_session(sid)

    def test_player_preselection_and_volume_controls(self):
        """Verifies GET /player renders pre-selected audio/sub/mode options and header volume controls."""
        from smart_download.services.preview_stream_bridge import register_preview_session, unregister_preview_session
        from smart_download.services.youtube_models import VideoFormatOption
        import urllib.request

        opt = VideoFormatOption(
            format_id="22", resolution_label="720p (HD)", height=720,
            ext="mp4", filesize_approx=10_000_000, fps=30
        )
        dub_ar = {"track_id": "ar", "label": "العربية (مدبلج)", "url": "https://stream.example.com/ar.m4a"}
        sub_en = {"sub_id": "en", "label": "English Subs", "language": "en"}
        sid = register_preview_session(
            url="https://www.youtube.com/watch?v=preselect_test",
            video_title="Preselect Test",
            options=[opt],
            audio_tracks=[{"track_id": "original", "label": "Original"}, dub_ar],
            subtitle_tracks=[{"sub_id": "none", "label": "None"}, sub_en],
            selected_audio_track=dub_ar,
            selected_sub_track=sub_en,
            subtitle_embed_mode="hard_burn",
        )
        try:
            player_url = f"{self.base_url}/player?sid={sid}"
            with urllib.request.urlopen(player_url, timeout=5) as resp:
                self.assertEqual(resp.getcode(), 200)
                html = resp.read().decode("utf-8")
                self.assertIn('<option value="1" selected>العربية (مدبلج)</option>', html)
                self.assertIn('<option value="1" selected>English Subs</option>', html)
                self.assertIn('<option value="hard_burn" selected>', html)
                self.assertIn('id="muteBtn"', html)
                self.assertIn('id="volSlider"', html)
                self.assertIn('🔊 العربية (مدبلج)', html)
                self.assertIn('💬 English Subs', html)
        finally:
            unregister_preview_session(sid)


if __name__ == "__main__":
    unittest.main()
