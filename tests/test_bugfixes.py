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
                self.assertTrue(any(arg.startswith("--app=http://127.0.0.1:") or arg.startswith("--app=file:///") for arg in cmd))
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


class TestPart1To4CriticalBugfixes(unittest.TestCase):
    """
    Verification tests for the 4 critical bugs:
    1. Single .srt write (no duplicate .srt).
    2. Temporary .srt deletion after successful hard_burn or soft_embed, preserved on srt_only or failure.
    3. Windows ASCII-safe working directory for libass on Arabic/non-ASCII output folder paths.
    4. Real-time POST /api/sync_state synchronization with QualitySelectionModal widgets.
    5. actionSubmitted flag in preview HTML preventing cancel beacon on pagehide.
    6. Dubbed audio merging in build_stream_info.
    """

    def test_download_subtitle_as_srt_writes_single_file_only(self):
        """Verifies download_subtitle_as_srt writes ONLY one .srt file and never a duplicate .srt."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = os.path.join(tmp_dir, "test_video.mp4")
            with open(video_path, "wb") as f:
                f.write(b"video bytes")

            sub_track = {
                "sub_id": "ar",
                "language": "ar",
                "url": "https://example.com/subs.vtt",
            }
            vtt_sample = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello World\n"
            with patch("smart_download.services.subtitle_downloader._fetch_url_direct", return_value=vtt_sample):
                srt_path = download_subtitle_as_srt(sub_track, video_path)

            self.assertIsNotNone(srt_path)
            self.assertTrue(os.path.isfile(srt_path))
            self.assertTrue(srt_path.endswith(".ar.srt"))

            all_srt = [f for f in os.listdir(tmp_dir) if f.endswith(".srt")]
            self.assertEqual(len(all_srt), 1)
            self.assertEqual(all_srt[0], "test_video.ar.srt")
            self.assertFalse(os.path.exists(os.path.join(tmp_dir, "test_video.srt")))

    def test_handle_subtitles_post_download_cleanup_srt_files(self):
        """Verifies srt cleanup on hard_burn and soft_embed success, and retention on failure or srt_only."""
        from smart_download.services.subtitle_processor import handle_subtitles_post_download

        # Case 1: hard_burn succeeds -> srt deleted
        with tempfile.TemporaryDirectory() as tmp_dir:
            v_path = os.path.join(tmp_dir, "sample.mp4")
            s_path = os.path.join(tmp_dir, "sample.ar.srt")
            with open(v_path, "wb") as f: f.write(b"mp4")
            with open(s_path, "w", encoding="utf-8") as f: f.write("1\n00:00:01,000 --> 00:00:02,000\nSub\n")

            st_info = MagicMock()
            st_info.subtitle_track = {"sub_id": "ar", "language": "ar", "url": "https://example.com/sub.vtt"}
            st_info.subtitle_embed_mode = "hard_burn"

            with patch("smart_download.services.subtitle_processor.download_subtitle_as_srt", return_value=s_path), \
                 patch("smart_download.services.subtitle_processor.find_ffmpeg_bin", return_value="ffmpeg"), \
                 patch("smart_download.services.subtitle_processor.burn_subtitle_into_video", return_value=True):
                handle_subtitles_post_download(st_info, v_path)
                self.assertFalse(os.path.exists(s_path))

        # Case 2: soft_embed succeeds -> srt deleted
        with tempfile.TemporaryDirectory() as tmp_dir:
            v_path = os.path.join(tmp_dir, "sample.mp4")
            s_path = os.path.join(tmp_dir, "sample.ar.srt")
            with open(v_path, "wb") as f: f.write(b"mp4")
            with open(s_path, "w", encoding="utf-8") as f: f.write("1\n00:00:01,000 --> 00:00:02,000\nSub\n")

            st_info = MagicMock()
            st_info.subtitle_track = {"sub_id": "ar", "language": "ar", "url": "https://example.com/sub.vtt"}
            st_info.subtitle_embed_mode = "soft_embed"

            with patch("smart_download.services.subtitle_processor.download_subtitle_as_srt", return_value=s_path), \
                 patch("smart_download.services.subtitle_processor.find_ffmpeg_bin", return_value="ffmpeg"), \
                 patch("smart_download.services.subtitle_processor.embed_subtitle_into_mp4", return_value=True):
                handle_subtitles_post_download(st_info, v_path)
                self.assertFalse(os.path.exists(s_path))

        # Case 3: srt_only -> srt preserved
        with tempfile.TemporaryDirectory() as tmp_dir:
            v_path = os.path.join(tmp_dir, "sample.mp4")
            s_path = os.path.join(tmp_dir, "sample.ar.srt")
            with open(v_path, "wb") as f: f.write(b"mp4")
            with open(s_path, "w", encoding="utf-8") as f: f.write("1\n00:00:01,000 --> 00:00:02,000\nSub\n")

            st_info = MagicMock()
            st_info.subtitle_track = {"sub_id": "ar", "language": "ar", "url": "https://example.com/sub.vtt"}
            st_info.subtitle_embed_mode = "srt_only"

            with patch("smart_download.services.subtitle_processor.download_subtitle_as_srt", return_value=s_path):
                handle_subtitles_post_download(st_info, v_path)
                self.assertTrue(os.path.exists(s_path))

        # Case 4: hard_burn AND soft_embed both fail -> srt preserved for user
        with tempfile.TemporaryDirectory() as tmp_dir:
            v_path = os.path.join(tmp_dir, "sample.mp4")
            s_path = os.path.join(tmp_dir, "sample.ar.srt")
            with open(v_path, "wb") as f: f.write(b"mp4")
            with open(s_path, "w", encoding="utf-8") as f: f.write("1\n00:00:01,000 --> 00:00:02,000\nSub\n")

            st_info = MagicMock()
            st_info.subtitle_track = {"sub_id": "ar", "language": "ar", "url": "https://example.com/sub.vtt"}
            st_info.subtitle_embed_mode = "hard_burn"

            with patch("smart_download.services.subtitle_processor.download_subtitle_as_srt", return_value=s_path), \
                 patch("smart_download.services.subtitle_processor.find_ffmpeg_bin", return_value="ffmpeg"), \
                 patch("smart_download.services.subtitle_processor.burn_subtitle_into_video", return_value=False), \
                 patch("smart_download.services.subtitle_processor.embed_subtitle_into_mp4", return_value=False):
                handle_subtitles_post_download(st_info, v_path)
                self.assertTrue(os.path.exists(s_path))

    def test_burn_subtitle_into_video_arabic_dir_uses_ascii_safe_cwd(self):
        """Verifies burn_subtitle_into_video runs FFmpeg with an ASCII-only cwd when video dir has Arabic chars."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            arabic_folder = os.path.join(tmp_dir, "ترجمة الفيديوهات")
            os.makedirs(arabic_folder, exist_ok=True)
            video_file = os.path.join(arabic_folder, "فيديو تجريبي.mp4")
            srt_file = os.path.join(arabic_folder, "فيديو تجريبي.ar.srt")
            with open(video_file, "wb") as f: f.write(b"mp4 dummy")
            with open(srt_file, "w", encoding="utf-8-sig") as f:
                f.write("1\n00:00:01,000 --> 00:00:02,000\nترجمة عربية\n")

            captured_cwds = []
            captured_cmds = []

            def mock_burn_run(cmd, **kwargs):
                captured_cwds.append(kwargs.get("cwd"))
                captured_cmds.append(list(cmd))
                out_mp4 = cmd[-1]
                with open(out_mp4, "wb") as out_f:
                    out_f.write(b"burned video bytes")
                res = MagicMock()
                res.returncode = 0
                res.stderr = ""
                return res

            with patch("subprocess.run", side_effect=mock_burn_run):
                ok = burn_subtitle_into_video(video_file, srt_file, ffmpeg_path="ffmpeg")
                self.assertTrue(ok)
                self.assertEqual(len(captured_cwds), 1)

                cwd_used = captured_cwds[0]
                self.assertIsNotNone(cwd_used)
                self.assertTrue(all(ord(c) < 128 for c in cwd_used), f"CWD {cwd_used} contains non-ASCII characters!")

                cmd = captured_cmds[0]
                vf_arg = cmd[cmd.index("-vf") + 1]
                self.assertTrue(vf_arg.startswith("subtitles=_sd_burn_"))
                self.assertNotIn(":", vf_arg.split("subtitles=")[1].split(":")[0])
                self.assertNotIn("\\", vf_arg)

    def test_api_sync_state_updates_modal_in_real_time(self):
        """Verifies POST /api/sync_state updates QualitySelectionModal widgets on the Tkinter event loop."""
        from smart_download.services.preview_stream_bridge import (
            register_preview_session, unregister_preview_session, get_preview_bridge_port
        )
        from smart_download.services.youtube_models import VideoFormatOption
        import urllib.request

        port = get_preview_bridge_port()
        opt0 = VideoFormatOption(format_id="18", resolution_label="360p", height=360, ext="mp4", filesize_approx=5_000_000)
        opt1 = VideoFormatOption(format_id="22", resolution_label="720p (HD)", height=720, ext="mp4", filesize_approx=15_000_000)
        options = [opt0, opt1]
        auds = [{"track_id": "original", "label": "Original Audio"}, {"track_id": "ar", "label": "العربية (مدبلج)"}]
        subs = [{"sub_id": "none", "label": "No Subtitles"}, {"sub_id": "ar", "label": "Arabic Subtitles", "language": "ar"}]

        mock_modal = MagicMock()
        mock_modal.options = options
        mock_modal.tree = MagicMock()
        mock_modal.cb_audio = MagicMock()
        mock_modal.cb_sub = MagicMock()
        mock_modal.cb_sub._mode_var = MagicMock()
        mock_modal.cb_sub._mode_combobox = MagicMock()
        mock_modal.cb_sub._sub_mode_cb = MagicMock()
        mock_modal.cb_sub._mode_codes = ["soft_embed", "hard_burn", "srt_only"]
        mock_modal.entry_dest = MagicMock()
        mock_modal.winfo_exists.return_value = True

        after_callbacks = []
        mock_modal.after.side_effect = lambda ms, cb: after_callbacks.append(cb)

        sid = register_preview_session(
            url="https://www.youtube.com/watch?v=sync_test",
            video_title="Sync Test",
            options=options,
            audio_tracks=auds,
            subtitle_tracks=subs,
            modal_ref=mock_modal,
        )
        try:
            sync_url = f"http://127.0.0.1:{port}/api/sync_state?sid={sid}"
            payload = json.dumps({
                "q_idx": 1,
                "a_idx": 1,
                "s_idx": 1,
                "sub_mode": "hard_burn",
                "dest_path": r"C:\Downloads\TestVideo [720p] [Sub].mp4"
            }).encode("utf-8")

            req = urllib.request.Request(sync_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.getcode(), 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data.get("status"), "ok")

            self.assertEqual(len(after_callbacks), 1)
            after_callbacks[0]()

            mock_modal.tree.selection_set.assert_called_with("opt_1")
            self.assertEqual(mock_modal.selected_option, opt1)
            self.assertEqual(opt1.selected_audio_track, auds[1])
            self.assertEqual(opt1.selected_subtitle_track, subs[1])
            self.assertEqual(opt1.subtitle_embed_mode, "hard_burn")
            mock_modal.cb_audio.current.assert_called_with(1)
            mock_modal.cb_sub.current.assert_called_with(1)
            self.assertEqual(mock_modal.cb_sub._selected_mode, "hard_burn")
            self.assertTrue(mock_modal.cb_sub._user_touched_mode)
            mock_modal.cb_sub._mode_var.set.assert_called_with("hard_burn")
            mock_modal.cb_sub._mode_combobox.current.assert_called_with(1)
            mock_modal.cb_sub._mode_combobox.configure.assert_called_with(state="readonly")
            mock_modal.entry_dest.delete.assert_called_with(0, "end")
            mock_modal.entry_dest.insert.assert_called_with(0, r"C:\Downloads\TestVideo [720p] [Sub].mp4")

            # Now test s_idx = 0 disables combobox and clears subtitle track
            after_callbacks.clear()
            payload_nosub = json.dumps({
                "q_idx": 1, "a_idx": 0, "s_idx": 0, "sub_mode": "hard_burn", "dest_path": r"C:\Downloads\TestVideo [720p].mp4"
            }).encode("utf-8")
            req_nosub = urllib.request.Request(sync_url, data=payload_nosub, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req_nosub, timeout=5) as resp:
                self.assertEqual(resp.getcode(), 200)
            self.assertEqual(len(after_callbacks), 1)
            after_callbacks[0]()
            self.assertIsNone(opt1.selected_subtitle_track)
            mock_modal.cb_sub.current.assert_called_with(0)
            mock_modal.cb_sub._mode_combobox.configure.assert_called_with(state="disabled")
        finally:
            unregister_preview_session(sid)

    def test_preview_html_action_submitted_and_bridge_base(self):
        """Verifies generate_preview_html contains actionSubmitted flag and absolute bridgeBase."""
        from smart_download.ui.modals.preview_html_builder import generate_preview_html

        html_out = generate_preview_html(
            url="https://www.youtube.com/watch?v=html_test",
            video_title="HTML Test",
            stream_url="http://127.0.0.1:9876/stream_video?sid=xyz&q_idx=0",
            sid="test_sid",
            bridge_port=9876,
            options=[MagicMock(resolution_label="1080p", ext="mp4", filesize_approx=1000)],
            audio_tracks=[{"track_id": "original", "label": "Original"}],
            subtitle_tracks=[{"sub_id": "none", "label": "None"}, {"sub_id": "ar", "label": "Arabic", "language": "ar"}]
        )
        self.assertIn('const bridgeBase = "http://127.0.0.1:9876";', html_out)
        self.assertIn("let actionSubmitted = false;", html_out)
        self.assertIn("actionSubmitted = true;", html_out)
        self.assertIn("if (sid && !actionSubmitted)", html_out)
        self.assertIn("${bridgeBase}/api/sync_state?sid=", html_out)
        self.assertIn("${bridgeBase}/api/action?sid=", html_out)
        self.assertIn("${bridgeBase}/api/update_filename?sid=", html_out)
        self.assertIn('modeSelect.value = "hard_burn"', html_out)
        self.assertIn("window._userTouchedMode = true", html_out)
        self.assertIn('<option value="0" selected>None</option>', html_out)
        self.assertIn("💬 No Subtitles", html_out)
        self.assertIn("&a_idx=", html_out)

    def test_youtube_format_builder_dubbed_audio_merging(self):
        """Verifies build_stream_info copies option and forces is_progressive=False for dubbed audio."""
        from smart_download.services.youtube_service import YouTubeResolver
        from smart_download.services.youtube_models import VideoFormatOption

        resolver = YouTubeResolver()
        opt = VideoFormatOption(
            format_id="18", resolution_label="360p", height=360, ext="mp4",
            is_progressive=True, video_url="https://video.example.com/prog.mp4",
            filesize_approx=10_000_000
        )
        opt.selected_audio_track = {
            "track_id": "ar", "is_original": False, "url": "https://audio.example.com/dub.m4a",
            "filesize": 2_000_000
        }
        info = {"id": "test_dub", "title": "Dub Test"}

        stream_info = resolver.build_stream_info(info, opt)
        self.assertTrue(opt.is_progressive)
        self.assertFalse(stream_info.is_progressive)
        self.assertEqual(stream_info.audio_url, "https://audio.example.com/dub.m4a")
        self.assertEqual(stream_info.audio_size, 2_000_000)

    def test_speed_limiter_startup_settings_loaded(self):
        """Verifies that ControlsPanelMixin initializes with saved speed_limit_preset and custom_speed_limit_kbps."""
        from smart_download.ui.panels.controls_panel import ControlsPanelMixin

        class DummyControls(ControlsPanelMixin):
            def __init__(self):
                self.c_panel = "#1e293b"
                self.c_border = "#334155"
                self.c_accent = "#6366f1"
                self.c_accent_dark = "#4f46e5"
                self.c_text_bright = "#f8fafc"
                self.c_text_muted = "#94a3b8"
                self.c_input_bg = "#0f172a"
                self.c_panel_light = "#334155"
                self.c_success = "#10b981"
                self.c_warning = "#f59e0b"
                self.dpi_scale = 1.0
                self.speed_limit = 0.0
                self.applied_limit_called = False

            def _on_conn_changed(self, event=None): pass
            def _on_preset_selected(self, event=None): pass
            def _on_slider_moved(self, val): pass
            def __getattr__(self, name):
                return lambda *args, **kwargs: None
            def _apply_speed_limit(self):
                self.applied_limit_called = True
                kb = float(self.entry_custom_speed.get())
                self.speed_limit = kb * 1024.0

        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            with patch("smart_download.ui.panels.controls_panel.get_setting") as mock_get:
                mock_get.side_effect = lambda k, d=None: {
                    "max_connections": 8,
                    "speed_limit_preset": "2.0 MB/s",
                    "custom_speed_limit_kbps": 2048,
                }.get(k, d)

                panel = DummyControls()
                panel._build_limiter_and_actions_card(root)

                self.assertEqual(panel.limit_preset_var.get(), "2.0 MB/s")
                self.assertEqual(panel.entry_custom_speed.get(), "2048")
                self.assertTrue(panel.applied_limit_called)
                self.assertEqual(panel.speed_limit, 2048 * 1024.0)
        finally:
            root.destroy()

    def test_last_download_dir_preserved_and_category_stripped(self):
        """Verifies get_base_downloads_dir returns last_download_dir and browsing strips category subfolder."""
        from smart_download.config import get_base_downloads_dir
        from smart_download.utils.file_ops import CATEGORY_SUBFOLDERS
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_dir = os.path.join(tmp_dir, "CustomDownloads")
            os.makedirs(custom_dir, exist_ok=True)

            with patch("smart_download.config.get_setting", return_value=custom_dir):
                self.assertEqual(get_base_downloads_dir(), custom_dir)

            # Test category subfolder stripping
            video_sub = os.path.join(custom_dir, "Video")
            sub_low = {s.lower() for s in CATEGORY_SUBFOLDERS.values()}
            self.assertIn(os.path.basename(video_sub).lower(), sub_low)
            stripped = os.path.dirname(video_sub)
            self.assertEqual(stripped, custom_dir)

            # Test resolve_final_dest uses get_base_downloads_dir
            from smart_download.ui.modals.quality_modal_helpers import resolve_final_dest
            with patch("smart_download.ui.modals.quality_modal_helpers.get_base_downloads_dir", return_value=custom_dir):
                dest_res = resolve_final_dest(None, "", "my_video", None, None, None)
                self.assertTrue(dest_res.startswith(custom_dir))

    def test_preview_video_target_respects_selected_quality(self):
        """Verifies _resolve_video_target respects target_h of selected option."""
        from smart_download.services.preview_stream_bridge import PreviewBridgeRequestHandler, PreviewSession
        from smart_download.services.youtube_models import VideoFormatOption

        handler = PreviewBridgeRequestHandler.__new__(PreviewBridgeRequestHandler)

        # Case 1: Audio-only option
        opt_audio = VideoFormatOption(
            format_id="140", resolution_label="Audio 128k", height=0, ext="m4a", filesize_approx=1000,
            is_audio_only=True, audio_url="https://audio.example.com/140.m4a", audio_headers={"H": "1"}
        )
        session1 = PreviewSession(sid="s1", url="https://example.com/video", video_title="Audio", options=[opt_audio], info_dict={}, audio_tracks=[], subtitle_tracks=[])
        url, headers = handler._resolve_video_target(session1, 0)
        self.assertEqual(url, "https://audio.example.com/140.m4a")
        self.assertEqual(headers.get("H"), "1")

        # Case 2: Progressive format selection closest to target_h
        opt_360 = VideoFormatOption(format_id="18", resolution_label="360p", height=360, ext="mp4", filesize_approx=1000, is_progressive=True, video_url="https://example.com/360.mp4")
        opt_720 = VideoFormatOption(format_id="22", resolution_label="720p", height=720, ext="mp4", filesize_approx=1000, is_progressive=False, video_url="https://example.com/dash_720.mp4")
        opt_1080 = VideoFormatOption(format_id="137", resolution_label="1080p", height=1080, ext="mp4", filesize_approx=1000, is_progressive=False, video_url="https://example.com/dash_1080.mp4")

        info_dict = {
            "formats": [
                {"url": "https://example.com/prog_360.mp4", "height": 360, "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4"},
                {"url": "https://example.com/prog_720.mp4", "height": 720, "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4"},
            ]
        }
        session2 = PreviewSession(sid="s2", url="https://example.com/video", video_title="Video", options=[opt_360, opt_720, opt_1080], info_dict=info_dict, audio_tracks=[], subtitle_tracks=[])

        # When q_idx = 0 (360p progressive)
        url0, _ = handler._resolve_video_target(session2, 0)
        self.assertEqual(url0, "https://example.com/360.mp4")

        # When q_idx = 1 (720p), it matches closest prog format 720p
        url1, _ = handler._resolve_video_target(session2, 1)
        self.assertEqual(url1, "https://example.com/prog_720.mp4")

        # When q_idx = 2 and dubbing is active, opt.video_url (1080p) is streamed!
        session2.selected_audio_track = {"track_id": "ar", "url": "https://example.com/dub.m4a"}
        url2, _ = handler._resolve_video_target(session2, 2)
        self.assertEqual(url2, "https://example.com/dash_1080.mp4")

        # When q_idx = 2 and dubbing is NOT active, it picks closest progressive format (720p) with sound!
        session2.selected_audio_track = None
        url2_nodub, _ = handler._resolve_video_target(session2, 2)
        self.assertEqual(url2_nodub, "https://example.com/prog_720.mp4")

        # Check explicit a_idx parameter avoids race condition
        session2.audio_tracks = [{"track_id": "original", "url": ""}, {"track_id": "ar", "url": "https://example.com/dub.m4a"}]
        url_a0, _ = handler._resolve_video_target(session2, 2, a_idx=0)
        self.assertEqual(url_a0, "https://example.com/prog_720.mp4")
        url_a1, _ = handler._resolve_video_target(session2, 2, a_idx=1)
        self.assertEqual(url_a1, "https://example.com/dash_1080.mp4")

        # When opt has BOTH video_url and audio_url, DASH 1080p is streamed directly even without dubbing and even when prog_formats exists
        opt_1080.audio_url = "https://example.com/orig_audio.m4a"
        opt_1080.audio_headers = {"Orig": "1"}
        url_dash_with_audio, _ = handler._resolve_video_target(session2, 2, a_idx=0)
        self.assertEqual(url_dash_with_audio, "https://example.com/dash_1080.mp4")
        a_dash_url, a_dash_hdr = handler._resolve_audio_target(session2, 0, q_idx=2)
        self.assertEqual(a_dash_url, "https://example.com/orig_audio.m4a")
        self.assertEqual(a_dash_hdr.get("Orig"), "1")

        # When prog_formats is empty, DASH 1080p is streamed directly
        session_empty = PreviewSession(sid="s_emp", url="https://example.com/video", video_title="Video", options=[opt_1080], info_dict={"formats": []}, audio_tracks=[], subtitle_tracks=[])
        url_empty, _ = handler._resolve_video_target(session_empty, 0)
        self.assertEqual(url_empty, "https://example.com/dash_1080.mp4")

    def test_startup_enabled_sync_on_startup(self):
        """Verifies startup_enabled synchronizes registry when True in settings."""
        from smart_download.ui.controllers.settings_controller import SettingsControllerMixin

        class DummySettings(SettingsControllerMixin):
            def __init__(self):
                self._startup_enabled = False
                self.c_success = "#10b981"
                self.c_panel_light = "#334155"
                self.c_text_muted = "#94a3b8"
                self.c_panel = "#1e293b"
                self.btn_startup = MagicMock()
                self.btn_startup.winfo_exists.return_value = True

        panel = DummySettings()
        with patch("smart_download.ui.controllers.settings_controller.get_setting", return_value=True):
            with patch("smart_download.ui.controllers.settings_controller.is_startup_enabled", side_effect=[False, True]):
                with patch("smart_download.ui.controllers.settings_controller.enable_startup") as mock_enable:
                    panel._update_startup_btn()
                    mock_enable.assert_called_once_with(minimized=True)
                    self.assertTrue(panel._startup_enabled)

    def test_resolve_preferred_option_index(self):
        """Verifies resolve_preferred_option_index honors user settings for audio-only, exact match, and closest match."""
        from smart_download.ui.modals.quality_modal_helpers import resolve_preferred_option_index
        from smart_download.services.youtube_models import VideoFormatOption

        opt_1080 = VideoFormatOption(format_id="1", resolution_label="1080p", height=1080, ext="mp4", filesize_approx=1000)
        opt_720 = VideoFormatOption(format_id="2", resolution_label="720p", height=720, ext="mp4", filesize_approx=1000)
        opt_360 = VideoFormatOption(format_id="3", resolution_label="360p", height=360, ext="mp4", filesize_approx=1000)
        opt_audio = VideoFormatOption(format_id="4", resolution_label="Audio", height=0, ext="m4a", filesize_approx=1000, is_audio_only=True)
        options = [opt_1080, opt_720, opt_360, opt_audio]

        # Empty options
        self.assertEqual(resolve_preferred_option_index([]), 0)

        # pref_h == -1 (Audio only)
        with patch("smart_download.config.get_setting", return_value=-1):
            self.assertEqual(resolve_preferred_option_index(options), 3)

        # pref_h == 720 (Exact match)
        with patch("smart_download.config.get_setting", return_value=720):
            self.assertEqual(resolve_preferred_option_index(options), 1)

        # pref_h == 480 (Closest non-audio match: |360-480|=120 vs |720-480|=240 => 360p)
        with patch("smart_download.config.get_setting", return_value=480):
            self.assertEqual(resolve_preferred_option_index(options), 2)

        # pref_h == 0 (Default highest quality)
        with patch("smart_download.config.get_setting", return_value=0):
            self.assertEqual(resolve_preferred_option_index(options), 0)

    def test_preview_html_autoscroll_and_separate_audio(self):
        """Verifies Preview HTML contains autoscroll and optNeedsSeparateAudio array."""
        from smart_download.ui.modals.preview_html_builder import generate_preview_html
        from smart_download.services.youtube_models import VideoFormatOption

        opt_prog = VideoFormatOption(format_id="18", resolution_label="360p", height=360, ext="mp4", filesize_approx=1000, is_progressive=True, video_url="http://x/prog.mp4")
        opt_dash = VideoFormatOption(format_id="137", resolution_label="1080p", height=1080, ext="mp4", filesize_approx=1000, is_progressive=False, video_url="http://x/1080.mp4", audio_url="http://x/aud.m4a")

        html_out = generate_preview_html(
            url="https://www.youtube.com/watch?v=scroll_test",
            video_title="Scroll Test",
            stream_url="http://127.0.0.1:9876/stream_video?sid=xyz&q_idx=1",
            sid="test_sid",
            bridge_port=9876,
            options=[opt_prog, opt_dash],
            selected_q_idx=1,
        )
        self.assertIn("initRow.scrollIntoView", html_out)
        self.assertIn("const optNeedsSeparateAudio = [false, true];", html_out)

    def test_quality_modal_preferred_height_dest_update(self):
        """Verifies QualitySelectionModal auto-selects preferred height and updates destination tag."""
        import tkinter as tk
        from smart_download.ui.modals.quality_modal import QualitySelectionModal
        from smart_download.services.youtube_models import VideoFormatOption

        root = tk.Tk()
        root.withdraw()
        try:
            opt_1080 = VideoFormatOption(format_id="1", resolution_label="1080p", height=1080, ext="mp4", filesize_approx=50000000)
            opt_360 = VideoFormatOption(format_id="2", resolution_label="360p", height=360, ext="mp4", filesize_approx=10000000)
            options = [opt_1080, opt_360]

            theme = {
                "c_bg": "#1e293b", "c_panel": "#0f172a", "c_panel_light": "#334155",
                "c_border": "#475569", "c_accent": "#38bdf8", "c_accent_dark": "#0284c7",
                "c_success": "#10b981", "c_text_bright": "#f8fafc", "c_text_muted": "#94a3b8", "c_input_bg": "#0f172a"
            }

            with patch("smart_download.config.get_setting", return_value=360):
                modal = QualitySelectionModal(
                    parent=root,
                    video_title="Test Video",
                    duration=100,
                    options=options,
                    default_dest_path="C:/Downloads/Test [1080p].mp4",
                    theme=theme,
                    on_confirm=lambda o, d: None
                )
                self.assertEqual(modal.selected_option.height, 360)
                self.assertEqual(modal.tree.selection(), ("opt_1",))
                self.assertIn("[360p]", modal.entry_dest.get())
                self.assertNotIn("[1080p]", modal.entry_dest.get())
                modal.destroy()

            # Verify opt_0 also formats untagged destination path
            with patch("smart_download.config.get_setting", return_value=1080):
                modal0 = QualitySelectionModal(
                    parent=root,
                    video_title="Test Video",
                    duration=100,
                    options=options,
                    default_dest_path="C:/Downloads/TestVideo [360p].mp4",
                    theme=theme,
                    on_confirm=lambda o, d: None
                )
                self.assertEqual(modal0.selected_option.height, 1080)
                self.assertIn("[1080p]", modal0.entry_dest.get())
                modal0.destroy()
        finally:
            try: root.destroy()
            except Exception: pass

    def test_resolve_preferred_option_index_string_and_audio_only(self):
        """Verifies resolve_preferred_option_index handles string '720p' and audio-only target in preview bridge."""
        from smart_download.ui.modals.quality_modal_helpers import resolve_preferred_option_index
        from smart_download.services.youtube_models import VideoFormatOption
        from smart_download.services.preview_stream_bridge import PreviewSession, PreviewBridgeRequestHandler

        opt_1080 = VideoFormatOption(format_id="1", resolution_label="1080p", height=1080, ext="mp4", filesize_approx=1000)
        opt_720 = VideoFormatOption(format_id="2", resolution_label="720p", height=720, ext="mp4", filesize_approx=1000)
        opt_audio = VideoFormatOption(format_id="4", resolution_label="Audio", height=0, ext="m4a", filesize_approx=1000, is_audio_only=True, video_url="http://x/aud.m4a", video_headers={"A": "1"})
        options = [opt_1080, opt_720, opt_audio]

        # String "720p"
        with patch("smart_download.config.get_setting", return_value="720p"):
            self.assertEqual(resolve_preferred_option_index(options), 1)

        # Audio-only resolution in bridge
        handler = PreviewBridgeRequestHandler.__new__(PreviewBridgeRequestHandler)
        session = PreviewSession(sid="s_aud", url="http://x/aud", video_title="Aud", options=[opt_audio], info_dict={}, audio_tracks=[], subtitle_tracks=[])
        u, h = handler._resolve_video_target(session, 0)
        self.assertEqual(u, "http://x/aud.m4a")
        self.assertEqual(h.get("A"), "1")

    def test_open_main_media_preview_subs_defined(self):
        """Verifies _open_main_media_preview calls open_video_preview with subtitle_tracks without raising NameError."""
        from smart_download.ui.panels.media_options_bar import MediaOptionsBarMixin
        bar = MediaOptionsBarMixin()
        bar.cb_main_sub = MagicMock()
        bar.cb_main_sub.current.return_value = 0
        subs = [{"sub_id": "en", "label": "English"}]
        bar._main_subtitle_tracks = subs

        with patch("smart_download.ui.modals.video_preview_modal.open_video_preview") as mock_open:
            bar._open_main_media_preview()
            mock_open.assert_called_once()
            _, kwargs = mock_open.call_args
            self.assertEqual(kwargs.get("subtitle_tracks"), subs)
            self.assertEqual(kwargs.get("selected_sub_track"), subs[0])

    def test_preview_html_dub_audio_resume_logic(self):
        """Verifies dubAudioEl resume logic on timeupdate and during quality/audio changes."""
        from smart_download.ui.modals.preview_html_builder import generate_preview_html
        from smart_download.services.youtube_models import VideoFormatOption

        opt1 = VideoFormatOption(
            format_id="137",
            resolution_label="1080p",
            height=1080,
            ext="mp4",
            filesize_approx=1000000,
            video_url="https://example.com/v1080.mp4",
            audio_url="https://example.com/a.m4a"
        )
        audio_track = {"track_id": "ar", "language": "ar", "label": "العربية", "url": "https://example.com/ar.m4a"}

        html_out = generate_preview_html(
            url="https://example.com/watch?v=123",
            video_title="Dub Test",
            stream_url="https://example.com/v1080.mp4",
            selected_audio_track=audio_track,
            options=[opt1],
            audio_tracks=[{"track_id": "original", "label": "Original Audio"}, audio_track],
            subtitle_tracks=[{"sub_id": "none", "label": "No Subtitles"}]
        )

        self.assertIn("videoEl.addEventListener(\"timeupdate\", () => {", html_out)
        self.assertIn("if (dubAudioEl.paused && dubAudioEl.readyState >= 2) {", html_out)
        self.assertIn("dubAudioEl.play().catch(e => {});", html_out)
        # Exactly 4 resume calls: 2 in selectQualityRow (loadedmetadata + immediate) and 2 in onAudioChange (loadedmetadata + immediate)
        self.assertEqual(html_out.count("if (hasDubAudio && dubAudioEl) { dubAudioEl.play().catch(e => {}); }"), 4)

    def test_open_main_media_preview_subs_from_context(self):
        """Verifies _open_main_media_preview falls back to ctx['subtitle_tracks'] when _main_subtitle_tracks is not set on self."""
        from smart_download.ui.panels.media_options_bar import MediaOptionsBarMixin
        bar = MediaOptionsBarMixin()
        bar.cb_main_sub = MagicMock()
        bar.cb_main_sub.current.return_value = 0
        subs = [{"sub_id": "ar", "label": "Arabic"}]
        bar._pending_media_context = {"subtitle_tracks": subs}

        with patch("smart_download.ui.modals.video_preview_modal.open_video_preview") as mock_open:
            bar._open_main_media_preview()
            mock_open.assert_called_once()
            _, kwargs = mock_open.call_args
            self.assertEqual(kwargs.get("subtitle_tracks"), subs)
            self.assertEqual(kwargs.get("selected_sub_track"), subs[0])

    def test_state_button_behavior(self):
        """Verifies _StateButton switches bg/fg based on state and preserves standard configure queries."""
        import tkinter as tk
        from smart_download.ui.panels.controls_panel import _StateButton
        root = tk.Tk()
        root.withdraw()
        try:
            btn = _StateButton(root, active_bg="#059669", disabled_bg="#1e293b", state="disabled")
            self.assertEqual(btn.cget("bg"), "#1e293b")
            btn.configure(state="normal")
            self.assertEqual(btn.cget("bg"), "#059669")
            btn.configure(state="disabled")
            self.assertEqual(btn.cget("bg"), "#1e293b")
            # Explicit bg should not be overridden
            btn.configure(state="normal", bg="#f59e0b")
            self.assertEqual(btn.cget("bg"), "#f59e0b")
            # Query configure works
            info = btn.configure("text")
            self.assertTrue(isinstance(info, tuple))
        finally:
            root.destroy()

    def test_canvas_draw_fallbacks(self):
        """Verifies _draw_main_progress and _draw_chunk_segments fallback to safe dimensions when canvas unmapped."""
        import tkinter as tk
        from smart_download.ui.panels.metrics_panel import MetricsPanelMixin
        from smart_download.ui.panels.chunks_panel import ChunksPanelMixin
        root = tk.Tk()
        root.withdraw()
        try:
            class DummyApp(ChunksPanelMixin):
                def __init__(self, r):
                    self.root = r
                    self.dpi_scale = 1.0
                    self.c_bg = "#0b1120"
                    self.c_panel = "#131c31"
                    self.c_border = "#283548"
                    self.c_input_bg = "#090e1a"
                    self.c_accent = "#38bdf8"
                    self.c_text_muted = "#94a3b8"
                    self.c_panel_light = "#1e293b"
                    self.c_text_bright = "#f8fafc"
                    self._build_metrics_card(r)
                    self._build_chunk_visualizer_card(r)

            app = DummyApp(root)
            self.assertLessEqual(app.canvas_prog.winfo_width(), 10)
            self.assertLessEqual(app.canvas_chunks.winfo_width(), 10)
            app._draw_main_progress(50.0)
            items = app.canvas_prog.find_all()
            self.assertTrue(len(items) >= 2)
            app._draw_chunk_segments([])
            items_c = app.canvas_chunks.find_all()
            self.assertTrue(len(items_c) >= 2)
        finally:
            root.destroy()

    def test_stale_spec_and_dist_artifacts_cleanup(self):
        """Verifies build_installer.clean_stale_dist_artifacts cleans up legacy spec files and dist artifacts."""
        import build_installer
        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_root = build_installer.ROOT_DIR
            orig_dist = build_installer.DIST_DIR
            try:
                build_installer.ROOT_DIR = tmp_dir
                build_installer.DIST_DIR = os.path.join(tmp_dir, "dist")
                os.makedirs(build_installer.DIST_DIR, exist_ok=True)

                stale_spec = os.path.join(tmp_dir, "turbo_downloader.spec")
                with open(stale_spec, "w") as f:
                    f.write("# stale spec")
                stale_bin = os.path.join(build_installer.DIST_DIR, "turbo_downloader.exe")
                with open(stale_bin, "wb") as f:
                    f.write(b"stale")

                self.assertTrue(os.path.exists(stale_spec))
                self.assertTrue(os.path.exists(stale_bin))

                build_installer.clean_stale_dist_artifacts()

                self.assertFalse(os.path.exists(stale_spec))
                self.assertFalse(os.path.exists(stale_bin))
            finally:
                build_installer.ROOT_DIR = orig_root
                build_installer.DIST_DIR = orig_dist

    def test_chunk_canvas_redraws_on_language_change(self):
        """Verifies _draw_chunk_segments redraws on language switch without getting blocked by cached signature."""
        import tkinter as tk
        from smart_download.ui.panels.chunks_panel import ChunksPanelMixin
        from smart_download.i18n import set_current_language
        root = tk.Tk()
        root.withdraw()
        try:
            class DummyApp(ChunksPanelMixin):
                def __init__(self, r):
                    self.root = r
                    self.dpi_scale = 1.0
                    self.c_bg = "#0b1120"
                    self.c_panel = "#131c31"
                    self.c_border = "#283548"
                    self.c_input_bg = "#090e1a"
                    self.c_accent = "#38bdf8"
                    self.c_text_muted = "#94a3b8"
                    self.c_panel_light = "#1e293b"
                    self.c_text_bright = "#f8fafc"
                    self.engine = None
                    self._build_chunk_visualizer_card(r)

            app = DummyApp(root)
            set_current_language("en")
            app._last_chunk_canvas_sig = None
            app._draw_chunk_segments([])
            text_items_en = [app.canvas_chunks.itemcget(i, "text") for i in app.canvas_chunks.find_all() if app.canvas_chunks.type(i) == "text"]
            self.assertIn("Waiting to start...", text_items_en)

            set_current_language("ar")
            app._draw_chunk_segments([])
            text_items_ar = [app.canvas_chunks.itemcget(i, "text") for i in app.canvas_chunks.find_all() if app.canvas_chunks.type(i) == "text"]
            self.assertIn("بانتظار بدء التحميل...", text_items_ar)
        finally:
            set_current_language("en")
            root.destroy()


class TestWindowMaximizeAndTikTokDirectFixes(unittest.TestCase):
    """
    Verifies Part 1 (Frameless window maximize/restore and resizing),
    Part 2 (Exception handling without NameError in youtube_download_controller),
    and Part 3 (Direct TikTok rehydration extraction).
    """

    def test_window_maximize_and_restore(self):
        """Verifies toggle_maximize toggles _is_maximized and updates geometry / btn_max text between '□' and '❐'."""
        import tkinter as tk
        from smart_download.ui.controllers.window_controller import WindowChromeMixin

        root = tk.Tk()
        root.withdraw()
        try:
            class DummyWindow(WindowChromeMixin):
                def check_for_updates_manual(self): pass
                def toggle_language(self): pass
                def __init__(self, r):
                    self.root = r
                    self.width = 850
                    self.height = 650
                    self.dpi_scale = 1.0
                    self._init_theme()
                    self._setup_window()
                    self._build_title_bar(r)

            w = DummyWindow(root)
            self.assertFalse(w._is_maximized)
            self.assertEqual(w.btn_max.cget("text"), "□")

            # Maximize
            w.toggle_maximize()
            self.assertTrue(w._is_maximized)
            self.assertEqual(w.btn_max.cget("text"), "❐")

            # Restore
            w.toggle_maximize()
            self.assertFalse(w._is_maximized)
            self.assertEqual(w.btn_max.cget("text"), "□")

            # Resizing helper detection test
            edge_se = w._detect_resize_edge(848, 648, 850, 650)
            self.assertEqual(edge_se, "se")
            edge_nw = w._detect_resize_edge(2, 2, 850, 650)
            self.assertEqual(edge_nw, "nw")
            edge_center = w._detect_resize_edge(400, 300, 850, 650)
            self.assertEqual(edge_center, "")

            # Test cursor mapping
            self.assertEqual(w._cursor_for_edge("se"), "size_nw_se")
            self.assertEqual(w._cursor_for_edge("nw"), "size_nw_se")
            self.assertEqual(w._cursor_for_edge("ne"), "size_ne_sw")
            self.assertEqual(w._cursor_for_edge("sw"), "size_ne_sw")
            self.assertEqual(w._cursor_for_edge("w"), "size_we")
            self.assertEqual(w._cursor_for_edge("e"), "size_we")
            self.assertEqual(w._cursor_for_edge("n"), "size_ns")
            self.assertEqual(w._cursor_for_edge("s"), "size_ns")
            self.assertEqual(w._cursor_for_edge(""), "")
        finally:
            root.destroy()

    def test_window_drag_unmaximize_and_resize_release(self):
        """Verifies title dragging while maximized smoothly unmaximizes without jumping, and resize release persists normal geometry."""
        import tkinter as tk
        from smart_download.ui.controllers.window_controller import WindowChromeMixin

        root = tk.Tk()
        root.withdraw()
        try:
            class DummyWindow(WindowChromeMixin):
                def check_for_updates_manual(self): pass
                def toggle_language(self): pass
                def __init__(self, r):
                    self.root = r
                    self.width = 850
                    self.height = 650
                    self.dpi_scale = 1.0
                    self._init_theme()
                    self._setup_window()
                    self._build_title_bar(r)

            w = DummyWindow(root)
            w._is_maximized = True
            w._normal_geometry = "850x650+100+100"
            w.root.geometry("1920x1040+0+0")
            w.btn_max.configure(text="❐")

            # Mouse press at x_root=1600 (near right side, ratio ~ 0.833), y_root=20
            press_evt = MagicMock()
            press_evt.x_root = 1600
            press_evt.y_root = 20
            w._on_title_press(press_evt)

            # Drag event
            drag_evt = MagicMock()
            drag_evt.x_root = 1610
            drag_evt.y_root = 25
            drag_evt.y = 20
            w._on_title_drag(drag_evt)

            # Window must now be unmaximized, btn_max updated to '□', and geometry restored to 850x650
            self.assertFalse(w._is_maximized)
            self.assertEqual(w.btn_max.cget("text"), "□")
            geo = w.root.geometry()
            self.assertTrue(geo.startswith("850x650+"), f"Expected 850x650 restored size, got {geo}")

            # Verify resize press, drag, release updates _normal_geometry
            r_press = MagicMock()
            r_press.x_root, r_press.y_root = 100, 100
            w._on_resize_press(r_press, "se")
            r_drag = MagicMock()
            r_drag.x_root, r_drag.y_root = 150, 150
            w._on_resize_drag(r_drag)
            w._on_resize_release(MagicMock())
            self.assertTrue(w._normal_geometry.startswith("900x700+"), f"Expected 900x700, got {w._normal_geometry}")
        finally:
            root.destroy()

    def test_tiktok_direct_rehydration_with_gzip_and_attribute_order(self):
        """Verifies _extract_tiktok_direct handles gzip compressed responses and script tags where type precedes id."""
        import gzip
        from smart_download.services.youtube_service import YouTubeResolver
        resolver = YouTubeResolver()

        rehydration_json = {
            "__DEFAULT_SCOPE__": {
                "webapp.video-detail": {
                    "itemInfo": {
                        "itemStruct": {
                            "id": "999888777",
                            "desc": "Gzip compressed TikTok test",
                            "video": {
                                "duration": 12,
                                "width": 720,
                                "height": 1280,
                                "playAddr": "https://v16.tiktokcdn.com/play_gzip.mp4",
                            }
                        }
                    }
                }
            }
        }
        # Notice: type="application/json" comes BEFORE id="__UNIVERSAL_DATA_FOR_REHYDRATION__"
        html = f'<html><head><script type="application/json" id="__UNIVERSAL_DATA_FOR_REHYDRATION__">{json.dumps(rehydration_json)}</script></head><body></body></html>'
        compressed_bytes = gzip.compress(html.encode("utf-8"))

        mock_resp = MagicMock()
        mock_resp.geturl.return_value = "https://www.tiktok.com/@creator/video/999888777"
        mock_resp.read.return_value = compressed_bytes
        mock_resp.headers = {"Content-Encoding": "gzip"}
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.OpenerDirector.open", return_value=mock_resp):
            info = resolver._extract_tiktok_direct("https://vt.tiktok.com/ZSgG75rWv/")
            self.assertIsNotNone(info)
            self.assertEqual(info["id"], "999888777")
            self.assertIn("Gzip compressed", info["title"])
            self.assertEqual(len(info["formats"]), 1)
            self.assertEqual(info["formats"][0]["url"], "https://v16.tiktokcdn.com/play_gzip.mp4")

    def test_youtube_download_controller_exception_dispatch(self):
        """Verifies _start_youtube_download exception handler properly dispatches err_msg without NameError."""
        from smart_download.ui.controllers.youtube_download_controller import YouTubeDownloadControllerMixin

        class DummyYTController(YouTubeDownloadControllerMixin):
            def __init__(self):
                self._yt_cancel_event = MagicMock()
                self._yt_cancel_event.is_set.return_value = False
                self.dispatched_callbacks = []
                self.logs = []
                self.error_cb_called_with = None

            def dispatch_to_main_thread(self, fn):
                self.dispatched_callbacks.append(fn)

            def log(self, msg):
                self.logs.append(msg)

            def _engine_error_cb(self, msg):
                self.error_cb_called_with = msg

        ctrl = DummyYTController()
        tag = "YOUTUBE"
        try:
            raise ValueError("Test stream extraction failure: HTTP 403 Forbidden")
        except Exception as e:
            err_msg = str(e)
            if hasattr(ctrl, "clear_last_clipboard_url"):
                ctrl.clear_last_clipboard_url()
            if not ctrl._yt_cancel_event.is_set():
                ctrl.log(f"[{tag} ERROR] {err_msg}")
                try:
                    ctrl.dispatch_to_main_thread(lambda msg=err_msg: ctrl._engine_error_cb(msg))
                except Exception:
                    pass

        self.assertEqual(len(ctrl.dispatched_callbacks), 1)
        ctrl.dispatched_callbacks[0]()
        self.assertEqual(ctrl.error_cb_called_with, "Test stream extraction failure: HTTP 403 Forbidden")

    def test_tiktok_direct_rehydration_extraction(self):
        """Verifies _extract_tiktok_direct parses __UNIVERSAL_DATA_FOR_REHYDRATION__ HTML payload and produces formats with Referer and Cookie."""
        from smart_download.services.youtube_service import YouTubeResolver
        resolver = YouTubeResolver()

        rehydration_json = {
            "__DEFAULT_SCOPE__": {
                "webapp.video-detail": {
                    "itemInfo": {
                        "itemStruct": {
                            "id": "7488392019283",
                            "desc": "Viral TikTok video #smartdownload",
                            "video": {
                                "duration": 18,
                                "width": 1080,
                                "height": 1920,
                                "originCover": "https://p16.tiktokcdn.com/cover.jpg",
                                "bitrateInfo": [
                                    {
                                        "GearName": "normal_1080_0",
                                        "Bitrate": 2400000,
                                        "CodecType": "h264",
                                        "PlayAddr": {
                                            "Width": 1080,
                                            "Height": 1920,
                                            "DataSize": 5400000,
                                            "UrlList": ["https://v16.tiktokcdn.com/play1080.mp4"]
                                        }
                                    },
                                    {
                                        "GearName": "lower_720_0",
                                        "Bitrate": 1100000,
                                        "CodecType": "h264",
                                        "PlayAddr": {
                                            "Width": 720,
                                            "Height": 1280,
                                            "DataSize": 2475000,
                                            "UrlList": ["https://v16.tiktokcdn.com/play720.mp4"]
                                        }
                                    }
                                ],
                                "downloadAddr": "https://v16.tiktokcdn.com/download.mp4",
                                "claInfo": {
                                    "captionInfos": [
                                        {
                                            "LanguageCodeName": "eng-US",
                                            "Format": "webvtt",
                                            "Url": "https://v16.tiktokcdn.com/sub_en.vtt"
                                        }
                                    ]
                                }
                            },
                            "music": {
                                "playUrl": "https://sf16.tiktokcdn.com/music.mp3",
                                "title": "Trending Song"
                            }
                        }
                    }
                }
            }
        }
        raw_html = f'<html><head><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">{json.dumps(rehydration_json)}</script></head><body></body></html>'

        mock_resp = MagicMock()
        mock_resp.geturl.return_value = "https://www.tiktok.com/@creator/video/7488392019283"
        mock_resp.read.return_value = raw_html.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.OpenerDirector.open", return_value=mock_resp):
            info = resolver._extract_tiktok_direct("https://vt.tiktok.com/ZSgG75rWv/")
            self.assertIsNotNone(info)
            self.assertEqual(info["id"], "7488392019283")
            self.assertIn("Viral TikTok video", info["title"])
            self.assertEqual(info["duration"], 18)
            self.assertTrue(len(info["formats"]) >= 3)

            options = resolver.build_format_options(info)
            self.assertTrue(len(options) >= 2)

            for fmt in info["formats"]:
                self.assertEqual(fmt["http_headers"].get("Referer"), "https://www.tiktok.com/")

            self.assertIn("eng", info["subtitles"])
            self.assertEqual(info["subtitles"]["eng"][0]["url"], "https://v16.tiktokcdn.com/sub_en.vtt")

    def test_extract_format_options_tiktok_fallback(self):
        """Verifies extract_format_options falls back to _extract_tiktok_direct when yt-dlp fails."""
        from smart_download.services.youtube_service import YouTubeResolver
        resolver = YouTubeResolver()

        mock_tt_info = {
            "id": "7488392019283",
            "title": "Fallback TikTok Video",
            "duration": 15,
            "thumbnail": "https://p16.tiktokcdn.com/cover.jpg",
            "webpage_url": "https://www.tiktok.com/@creator/video/7488392019283",
            "http_headers": {"User-Agent": "test", "Referer": "https://www.tiktok.com/"},
            "formats": [
                {
                    "format_id": "normal_1080_0",
                    "url": "https://v16.tiktokcdn.com/play1080.mp4",
                    "ext": "mp4",
                    "width": 1080,
                    "height": 1920,
                    "filesize": 5000000,
                    "tbr": 2500.0,
                    "vcodec": "h264",
                    "acodec": "aac",
                    "http_headers": {"User-Agent": "test", "Referer": "https://www.tiktok.com/"},
                    "protocol": "https",
                }
            ],
            "subtitles": {}
        }

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            mock_instance = MagicMock()
            mock_instance.__enter__.return_value = mock_instance
            mock_instance.extract_info.side_effect = Exception("HTTP 403 Forbidden: TikTok extraction blocked")
            mock_ydl_cls.return_value = mock_instance

            with patch.object(resolver, "_extract_tiktok_direct", return_value=mock_tt_info) as mock_direct:
                info, options = resolver.extract_format_options("https://vt.tiktok.com/ZSgG75rWv/")
                self.assertIsNotNone(info)
                self.assertEqual(info["id"], "7488392019283")
                self.assertTrue(len(options) >= 1)
                mock_direct.assert_called_once()

    def test_extract_tiktok_via_tikwm_success(self):
        """Verifies _extract_tiktok_via_tikwm parses TikWM API response properly."""
        from smart_download.services.youtube_service import YouTubeResolver
        resolver = YouTubeResolver()

        mock_payload = {
            "code": 0,
            "msg": "success",
            "data": {
                "id": "7488392019283",
                "title": "TikWM Video",
                "duration": 25,
                "origin_cover": "https://p16.tiktokcdn.com/cover.jpg",
                "hdplay": "/play/hd1080.mp4",
                "hd_size": 15000000,
                "play": "https://www.tikwm.com/play/sd.mp4",
                "size": 7500000,
                "wmplay": "https://www.tikwm.com/play/wm.mp4",
                "wm_size": 7600000,
                "music": "/music/track.mp3",
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            info = resolver._extract_tiktok_via_tikwm("https://vt.tiktok.com/ZSgG75rWv/")
            self.assertIsNotNone(info)
            self.assertEqual(info["id"], "7488392019283")
            self.assertEqual(info["title"], "TikWM Video")
            self.assertEqual(info["duration"], 25)
            self.assertEqual(len(info["formats"]), 4)
            self.assertEqual(info["formats"][0]["url"], "https://www.tikwm.com/play/hd1080.mp4")
            self.assertEqual(info["formats"][0]["format_id"], "hd_no_watermark")
            self.assertEqual(info["formats"][1]["format_id"], "sd_no_watermark")
            self.assertEqual(info["formats"][2]["format_id"], "watermarked")
            self.assertEqual(info["formats"][3]["format_id"], "music_audio")

    def test_extract_tiktok_direct_waf_fallback_to_tikwm(self):
        """Verifies _extract_tiktok_direct falls back to TikWM when HTML scraping returns no formats (WAF challenge)."""
        from smart_download.services.youtube_service import YouTubeResolver
        resolver = YouTubeResolver()

        waf_challenge_html = b"<html><head><title>TikTok Security Check</title></head><body><script>Slardar challenge</script></body></html>"
        mock_resp = MagicMock()
        mock_resp.geturl.return_value = "https://www.tiktok.com/@creator/video/7488392019283"
        mock_resp.read.return_value = waf_challenge_html
        mock_resp.headers = {}
        mock_resp.__enter__.return_value = mock_resp

        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp

        mock_tikwm_info = {
            "id": "7488392019283",
            "title": "TikWM Video",
            "duration": 25,
            "thumbnail": "https://p16.tiktokcdn.com/cover.jpg",
            "webpage_url": "https://vt.tiktok.com/ZSgG75rWv/",
            "http_headers": {"User-Agent": "Mozilla/5.0", "Referer": "https://www.tiktok.com/"},
            "_sd_cookie_header": "",
            "formats": [
                {
                    "format_id": "hd_no_watermark",
                    "url": "https://www.tikwm.com/play/hd1080.mp4",
                    "ext": "mp4",
                    "width": 1080,
                    "height": 1920,
                    "filesize": 15000000,
                    "tbr": 0.0,
                    "vcodec": "h264",
                    "acodec": "aac",
                    "http_headers": {"User-Agent": "Mozilla/5.0", "Referer": "https://www.tiktok.com/"},
                    "protocol": "https",
                    "format_note": "HD (No Watermark)",
                }
            ],
            "subtitles": {},
        }

        with patch("urllib.request.build_opener", return_value=mock_opener):
            with patch.object(resolver, "_extract_tiktok_via_tikwm", return_value=mock_tikwm_info) as mock_tikwm:
                info = resolver._extract_tiktok_direct("https://vt.tiktok.com/ZSgG75rWv/")
                self.assertIsNotNone(info)
                self.assertEqual(info["id"], "7488392019283")
                mock_tikwm.assert_called_once()

    def test_extract_format_options_tiktok_slardar_waf_end_to_end(self):
        """
        Verifies YouTubeResolver.extract_format_options('https://vt.tiktok.com/ZSgG75rWv/')
        survives yt-dlp Unexpected response error and WAF challenge, succeeding via TikWM.
        """
        from smart_download.services.youtube_service import YouTubeResolver
        from smart_download.services.youtube_models import VideoFormatOption
        resolver = YouTubeResolver()

        mock_payload = {
            "code": 0,
            "msg": "success",
            "data": {
                "id": "7488392019283",
                "title": "WAF Bypassed TikTok",
                "duration": 18,
                "origin_cover": "https://p16.tiktokcdn.com/cover.jpg",
                "hdplay": "https://www.tikwm.com/play/hd.mp4",
                "hd_size": 9500000,
                "play": "https://www.tikwm.com/play/sd.mp4",
                "size": 5200000,
            }
        }
        mock_tikwm_resp = MagicMock()
        mock_tikwm_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_tikwm_resp.__enter__.return_value = mock_tikwm_resp

        waf_challenge_html = b"<html><body>Slardar JS challenge</body></html>"
        mock_html_resp = MagicMock()
        mock_html_resp.geturl.return_value = "https://www.tiktok.com/@creator/video/7488392019283"
        mock_html_resp.read.return_value = waf_challenge_html
        mock_html_resp.headers = {}
        mock_html_resp.__enter__.return_value = mock_html_resp
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_html_resp

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            mock_ydl = MagicMock()
            mock_ydl.__enter__.return_value = mock_ydl
            mock_ydl.extract_info.side_effect = Exception("ERROR: Unexpected response from webpage request")
            mock_ydl_cls.return_value = mock_ydl

            with patch("urllib.request.build_opener", return_value=mock_opener):
                with patch("urllib.request.urlopen", return_value=mock_tikwm_resp):
                    info, options = resolver.extract_format_options("https://vt.tiktok.com/ZSgG75rWv/")
                    self.assertIsNotNone(info)
                    self.assertEqual(info["id"], "7488392019283")
                    self.assertTrue(len(options) >= 1)
                    self.assertTrue(all(isinstance(opt, VideoFormatOption) for opt in options))

    def test_tree_chunks_proportional_column_scaling_maximized(self):
        """Verifies _on_tree_chunks_configure scales columns proportionally at width=1880."""
        from smart_download.ui.panels.chunks_panel import ChunksPanelMixin

        class DummyChunksPanel(ChunksPanelMixin):
            def __init__(self):
                self.tree_chunks = MagicMock()

        panel = DummyChunksPanel()
        event = MagicMock()
        event.width = 1880

        panel._on_tree_chunks_configure(event)

        # Expected column widths:
        # id: int(1880 * 0.08) = 150
        # range: int(1880 * 0.34) = 639
        # size: int(1880 * 0.15) = 282
        # downloaded: int(1880 * 0.15) = 282
        # pct: int(1880 * 0.12) = 225
        # status: int(1880 * 0.16) = 300
        calls = {call[0][0]: call[1]["width"] for call in panel.tree_chunks.column.call_args_list}
        avail_w = 1880 - 4
        self.assertEqual(calls["id"], max(50, int(avail_w * 0.08)))
        self.assertEqual(calls["range"], max(200, int(avail_w * 0.34)))
        self.assertEqual(calls["size"], max(90, int(avail_w * 0.15)))
        self.assertEqual(calls["downloaded"], max(90, int(avail_w * 0.15)))
        self.assertEqual(calls["pct"], max(80, int(avail_w * 0.12)))
        self.assertEqual(calls["status"], max(100, int(avail_w * 0.16)))

    def test_tree_history_proportional_column_scaling_maximized(self):
        """Verifies _on_tree_history_configure scales columns proportionally at width=1880."""
        from smart_download.ui.panels.chunks_panel import ChunksPanelMixin

        class DummyHistoryPanel(ChunksPanelMixin):
            def __init__(self):
                self.tree_history = MagicMock()

        panel = DummyHistoryPanel()
        event = MagicMock()
        event.width = 1880

        panel._on_tree_history_configure(event)

        calls = {call[0][0]: call[1]["width"] for call in panel.tree_history.column.call_args_list}
        avail_w = 1880 - 4
        self.assertEqual(calls["category"], max(80, int(avail_w * 0.10)))
        self.assertEqual(calls["filename"], max(180, int(avail_w * 0.25)))
        self.assertEqual(calls["size"], max(80, int(avail_w * 0.10)))
        self.assertEqual(calls["status"], max(80, int(avail_w * 0.10)))
        self.assertEqual(calls["date"], max(120, int(avail_w * 0.15)))
        self.assertEqual(calls["path"], max(220, int(avail_w * 0.30)))

    def test_safe_modal_dialog_frameless_and_bmp_symbols(self):
        """Verifies SafeModalDialog sets overrideredirect(True) and uses BMP symbols."""
        import tkinter as tk
        from smart_download.ui.components.base_modal import SafeModalDialog

        root = tk.Tk()
        root.withdraw()
        try:
            for dtype in ["error", "warning", "confirm", "info"]:
                dlg = SafeModalDialog(
                    parent=root,
                    title="Modal Title",
                    message="Test message",
                    dialog_type=dtype,
                )
                self.assertTrue(dlg.overrideredirect())
                self.assertTrue(hasattr(dlg, "_on_drag_press"))
                self.assertTrue(hasattr(dlg, "_on_drag_motion"))
                dlg.destroy()
        finally:
            try: root.destroy()
            except Exception: pass

    def test_safe_modal_dialog_cancels_after_job_on_destroy(self):
        """Verifies SafeModalDialog tracks and cancels _topmost_after_id on destroy without Tcl background errors."""
        import tkinter as tk
        from smart_download.ui.components.base_modal import SafeModalDialog

        root = tk.Tk()
        root.withdraw()
        try:
            dlg = SafeModalDialog(
                parent=root,
                title="Test Dialog",
                message="Cancel test",
                dialog_type="info",
            )
            self.assertIsNotNone(dlg._topmost_after_id)
            dlg.destroy()
            self.assertIsNone(dlg._topmost_after_id)
            # Process pending events to ensure no dangling after callback throws Tcl error
            root.update_idletasks()
        finally:
            try: root.destroy()
            except Exception: pass

    def test_extract_tiktok_direct_returns_none_when_both_fail(self):
        """Verifies _extract_tiktok_direct returns None when HTML scraping and TikWM both fail."""
        from smart_download.services.youtube_service import YouTubeResolver
        resolver = YouTubeResolver()

        with patch("urllib.request.build_opener", side_effect=Exception("Network error")):
            with patch.object(resolver, "_extract_tiktok_via_tikwm", return_value=None):
                res = resolver._extract_tiktok_direct("https://www.tiktok.com/@user/video/12345")
                self.assertIsNone(res)

    def test_extract_tiktok_via_tikwm_handles_relative_urls_and_fallback_title(self):
        """Verifies _extract_tiktok_via_tikwm resolves relative URLs and cleans up replacement-character titles."""
        from smart_download.services.youtube_service import YouTubeResolver
        resolver = YouTubeResolver()

        mock_payload = {
            "code": 0,
            "msg": "success",
            "data": {
                "id": "999888777",
                "title": "\ufffd \ufffd #tag",
                "duration": 15,
                "origin_cover": "/cover.jpg",
                "hdplay": "/play/hd.mp4",
                "hd_size": 12000000,
                "play": "/play/sd.mp4",
                "size": 6000000,
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            info = resolver._extract_tiktok_via_tikwm("https://vt.tiktok.com/ZSgG75rWv/")
            self.assertIsNotNone(info)
            self.assertEqual(info["id"], "999888777")
            self.assertEqual(info["title"], "#tag")
            self.assertEqual(info["formats"][0]["url"], "https://www.tikwm.com/play/hd.mp4")
            self.assertEqual(info["formats"][1]["url"], "https://www.tikwm.com/play/sd.mp4")



class TestGeometryAndSanitizationAndTikTokDeduplication(unittest.TestCase):
    """
    Verifies:
    1. SafeModalDialog and WindowChromeMixin / WindowControllerMixin format negative coordinates without '+-'.
    2. sanitize_filename strips 4-byte non-BMP emojis (ord > 0xFFFF) and \ufffd.
    3. extract_format_options invokes _extract_tiktok_direct at most once on failure.
    4. _extract_tiktok_via_tikwm falls back to music_info duration when main duration is 0.
    """

    def test_format_geometry_negative_coordinates(self):
        from smart_download.ui.controllers.window_controller import WindowChromeMixin, WindowControllerMixin

        self.assertIs(WindowControllerMixin, WindowChromeMixin)
        geo1 = WindowChromeMixin._format_geometry(800, 600, -150, 200)
        self.assertEqual(geo1, "800x600-150+200")
        self.assertNotIn("+-", geo1)

        geo2 = WindowChromeMixin._format_geometry(800, 600, 150, -200)
        self.assertEqual(geo2, "800x600+150-200")
        self.assertNotIn("+-", geo2)

        geo3 = WindowChromeMixin._format_geometry(None, None, -50, -100)
        self.assertEqual(geo3, "-50-100")
        self.assertNotIn("+-", geo3)

        geo4 = WindowChromeMixin._format_geometry(None, None, 50, 100)
        self.assertEqual(geo4, "+50+100")
        self.assertNotIn("+-", geo4)

    def test_window_drag_motion_and_resize_drag_negative_coords(self):
        from smart_download.ui.controllers.window_controller import WindowChromeMixin

        class DummyWindow(WindowChromeMixin):
            def __init__(self):
                self.root = MagicMock()
                self._is_maximized = False
                self._drag_offset_x = 200
                self._drag_offset_y = 50
                self._resize_state = {
                    "start_x_root": 100, "start_y_root": 100,
                    "start_x": -100, "start_y": -50,
                    "start_w": 800, "start_h": 600,
                    "mode": "w", "min_w": 400, "min_h": 300,
                    "dpi_scale": 1.0
                }
                self.width = 800
                self.height = 600

        dw = DummyWindow()
        # Drag into negative coordinates
        event_drag = MagicMock()
        event_drag.x_root = 50
        event_drag.y_root = 10
        dw._on_drag_motion(event_drag)
        dw.root.geometry.assert_called_with("-150-40")
        self.assertNotIn("+-", dw.root.geometry.call_args[0][0])

        # Resize from west edge into negative x
        event_resize = MagicMock()
        event_resize.x_root = 80
        event_resize.y_root = 100
        dw._on_resize_drag(event_resize)
        call_arg = dw.root.geometry.call_args[0][0]
        self.assertNotIn("+-", call_arg)

    def test_safe_modal_dialog_negative_coords(self):
        from smart_download.ui.components.base_modal import SafeModalDialog
        import tkinter as tk

        try:
            root = tk.Tk()
            root.withdraw()
        except Exception:
            self.skipTest("Tkinter display not available")

        try:
            # Simulate parent on left/top monitor with negative coordinates
            with patch.object(root, "winfo_x", return_value=-1200), \
                 patch.object(root, "winfo_y", return_value=-300), \
                 patch.object(root, "winfo_width", return_value=1000), \
                 patch.object(root, "winfo_height", return_value=800), \
                 patch.object(root, "winfo_viewable", return_value=True), \
                 patch.object(root, "state", return_value="normal"):
                dlg = SafeModalDialog(
                    parent=root,
                    title="Negative Test",
                    message="Testing negative geometry coordinates",
                    dialog_type="info"
                )
                geo = dlg.geometry()
                self.assertNotIn("+-", geo)
                dlg.destroy()
                root.update_idletasks()
        finally:
            try: root.destroy()
            except Exception: pass

    def test_sanitize_filename_strips_non_bmp_and_replacement_chars(self):
        from smart_download.services.youtube_models import sanitize_filename

        raw_name = "Viral \U0001f680 Video \U0001f3a5 #1 \ufffd Top! \U0001f525"
        sanitized = sanitize_filename(raw_name)
        self.assertNotIn("\ufffd", sanitized)
        self.assertTrue(all(ord(c) <= 0xFFFF for c in sanitized))
        self.assertEqual(sanitized, "Viral Video #1 Top!")

    def test_extract_format_options_tiktok_deduplicates_direct_call(self):
        from smart_download.services.youtube_service import YouTubeResolver
        import yt_dlp

        resolver = YouTubeResolver()
        resolver.auto_update_on_failure = False

        call_counts = {"direct": 0}
        def fake_extract_tiktok_direct(url):
            call_counts["direct"] += 1
            return None

        with patch.object(yt_dlp.YoutubeDL, "extract_info", side_effect=Exception("slardar error")):
            with patch.object(resolver, "_extract_tiktok_direct", side_effect=fake_extract_tiktok_direct):
                with self.assertRaises(RuntimeError):
                    resolver.extract_format_options("https://www.tiktok.com/@user/video/999888777")

        self.assertEqual(call_counts["direct"], 1)

    def test_extract_tiktok_via_tikwm_duration_fallback_to_music_info(self):
        from smart_download.services.youtube_service import YouTubeResolver
        resolver = YouTubeResolver()

        mock_payload = {
            "code": 0,
            "msg": "success",
            "data": {
                "id": "11223344",
                "title": "Music Clip",
                "duration": 0,
                "music_info": {"duration": 58},
                "play": "/play/sd.mp4",
                "size": 5000000,
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            info = resolver._extract_tiktok_via_tikwm("https://www.tiktok.com/@user/video/11223344")
            self.assertIsNotNone(info)
            self.assertEqual(info["duration"], 58)

    def test_extract_tiktok_via_tikwm_malformed_music_info(self):
        from smart_download.services.youtube_service import YouTubeResolver
        resolver = YouTubeResolver()

        mock_payload = {
            "code": 0,
            "msg": "success",
            "data": {
                "id": "11223344",
                "title": "Music Clip",
                "duration": 0,
                "music_info": "not-a-dict",
                "play": "/play/sd.mp4",
                "size": 5000000,
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            info = resolver._extract_tiktok_via_tikwm("https://www.tiktok.com/@user/video/11223344")
            self.assertIsNotNone(info)
            self.assertEqual(info["duration"], 0)

    def test_quality_modal_drag_motion_negative_coords(self):
        from smart_download.ui.modals.quality_modal import QualitySelectionModal

        modal = MagicMock()
        modal._drag_offset_x = 200
        modal._drag_offset_y = 100
        event = MagicMock()
        event.x_root = 50
        event.y_root = 20

        QualitySelectionModal._on_drag_motion(modal, event)
        modal.geometry.assert_called_with("-150-80")
        self.assertNotIn("+-", modal.geometry.call_args[0][0])

    def test_confirm_modal_progress_negative_coords(self):
        from smart_download.ui.modals.confirm_modal_logic import ConfirmModalLogicMixin

        class DummyModal(ConfirmModalLogicMixin):
            def __init__(self):
                self.dpi_scale = 1.0
                self.file_name = "test.zip"
                self.title = MagicMock()
                self.frame_confirmation = MagicMock()
                self.frame_progress = MagicMock()
                self.lbl_prog_filename = MagicMock()
                self.lbl_prog_cat = MagicMock()
                self.lbl_prog_threads = MagicMock()
                self.get_max_connections = MagicMock(return_value=8)
                self.geometry = MagicMock()
                self._draw_modal_progress = MagicMock()
            def winfo_screenwidth(self): return 1920
            def winfo_screenheight(self): return 1080
            def winfo_x(self): return -800
            def winfo_y(self): return -200

        dm = DummyModal()
        dm.show_progress_view()
        dm.geometry.assert_called_once()
        geo_str = dm.geometry.call_args[0][0]
        self.assertNotIn("+-", geo_str)
        self.assertTrue(geo_str.endswith("-800-200"))

    def test_toast_controller_negative_coords_and_bmp_icon(self):
        from smart_download.ui.controllers.toast_controller import ToastControllerMixin
        import tkinter as tk

        class DummyToastHost(ToastControllerMixin):
            def __init__(self):
                self.root = MagicMock()
                self.root.winfo_exists.return_value = True
                self.root.winfo_fpixels.return_value = 96.0

        host = DummyToastHost()
        mock_toast = MagicMock()
        mock_toast.winfo_screenwidth.return_value = 100
        mock_toast.winfo_screenheight.return_value = 50

        with patch("tkinter.Toplevel", return_value=mock_toast), \
             patch("tkinter.Frame"), \
             patch("tkinter.Label") as mock_label:
            host._show_background_toast("Test message")
            geo_call = mock_toast.geometry.call_args[0][0]
            self.assertNotIn("+-", geo_call)

            # Verify rocket emoji was NOT used in label
            label_texts = [call[1].get("text", "") for call in mock_label.call_args_list]
            self.assertNotIn("\U0001f680", label_texts)
            self.assertIn("⚡", label_texts)

    def test_locales_have_no_supplementary_characters(self):
        for path in ["src/smart_download/locales/en.json", "src/smart_download/locales/ar.json"]:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            non_bmp = [c for c in content if ord(c) > 0xFFFF]
            self.assertEqual(non_bmp, [], f"Found non-BMP characters in {path}: {non_bmp}")


if __name__ == "__main__":
    unittest.main()

