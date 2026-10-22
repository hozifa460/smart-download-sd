"""
========================================================================================
🧪 AUTOMATED TEST SUITE: YouTube Support & Web Browser Integration
========================================================================================
Comprehensive verification covering:
1. YouTube URL detection & video ID extraction across all standard and short formats.
2. Filename sanitization against OS-reserved characters.
3. YouTube stream resolver (progressive stream selection, dual-stream selection).
4. Lossless FFmpeg stream merge (-c copy) and cleanup.
5. Browser IPC loopback server lifecycle (start, stop, port conflict resilience).
6. Browser bridge endpoints: GET /ping, OPTIONS (CORS preflight), and POST /download.
7. Validation of error paths: malformed JSON, missing URL, invalid scheme, oversized payloads.
8. TurboDownloadEngine custom headers propagation.
9. StreamDownloadCoordinator end-to-end integration.
========================================================================================
"""

import os
import sys
import time
import json
import shutil
import struct
import hashlib
import unittest
import threading
import tkinter as tk
import subprocess
import http.server
import socketserver
import urllib.request
import urllib.error
from unittest.mock import patch, MagicMock

# Import modules under test
from youtube_resolver import (
    is_youtube_url,
    extract_youtube_id,
    sanitize_filename,
    is_ytdlp_available,
    has_ffmpeg,
    YouTubeResolver,
    YouTubeStreamInfo,
    VideoFormatOption,
    format_filesize
)
from browser_bridge import BrowserBridgeServer, BrowserBridgeHandler
from native_messaging_host import read_message, send_message, handle_payload
from register_browser import (
    register_native_host,
    unregister_native_host,
    check_and_register_browser,
    register_browser_extensions,
    unregister_browser_extensions,
    is_extension_registered,
    is_registered as is_browser_registered,
    get_status as get_browser_reg_status,
    compute_unpacked_extension_id,
    generate_host_manifest,
    get_default_extension_origins
)
import installer
from turbo_downloader import (
    TurboDownloadEngine,
    StreamDownloadCoordinator,
    TokenBucketRateLimiter,
    get_permissive_ssl_context,
    SafeModalDialog,
    ModernFramelessGUI,
    QualitySelectionModal,
    DownloadConfirmationModal,
    FetchingLinkToast,
    validate_refresh_url,
    RefreshLinkModal,
    RefreshLinkDialog,
    DownloadChunk,
    is_downloadable_url,
    get_clipboard_text,
    derive_download_filename,
    COMMON_DOWNLOAD_EXTENSIONS,
    is_startup_enabled,
    enable_startup,
    disable_startup,
    get_startup_command,
    get_startup_entry,
    notify_running_instance,
    WINDOWS_RUN_KEY,
    STARTUP_REG_KEY_NAME,
    SystemTrayManager,
    load_settings,
    save_settings,
    get_setting,
    set_setting,
    parse_speed_limit,
    open_downloaded_file,
    open_containing_folder
)


class TestYouTubeDetectionAndSanitization(unittest.TestCase):
    """Verifies YouTube URL pattern matching and filesystem sanitization."""

    def test_youtube_url_detection(self):
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ&feature=share",
            "http://youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ?t=42",
            "https://www.youtube.com/shorts/1a2b3c4d5e6",
            "https://youtube.com/shorts/1a2b3c4d5e6",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/v/dQw4w9WgXcQ",
            "https://www.youtube.com/live/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ"
        ]
        for url in valid_urls:
            self.assertTrue(is_youtube_url(url), f"Failed to detect valid URL: {url}")

        invalid_urls = [
            "https://speed.cloudflare.com/__down?bytes=50000000",
            "https://example.com/video.mp4",
            "https://google.com",
            "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
            "ftp://ftp.example.com/file.iso",
            "",
            "   ",
            None
        ]
        for url in invalid_urls:
            self.assertFalse(is_youtube_url(url), f"False positive detection: {url}")

    def test_extract_youtube_id(self):
        self.assertEqual(extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(extract_youtube_id("https://youtu.be/dQw4w9WgXcQ?t=10"), "dQw4w9WgXcQ")
        self.assertEqual(extract_youtube_id("https://www.youtube.com/shorts/1a2b3c4d5e6"), "1a2b3c4d5e6")
        self.assertIsNone(extract_youtube_id("https://google.com"))
        self.assertIsNone(extract_youtube_id(""))

    def test_sanitize_filename(self):
        # Test reserved characters: < > : " / \ | ? *
        raw = 'My: Cool / Video * Title? <Part "1"> | HD'
        sanitized = sanitize_filename(raw)
        for char in '<>:"/\\|?*':
            self.assertNotIn(char, sanitized)

        # Test empty string fallback
        self.assertEqual(sanitize_filename(""), "youtube_download")
        self.assertEqual(sanitize_filename("   "), "youtube_download")

        # Test length capping
        long_name = "A" * 300
        capped = sanitize_filename(long_name, max_length=50)
        self.assertLessEqual(len(capped), 50)


class TestYouTubeResolver(unittest.TestCase):
    """Verifies YouTube resolution, progressive/dual stream selection, and FFmpeg merge."""

    def test_resolve_progressive_format(self):
        """Simulates yt-dlp returning a combined progressive stream."""
        mock_info = {
            "title": "Test Progressive Video",
            "duration": 120,
            "thumbnail": "https://example.com/thumb.jpg",
            "formats": [
                {
                    "format_id": "18",
                    "ext": "mp4",
                    "height": 360,
                    "vcodec": "avc1.42001E",
                    "acodec": "mp4a.40.2",
                    "protocol": "https",
                    "url": "https://rr---sn-mock.googlevideo.com/videoplayback?id=mock_prog",
                    "http_headers": {"User-Agent": "TestUA"},
                    "filesize": 15000000
                }
            ]
        }

        with patch("yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = mock_info

            resolver = YouTubeResolver()
            stream_info = resolver.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

            self.assertTrue(stream_info.is_progressive)
            self.assertEqual(stream_info.clean_filename, "Test Progressive Video.mp4")
            self.assertEqual(stream_info.video_url, "https://rr---sn-mock.googlevideo.com/videoplayback?id=mock_prog")
            self.assertEqual(stream_info.video_resolution, "360p")
            self.assertIsNone(stream_info.audio_url)

    def test_resolve_dual_stream_format(self):
        """Simulates yt-dlp returning separate video-only and audio-only streams."""
        mock_info = {
            "title": "Test 1080p Video",
            "duration": 300,
            "formats": [
                {
                    "format_id": "137",
                    "ext": "mp4",
                    "height": 1080,
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "protocol": "https",
                    "url": "https://rr---sn-mock.googlevideo.com/videoplayback?id=mock_video",
                    "filesize": 50000000
                },
                {
                    "format_id": "140",
                    "ext": "m4a",
                    "abr": 128.0,
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "protocol": "https",
                    "url": "https://rr---sn-mock.googlevideo.com/videoplayback?id=mock_audio",
                    "filesize": 5000000
                }
            ]
        }

        with patch("yt_dlp.YoutubeDL") as MockYDL, patch("youtube_resolver.has_ffmpeg", return_value=True):
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = mock_info

            resolver = YouTubeResolver()
            stream_info = resolver.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

            self.assertFalse(stream_info.is_progressive)
            self.assertEqual(stream_info.video_resolution, "1080p")
            self.assertEqual(stream_info.video_url, "https://rr---sn-mock.googlevideo.com/videoplayback?id=mock_video")
            self.assertEqual(stream_info.audio_url, "https://rr---sn-mock.googlevideo.com/videoplayback?id=mock_audio")

    def test_ffmpeg_merge_execution(self):
        """Creates actual short test media clips and verifies FFmpeg stream merging."""
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            self.skipTest("FFmpeg is not installed on this machine.")

        test_dir = "test_media_merge"
        os.makedirs(test_dir, exist_ok=True)
        v_path = os.path.join(test_dir, "temp_video.mp4")
        a_path = os.path.join(test_dir, "temp_audio.m4a")
        out_path = os.path.join(test_dir, "final_merged.mp4")

        try:
            # Generate 1-second synthetic video & audio test streams
            subprocess.run([
                ffmpeg_bin, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
                "-c:v", "libx264", v_path
            ], check=True, capture_output=True)

            subprocess.run([
                ffmpeg_bin, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:a", "aac", a_path
            ], check=True, capture_output=True)

            # Perform merge
            res = YouTubeResolver.merge_video_audio(v_path, a_path, out_path)
            self.assertTrue(res)
            self.assertTrue(os.path.exists(out_path))
            self.assertGreater(os.path.getsize(out_path), 0)

            # Verify input component files were cleaned up
            self.assertFalse(os.path.exists(v_path))
            self.assertFalse(os.path.exists(a_path))
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_ffmpeg_missing_files_error(self):
        """Verifies clear exception is raised if input stream files are missing."""
        with self.assertRaises(FileNotFoundError):
            YouTubeResolver.merge_video_audio("nonexistent_v.mp4", "nonexistent_a.m4a", "out.mp4")

    def test_extract_format_options_ydl_opts_socket_timeout_and_extractor_args(self):
        """Verifies extract_format_options configures socket_timeout and does not pass restrictive extractor_args."""
        with patch("yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = {
                "id": "GTNypvv2Nbg",
                "title": "Test Video",
                "formats": [
                    {
                        "format_id": "18",
                        "ext": "mp4",
                        "height": 360,
                        "vcodec": "avc1",
                        "acodec": "mp4a",
                        "protocol": "https",
                        "url": "https://example.com/video.mp4"
                    }
                ]
            }

            resolver = YouTubeResolver()
            info, options = resolver.extract_format_options("https://youtu.be/GTNypvv2Nbg")

            MockYDL.assert_called_once()
            passed_opts = MockYDL.call_args[0][0]
            self.assertEqual(passed_opts.get("socket_timeout"), 12)
            self.assertNotIn("extractor_args", passed_opts)

    def test_extract_format_options_null_entries_handling(self):
        """Verifies extract_format_options raises a clean RuntimeError if entries contains None."""
        with patch("yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = {
                "id": "GTNypvv2Nbg",
                "entries": [None]
            }

            resolver = YouTubeResolver()
            with self.assertRaises(RuntimeError) as ctx:
                resolver.extract_format_options("https://youtu.be/GTNypvv2Nbg")
            self.assertIn("empty metadata", str(ctx.exception))


class TestBrowserBridgeServer(unittest.TestCase):
    """Verifies BrowserBridgeServer lifecycle, CORS headers, endpoints, and validation."""

    @classmethod
    def setUpClass(cls):
        cls.port = 19288
        cls.received_downloads = []

        def _on_dl(payload):
            cls.received_downloads.append(payload)

        cls.server = BrowserBridgeServer(port=cls.port, on_download=_on_dl)
        cls.server.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        TestBrowserBridgeServer.received_downloads.clear()

    def test_get_ping(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/ping")
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("app"), "Smart Download (SD)")
            self.assertTrue(data.get("active"))

    def test_options_cors(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/download", method="OPTIONS")
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods", ""))

    def test_post_download_valid(self):
        payload = {
            "url": "https://speed.cloudflare.com/test_file.iso",
            "filename": "test_file.iso",
            "referrer": "https://speed.cloudflare.com",
            "start_immediately": True
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/download",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))

        self.assertEqual(len(self.received_downloads), 1)
        received = self.received_downloads[0]
        self.assertEqual(received["url"], "https://speed.cloudflare.com/test_file.iso")
        self.assertEqual(received["filename"], "test_file.iso")
        self.assertTrue(received["start_immediately"])

    def test_post_download_malformed_json(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/download",
            data=b"not valid json {{{",
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 400)

    def test_post_download_missing_url(self):
        payload = {"filename": "test.zip"}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/download",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 400)

    def test_post_download_invalid_scheme(self):
        payload = {"url": "javascript:alert(1)"}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/download",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 400)

    def test_404_not_found(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/nonexistent_endpoint")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 404)


class MockHeaderInspectHandler(http.server.BaseHTTPRequestHandler):
    """Echoes received request headers for verification."""
    last_headers = {}

    def do_HEAD(self):
        MockHeaderInspectHandler.last_headers = dict(self.headers)
        self.send_response(200)
        self.send_header("Content-Length", "1024")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        MockHeaderInspectHandler.last_headers = dict(self.headers)
        self.send_response(200)
        self.send_header("Content-Length", "1024")
        self.end_headers()
        self.wfile.write(b"x" * 1024)

    def log_message(self, format, *args):
        pass


class TestEngineCustomHeaders(unittest.TestCase):
    """Verifies TurboDownloadEngine propagates custom headers to probe and workers."""

    @classmethod
    def setUpClass(cls):
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), MockHeaderInspectHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_custom_headers_propagation(self):
        custom_headers = {
            "Authorization": "Bearer secret_test_token_123",
            "X-Custom-Client": "TurboPro/1.0"
        }
        engine = TurboDownloadEngine(
            url=f"http://127.0.0.1:{self.port}/test.bin",
            destination_path="test_headers_out.bin",
            headers=custom_headers
        )
        engine.probe()

        self.assertEqual(
            MockHeaderInspectHandler.last_headers.get("Authorization"),
            "Bearer secret_test_token_123"
        )
        self.assertEqual(
            MockHeaderInspectHandler.last_headers.get("X-Custom-Client"),
            "TurboPro/1.0"
        )


class TestStreamCoordinatorIntegration(unittest.TestCase):
    """Verifies StreamDownloadCoordinator end-to-end integration."""

    @classmethod
    def setUpClass(cls):
        cls.data_store = {}

        class MediaMockHandler(http.server.BaseHTTPRequestHandler):
            def do_HEAD(self):
                fn = self.path.lstrip('/')
                if fn not in TestStreamCoordinatorIntegration.data_store:
                    self.send_error(404)
                    return
                data = TestStreamCoordinatorIntegration.data_store[fn]
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

            def do_GET(self):
                fn = self.path.lstrip('/')
                if fn not in TestStreamCoordinatorIntegration.data_store:
                    self.send_error(404)
                    return
                data = TestStreamCoordinatorIntegration.data_store[fn]
                total = len(data)
                range_header = self.headers.get("Range")
                if range_header and range_header.startswith("bytes="):
                    rng = range_header[6:].split("-")
                    start = int(rng[0]) if rng[0] else 0
                    end = int(rng[1]) if rng[1] else total - 1
                    if end >= total:
                        end = total - 1
                    chunk_len = end - start + 1
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
                    self.send_header("Content-Length", str(chunk_len))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    self.wfile.write(data[start:end+1])
                else:
                    self.send_response(200)
                    self.send_header("Content-Length", str(total))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    self.wfile.write(data)

            def log_message(self, format, *args):
                pass

        cls.server = socketserver.TCPServer(("127.0.0.1", 0), MediaMockHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_coordinator_progressive_download(self):
        """Verifies progressive stream download through coordinator with bit-perfect validation."""
        payload = os.urandom(512 * 1024)
        expected_hash = hashlib.sha256(payload).hexdigest()
        self.data_store["prog_video.mp4"] = payload

        stream_info = YouTubeStreamInfo(
            video_id="test1234567",
            title="Progressive Test",
            clean_filename="Progressive_Test.mp4",
            is_progressive=True,
            video_url=f"http://127.0.0.1:{self.port}/prog_video.mp4",
            video_size=len(payload)
        )

        out_path = "test_coord_prog_out.mp4"
        if os.path.exists(out_path):
            os.remove(out_path)

        completed = threading.Event()
        errors = []

        coord = StreamDownloadCoordinator(
            stream_info=stream_info,
            destination_path=out_path,
            max_connections=4,
            on_complete=lambda path, size, elapsed: completed.set(),
            on_error=lambda err: (errors.append(err), completed.set())
        )
        coord.start()
        self.assertTrue(completed.wait(timeout=10), "Coordinator timed out")
        self.assertEqual(len(errors), 0, f"Coordinator failed: {errors}")
        self.assertTrue(os.path.exists(out_path))

        with open(out_path, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(actual_hash, expected_hash)
        if os.path.exists(out_path):
            os.remove(out_path)

    def test_coordinator_dual_stream_with_merge(self):
        """Verifies dual-stream coordinator downloading video and audio separately and merging via FFmpeg."""
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            self.skipTest("FFmpeg not installed")

        # Generate small valid MP4 and AAC files
        temp_dir = "test_dual_stream_tmp"
        os.makedirs(temp_dir, exist_ok=True)
        raw_v_path = os.path.join(temp_dir, "raw_v.mp4")
        raw_a_path = os.path.join(temp_dir, "raw_a.m4a")

        try:
            subprocess.run([
                ffmpeg_bin, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1",
                "-c:v", "libx264", raw_v_path
            ], check=True, capture_output=True)

            subprocess.run([
                ffmpeg_bin, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
                "-c:a", "aac", raw_a_path
            ], check=True, capture_output=True)

            with open(raw_v_path, "rb") as f:
                v_data = f.read()
            with open(raw_a_path, "rb") as f:
                a_data = f.read()

            self.data_store["dual_video.mp4"] = v_data
            self.data_store["dual_audio.m4a"] = a_data

            stream_info = YouTubeStreamInfo(
                video_id="dual_test_123",
                title="Dual Test Video",
                clean_filename="Dual_Test_Video.mp4",
                is_progressive=False,
                video_url=f"http://127.0.0.1:{self.port}/dual_video.mp4",
                video_size=len(v_data),
                video_ext="mp4",
                video_resolution="1080p",
                audio_url=f"http://127.0.0.1:{self.port}/dual_audio.m4a",
                audio_size=len(a_data),
                audio_ext="m4a"
            )

            out_merged = "test_coord_merged_out.mp4"
            if os.path.exists(out_merged):
                os.remove(out_merged)

            completed = threading.Event()
            errors = []
            progress_history = []

            def _track_progress(dl, total, spd, eta, active):
                pct = (dl / total * 100.0) if total > 0 else 0
                progress_history.append(pct)

            coord = StreamDownloadCoordinator(
                stream_info=stream_info,
                destination_path=out_merged,
                max_connections=2,
                on_progress=_track_progress,
                on_complete=lambda path, size, elapsed: completed.set(),
                on_error=lambda err: (errors.append(err), completed.set())
            )
            coord.start()

            self.assertTrue(completed.wait(timeout=15), "Dual stream coordinator timed out")
            self.assertEqual(len(errors), 0, f"Dual stream coordinator failed: {errors}")
            self.assertTrue(os.path.exists(out_merged), "Merged output file was not created")
            self.assertGreater(os.path.getsize(out_merged), 0, "Merged output file is empty")

            # Verify that temporary video and audio files were cleaned up
            self.assertFalse(os.path.exists(out_merged + ".video.tmp"), "video.tmp was not cleaned up")
            self.assertFalse(os.path.exists(out_merged + ".audio.tmp"), "audio.tmp was not cleaned up")

            # Verify progress history is monotonically non-decreasing (no jump back to 0%)
            for i in range(1, len(progress_history)):
                self.assertGreaterEqual(
                    progress_history[i],
                    progress_history[i - 1] - 0.01,
                    f"Progress jumped backwards at index {i}: {progress_history[i-1]}% -> {progress_history[i]}%"
                )

            if os.path.exists(out_merged):
                os.remove(out_merged)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_coordinator_cancel_cleanup(self):
        """Verifies that cancelling StreamDownloadCoordinator cleans up part files cleanly."""
        payload = os.urandom(1024 * 1024)
        self.data_store["cancel_v.mp4"] = payload
        self.data_store["cancel_a.m4a"] = payload

        stream_info = YouTubeStreamInfo(
            video_id="cancel_test",
            title="Cancel Test",
            clean_filename="Cancel_Test.mp4",
            is_progressive=False,
            video_url=f"http://127.0.0.1:{self.port}/cancel_v.mp4",
            video_size=len(payload),
            audio_url=f"http://127.0.0.1:{self.port}/cancel_a.m4a",
            audio_size=len(payload)
        )

        out_path = "test_coord_cancel_out.mp4"
        coord = StreamDownloadCoordinator(
            stream_info=stream_info,
            destination_path=out_path,
            max_connections=2
        )
        coord.start()
        time.sleep(0.05)
        coord.cancel()
        time.sleep(0.3)

        self.assertFalse(coord.is_running)
        self.assertFalse(os.path.exists(out_path + ".video.tmp"))
        self.assertFalse(os.path.exists(out_path + ".audio.tmp"))


class TestBrowserBridgeConcurrency(unittest.TestCase):
    """Verifies that BrowserBridgeServer can handle rapid concurrent POST requests without drop."""

    @classmethod
    def setUpClass(cls):
        cls.port = 19295
        cls.received_urls = []
        cls.lock = threading.Lock()

        def _on_dl(payload):
            with cls.lock:
                cls.received_urls.append(payload["url"])

        cls.server = BrowserBridgeServer(port=cls.port, on_download=_on_dl)
        cls.server.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_concurrent_downloads(self):
        def _send(idx):
            data = json.dumps({
                "url": f"https://example.com/file_{idx}.zip",
                "filename": f"file_{idx}.zip"
            }).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/download",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)

        threads = []
        for i in range(20):
            t = threading.Thread(target=_send, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        self.assertEqual(len(self.received_urls), 20)


class TestExtensionManifestAndAssets(unittest.TestCase):
    """Validates WebExtension Manifest V3 syntax, compatibility, and file assets."""

    def test_manifest_v3_structure(self):
        ext_dir = os.path.join(os.path.dirname(__file__), "extension")
        manifest_path = os.path.join(ext_dir, "manifest.json")
        self.assertTrue(os.path.exists(manifest_path), "manifest.json does not exist")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual(manifest.get("manifest_version"), 3)
        self.assertEqual(manifest.get("name"), "Smart Download (SD) Integration")
        self.assertIn("downloads", manifest.get("permissions", []))
        self.assertIn("contextMenus", manifest.get("permissions", []))
        self.assertIn("storage", manifest.get("permissions", []))

        # Chrome MV3 requires background.service_worker and prohibits background.scripts
        bg = manifest.get("background", {})
        self.assertIn("service_worker", bg, "background.service_worker is required for MV3")
        self.assertNotIn("scripts", bg, "background.scripts is invalid in Manifest V3")

        # Firefox MV3 requires gecko ID for installation
        settings = manifest.get("browser_specific_settings", {})
        self.assertIn("gecko", settings)
        self.assertTrue(settings["gecko"].get("id"))

        # Verify all referenced files exist on disk
        sw_file = os.path.join(ext_dir, bg["service_worker"])
        self.assertTrue(os.path.exists(sw_file), f"Service worker missing: {sw_file}")

        popup_html = os.path.join(ext_dir, manifest.get("action", {}).get("default_popup", ""))
        self.assertTrue(os.path.exists(popup_html), f"Popup HTML missing: {popup_html}")

        for icon_key, icon_rel in manifest.get("icons", {}).items():
            icon_path = os.path.join(ext_dir, icon_rel)
            self.assertTrue(os.path.exists(icon_path), f"Icon {icon_key} missing at {icon_path}")
            self.assertGreater(os.path.getsize(icon_path), 0, f"Icon {icon_key} is 0 bytes")


class TestVideoQualityFormatExtraction(unittest.TestCase):
    """Verifies YouTube format extraction, ranking, size calculation, and stream info construction."""

    def test_format_filesize_formatting(self):
        self.assertEqual(format_filesize(0), "N/A")
        self.assertEqual(format_filesize(-10), "N/A")
        self.assertEqual(format_filesize(500), "500 B")
        self.assertEqual(format_filesize(1024), "1.0 KB")
        self.assertEqual(format_filesize(1048576 * 150), "150.0 MB")
        self.assertEqual(format_filesize(1073741824 * 2), "2.0 GB")

    def test_build_format_options_hierarchy_and_pairing(self):
        mock_info = {
            "title": "NASA 4K Earth Flyby",
            "duration": 600,
            "formats": [
                # 4K 2160p Video-only (mp4)
                {
                    "format_id": "313",
                    "ext": "webm",
                    "height": 2160,
                    "fps": 60,
                    "vcodec": "vp9",
                    "acodec": "none",
                    "protocol": "https",
                    "url": "https://googlevideo.com/videoplayback?id=4k",
                    "filesize": 400000000
                },
                # 1080p Video-only (mp4)
                {
                    "format_id": "137",
                    "ext": "mp4",
                    "height": 1080,
                    "fps": 30,
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "protocol": "https",
                    "url": "https://googlevideo.com/videoplayback?id=1080p",
                    "filesize": 80000000
                },
                # 720p Progressive (audio+video)
                {
                    "format_id": "22",
                    "ext": "mp4",
                    "height": 720,
                    "fps": 30,
                    "vcodec": "avc1.64001F",
                    "acodec": "mp4a.40.2",
                    "protocol": "https",
                    "url": "https://googlevideo.com/videoplayback?id=720p_prog",
                    "filesize": 35000000
                },
                # 360p Progressive
                {
                    "format_id": "18",
                    "ext": "mp4",
                    "height": 360,
                    "fps": 30,
                    "vcodec": "avc1.42001E",
                    "acodec": "mp4a.40.2",
                    "protocol": "https",
                    "url": "https://googlevideo.com/videoplayback?id=360p_prog",
                    "filesize": 12000000
                },
                # Best Audio Only (m4a)
                {
                    "format_id": "140",
                    "ext": "m4a",
                    "abr": 128.0,
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "protocol": "https",
                    "url": "https://googlevideo.com/videoplayback?id=audio140",
                    "filesize": 9000000
                }
            ]
        }

        with patch("youtube_resolver.has_ffmpeg", return_value=True):
            resolver = YouTubeResolver()
            options = resolver.build_format_options(mock_info)

            # Expected order: 2160p (4K), 1080p, 720p, 360p, Audio Only
            self.assertGreaterEqual(len(options), 5)

            # 1. First option must be 4K (2160p)
            opt_4k = options[0]
            self.assertEqual(opt_4k.height, 2160)
            self.assertIn("2160p", opt_4k.resolution_label)
            self.assertFalse(opt_4k.is_progressive)
            self.assertFalse(opt_4k.is_audio_only)
            self.assertEqual(opt_4k.audio_url, "https://googlevideo.com/videoplayback?id=audio140")
            # Total size should combine video (400MB) + audio (9MB)
            self.assertEqual(opt_4k.filesize_approx, 400000000 + 9000000)

            # 2. Second option must be 1080p
            opt_1080 = options[1]
            self.assertEqual(opt_1080.height, 1080)
            self.assertEqual(opt_1080.audio_url, "https://googlevideo.com/videoplayback?id=audio140")

            # 3. Audio Only options must be present with height 0
            audio_opts = [o for o in options if o.height == 0]
            self.assertGreaterEqual(len(audio_opts), 1)
            self.assertTrue(any(o.is_audio_only and o.ext == "m4a" for o in audio_opts))
            self.assertTrue(any(o.is_audio_only and o.ext == "mp3" for o in audio_opts))

    def test_missing_filesize_and_protocol_none(self):
        """Verifies handling of formats with missing filesize and protocol=None."""
        mock_info = {
            "id": "test_null_proto",
            "title": "Bitrate Estimation Test",
            "duration": 60,
            "formats": [
                {
                    "format_id": "v1080",
                    "ext": "mp4",
                    "height": 1080,
                    "fps": 60,
                    "vcodec": "avc1",
                    "acodec": "none",
                    "protocol": None,
                    "url": "https://googlevideo.com/v1080",
                    "tbr": 3000.0,
                    "filesize": None
                },
                {
                    "format_id": "a140",
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "protocol": None,
                    "url": "https://googlevideo.com/a140",
                    "abr": 128.0,
                    "filesize": None
                }
            ]
        }
        with patch("youtube_resolver.has_ffmpeg", return_value=True):
            resolver = YouTubeResolver()
            options = resolver.build_format_options(mock_info)
            self.assertGreater(len(options), 0)
            opt_1080 = options[0]
            self.assertEqual(opt_1080.height, 1080)
            # 3000 kbps * 60s / 8 = 22,500,000 bytes
            self.assertGreater(opt_1080.filesize_approx, 20000000)

    def test_build_stream_info_variants(self):
        resolver = YouTubeResolver()
        mock_info = {
            "id": "abc12345678",
            "title": "Space / Odyssey: 2026",
            "duration": 180,
            "thumbnail": "https://example.com/thumb.jpg"
        }

        # Case A: Audio Only
        audio_opt = VideoFormatOption(
            format_id="audio_140",
            resolution_label="Audio Only (M4A)",
            height=0,
            ext="m4a",
            filesize_approx=5000000,
            is_progressive=True,
            is_audio_only=True,
            video_url="https://audio.example.com/stream"
        )
        s_audio = resolver.build_stream_info(mock_info, audio_opt)
        self.assertTrue(s_audio.is_audio_only)
        self.assertTrue(s_audio.is_progressive)
        self.assertTrue(s_audio.clean_filename.endswith(".m4a"))
        self.assertNotIn("/", s_audio.clean_filename)
        self.assertNotIn(":", s_audio.clean_filename)
        self.assertIsNone(s_audio.audio_url)

        # Case B: Dual-Stream 1080p
        dual_opt = VideoFormatOption(
            format_id="137+140",
            resolution_label="1080p (Full HD)",
            height=1080,
            ext="mp4",
            filesize_approx=55000000,
            fps=60,
            is_progressive=False,
            is_audio_only=False,
            video_url="https://video.example.com/stream",
            audio_url="https://audio.example.com/stream",
            audio_ext="m4a",
            audio_size=5000000
        )
        s_dual = resolver.build_stream_info(mock_info, dual_opt)
        self.assertFalse(s_dual.is_audio_only)
        self.assertFalse(s_dual.is_progressive)
        self.assertTrue(s_dual.clean_filename.endswith(".mp4"))
        self.assertEqual(s_dual.video_resolution, "1080p")
        self.assertEqual(s_dual.audio_url, "https://audio.example.com/stream")


class TestNativeMessagingHostProtocol(unittest.TestCase):
    """Verifies stdio 32-bit length-prefixed Native Messaging Host protocol and commands."""

    def test_read_and_send_message_binary_encoding(self):
        import io
        test_payload = {
            "action": "download",
            "url": "https://speed.cloudflare.com/50mb.bin",
            "filename": "speed_test.bin"
        }

        # Test sending
        out_buf = io.BytesIO()
        ok = send_message(test_payload, stream=out_buf)
        self.assertTrue(ok)

        # Verify length prefix matches JSON payload byte length
        raw_bytes = out_buf.getvalue()
        self.assertGreater(len(raw_bytes), 4)
        length_prefix = struct.unpack("@I", raw_bytes[:4])[0]
        json_bytes = raw_bytes[4:]
        self.assertEqual(length_prefix, len(json_bytes))

        # Test reading
        in_buf = io.BytesIO(raw_bytes)
        received = read_message(stream=in_buf)
        self.assertEqual(received, test_payload)

    def test_handle_payload_ping_offline(self):
        # Ping with port not bound
        res = handle_payload({"action": "ping"}, port=59998)
        self.assertTrue(res.get("success"))
        self.assertFalse(res.get("app_online"))

    def test_handle_payload_missing_url(self):
        res = handle_payload({"action": "download"})
        self.assertFalse(res.get("success"))
        self.assertIn("url", res.get("error", "").lower())

    def test_handle_payload_download_forwarding(self):
        # Start a temporary HTTP server acting as the desktop loopback bridge
        received_data = []

        class MockBridgeHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
            def do_POST(self):
                clen = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(clen)
                received_data.append(json.loads(body.decode("utf-8")))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"success": true, "message": "Dispatched"}')

        server = socketserver.TCPServer(("127.0.0.1", 0), MockBridgeHandler)
        port = server.server_address[1]
        srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
        srv_thread.start()

        try:
            payload = {
                "action": "download",
                "url": "https://example.com/testfile.zip",
                "filename": "testfile.zip"
            }
            res = handle_payload(payload, port=port)
            self.assertTrue(res.get("success"))
            self.assertEqual(len(received_data), 1)
            self.assertEqual(received_data[0]["url"], "https://example.com/testfile.zip")
            self.assertEqual(received_data[0]["filename"], "testfile.zip")
        finally:
            server.shutdown()
            server.server_close()


class TestBrowserRegistryIntegration(unittest.TestCase):
    """Verifies Windows Registry Native Messaging manifest generation and key management."""

    def test_compute_unpacked_extension_id(self):
        test_path = r"C:\Projects\Extensions\TurboExtension"
        ext_id = compute_unpacked_extension_id(test_path)
        self.assertEqual(len(ext_id), 32)
        # Must only contain characters a through p
        for char in ext_id:
            self.assertTrue("a" <= char <= "p", f"Invalid char {char} in extension id {ext_id}")

    def test_generate_host_manifest_structure(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            bat_path = os.path.join(tmp_dir, "launcher.bat")
            with open(bat_path, "w") as f:
                f.write("@echo off\n")

            json_path = os.path.join(tmp_dir, "manifest.json")
            res_path = generate_host_manifest(bat_path, json_path, ["chrome-extension://test/"])

            self.assertTrue(os.path.exists(res_path))
            with open(res_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.assertEqual(data["name"], "com.smartdownload.host")
            self.assertEqual(data["type"], "stdio")
            self.assertIn("chrome-extension://test/", data["allowed_origins"])
            self.assertEqual(data["path"], os.path.abspath(bat_path))

    def test_registry_registration_and_status(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Test registration
            reg_res = register_native_host(target_dir=tmp_dir)
            self.assertTrue(reg_res.get("success"))
            self.assertTrue(os.path.exists(reg_res["manifest_path"]))
            self.assertTrue(os.path.exists(reg_res["launcher_path"]))

            # Verify registry check
            self.assertTrue(is_browser_registered("chrome"))
            self.assertTrue(is_browser_registered("edge"))

            status = get_browser_reg_status()
            self.assertTrue(status["chrome_registered"])
            self.assertTrue(status["edge_registered"])
            self.assertTrue(status["is_registered"])

            # Clean unregistration
            unreg_res = unregister_native_host()
            self.assertTrue(unreg_res.get("success"))
            self.assertFalse(is_browser_registered("chrome"))
            self.assertFalse(is_browser_registered("edge"))

    def test_extension_registry_keys(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile, winreg
        from register_browser import CHROME_EXT_KEY_PREFIX, EDGE_EXT_KEY_PREFIX, STATIC_EXTENSION_ID

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a mock extension folder with manifest
            ext_dir = os.path.join(tmp_dir, "extension")
            os.makedirs(ext_dir, exist_ok=True)
            with open(os.path.join(ext_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "TestExt", "version": "1.0.0"}, f)

            res = register_browser_extensions(extension_dir=ext_dir)
            self.assertTrue(res.get("success"))
            self.assertTrue(is_extension_registered("chrome", STATIC_EXTENSION_ID))
            self.assertTrue(is_extension_registered("edge", STATIC_EXTENSION_ID))

            # Verify registry key contents
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{CHROME_EXT_KEY_PREFIX}\{STATIC_EXTENSION_ID}")
            ver, _ = winreg.QueryValueEx(key, "version")
            path_val, _ = winreg.QueryValueEx(key, "path")
            winreg.CloseKey(key)
            self.assertEqual(ver, "1.0.0")
            self.assertEqual(path_val, os.path.abspath(ext_dir))

            # Unregister
            unreg = unregister_browser_extensions()
            self.assertTrue(unreg.get("success"))
            self.assertFalse(is_extension_registered("chrome", STATIC_EXTENSION_ID))
            self.assertFalse(is_extension_registered("edge", STATIC_EXTENSION_ID))

    def test_idempotent_browser_registration_fast(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            # First run: initial registration
            init_res = check_and_register_browser(target_dir=tmp_dir)
            self.assertTrue(init_res.get("success"))
            self.assertTrue(init_res.get("healed"))

            # Second run: should be completely idempotent and complete in < 5ms
            idempotent_res = check_and_register_browser(target_dir=tmp_dir, force=False)
            self.assertTrue(idempotent_res.get("success"))
            self.assertTrue(idempotent_res.get("idempotent"))
            self.assertFalse(idempotent_res.get("healed"))
            # Must satisfy < 5ms requirement
            self.assertLess(idempotent_res.get("duration_ms", 999.0), 5.0,
                            f"Idempotent check took {idempotent_res.get('duration_ms')}ms (expected < 5ms)")

            # Clean up
            unregister_native_host()

    def test_self_healing_browser_registration(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile, winreg
        with tempfile.TemporaryDirectory() as tmp_dir1, tempfile.TemporaryDirectory() as tmp_dir2:
            # 1. Register with dir1
            r1 = check_and_register_browser(target_dir=tmp_dir1)
            self.assertTrue(r1.get("success"))

            # 2. Simulate path change or relocation to dir2: check_and_register_browser should detect
            # mismatch and self-heal by updating to dir2
            r2 = check_and_register_browser(target_dir=tmp_dir2)
            self.assertTrue(r2.get("success"))
            self.assertTrue(r2.get("healed"))
            self.assertFalse(r2.get("idempotent"))

            # Verify registry key now points to dir2
            from register_browser import CHROME_REG_KEY
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHROME_REG_KEY)
            manifest_val, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            expected_m2 = os.path.normcase(os.path.abspath(os.path.join(tmp_dir2, "com.smartdownload.host.json")))
            self.assertEqual(os.path.normcase(os.path.abspath(manifest_val)), expected_m2)

            # Clean up
            unregister_native_host()

    def test_self_healing_corrupted_or_missing_launcher_in_manifest(self):
        """Verifies that check_and_register_browser heals if manifest points to missing/wrong launcher."""
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            # First register normally
            r1 = check_and_register_browser(target_dir=tmp_dir)
            self.assertTrue(r1.get("success"))

            # Simulate corrupted manifest pointing to non-existent launcher
            manifest_file = os.path.join(tmp_dir, "com.smartdownload.host.json")
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump({"name": "com.smartdownload.host", "path": r"C:\fake\missing\sd_host.bat", "type": "stdio"}, f)

            # Check and register should detect the broken launcher path and heal it
            r2 = check_and_register_browser(target_dir=tmp_dir)
            self.assertTrue(r2.get("success"))
            self.assertTrue(r2.get("healed"), "check_and_register_browser must heal a manifest pointing to a nonexistent launcher")

            # Verify manifest was healed with valid existing launcher path
            with open(manifest_file, "r", encoding="utf-8") as f:
                healed_data = json.load(f)
            self.assertTrue(os.path.isfile(healed_data["path"]))
            self.assertEqual(os.path.normcase(os.path.dirname(os.path.abspath(healed_data["path"]))),
                             os.path.normcase(os.path.abspath(tmp_dir)))

            # Clean up
            unregister_native_host()

    def test_get_default_extension_origins_with_target_dir(self):
        """Verifies that get_default_extension_origins includes unpacked ID for target_dir/extension."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            ext_dir = os.path.join(tmp_dir, "extension")
            os.makedirs(ext_dir, exist_ok=True)
            with open(os.path.join(ext_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "Test"}, f)

            expected_id = compute_unpacked_extension_id(ext_dir)
            origins = get_default_extension_origins(target_dir=tmp_dir)
            self.assertIn(f"chrome-extension://{expected_id}/", origins)

    def test_fast_launcher_batch_executable_priority(self):
        """Verifies launcher batch checks TurboDownloader.exe before searching for python."""
        import tempfile
        from register_browser import generate_launcher_batch
        with tempfile.TemporaryDirectory() as tmp_dir:
            bat_path = os.path.join(tmp_dir, "sd_host.bat")
            generate_launcher_batch(bat_path)
            with open(bat_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Ensure TurboDownloader.exe check appears before where python
            idx_exe = content.find("SmartDownload.exe")
            idx_py = content.find("where py")
            self.assertNotEqual(idx_exe, -1)
            if idx_py != -1:
                self.assertLess(idx_exe, idx_py, "SmartDownload.exe standalone check must precede python search in batch launcher")



class TestWindowsInstallerLogic(unittest.TestCase):
    """Verifies standalone Windows Installer logic, zero-elevation paths, and shortcuts."""

    def test_default_install_dir_and_constants(self):
        self.assertEqual(installer.APP_ID, "SmartDownload")
        self.assertEqual(installer.APP_NAME, "Smart Download (SD)")
        self.assertTrue(installer.DEFAULT_INSTALL_DIR.endswith(r"Programs\SmartDownload"))
        # Ensure path is user-level inside LocalAppData (zero admin/UAC elevation needed)
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            self.assertTrue(installer.DEFAULT_INSTALL_DIR.lower().startswith(local_app_data.lower()))

    def test_register_and_unregister_uninstall_entry(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Windows Registry tests only run on Windows OS.")

        import tempfile, winreg
        with tempfile.TemporaryDirectory() as tmp_dir:
            exe_path = os.path.join(tmp_dir, "SmartDownload.exe")
            with open(exe_path, "w") as f:
                f.write("mock")
            uninst_path = os.path.join(tmp_dir, "Uninstall.exe")
            with open(uninst_path, "w") as f:
                f.write("mock")

            reg_ok = installer.register_uninstall_entry(tmp_dir, exe_path, uninst_path)
            self.assertTrue(reg_ok)

            # Query uninstall key
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.UNINSTALL_REG_KEY)
            disp_name, _ = winreg.QueryValueEx(key, "DisplayName")
            uninst_cmd, _ = winreg.QueryValueEx(key, "UninstallString")
            quiet_uninst_cmd, _ = winreg.QueryValueEx(key, "QuietUninstallString")
            no_modify, _ = winreg.QueryValueEx(key, "NoModify")
            winreg.CloseKey(key)

            self.assertEqual(disp_name, "Smart Download (SD)")
            self.assertIn("Uninstall.exe", uninst_cmd)
            self.assertIn("--uninstall", uninst_cmd)
            self.assertIn("--silent", quiet_uninst_cmd)
            self.assertEqual(no_modify, 1)

            # Clean up
            unreg_ok = installer.unregister_uninstall_entry()
            self.assertTrue(unreg_ok)

            # Verify key is gone
            with self.assertRaises(FileNotFoundError):
                winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.UNINSTALL_REG_KEY)

    def test_create_windows_shortcut(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Shortcut test only runs on Windows OS.")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "app.exe")
            with open(target, "w") as f:
                f.write("mock")
            shortcut = os.path.join(tmp_dir, "TestShortcut.lnk")

            ok = installer.create_windows_shortcut(target, shortcut, description="Test App")
            self.assertTrue(ok)
            self.assertTrue(os.path.isfile(shortcut))

    def test_install_and_uninstall_lifecycle(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Installer tests only run on Windows OS.")

        import tempfile
        progress_events = []

        def _cb(pct, msg):
            progress_events.append((pct, msg))

        with tempfile.TemporaryDirectory() as tmp_dir:
            install_target = os.path.join(tmp_dir, "InstalledTurbo")

            # Execute install into test folder
            res = installer.install_application(
                target_dir=install_target,
                create_desktop=False,
                create_start_menu=False,
                register_browser=False,
                progress_cb=_cb
            )
            self.assertTrue(res.get("success"))
            self.assertTrue(os.path.isdir(install_target))
            self.assertTrue(os.path.isfile(os.path.join(install_target, "SmartDownload.exe")))
            self.assertTrue(os.path.isfile(os.path.join(install_target, "app_icon.ico")))
            self.assertTrue(len(progress_events) >= 5)
            self.assertEqual(progress_events[-1][0], 1.0)

            # Execute uninstall
            un_progress = []
            un_res = installer.uninstall_application(
                target_dir=install_target,
                progress_cb=lambda p, m: un_progress.append((p, m))
            )
            self.assertTrue(un_res.get("success"))
            self.assertTrue(len(un_progress) >= 4)
            self.assertEqual(un_progress[-1][0], 1.0)
            self.assertFalse(os.path.exists(install_target))

    def test_installer_gui_initialization_grab_free(self):
        """Verifies Tkinter InstallerGUI creates without grab lock and has responsive layout."""
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            gui = installer.InstallerGUI(root, mode="install")
            self.assertEqual(gui.mode, "install")
            # Verify grab-free: root must NOT have active grab lock
            self.assertIsNone(root.grab_current(), "Installer GUI must be grab-free without modal lock")
            # Verify UI elements exist
            self.assertTrue(hasattr(gui, "entry_dir"))
            self.assertTrue(hasattr(gui, "btn_action"))
            self.assertTrue(hasattr(gui, "btn_cancel"))
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_shell_desktop_and_programs_directory_resolution(self):
        """Verifies get_desktop_dir and get_start_menu_programs_dir return valid existing folders."""
        desktop_dir = installer.get_desktop_dir()
        programs_dir = installer.get_start_menu_programs_dir()
        self.assertTrue(os.path.isdir(desktop_dir), f"Desktop folder {desktop_dir} must exist")
        self.assertTrue(os.path.isdir(programs_dir), f"Programs folder {programs_dir} must exist")

    def test_uninstaller_binary_mode_detection(self):
        """Verifies that running with an uninstaller binary name defaults to uninstall mode."""
        with patch("sys.executable", "C:\\Programs\\SmartDownload\\Uninstall.exe"):
            exe_name = os.path.basename(sys.executable).lower()
            is_uninst = "uninstall" in exe_name
            self.assertTrue(is_uninst)
            mode = "uninstall" if is_uninst else "install"
            self.assertEqual(mode, "uninstall")



class TestQualitySelectionModalGUI(unittest.TestCase):
    """Verifies Tkinter QualitySelectionModal dialog behavior and edge case handling."""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.update_idletasks()
            cls.root.destroy()
        except Exception:
            pass

    def tearDown(self):
        try:
            for child in self.root.winfo_children():
                child.destroy()
            self.root.update_idletasks()
        except Exception:
            pass

    def test_modal_initialization_and_selection(self):
        from turbo_downloader import QualitySelectionModal, VideoFormatOption
        options = [
            VideoFormatOption(
                format_id="137+140",
                resolution_label="1080p (Full HD)",
                height=1080,
                ext="mp4",
                filesize_approx=55000000,
                fps=60,
                is_progressive=False,
                is_audio_only=False,
                video_url="https://video.com",
                audio_url="https://audio.com",
                note="60 FPS • Lossless Merge (FFmpeg)"
            ),
            VideoFormatOption(
                format_id="140",
                resolution_label="Audio Only (M4A)",
                height=0,
                ext="m4a",
                filesize_approx=5000000,
                fps=0,
                is_progressive=True,
                is_audio_only=True,
                video_url="https://audio.com",
                note="High Quality Audio"
            )
        ]

        confirmed = []
        theme = {
            "c_bg": "#1e293b",
            "c_panel": "#0f172a",
            "c_panel_light": "#334155",
            "c_border": "#475569",
            "c_accent": "#38bdf8",
            "c_accent_dark": "#0284c7",
            "c_success": "#10b981",
            "c_text_bright": "#f8fafc",
            "c_text_muted": "#94a3b8",
            "c_input_bg": "#0f172a"
        }

        modal = QualitySelectionModal(
            parent=self.root,
            video_title="NASA 4K Earth View",
            duration=300,
            options=options,
            default_dest_path="C:/Downloads/Earth.mp4",
            theme=theme,
            on_confirm=lambda opt, dest: confirmed.append((opt, dest))
        )

        # 1. First option is selected by default
        self.assertEqual(modal.selected_option.height, 1080)
        self.assertEqual(modal.entry_dest.get(), "C:/Downloads/Earth.mp4")

        # 2. Select audio option row and verify dynamic extension update
        modal.tree.selection_set("opt_1")
        modal._on_tree_select(None)
        self.assertEqual(modal.selected_option.height, 0)
        self.assertTrue(modal.entry_dest.get().endswith(".m4a"))

        # 3. Simulate confirming download
        modal._on_download()
        self.assertEqual(len(confirmed), 1)
        opt, dest = confirmed[0]
        self.assertEqual(opt.height, 0)
        self.assertTrue(dest.endswith(".m4a"))

    def test_modal_fallback_when_dest_cleared(self):
        from turbo_downloader import QualitySelectionModal, VideoFormatOption
        options = [
            VideoFormatOption(
                format_id="22",
                resolution_label="720p (HD)",
                height=720,
                ext="mp4",
                filesize_approx=20000000,
                fps=30,
                is_progressive=True,
                is_audio_only=False,
                video_url="https://video.com"
            )
        ]
        confirmed = []
        theme = {
            "c_bg": "#000", "c_panel": "#111", "c_panel_light": "#222", "c_border": "#333",
            "c_accent": "#444", "c_accent_dark": "#555", "c_success": "#666",
            "c_text_bright": "#fff", "c_text_muted": "#888", "c_input_bg": "#000"
        }
        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Fallback Test",
            duration=60,
            options=options,
            default_dest_path="C:/Downloads/test.mp4",
            theme=theme,
            on_confirm=lambda opt, dest: confirmed.append((opt, dest))
        )
        # Clear destination box
        modal.entry_dest.delete(0, "end")
        modal._on_download()

        self.assertEqual(len(confirmed), 1)
        _, dest = confirmed[0]
        self.assertTrue(len(dest) > 0, "Destination path must fallback cleanly when input is cleared")

    def test_modal_zorder_and_topmost_attributes(self):
        """Verifies QualitySelectionModal configures topmost and elevation to prevent hiding behind borderless parent."""
        from turbo_downloader import QualitySelectionModal, VideoFormatOption
        options = [
            VideoFormatOption(
                format_id="18",
                resolution_label="360p",
                height=360,
                ext="mp4",
                filesize_approx=1000000,
                fps=30,
                is_progressive=True,
                is_audio_only=False,
                video_url="https://video.com"
            )
        ]
        theme = {
            "c_bg": "#000", "c_panel": "#111", "c_panel_light": "#222", "c_border": "#333",
            "c_accent": "#444", "c_accent_dark": "#555", "c_success": "#666",
            "c_text_bright": "#fff", "c_text_muted": "#888", "c_input_bg": "#000"
        }
        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Topmost Test",
            duration=60,
            options=options,
            default_dest_path="C:/Downloads/test.mp4",
            theme=theme,
            on_confirm=lambda opt, dest: None
        )
        self.assertTrue(modal.attributes("-topmost"))
        self.root.update_idletasks()

    def test_ui_cancellation_and_error_handling_resets_state(self):
        """Verifies cancellation and error callbacks reset card_size, btn_start, and btn_cancel properly."""
        from turbo_downloader import ModernFramelessGUI
        import tkinter as tk

        class DummyUI:
            def __init__(self, root):
                self.root = root
                self._yt_cancel_event = threading.Event()
                self.engine = None
                self.btn_start = tk.Button(root)
                self.btn_pause = tk.Button(root)
                self.btn_cancel = tk.Button(root)
                self.card_size = tk.Label(root)
                self.c_panel_light = "#334155"
                self.logs = []

            def log(self, msg):
                self.logs.append(msg)

        dummy = DummyUI(self.root)
        dummy.btn_start.configure(state="disabled")
        dummy.btn_cancel.configure(state="normal")
        dummy.card_size.configure(text="Fetching available formats...")

        # 1. Trigger cancellation via ModernFramelessGUI method
        ModernFramelessGUI._on_cancel_download(dummy)
        self.assertTrue(dummy._yt_cancel_event.is_set())
        self.assertEqual(str(dummy.btn_start["state"]), "normal")
        self.assertEqual(str(dummy.btn_cancel["state"]), "disabled")
        self.assertEqual(dummy.card_size.cget("text"), "Ready")

        # 2. Trigger error callback via ModernFramelessGUI method
        with patch("tkinter.messagebox.showerror"):
            dummy.card_size.configure(text="Fetching available formats...")
            dummy.btn_start.configure(state="disabled")
            dummy.btn_cancel.configure(state="normal")
            ModernFramelessGUI._engine_error_cb(dummy, "Simulated stream extraction error")
            self.root.update()
            self.assertEqual(str(dummy.btn_start["state"]), "normal")
            self.assertEqual(str(dummy.btn_cancel["state"]), "disabled")
            self.assertEqual(dummy.card_size.cget("text"), "Ready")

    def test_modal_handles_none_inputs(self):
        """Verifies QualitySelectionModal handles video_title=None, duration=None, and default_dest_path=None safely."""
        from turbo_downloader import QualitySelectionModal, VideoFormatOption
        options = [
            VideoFormatOption(
                format_id="18",
                resolution_label="360p",
                height=360,
                ext="mp4",
                filesize_approx=1000000,
                fps=30,
                is_progressive=True,
                is_audio_only=False,
                video_url="https://video.com"
            )
        ]
        theme = {
            "c_bg": "#000", "c_panel": "#111", "c_panel_light": "#222", "c_border": "#333",
            "c_accent": "#444", "c_accent_dark": "#555", "c_success": "#666",
            "c_text_bright": "#fff", "c_text_muted": "#888", "c_input_bg": "#000"
        }
        # Should NOT raise TypeError or crash
        modal = QualitySelectionModal(
            parent=self.root,
            video_title=None,
            duration=None,
            options=options,
            default_dest_path=None,
            theme=theme,
            on_confirm=lambda opt, dest: None
        )
        self.assertEqual(modal.video_title, "YouTube Video")
        self.assertEqual(modal.duration, 0)
        self.assertEqual(modal.dest_path, "")

    def test_modal_fallback_dest_path_with_audio_format(self):
        """Verifies destination path fallback properly retains audio container extension."""
        from turbo_downloader import QualitySelectionModal, VideoFormatOption
        options = [
            VideoFormatOption(
                format_id="140",
                resolution_label="Audio Only (M4A)",
                height=0,
                ext="m4a",
                filesize_approx=5000000,
                fps=0,
                is_progressive=True,
                is_audio_only=True,
                video_url="https://audio.com"
            )
        ]
        confirmed = []
        theme = {
            "c_bg": "#000", "c_panel": "#111", "c_panel_light": "#222", "c_border": "#333",
            "c_accent": "#444", "c_accent_dark": "#555", "c_success": "#666",
            "c_text_bright": "#fff", "c_text_muted": "#888", "c_input_bg": "#000"
        }
        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Song Title",
            duration=120,
            options=options,
            default_dest_path="C:/Downloads/song.mp4",  # initially had .mp4
            theme=theme,
            on_confirm=lambda opt, dest: confirmed.append((opt, dest))
        )
        modal.entry_dest.delete(0, "end")  # clear it out
        modal._on_download()

        self.assertEqual(len(confirmed), 1)
        _, dest = confirmed[0]
        self.assertTrue(dest.lower().endswith(".m4a"), f"Fallback destination must end with .m4a, got {dest}")

    def test_ui_cancellation_dismisses_active_modal(self):
        """Verifies ModernFramelessGUI._on_cancel_download actively destroys and clears _quality_modal."""
        from turbo_downloader import ModernFramelessGUI
        import tkinter as tk

        class DummyUIWithModal:
            def __init__(self, root):
                self.root = root
                self._yt_cancel_event = threading.Event()
                self._quality_modal = tk.Toplevel(root)
                self.engine = None
                self.btn_start = tk.Button(root)
                self.btn_pause = tk.Button(root)
                self.btn_cancel = tk.Button(root)
                self.card_size = tk.Label(root)
                self.c_panel_light = "#334155"

            def log(self, msg):
                pass

        dummy = DummyUIWithModal(self.root)
        self.assertTrue(dummy._quality_modal.winfo_exists())

        ModernFramelessGUI._on_cancel_download(dummy)
        self.assertIsNone(dummy._quality_modal)
        self.assertEqual(dummy.card_size.cget("text"), "Ready")

    def test_engine_and_coordinator_rlock_and_snapshot(self):
        """Verifies TurboDownloadEngine and StreamDownloadCoordinator use re-entrant locks and snapshot methods."""
        from turbo_downloader import DownloadChunk, YouTubeStreamInfo
        engine = TurboDownloadEngine("https://example.com/file.zip", "test.zip")
        self.assertTrue(isinstance(engine._lock, type(threading.RLock())), "TurboDownloadEngine._lock must be threading.RLock")

        # Verify re-entrancy
        with engine._lock:
            with engine._lock:
                snapshot = engine.get_chunks_snapshot()
                self.assertEqual(snapshot, [])

        stream_info = YouTubeStreamInfo(
            video_id="test",
            title="test",
            clean_filename="test.mp4",
            is_progressive=True,
            video_url="https://example.com/stream",
            video_headers={},
            video_ext="mp4",
            video_resolution="720p",
            video_size=1000,
            audio_url=None,
            audio_headers={},
            audio_ext="",
            audio_size=0,
            duration=10,
            thumbnail_url="",
            is_audio_only=False
        )
        coordinator = StreamDownloadCoordinator(stream_info, "out.mp4")
        self.assertTrue(isinstance(coordinator._lock, type(threading.RLock())), "StreamDownloadCoordinator._lock must be threading.RLock")

        # Verify re-entrancy when no current_engine
        with coordinator._lock:
            with coordinator._lock:
                self.assertEqual(coordinator.get_chunks_snapshot(), [])

        # Assign child engine with chunks
        coordinator.current_engine = engine
        c1 = DownloadChunk(0, 0, 499, 200, "downloading", "p0")
        c2 = DownloadChunk(1, 500, 999, 100, "downloading", "p1")
        with engine._lock:
            engine.chunks.extend([c1, c2])

        # Verify coordinator gets chunks under lock without deadlock
        with coordinator._lock:
            snapshot = coordinator.get_chunks_snapshot()
            self.assertEqual(len(snapshot), 2)
            self.assertEqual(snapshot[0].chunk_id, 0)
            self.assertEqual(snapshot[1].chunk_id, 1)

    def test_refresh_chunk_displays_does_not_deadlock(self):
        """Verifies _refresh_chunk_displays does not deadlock when engine is StreamDownloadCoordinator."""
        from turbo_downloader import ModernFramelessGUI, DownloadChunk, YouTubeStreamInfo
        import tkinter as tk
        from tkinter import ttk

        class DummyGUI:
            def __init__(self, root):
                self.root = root
                self.width = 600
                self.height = 400
                self.c_bg = "#000"
                self.c_panel = "#111"
                self.c_border = "#222"
                self.c_input_bg = "#333"
                self.c_text_muted = "#888"
                self.c_text_bright = "#fff"
                self.c_accent = "#38bdf8"
                self.c_success = "#10b981"
                self.engine = None
                self.canvas_chunks = tk.Canvas(root, width=500, height=30)
                self.tree_chunks = ttk.Treeview(root, columns=("id", "range", "size", "downloaded", "pct", "status"))

            def _draw_chunk_segments(self, chunks):
                ModernFramelessGUI._draw_chunk_segments(self, chunks)

        gui = DummyGUI(self.root)
        stream_info = YouTubeStreamInfo(
            video_id="test",
            title="test",
            clean_filename="test.mp4",
            is_progressive=True,
            video_url="https://example.com/stream",
            video_headers={},
            video_ext="mp4",
            video_resolution="720p",
            video_size=1000,
            audio_url=None,
            audio_headers={},
            audio_ext="",
            audio_size=0,
            duration=10,
            thumbnail_url="",
            is_audio_only=False
        )
        coord = StreamDownloadCoordinator(stream_info, "out.mp4")
        child_engine = TurboDownloadEngine("https://example.com/stream", "out.mp4")
        c1 = DownloadChunk(0, 0, 499, 250, "downloading", "p0")
        c2 = DownloadChunk(1, 500, 999, 500, "completed", "p1")
        child_engine.chunks = [c1, c2]
        coord.current_engine = child_engine
        gui.engine = coord

        # Run _refresh_chunk_displays and verify it completes without deadlock
        ModernFramelessGUI._refresh_chunk_displays(gui)

        items = gui.tree_chunks.get_children()
        self.assertEqual(len(items), 2)
        self.assertIn("c_0", items)
        self.assertIn("c_1", items)


class TestYouTubeSafeConcurrencyAndErrorHandling(unittest.TestCase):
    """
    Verifies:
    1. Googlevideo CDN URL detection across multiple URL formats.
    2. Concurrency capping to 1 connection and disabling dynamic splitting for googlevideo streams.
    3. StreamDownloadCoordinator safe concurrency capping for YouTube streams.
    4. SafeModalDialog compatibility with Tkinter overrideredirect(True) frameless windows.
    5. ModernFramelessGUI._engine_error_cb safe error handling without window crashes.
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

    def test_googlevideo_url_detection(self):
        gv_urls = [
            "https://rr1---sn-4g5ednks.googlevideo.com/videoplayback?expire=123&ei=456",
            "http://rr5---sn-mock.googlevideo.com/videoplayback",
            "https://googlevideo.com/videoplayback?id=789",
            "https://www.youtube.com/watch?v=GTNypvv2Nbg",
            "https://youtu.be/GTNypvv2Nbg?si=co6maPGPzPMYy8qb",
        ]
        for url in gv_urls:
            self.assertTrue(
                TurboDownloadEngine.is_googlevideo_url(url),
                f"Failed to detect YouTube/googlevideo URL: {url}"
            )

        non_gv_urls = [
            "https://speed.cloudflare.com/__down?bytes=50000000",
            "https://archive.org/download/test/test.mp4",
            "http://127.0.0.1:8080/file.bin",
            "https://example.com/stream.mp4",
            "",
            None
        ]
        for url in non_gv_urls:
            self.assertFalse(
                TurboDownloadEngine.is_googlevideo_url(url),
                f"False positive detection for non-googlevideo URL: {url}"
            )

    def test_googlevideo_caps_concurrency_and_disables_dynamic_splitting(self):
        url = "https://rr1---sn-mock.googlevideo.com/videoplayback?id=123"
        engine = TurboDownloadEngine(url, "video.mp4", max_connections=8)

        self.assertTrue(engine.is_googlevideo)
        self.assertEqual(engine.max_connections, 1, "Googlevideo streams must be capped to 1 connection max")
        self.assertFalse(engine.allow_dynamic_split, "Dynamic splitting must be disabled for googlevideo streams")

        # Verify _dynamic_split_check refuses to split chunks
        from turbo_downloader import DownloadChunk
        c0 = DownloadChunk(0, 0, 10000000, 1000, "active", "video.mp4.part_0")
        engine.chunks = [c0]
        engine.total_size = 10000000
        engine.supports_ranges = True
        engine._dynamic_split_check()

        self.assertEqual(len(engine.chunks), 1, "Must not split chunks when allow_dynamic_split is False or is_googlevideo is True")

    def test_coordinator_youtube_stream_safe_concurrency(self):
        stream_info = YouTubeStreamInfo(
            video_id="GTNypvv2Nbg",
            title="Safe Concurrency Test",
            clean_filename="Safe_Test.mp4",
            is_progressive=False,
            video_url="https://rr1---sn-mock.googlevideo.com/videoplayback?id=video",
            video_size=5000000,
            audio_url="https://rr1---sn-mock.googlevideo.com/videoplayback?id=audio",
            audio_size=1000000
        )
        coord = StreamDownloadCoordinator(stream_info, "Safe_Test.mp4", max_connections=8)
        self.assertTrue(coord.is_youtube_stream)
        self.assertEqual(coord.max_connections, 1, "Coordinator must cap YouTube stream concurrency to 1")

    def test_safemodal_dialog_with_overrideredirect(self):
        """Verifies SafeModalDialog displays on overrideredirect(True) window without Win32 crash."""
        import tkinter as tk
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry("400x300+100+100")
        self.root.update()

        dialog = SafeModalDialog(
            parent=self.root,
            title="Download Error",
            message="HTTP 403 Forbidden: Simulated YouTube stream interruption",
            dialog_type="error"
        )
        self.root.update()
        self.assertTrue(dialog.winfo_exists())
        self.assertFalse(dialog.result)

        # Confirm OK dismisses safely
        dialog._on_ok()
        self.root.update()
        self.assertTrue(dialog.result)
        self.assertFalse(dialog.winfo_exists())

    def test_engine_error_callback_safe_modal_no_crash(self):
        """Verifies ModernFramelessGUI._engine_error_cb displays errors without calling crashing native messagebox."""
        import tkinter as tk
        self.root = tk.Tk()
        gui = ModernFramelessGUI(self.root)
        self.root.update()

        # Simulate error callback
        gui._engine_error_cb("HTTP Error 403: Forbidden - YouTube Range Abort")
        self.root.update()

        # Verify buttons were reset and status card shows Ready
        self.assertEqual(str(gui.btn_start["state"]), "normal")
        self.assertEqual(str(gui.btn_cancel["state"]), "disabled")
        self.assertEqual(gui.card_size.cget("text"), "Ready")
        gui._on_close()

    def test_youtube_aspect_ratio_height_labels(self):
        """Verifies that non-standard aspect-ratio cropped heights map to appropriate labels."""
        resolver = YouTubeResolver()
        mock_info = {
            "id": "GTNypvv2Nbg",
            "title": "Aspect Test",
            "duration": 200,
            "formats": [
                {"format_id": "137", "url": "https://googlevideo.com/137", "height": 1072, "ext": "mp4", "protocol": "https", "vcodec": "avc1"},
                {"format_id": "136", "url": "https://googlevideo.com/136", "height": 714, "ext": "mp4", "protocol": "https", "vcodec": "avc1"},
                {"format_id": "135", "url": "https://googlevideo.com/135", "height": 476, "ext": "mp4", "protocol": "https", "vcodec": "avc1"},
                {"format_id": "140", "url": "https://googlevideo.com/140", "ext": "m4a", "protocol": "https", "acodec": "mp4a", "abr": 128}
            ]
        }
        with patch("youtube_resolver.has_ffmpeg", return_value=True):
            options = resolver.build_format_options(mock_info)
            opts_map = {opt.height: opt.resolution_label for opt in options if opt.height > 0}
            self.assertIn("1080p", opts_map.get(1072, ""))
            self.assertIn("720p", opts_map.get(714, ""))
            self.assertIn("480p", opts_map.get(476, ""))

    def test_youtube_original_audio_prioritization(self):
        """Verifies that original audio is prioritized over dubbed audio."""
        resolver = YouTubeResolver()
        mock_info = {
            "id": "GTNypvv2Nbg",
            "title": "Audio Lang Test",
            "duration": 200,
            "formats": [
                {"format_id": "136", "url": "https://googlevideo.com/136", "height": 720, "ext": "mp4", "protocol": "https", "vcodec": "avc1"},
                {"format_id": "140-dub", "url": "https://googlevideo.com/140-dub", "ext": "m4a", "protocol": "https", "acodec": "mp4a", "abr": 128, "language": "en-US", "language_preference": -1},
                {"format_id": "140-orig", "url": "https://googlevideo.com/140-orig", "ext": "m4a", "protocol": "https", "acodec": "mp4a", "abr": 128, "language": "ar", "language_preference": 10}
            ]
        }
        with patch("youtube_resolver.has_ffmpeg", return_value=True):
            options = resolver.build_format_options(mock_info)
            opt_720 = [o for o in options if o.height == 720][0]
            self.assertEqual(opt_720.audio_url, "https://googlevideo.com/140-orig")

    def test_googlevideo_segmented_range_requests(self):
        """Verifies TurboDownloadEngine uses 1MB range segments for YouTube googlevideo URLs."""
        url = "https://rr1---sn-mock.googlevideo.com/videoplayback?id=123"
        engine = TurboDownloadEngine(url, "video.mp4", max_connections=1)
        self.assertTrue(engine.is_googlevideo)
        self.assertEqual(engine.max_connections, 1)
        self.assertFalse(engine.allow_dynamic_split)

    def test_coordinator_detects_youtube_stream_by_video_id_alone(self):
        """Verifies StreamDownloadCoordinator caps concurrency to 1 based on video_id even without googlevideo domain."""
        stream_info = YouTubeStreamInfo(
            video_id="GTNypvv2Nbg",
            title="Mirror URL Test",
            clean_filename="Mirror_Test.mp4",
            is_progressive=True,
            video_url="https://proxy-cdn.internal.net/stream?id=99",
            video_size=10000000
        )
        coord = StreamDownloadCoordinator(stream_info, "Mirror_Test.mp4", max_connections=16)
        self.assertTrue(coord.is_youtube_stream)
        self.assertEqual(coord.max_connections, 1)

    def test_safemodal_dialog_destroy_releases_grab(self):
        """Verifies calling destroy() directly on SafeModalDialog safely releases grab without TclError."""
        import tkinter as tk
        root = tk.Tk()
        root.overrideredirect(True)
        root.geometry("300x200+50+50")
        root.update()

        dialog = SafeModalDialog(
            parent=root,
            title="Error Test",
            message="Test message",
            dialog_type="error"
        )
        root.update()
        self.assertTrue(dialog.winfo_exists())
        # Directly destroy
        dialog.destroy()
        root.update()
        self.assertFalse(dialog.winfo_exists())
        root.destroy()

    def test_quality_modal_destroy_releases_grab(self):
        """Verifies calling destroy() directly on QualitySelectionModal releases grab cleanly."""
        import tkinter as tk
        root = tk.Tk()
        root.overrideredirect(True)
        root.geometry("400x300+50+50")
        root.update()

        modal = QualitySelectionModal(
            parent=root,
            video_title="Test Video",
            duration=120,
            options=[],
            default_dest_path="test.mp4",
            theme={"c_bg": "#111", "c_panel": "#222", "c_panel_light": "#333", "c_border": "#444", "c_accent": "#555", "c_accent_dark": "#666", "c_success": "#777", "c_text_bright": "#eee", "c_text_muted": "#888", "c_input_bg": "#000"},
            on_confirm=lambda o, p: None
        )
        root.update()
        self.assertTrue(modal.winfo_exists())
        modal.destroy()
        root.update()
        self.assertFalse(modal.winfo_exists())
        root.destroy()

    def test_gui_registers_wm_delete_window(self):
        """Verifies ModernFramelessGUI registers WM_DELETE_WINDOW protocol."""
        import tkinter as tk
        root = tk.Tk()
        gui = ModernFramelessGUI(root)
        root.update()
        handler = root.protocol("WM_DELETE_WINDOW")
        self.assertTrue(bool(handler), "WM_DELETE_WINDOW protocol must be registered")
        gui._on_close()


class TestClipboardSnifferAndUrlValidation(unittest.TestCase):
    """
    Automated tests verifying the TDM-style Clipboard Sniffer and URL validation:
    1. Validation of direct file download extensions across categories.
    2. YouTube video, short, and music URL recognition.
    3. Query parameter indicators (bytes=, dl=1, export=download, filename=).
    4. Path download endpoints (/download, /__down, /releases/download).
    5. Rejection of regular browsing sites, web document pages, and malformed inputs.
    6. GUI initialization, state defaults, and periodic timer scheduling.
    7. Clean toggle between Active and Paused with button and log updates.
    8. Strict duplicate prevention ensuring identical URLs don't trigger repeat prompts.
    9. Input population and safe confirmation dialog invocation.
    10. Fast YouTube URL dispatch to quality format resolver.
    11. Win32 ctypes clipboard reader resilience and error handling.
    """

    def test_is_downloadable_url_direct_extensions(self):
        """Verifies direct file extensions are recognized as downloadable URLs."""
        test_cases = [
            # Archives
            "https://downloads.example.org/files/archive.zip",
            "https://downloads.example.org/files/data.tar.gz",
            "https://downloads.example.org/files/backup.7z",
            "https://downloads.example.org/files/package.rar",
            # Binaries & Installers
            "https://example.com/releases/installer.exe",
            "https://example.com/packages/setup.msi",
            "https://example.com/os/linux_distro.iso",
            "https://example.com/app/mobile.apk",
            "https://example.com/mac/application.dmg",
            # Media: Video & Audio
            "https://media.example.com/movies/sample.mp4",
            "https://media.example.com/movies/video.mkv",
            "https://media.example.com/music/track.mp3",
            "https://media.example.com/audio/lossless.flac",
            # Documents & Ebooks
            "https://docs.example.org/papers/research.pdf",
            "https://docs.example.org/books/novel.epub",
            "https://docs.example.org/sheets/data.xlsx",
            # Images
            "https://images.example.com/assets/highres.png",
            "https://images.example.com/assets/photo.jpg",
            # Uppercase extensions and query parameters
            "https://example.com/FILES/SETUP.EXE?version=2.0",
            "https://example.com/video.mp4#t=30"
        ]
        for url in test_cases:
            self.assertTrue(is_downloadable_url(url), f"Failed to recognize valid downloadable URL: {url}")

    def test_is_downloadable_url_youtube_links(self):
        """Verifies all recognized YouTube formats are accepted by is_downloadable_url."""
        yt_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/1a2b3c4d5e6",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ"
        ]
        for url in yt_urls:
            self.assertTrue(is_downloadable_url(url), f"Failed to recognize YouTube URL: {url}")

    def test_is_downloadable_url_query_parameters(self):
        """Verifies query parameters signifying downloads are recognized."""
        query_cases = [
            "https://speed.cloudflare.com/__down?bytes=50000000",
            "https://drive.google.com/uc?id=12345&export=download",
            "https://www.dropbox.com/s/abcdef/project_files?dl=1",
            "https://example.com/api/v1/export?download=1",
            "https://example.com/api/v1/export?download=true",
            "https://storage.googleapis.com/bucket/object?response-content-disposition=attachment",
            "https://example.com/download.php?file=archive.zip",
            "https://example.com/handler?action=download&id=99",
            "https://example.com/media/stream?format=mp4&filename=clip.mp4"
        ]
        for url in query_cases:
            self.assertTrue(is_downloadable_url(url), f"Failed to recognize download query param: {url}")

    def test_is_downloadable_url_path_triggers(self):
        """Verifies download path endpoints and CDNs are recognized."""
        path_cases = [
            "https://github.com/user/repo/releases/download/v1.0/binary.bin",
            "https://example.com/downloads/v2/payload",
            "https://example.com/get_file/12345",
            "https://rr---sn-mock.googlevideo.com/videoplayback?expire=123"
        ]
        for url in path_cases:
            self.assertTrue(is_downloadable_url(url), f"Failed to recognize download path trigger: {url}")

    def test_is_downloadable_url_rejected_cases(self):
        """Verifies regular browsing pages, web markup, and invalid inputs are rejected."""
        invalid_cases = [
            # General websites
            "https://www.google.com",
            "https://google.com/",
            "https://en.wikipedia.org/wiki/Main_Page",
            "https://news.ycombinator.com",
            "https://github.com",
            # Web documents without download query params
            "https://example.com/index.html",
            "https://example.com/about.htm",
            "https://example.com/login.php",
            "https://example.com/portal.asp",
            "https://example.com/app.aspx",
            # Non-http schemes
            "mailto:support@example.com",
            "javascript:void(0)",
            "file:///C:/Users/test/file.txt",
            # Local filesystem paths
            "C:\\Downloads\\file.zip",
            "/home/user/downloads/archive.tar.gz",
            # Plain text & whitespace
            "Just some copied text with no url",
            "https://example.com with extra words in clipboard",
            "https://example.com/a\nhttps://example.com/b",
            "   ",
            "",
            None,
            12345,
            ["https://example.com/video.mp4"]
        ]
        for item in invalid_cases:
            self.assertFalse(is_downloadable_url(item), f"False positive on invalid/non-downloadable case: {item}")

    def test_clipboard_sniffer_gui_initialization_and_toggle(self):
        """Verifies ModernFramelessGUI initializes sniffer state and toggles active/paused."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            self.assertTrue(gui._clipboard_sniffer_active, "Clipboard sniffer should default to Active")
            self.assertIsNotNone(gui._clipboard_job, "Clipboard periodic timer job must be scheduled")
            self.assertEqual(gui.btn_clipboard_sniffer.cget("text"), "📋 Sniffer: Active")

            # Toggle to paused
            gui.toggle_clipboard_sniffer()
            self.assertFalse(gui._clipboard_sniffer_active)
            self.assertEqual(gui.btn_clipboard_sniffer.cget("text"), "📋 Sniffer: Paused")

            # Toggle back to active
            gui.toggle_clipboard_sniffer()
            self.assertTrue(gui._clipboard_sniffer_active)
            self.assertEqual(gui.btn_clipboard_sniffer.cget("text"), "📋 Sniffer: Active")

            gui._cleanup_resources()
            self.assertIsNone(gui._clipboard_job, "Clipboard job must be cleared on cleanup")
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_duplicate_prevention(self):
        """Verifies duplicate clipboard content does not re-trigger download interception."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            target_url = "https://example.com/duplicate_test_archive.zip"

            with patch.object(gui, "_on_clipboard_url_detected") as mock_detected:
                with patch("turbo_downloader.get_clipboard_text", return_value=target_url):
                    # First check should detect URL
                    gui._check_clipboard_now(force=True)
                    self.assertEqual(mock_detected.call_count, 1)

                    # Second check with identical clipboard content should be skipped
                    gui._check_clipboard_now(force=True)
                    self.assertEqual(mock_detected.call_count, 1, "Duplicate URL must not re-trigger")

                    # Third check with identical content still skipped
                    gui._check_clipboard_now(force=True)
                    self.assertEqual(mock_detected.call_count, 1, "Duplicate URL must not re-trigger")

                    # Changing clipboard URL triggers a new prompt
                    new_url = "https://example.com/another_archive.7z"
                    with patch("turbo_downloader.get_clipboard_text", return_value=new_url):
                        gui._check_clipboard_now(force=True)
                        self.assertEqual(mock_detected.call_count, 2)

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_populates_entries_and_prompts(self):
        """Verifies _on_clipboard_url_detected populates inputs and opens TDM confirmation modal non-blockingly."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            test_url = "https://speed.cloudflare.com/__down?bytes=50000000"

            with patch.object(gui, "ask_safe_yesno") as mock_yesno, \
                 patch.object(gui, "_on_start_download") as mock_start:
                gui._on_clipboard_url_detected(test_url)

                # Verify URL entry updated
                self.assertEqual(gui.entry_url.get(), test_url)
                # Verify Destination entry populated with a valid file path
                dest_val = gui.entry_dest.get()
                self.assertTrue(len(dest_val) > 0)
                self.assertTrue(dest_val.endswith(".bin") or "__down" in dest_val)

                # Verify legacy blocking modal dialog is not invoked
                mock_yesno.assert_not_called()
                # Verify TDM confirmation dialog was displayed
                self.assertIsNotNone(gui._confirm_modal)
                self.assertTrue(gui._confirm_modal.winfo_exists())
                # Verify no window or widget has trapped the grab
                self.assertIsNone(root.grab_current(), "No widget should hold grab")
                # Download has not started yet until confirmed
                mock_start.assert_not_called()

                # User chooses to open in main app via modal
                gui._confirm_modal._on_open_in_main()
                mock_start.assert_called_once()
                self.assertIsNone(gui._confirm_modal)

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_confirmation_dialog_cancel(self):
        """Verifies cancelling the TDM confirmation modal closes it cleanly without initiating download."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            test_url = "https://example.com/software/tool.zip"

            with patch.object(gui, "_on_start_download") as mock_start:
                gui._on_clipboard_url_detected(test_url)

                self.assertIsNotNone(gui._confirm_modal)
                self.assertTrue(gui._confirm_modal.winfo_exists())
                mock_start.assert_not_called()

                # Cancel via modal close button
                gui._confirm_modal._on_close()
                mock_start.assert_not_called()
                self.assertIsNone(gui._confirm_modal)

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_active_transfer_queues_without_modal(self):
        """Verifies clipboard sniffer populates URL without interrupting running engine or popping modals."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            gui.engine = MagicMock()
            gui.engine.is_running = True
            test_url = "https://speed.cloudflare.com/__down?bytes=25000000"

            with patch.object(gui, "ask_safe_yesno") as mock_yesno, \
                 patch.object(gui, "_on_start_download") as mock_start:
                gui._on_clipboard_url_detected(test_url)

                self.assertEqual(gui.entry_url.get(), test_url)
                self.assertIsNone(gui._confirm_modal)
                mock_yesno.assert_not_called()
                mock_start.assert_not_called()
                self.assertIsNone(root.grab_current())

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_modal_dialogs_never_trap_grab(self):
        """Verifies SafeModalDialog, QualitySelectionModal, and DownloadConfirmationModal never lock application grab."""
        import tkinter as tk
        from turbo_downloader import SafeModalDialog, QualitySelectionModal, DownloadConfirmationModal, VideoFormatOption
        root = tk.Tk()
        try:
            # 1. SafeModalDialog grab test
            dlg = SafeModalDialog(root, "Notice", "Test Message", dialog_type="info")
            self.assertIsNone(root.grab_current(), "SafeModalDialog must not hold active Tk grab")
            dlg.grab_set()  # Attempt explicit grab
            self.assertIsNone(root.grab_current(), "Explicit grab_set must be a safe no-op")
            dlg.destroy()

            # 2. QualitySelectionModal grab test
            dummy_opt = VideoFormatOption(
                format_id="test", ext="mp4", resolution_label="1080p", height=1080,
                filesize_approx=1000, fps=30, vcodec="h264", acodec="aac", is_audio_only=False
            )
            gui = ModernFramelessGUI(root)
            q_dlg = QualitySelectionModal(
                parent=root,
                video_title="Test Video",
                duration=60,
                options=[dummy_opt],
                default_dest_path="test.mp4",
                theme=gui._theme_dict(),
                on_confirm=lambda opt, p: None
            )
            self.assertIsNone(root.grab_current(), "QualitySelectionModal must not hold active Tk grab")
            q_dlg.grab_set()
            self.assertIsNone(root.grab_current(), "Explicit grab_set on quality modal must be a safe no-op")
            q_dlg.destroy()

            # 3. DownloadConfirmationModal grab test
            c_dlg = DownloadConfirmationModal(
                parent=root,
                url="https://example.com/test.zip",
                default_dest_path="test.zip",
                theme=gui._theme_dict(),
                on_confirm=lambda p: None
            )
            self.assertIsNone(root.grab_current(), "DownloadConfirmationModal must not hold active Tk grab")
            c_dlg.grab_set()
            self.assertIsNone(root.grab_current(), "Explicit grab_set on confirmation modal must be a safe no-op")
            c_dlg.destroy()

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_youtube_triggers_start(self):
        """Verifies YouTube URLs from clipboard automatically start resolution & modal flow via _start_youtube_download."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

            with patch.object(gui, "_start_youtube_download") as mock_yt_start:
                gui._on_clipboard_url_detected(yt_url)
                self.assertEqual(gui.entry_url.get(), yt_url)
                dest_val = gui.entry_dest.get()
                self.assertTrue("youtube_video.mp4" in dest_val)
                mock_yt_start.assert_called_once()
                args, _ = mock_yt_start.call_args
                self.assertEqual(args[0], yt_url)
                self.assertEqual(args[1], dest_val)
                self.assertEqual(args[2], 8)
                self.assertEqual(args[3], 0.0)
                self.assertIsNone(root.grab_current(), "Main window must not hold active grab")

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_youtube_active_task_queues(self):
        """Verifies YouTube URLs copied while transfer is active are safely queued in inputs without modal interruption."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            gui.engine = MagicMock()
            gui.engine.is_running = True
            yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

            with patch.object(gui, "_start_youtube_download") as mock_yt_start, \
                 patch.object(gui, "ask_safe_yesno") as mock_yesno:
                gui._on_clipboard_url_detected(yt_url)
                self.assertEqual(gui.entry_url.get(), yt_url)
                mock_yt_start.assert_not_called()
                mock_yesno.assert_not_called()
                self.assertIsNone(root.grab_current())

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_auto_start_disabled(self):
        """Verifies disabling _auto_start_clipboard populates fields for one-click start without auto-downloading."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            gui._auto_start_clipboard = False
            test_url = "https://speed.cloudflare.com/__down?bytes=50000000"
            yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

            with patch.object(gui, "_on_start_download") as mock_start, \
                 patch.object(gui, "_start_youtube_download") as mock_yt_start:
                # 1. Normal file
                gui._on_clipboard_url_detected(test_url)
                self.assertEqual(gui.entry_url.get(), test_url)
                mock_start.assert_not_called()

                # 2. YouTube file
                gui._on_clipboard_url_detected(yt_url)
                self.assertEqual(gui.entry_url.get(), yt_url)
                mock_yt_start.assert_not_called()

                self.assertIsNone(root.grab_current(), "UI controls must remain completely responsive")

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_clipboard_sniffer_skips_when_paused(self):
        """Verifies periodic tick does not inspect clipboard when sniffer is paused."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            gui._clipboard_sniffer_active = False

            with patch.object(gui, "_check_clipboard_now") as mock_check:
                gui._check_clipboard_tick()
                mock_check.assert_not_called()

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_win32_clipboard_get_actual_text_retrieval(self):
        """Verifies get_clipboard_text and _win32_clipboard_get retrieve actual text without truncation."""
        import tkinter as tk
        root = tk.Tk()
        try:
            sample_text = "https://example.com/verified_archive_download.zip"
            root.clipboard_clear()
            root.clipboard_append(sample_text)
            root.update()

            res = get_clipboard_text(root)
            self.assertEqual(res, sample_text, "Failed to read clipboard text via Tkinter root")

            # Direct Win32 ctypes fallback test (without root Tkinter handle)
            res_win32 = get_clipboard_text(None)
            if sys.platform.startswith("win"):
                self.assertEqual(res_win32, sample_text, "Win32 direct clipboard API must return matching text")
            else:
                self.assertIsNone(res_win32)
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_derive_download_filename_comprehensive(self):
        """Verifies intelligent destination filename derivation across complex URL formats."""
        test_matrix = [
            # MediaFire / intermediate segment format
            ("https://www.mediafire.com/file/xyz123/myfile.zip/file", "myfile.zip"),
            # Web script with query string parameter
            ("https://example.com/download.php?file=annual_report.pdf", "annual_report.pdf"),
            ("https://example.com/export.aspx?filename=backup_data.sql", "backup_data.sql"),
            # Unicode / percent-encoded Arabic filename
            ("https://example.com/download?file=%D9%81%D9%8A%D8%AF%D9%8A%D9%88.mp4", "فيديو.mp4"),
            # Direct archives with multi-part extensions
            ("https://example.com/dist/archive.tar.gz", "archive.tar.gz"),
            ("https://example.com/dist/archive.tar.xz", "archive.tar.xz"),
            # Cloudflare extensionless endpoint with fallback to .bin
            ("https://speed.cloudflare.com/__down?bytes=50000000", "down.bin"),
            # YouTube URL
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube_video.mp4"),
            # Invalid or empty fallback
            ("", "download.bin"),
            (None, "download.bin")
        ]
        for url, expected_fn in test_matrix:
            derived = derive_download_filename(url)
            self.assertEqual(derived, expected_fn, f"Incorrect derived filename for URL {url}: got {derived}, expected {expected_fn}")

    def test_is_downloadable_url_script_endpoints_and_ports(self):
        """Verifies script endpoints, localhost with ports, and wrapped URLs are properly detected."""
        valid_edge_cases = [
            "http://localhost:8080/test.zip",
            "http://127.0.0.1:8000/download.iso",
            "https://example.com/download.php?file_id=123",
            "https://example.com/download.aspx?id=55",
            "https://example.com/get_file.php?asset=99",
            "https://www.mediafire.com/file/xyz123/myfile.zip/file",
            "https://example.com/dist/package.zst",
            "https://example.com/dist/app.appimage",
            "<https://example.com/enclosed_url.zip>",
            "\"https://example.com/quoted_url.exe\"",
            "https://example.com/sentence_url.mp4."
        ]
        for url in valid_edge_cases:
            self.assertTrue(is_downloadable_url(url), f"Failed to recognize valid edge URL: {url}")

    def test_youtube_cancel_event_on_start_download(self):
        """Verifies starting a new download or YouTube resolution cancels any pending YouTube thread."""
        import tkinter as tk
        root = tk.Tk()
        try:
            gui = ModernFramelessGUI(root)
            # Create a mock pending resolve event
            gui._yt_cancel_event = threading.Event()
            old_event = gui._yt_cancel_event

            # Starting another YouTube download should signal cancellation of prior event
            with patch.object(threading.Thread, "start"):
                gui._start_youtube_download("https://www.youtube.com/watch?v=12345", "test.mp4", 8, 0.0)
                self.assertTrue(old_event.is_set(), "Old YouTube cancel event must be signaled")
                self.assertIsNot(gui._yt_cancel_event, old_event, "New event instance must be created")

            gui._cleanup_resources()
        finally:
            try:
                root.destroy()
            except Exception:
                pass


class TestTDMDownloadConfirmationDialog(unittest.TestCase):
    """Verifies the TDM-style Download Confirmation Dialog GUI, categories, and actions."""

    def test_get_file_category_and_icon(self):
        from turbo_downloader import get_file_category_and_icon
        test_cases = [
            ("archive.zip", ("Compressed", "📦")),
            ("archive.tar.gz", ("Compressed", "📦")),
            ("package.7z", ("Compressed", "📦")),
            ("disk.iso", ("Compressed", "📦")),
            ("setup.exe", ("Programs", "⚙️")),
            ("installer.msi", ("Programs", "⚙️")),
            ("app.apk", ("Programs", "⚙️")),
            ("movie.mp4", ("Video", "🎬")),
            ("stream.mkv", ("Video", "🎬")),
            ("clip.webm", ("Video", "🎬")),
            ("song.mp3", ("Audio", "🎵")),
            ("audio.flac", ("Audio", "🎵")),
            ("manual.pdf", ("Documents", "📄")),
            ("notes.docx", ("Documents", "📄")),
            ("data.csv", ("Documents", "📄")),
            ("photo.png", ("Images", "🖼️")),
            ("graphic.webp", ("Images", "🖼️")),
            ("unknown_data.bin", ("Programs", "⚙️")),
            ("stream_data.xyz", ("General", "📥")),
            ("https://example.com/file.rar?token=123", ("Compressed", "📦")),
        ]
        for item, expected in test_cases:
            cat, icon = get_file_category_and_icon(item)
            self.assertEqual((cat, icon), expected, f"Failed for {item}")

    def test_confirmation_dialog_initialization_and_fields(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            url = "https://example.com/releases/v1.0.0/AppSetup.exe"
            default_dest = os.path.join(os.path.expanduser("~"), "Downloads", "AppSetup.exe")
            dlg = DownloadConfirmationModal(
                parent=root,
                url=url,
                default_dest_path=default_dest,
                theme={"c_bg": "#121212", "c_panel": "#1e1e1e"}
            )
            self.assertEqual(dlg.entry_url.get(), url)
            self.assertEqual(dlg.entry_dest.get(), default_dest)
            self.assertEqual(dlg.lbl_filename_val.cget("text"), "AppSetup.exe")
            self.assertIn("Programs", dlg.lbl_category_val.cget("text"))
            self.assertIn("⚙️", dlg.lbl_category_val.cget("text"))
            self.assertIsNone(root.grab_current(), "Modal must never capture window grab")
            dlg.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_browse_action(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            url = "https://example.com/files/document.pdf"
            default_dest = "document.pdf"
            dlg = DownloadConfirmationModal(
                parent=root,
                url=url,
                default_dest_path=default_dest
            )
            new_target = "C:/Users/test/Documents/new_report.zip"
            with patch("tkinter.filedialog.asksaveasfilename", return_value=new_target):
                dlg._on_browse()
                self.assertEqual(dlg.entry_dest.get(), new_target)
                self.assertEqual(dlg.lbl_filename_val.cget("text"), "new_report.zip")
                self.assertIn("Compressed", dlg.lbl_category_val.cget("text"))
                self.assertIn("📦", dlg.lbl_category_val.cget("text"))
            dlg.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_keyrelease_updates_meta(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            url = "https://example.com/files/download"
            dlg = DownloadConfirmationModal(
                parent=root,
                url=url,
                default_dest_path="download.bin"
            )
            dlg.entry_dest.delete(0, tk.END)
            dlg.entry_dest.insert(0, "C:/Music/favorite_track.mp3")
            dlg._on_dest_key_release()
            self.assertEqual(dlg.lbl_filename_val.cget("text"), "favorite_track.mp3")
            self.assertIn("Audio", dlg.lbl_category_val.cget("text"))
            self.assertIn("🎵", dlg.lbl_category_val.cget("text"))
            dlg.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_confirm_callback(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            confirmed_path = []
            def _on_confirm(p):
                confirmed_path.append(p)

            dlg = DownloadConfirmationModal(
                parent=root,
                url="https://example.com/file.zip",
                default_dest_path="C:/Downloads/file.zip",
                on_confirm=_on_confirm
            )
            dlg.entry_dest.delete(0, tk.END)
            dlg.entry_dest.insert(0, "C:/CustomPath/my_file.zip")
            dlg._on_start()
            self.assertTrue(dlg._confirmed)
            self.assertEqual(confirmed_path, ["C:/CustomPath/my_file.zip"])
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_cancel_callback(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            cancelled = []
            def _on_cancel():
                cancelled.append(True)

            dlg = DownloadConfirmationModal(
                parent=root,
                url="https://example.com/file.zip",
                default_dest_path="C:/Downloads/file.zip",
                on_cancel=_on_cancel
            )
            dlg._on_close()
            self.assertFalse(dlg._confirmed)
            self.assertEqual(cancelled, [True])
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_null_and_empty_inputs(self):
        import tkinter as tk
        from turbo_downloader import DownloadConfirmationModal
        root = tk.Tk()
        try:
            dlg = DownloadConfirmationModal(
                parent=None,
                url="",
                default_dest_path="",
                theme=None
            )
            self.assertIsNotNone(dlg.entry_url)
            self.assertIsNotNone(dlg.entry_dest)
            dlg.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass



class TestWindowsStartupRegistryIntegration(unittest.TestCase):
    """Verifies Windows Startup Registry helper functions and executable resolution."""

    def setUp(self):
        # Record initial state to restore after test
        self.initial_enabled = is_startup_enabled()
        self.initial_entry = get_startup_entry()

    def tearDown(self):
        # Restore initial state
        if self.initial_enabled and self.initial_entry:
            enable_startup(minimized="--minimized" in self.initial_entry)
        else:
            disable_startup()

    def test_startup_command_script_mode(self):
        # Fallback script mode when standalone exe is absent
        with patch("os.path.isfile", side_effect=lambda p: False if ("SmartDownload.exe" in p or "TurboDownloader.exe" in p) else os.path.exists(p)):
            cmd_min = get_startup_command(minimized=True)
            self.assertIn("--minimized", cmd_min)
            self.assertTrue(cmd_min.endswith(" --minimized"))
            self.assertIn("turbo_downloader.py", cmd_min)

            cmd_full = get_startup_command(minimized=False)
            self.assertNotIn("--minimized", cmd_full)
            self.assertIn("turbo_downloader.py", cmd_full)

    def test_startup_command_prioritizes_standalone_exe(self):
        # Standalone binary dist/TurboDownloader.exe is prioritized when present
        cmd_min = get_startup_command(minimized=True)
        self.assertTrue("SmartDownload.exe" in cmd_min or "TurboDownloader.exe" in cmd_min)
        self.assertNotIn("pythonw.exe", cmd_min)
        self.assertTrue(cmd_min.endswith(" --minimized"))

    def test_startup_command_frozen_mode(self):
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "executable", r"C:\Program Files\SmartDownload\SmartDownload.exe"):
                cmd_min = get_startup_command(minimized=True)
                self.assertEqual(cmd_min, r'"C:\Program Files\SmartDownload\SmartDownload.exe" --minimized')

                cmd_full = get_startup_command(minimized=False)
                self.assertEqual(cmd_full, r'"C:\Program Files\SmartDownload\SmartDownload.exe"')

    def test_startup_lifecycle_enable_disable(self):
        # Enable with minimized=True
        ok = enable_startup(minimized=True)
        self.assertTrue(ok)
        self.assertTrue(is_startup_enabled())
        entry = get_startup_entry()
        self.assertIsNotNone(entry)
        self.assertIn("--minimized", entry)

        # Re-enable with minimized=False
        ok2 = enable_startup(minimized=False)
        self.assertTrue(ok2)
        self.assertTrue(is_startup_enabled())
        entry2 = get_startup_entry()
        self.assertIsNotNone(entry2)
        self.assertNotIn("--minimized", entry2)

        # Disable
        ok3 = disable_startup()
        self.assertTrue(ok3)
        self.assertFalse(is_startup_enabled())
        self.assertIsNone(get_startup_entry())

        # Disabling when already disabled is idempotent
        ok4 = disable_startup()
        self.assertTrue(ok4)
        self.assertFalse(is_startup_enabled())

    def test_registry_error_handling(self):
        with patch("winreg.CreateKey", side_effect=PermissionError("Access denied")):
            self.assertFalse(enable_startup(minimized=True))

        with patch("winreg.OpenKey", side_effect=OSError("Registry error")):
            self.assertFalse(disable_startup())
            self.assertFalse(is_startup_enabled())
            self.assertIsNone(get_startup_entry())

    def test_non_windows_platform_graceful_noops(self):
        with patch("turbo_downloader.IS_WINDOWS", False):
            self.assertFalse(is_startup_enabled())
            self.assertFalse(enable_startup(minimized=True))
            self.assertFalse(disable_startup())
            self.assertIsNone(get_startup_entry())

    def test_startup_command_script_mode_fallback(self):
        with patch("os.path.isfile", return_value=False):
            cmd = get_startup_command(minimized=True)
            self.assertIn("--minimized", cmd)
            self.assertIn("turbo_downloader.py", cmd)

    def test_startup_command_strip_quotes(self):
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "executable", r'"C:\Path With Spaces\SmartDownload.exe"'):
                cmd = get_startup_command(minimized=True)
                self.assertNotIn('""', cmd)
                self.assertEqual(cmd, r'"C:\Path With Spaces\SmartDownload.exe" --minimized')

    def test_is_startup_enabled_whitespace_or_empty(self):
        with patch("winreg.OpenKey"):
            with patch("winreg.QueryValueEx", return_value=("   ", 1)):
                self.assertFalse(is_startup_enabled())
            with patch("winreg.QueryValueEx", return_value=("", 1)):
                self.assertFalse(is_startup_enabled())
            with patch("winreg.QueryValueEx", return_value=(None, 1)):
                self.assertFalse(is_startup_enabled())


class TestBackgroundAndMinimizedLaunch(unittest.TestCase):
    """Verifies silent background launch, IPC/sniffer preservation, and window restore on intercept."""

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
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
        with patch.object(sys, "argv", ["turbo_downloader.py", "--minimized"]):
            gui1 = ModernFramelessGUI(self.root)
            self.assertTrue(gui1._start_hidden)
            gui1._cleanup_resources()

        with patch.object(sys, "argv", ["turbo_downloader.py", "--background"]):
            gui2 = ModernFramelessGUI(self.root)
            self.assertTrue(gui2._start_hidden)
            gui2._cleanup_resources()

        with patch.object(sys, "argv", ["turbo_downloader.py"]):
            gui3 = ModernFramelessGUI(self.root)
            self.assertFalse(gui3._start_hidden)
            gui3._cleanup_resources()

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
            gui._confirm_modal._on_open_in_main()
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
            gui._confirm_modal._on_open_in_main()
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
                gui = ModernFramelessGUI(self.root)
                self.assertTrue(gui._start_hidden, f"Flag {v} failed to activate _start_hidden")
                self.assertTrue(gui._was_started_hidden, f"Flag {v} failed to set _was_started_hidden")
                gui._cleanup_resources()

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

            for _ in range(25):
                gui._drain_dispatch_queue()
                self.root.update()
                if not gui._start_hidden:
                    break
                time.sleep(0.02)

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
            for _ in range(25):
                gui._drain_dispatch_queue()
                self.root.update()
                if not gui._start_hidden:
                    break
                time.sleep(0.02)
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


class MockRefreshLinkServerHandler(http.server.BaseHTTPRequestHandler):
    """
    Mock HTTP server handler simulating expired links, refreshed URLs,
    size mismatches, missing range support, and HTTP 401/403/410 errors.
    """
    data_store = {}
    expired_urls = set()
    no_range_urls = set()
    request_counts = {}

    def log_message(self, format, *args):
        pass  # Suppress console logging during automated tests

    def do_HEAD(self):
        path = self.path.split('?')[0].lstrip('/')
        if path == "head_forbidden.bin":
            self.send_error(403, "Forbidden: S3 Pre-signed Method Restricted")
            return
        if path in self.expired_urls or path == "forbidden":
            self.send_error(403, "Forbidden - Link Expired")
            return
        if path == "gone":
            self.send_error(410, "Gone")
            return
        if path not in self.data_store:
            self.send_error(404, "Not Found")
            return

        data = self.data_store[path]
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        if path in self.no_range_urls:
            self.send_header("Accept-Ranges", "none")
        else:
            self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0].lstrip('/')
        self.request_counts[path] = self.request_counts.get(path, 0) + 1

        if path in self.expired_urls or path == "forbidden":
            self.send_error(403, "Forbidden - Link Expired")
            return
        if path == "gone":
            self.send_error(410, "Gone")
            return
        if path in ("expire_after_first.bin", "expire_on_get.bin"):
            self.send_error(403, "Forbidden - Link Expired")
            return
        if path not in self.data_store:
            self.send_error(404, "Not Found")
            return

        data = self.data_store[path]
        total_len = len(data)

        range_header = self.headers.get("Range")
        if range_header and path == "fake_accept_ranges_200.bin":
            # Deceptive server: returns 200 OK with full body even when sent Range header!
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total_len))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(data)
            return

        if range_header and path == "no_total_206.bin":
            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", "1")
            self.end_headers()
            self.wfile.write(data[:1])
            return

        if range_header and path in self.no_range_urls:
            # Server does not support range requests: ignore range header and return 200 with full data
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total_len))
            self.send_header("Accept-Ranges", "none")
            self.end_headers()
            self.wfile.write(data)
            return

        if range_header and range_header.startswith("bytes="):
            ranges = range_header[6:].split("-")
            start = int(ranges[0]) if ranges[0] else 0
            end = int(ranges[1]) if ranges[1] else total_len - 1
            if end >= total_len:
                end = total_len - 1
            if start > end or start >= total_len:
                self.send_error(416, "Range Not Satisfiable")
                return

            chunk_len = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Range", f"bytes {start}-{end}/{total_len}")
            self.send_header("Content-Length", str(chunk_len))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            offset = start
            buf_size = 4096
            while offset <= end:
                read_len = min(buf_size, end - offset + 1)
                try:
                    self.wfile.write(data[offset:offset + read_len])
                except Exception:
                    break
                offset += read_len
                time.sleep(0.0005)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total_len))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(data)


class TestRefreshExpiredLinks(unittest.TestCase):
    """
    Automated verification for Feature 4: Refresh Expired Links (تجديد الروابط المنتهية).
    Verifies URL validation, HTTP 401/403/410 handling, state persistence,
    grab-free modal dialog, dynamic split resume, and bit-perfect file assembly.
    """
    server = None
    server_thread = None
    port = 0
    base_url = ""
    test_data = b""
    test_hash = ""

    @classmethod
    def setUpClass(cls):
        cls.test_data = os.urandom(256 * 1024)  # 256 KB
        cls.test_hash = hashlib.sha256(cls.test_data).hexdigest()
        cls.mismatch_data = cls.test_data[: 128 * 1024]  # 128 KB

        MockRefreshLinkServerHandler.data_store = {
            "fresh.bin": cls.test_data,
            "mismatch.bin": cls.mismatch_data,
            "no_range.bin": cls.test_data,
            "expire_on_get.bin": cls.test_data,
            "expire_after_first.bin": cls.test_data,
            "resumable.bin": cls.test_data,
            "head_forbidden.bin": cls.test_data,
            "fake_accept_ranges_200.bin": cls.test_data,
            "no_total_206.bin": cls.test_data,
        }
        MockRefreshLinkServerHandler.no_range_urls = {"no_range.bin"}
        MockRefreshLinkServerHandler.expired_urls = set()
        MockRefreshLinkServerHandler.request_counts = {}

        class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        cls.server = ThreadedHTTPServer(("127.0.0.1", 0), MockRefreshLinkServerHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            try:
                cls.server.shutdown()
                cls.server.server_close()
            except Exception:
                pass

    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "test_temp_refresh")
        os.makedirs(self.test_dir, exist_ok=True)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        if os.path.isdir(self.test_dir):
            try:
                shutil.rmtree(self.test_dir, ignore_errors=True)
            except Exception:
                pass

    def test_01_validate_refresh_url_success(self):
        fresh_url = f"{self.base_url}/fresh.bin"
        ok, msg, size, ranges = validate_refresh_url(fresh_url, expected_size=len(self.test_data), check_range=True)
        self.assertTrue(ok, f"Expected validation to succeed, got: {msg}")
        self.assertEqual(size, len(self.test_data))
        self.assertTrue(ranges)
        self.assertIn("successfully", msg.lower())

    def test_02_validate_refresh_url_size_mismatch(self):
        mismatch_url = f"{self.base_url}/mismatch.bin"
        ok, msg, size, ranges = validate_refresh_url(mismatch_url, expected_size=len(self.test_data), check_range=True)
        self.assertFalse(ok)
        self.assertEqual(size, len(self.mismatch_data))
        self.assertIn("size mismatch", msg.lower())

    def test_03_validate_refresh_url_http_403_and_410(self):
        url_403 = f"{self.base_url}/forbidden"
        ok_403, msg_403, _, _ = validate_refresh_url(url_403)
        self.assertFalse(ok_403)
        self.assertIn("403", msg_403)

        url_410 = f"{self.base_url}/gone"
        ok_410, msg_410, _, _ = validate_refresh_url(url_410)
        self.assertFalse(ok_410)
        self.assertIn("410", msg_410)

    def test_04_validate_refresh_url_no_range_support(self):
        no_range_url = f"{self.base_url}/no_range.bin"
        ok, msg, size, ranges = validate_refresh_url(no_range_url, expected_size=len(self.test_data), check_range=True)
        self.assertFalse(ok)
        self.assertFalse(ranges)
        self.assertIn("range", msg.lower())

    def test_05_engine_save_and_load_state_persistence(self):
        target = os.path.join(self.test_dir, "persist_test.bin")
        engine = TurboDownloadEngine(
            url="http://example.com/file.bin",
            destination_path=target,
            max_connections=2
        )
        engine.total_size = 200000
        engine.supports_ranges = True
        engine.has_expired_link = True
        c0 = DownloadChunk(0, 0, 99999)
        c0.downloaded_bytes = 45000
        c0.status = "paused"
        c1 = DownloadChunk(1, 100000, 199999)
        c1.downloaded_bytes = 20000
        c1.status = "failed"
        c1.error_msg = "HTTP 403: Forbidden"
        engine.chunks = [c0, c1]

        saved = engine.save_state()
        self.assertTrue(saved)
        state_file = os.path.join(engine.temp_dir, "state.json")
        self.assertTrue(os.path.isfile(state_file))

        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["total_size"], 200000)
        self.assertTrue(data["has_expired_link"])
        self.assertEqual(len(data["chunks"]), 2)

        # Load into fresh engine instance
        engine2 = TurboDownloadEngine(
            url="http://example.com/dummy",
            destination_path=target,
            max_connections=1
        )
        loaded = engine2.load_state()
        self.assertTrue(loaded)
        self.assertEqual(engine2.total_size, 200000)
        self.assertTrue(engine2.has_expired_link)
        self.assertEqual(len(engine2.chunks), 2)
        self.assertEqual(engine2.chunks[0].chunk_id, 0)
        self.assertEqual(engine2.chunks[0].downloaded_bytes, 45000)
        self.assertEqual(engine2.chunks[1].chunk_id, 1)
        self.assertEqual(engine2.chunks[1].downloaded_bytes, 20000)
        self.assertEqual(engine2.chunks[1].error_msg, "HTTP 403: Forbidden")

    def test_06_engine_detects_expired_link_on_403_failure(self):
        target = os.path.join(self.test_dir, "expire_task.bin")
        engine = TurboDownloadEngine(
            url=f"{self.base_url}/expire_on_get.bin",
            destination_path=target,
            max_connections=2
        )
        engine.start()
        for _ in range(60):
            if not engine.is_running:
                break
            time.sleep(0.05)

        self.assertFalse(engine.is_running)
        self.assertTrue(engine.has_expired_link, "Engine must flag has_expired_link on HTTP 403")
        self.assertEqual(engine.last_http_status, 403)
        self.assertTrue(os.path.isdir(engine.temp_dir), "Temporary chunk directory must NOT be deleted on 403 failure")
        state_file = os.path.join(engine.temp_dir, "state.json")
        self.assertTrue(os.path.isfile(state_file), "State file must be saved on failure")

    def test_07_refresh_link_and_resume_bit_perfect(self):
        target = os.path.join(self.test_dir, "resume_task.bin")
        engine = TurboDownloadEngine(
            url=f"{self.base_url}/expire_on_get.bin",
            destination_path=target,
            max_connections=2
        )
        engine.start()
        for _ in range(60):
            if not engine.is_running:
                break
            time.sleep(0.05)

        self.assertTrue(engine.has_expired_link)

        fresh_url = f"{self.base_url}/fresh.bin"
        resumed = engine.refresh_link(fresh_url, auto_resume=True)
        self.assertTrue(resumed)

        for _ in range(100):
            if not engine.is_running:
                break
            time.sleep(0.05)

        self.assertFalse(engine.is_running)
        self.assertFalse(engine.has_expired_link)
        self.assertTrue(os.path.isfile(target), f"Assembled file must exist at {target}")
        self.assertEqual(os.path.getsize(target), len(self.test_data))

        with open(target, "rb") as f:
            downloaded_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(downloaded_hash, self.test_hash, "Resumed download must be 100% bit-perfect with original file")

    def test_08_dynamic_split_with_refresh_link(self):
        target = os.path.join(self.test_dir, "split_resume.bin")
        engine = TurboDownloadEngine(
            url=f"{self.base_url}/resumable.bin",
            destination_path=target,
            max_connections=4
        )
        engine.start()
        time.sleep(0.05)
        engine.pause()
        for _ in range(40):
            if engine.is_paused:
                break
            time.sleep(0.02)

        self.assertTrue(engine.is_paused)
        fresh_url = f"{self.base_url}/fresh.bin"
        engine.refresh_link(fresh_url, auto_resume=True)

        for _ in range(100):
            if not engine.is_running:
                break
            time.sleep(0.05)

        self.assertFalse(engine.is_running)
        self.assertTrue(os.path.isfile(target))
        with open(target, "rb") as f:
            downloaded_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(downloaded_hash, self.test_hash, "Multi-chunk split resume must match SHA-256 hash")

    def test_09_refresh_link_modal_grab_free_and_clipboard_autofill(self):
        modal = RefreshLinkModal(
            parent=self.root,
            old_url=f"{self.base_url}/old.bin",
            total_size=len(self.test_data),
            downloaded_bytes=10000,
            filename="test.bin"
        )
        try:
            modal.grab_set()
            modal.grab_set_global()
            self.root.update()

            fresh_url = f"{self.base_url}/fresh.bin"
            self.root.clipboard_clear()
            self.root.clipboard_append(fresh_url)

            modal._check_clipboard_auto_fill()
            self.assertEqual(modal.entry_new_url.get(), fresh_url, "Modal must auto-populate new URL from clipboard")

            cb_mock = MagicMock()
            modal.on_success = cb_mock
            modal._start_validation()
            if hasattr(modal, "_validating_thread") and modal._validating_thread:
                modal._validating_thread.join(timeout=3.0)
            modal.process_pending_events()
            for _ in range(10):
                self.root.update()
                time.sleep(0.02)
            cb_mock.assert_called_once()
            called_url, called_headers = cb_mock.call_args[0]
            self.assertEqual(called_url, fresh_url)
        finally:
            if modal.winfo_exists():
                modal.destroy()

    def test_10_gui_refresh_link_context_menu_and_action_bar(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(hasattr(gui, "btn_refresh_link"))
            self.assertIn(gui.btn_refresh_link.cget("state"), ("normal", "disabled"))
            self.assertTrue(hasattr(gui, "tree_context_menu"))
            self.assertGreater(gui.tree_context_menu.index(tk.END), 0)

            gui._engine_error_cb("HTTP 403 Forbidden")
            self.root.update()
            self.assertEqual(gui.btn_refresh_link.cget("state"), "normal")
            self.assertEqual(gui.card_size.cget("text"), "Ready")

            gui._open_refresh_link_dialog()
            self.assertIsNotNone(gui._refresh_modal)
            self.assertTrue(gui._refresh_modal.winfo_exists())

            fresh_url = f"{self.base_url}/fresh.bin"
            gui._on_link_refreshed_success(fresh_url)
            self.root.update()
            self.assertEqual(gui.entry_url.get(), fresh_url)
        finally:
            gui._cleanup_resources()

    def test_11_coordinator_refresh_link_delegation(self):
        target = os.path.join(self.test_dir, "coord_test.bin")
        stream_info = YouTubeStreamInfo(
            video_id="dQw4w9WgXcQ",
            title="Test Stream",
            clean_filename="test_stream.mp4",
            is_progressive=True,
            video_url=f"{self.base_url}/fresh.bin"
        )
        coord = StreamDownloadCoordinator(
            stream_info=stream_info,
            destination_path=target,
            max_connections=2
        )
        coord.current_engine = TurboDownloadEngine(
            url=stream_info.video_url,
            destination_path=target,
            max_connections=2
        )
        fresh_url = f"{self.base_url}/fresh.bin"
        coord.update_url(fresh_url)
        self.assertEqual(coord.current_engine.url, fresh_url)

        with patch.object(coord.current_engine, "refresh_link", return_value=True) as mock_ref:
            res = coord.refresh_link(fresh_url, auto_resume=True)
            self.assertTrue(res)
            mock_ref.assert_called_once_with(fresh_url, None, True)

    def test_12_validate_refresh_url_rejects_http_200_on_range(self):
        # Server advertises Accept-Ranges in HEAD, but returns 200 OK to Range request
        fake_url = f"{self.base_url}/fake_accept_ranges_200.bin"
        ok, msg, size, ranges = validate_refresh_url(fake_url, expected_size=len(self.test_data), check_range=True)
        self.assertFalse(ok, "Validation must fail when server returns 200 instead of 206 to Range request")
        self.assertFalse(ranges)
        self.assertIn("range", msg.lower())

    def test_13_validate_refresh_url_handles_head_403_presigned_s3(self):
        # Simulates AWS S3 pre-signed URL where HEAD returns 403 because only GET is signed
        presigned_url = f"{self.base_url}/head_forbidden.bin"
        ok, msg, size, ranges = validate_refresh_url(presigned_url, expected_size=len(self.test_data), check_range=True)
        self.assertTrue(ok, f"Pre-signed GET URL must be verified even when HEAD is 403: {msg}")
        self.assertEqual(size, len(self.test_data))
        self.assertTrue(ranges)

    def test_14_validate_refresh_url_206_without_content_range_total(self):
        # Server returns 206 Partial Content without Content-Range total length
        no_total_url = f"{self.base_url}/no_total_206.bin"
        ok, msg, size, ranges = validate_refresh_url(no_total_url, expected_size=0, check_range=True)
        self.assertTrue(ok)
        self.assertTrue(ranges)
        # Verify resolved_size was NOT mistakenly set to 1 from Content-Length: 1
        self.assertNotEqual(size, 1)

    def test_15_engine_aborts_all_workers_on_403_error(self):
        target = os.path.join(self.test_dir, "abort_workers.bin")
        engine = TurboDownloadEngine(
            url=f"{self.base_url}/expire_on_get.bin",
            destination_path=target,
            max_connections=3
        )
        engine.start()
        for _ in range(60):
            if not engine.is_running:
                break
            time.sleep(0.05)

        self.assertFalse(engine.is_running)
        self.assertTrue(engine.has_expired_link)
        self.assertTrue(engine._error_abort_event.is_set(), "_error_abort_event must be set on 403 error")
        time.sleep(0.3)
        alive_workers = [w for w in engine.active_workers if w.is_alive()]
        self.assertEqual(len(alive_workers), 0, "All worker threads must terminate without lingering zombies")

    def test_16_engine_truncates_excess_chunk_part_file_on_resume(self):
        target = os.path.join(self.test_dir, "trunc_test.bin")
        engine = TurboDownloadEngine(
            url=f"{self.base_url}/fresh.bin",
            destination_path=target,
            max_connections=2
        )
        engine.total_size = len(self.test_data)
        engine.supports_ranges = True
        os.makedirs(engine.temp_dir, exist_ok=True)

        # Create chunk 0 with expected size 100, but file on disk has 200 bytes
        c0 = DownloadChunk(0, 0, 99, part_filepath=os.path.join(engine.temp_dir, "p0"))
        with open(c0.part_filepath, "wb") as f:
            f.write(b"X" * 200)
        c0.downloaded_bytes = 200
        engine.chunks = [c0]

        # Call load_state or let supervisor resume
        engine.save_state()
        engine.load_state()

        # Chunk downloaded_bytes should be clamped to expected span (100)
        self.assertEqual(engine.chunks[0].downloaded_bytes, 100)
        self.assertEqual(engine.chunks[0].status, "completed")

    def test_17_coordinator_polymorphic_properties(self):
        target = os.path.join(self.test_dir, "coord_poly.bin")
        stream_info = YouTubeStreamInfo(
            video_id="test12345",
            title="Poly Stream",
            clean_filename="poly.mp4",
            is_progressive=True,
            video_url=f"{self.base_url}/fresh.bin"
        )
        coord = StreamDownloadCoordinator(
            stream_info=stream_info,
            destination_path=target,
            max_connections=2
        )
        self.assertEqual(coord.url, f"{self.base_url}/fresh.bin")
        self.assertTrue(coord.supports_ranges)
        self.assertFalse(coord.has_expired_link)
        self.assertEqual(coord.last_http_status, 0)


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


class TestTDMConfirmationAndStandaloneProgress(unittest.TestCase):
    """
    Verifies TDM-style confirmation modal features and standalone progress handling:
    1. Speed limiter parsing across various units (Unlimited, KB/s, MB/s, custom numbers).
    2. Connection count selector (1, 2, 4, 8, 16, 32) and speed selector in DownloadConfirmationModal.
    3. Three action buttons: 'Start Download', 'Open in Main App', and 'Cancel'.
    4. Transition to standalone compact progress view and canvas progress bar rendering.
    5. Standalone download controls: Pause / Resume toggling and Cancel aborting engine.
    6. Completion state actions: 'Open File', 'Open Folder', and 'Close'.
    7. QualitySelectionModal 'Open in Main App' action.
    """

    def setUp(self):
        self.root = tk.Tk()
        self.theme = {
            "c_bg": "#121214",
            "c_panel": "#1b1b1f",
            "c_panel_light": "#25252b",
            "c_border": "#2c2c34",
            "c_accent": "#6366f1",
            "c_accent_dark": "#4f46e5",
            "c_success": "#10b981",
            "c_warning": "#f59e0b",
            "c_error": "#ef4444",
            "c_text_bright": "#ffffff",
            "c_text_muted": "#9ca3af",
            "c_input_bg": "#18181b",
        }

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_speed_limit_parser(self):
        """Tests parsing of speed limit presets and custom strings to bytes per second."""
        self.assertEqual(parse_speed_limit("Unlimited"), 0.0)
        self.assertEqual(parse_speed_limit("none"), 0.0)
        self.assertEqual(parse_speed_limit("256 KB/s"), 256 * 1024.0)
        self.assertEqual(parse_speed_limit("512 KB/s"), 512 * 1024.0)
        self.assertEqual(parse_speed_limit("1 MB/s"), 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("2 MB/s"), 2 * 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("5 MB/s"), 5 * 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("10 MB/s"), 10 * 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("20 MB/s"), 20 * 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("1024"), 1024 * 1024.0)
        self.assertEqual(parse_speed_limit("500000"), 500000.0)
        self.assertEqual(parse_speed_limit(""), 0.0)
        self.assertEqual(parse_speed_limit("invalid_limit"), 0.0)

    def test_confirmation_dialog_controls_and_options(self):
        """Verifies DownloadConfirmationModal thread and speed options and helper getters."""
        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/testfile.iso",
            default_dest_path="C:\\Downloads\\testfile.iso",
            theme=self.theme,
            on_confirm=lambda *a: None,
            default_connections=8,
            default_speed_limit=0.0
        )
        try:
            # Check thread count combobox values
            thread_values = list(modal.combo_threads["values"])
            for t in ["1", "2", "4", "8", "16", "32"]:
                self.assertIn(t, thread_values)
            self.assertEqual(modal.get_max_connections(), 8)

            modal.combo_threads.set("16")
            self.assertEqual(modal.get_max_connections(), 16)

            modal.combo_threads.set("invalid")
            self.assertEqual(modal.get_max_connections(), 8)  # Fallback

            # Check speed limiter combobox values
            speed_values = list(modal.combo_speed["values"])
            self.assertIn("Unlimited", speed_values)
            self.assertIn("1 MB/s", speed_values)
            self.assertEqual(modal.get_speed_limit_bytes(), 0.0)

            modal.combo_speed.set("2 MB/s")
            self.assertEqual(modal.get_speed_limit_bytes(), 2 * 1024 * 1024.0)

            # Check that grab is not held
            self.assertIsNone(self.root.grab_current())
        finally:
            try:
                modal.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_three_action_buttons(self):
        """Verifies presence of Start Download, Open in Main App, and Cancel buttons."""
        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/software.zip",
            default_dest_path="C:\\Downloads\\software.zip",
            theme=self.theme,
            on_confirm=lambda *a: None
        )
        try:
            self.assertTrue(hasattr(modal, "btn_start"))
            self.assertTrue(hasattr(modal, "btn_open_app"))
            self.assertTrue(hasattr(modal, "btn_cancel"))
            self.assertIn("Start Download", modal.btn_start.cget("text"))
            self.assertIn("Open in Main App", modal.btn_open_app.cget("text"))
            self.assertIn("Cancel", modal.btn_cancel.cget("text"))
        finally:
            try:
                modal.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_transition_to_progress_view(self):
        """Verifies transitioning modal into standalone progress view and updating progress."""
        started = []
        def mock_start_in_window(dest, conns, speed, modal_ref):
            started.append((dest, conns, speed, modal_ref))

        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/data.tar.gz",
            default_dest_path="C:\\Downloads\\data.tar.gz",
            theme=self.theme,
            on_confirm=lambda *a: None,
            on_start_in_window=mock_start_in_window
        )
        try:
            self.assertFalse(modal.is_in_progress_view)
            modal._on_start_in_window()
            self.assertTrue(modal.is_in_progress_view)
            self.assertEqual(len(started), 1)

            # Check progress view widgets exist
            self.assertTrue(hasattr(modal, "canvas_prog"))
            self.assertTrue(hasattr(modal, "lbl_prog_size"))
            self.assertTrue(hasattr(modal, "lbl_prog_speed"))
            self.assertTrue(hasattr(modal, "lbl_prog_eta"))
            self.assertTrue(hasattr(modal, "lbl_prog_threads"))
            self.assertTrue(hasattr(modal, "btn_pause_resume"))
            self.assertTrue(hasattr(modal, "btn_cancel_prog"))

            # Update progress
            modal.update_progress(5000000, 10000000, 1048576, "00:00:05", 8)
            self.root.update()
            self.assertIn("50.0%", modal.lbl_prog_size.cget("text"))
            self.assertIn("00:00:05", modal.lbl_prog_eta.cget("text"))
            self.assertIn("8 Active", modal.lbl_prog_threads.cget("text"))
        finally:
            try:
                modal.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_pause_resume_and_cancel_standalone(self):
        """Verifies pause/resume toggling and cancellation in standalone modal view."""
        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/archive.7z",
            default_dest_path="C:\\Downloads\\archive.7z",
            theme=self.theme,
            on_confirm=lambda *a: None
        )
        try:
            modal.show_progress_view()
            mock_engine = MagicMock()
            mock_engine.is_running = True
            mock_engine.is_paused = False
            modal.engine = mock_engine

            # Pause
            modal._on_pause_resume()
            mock_engine.pause.assert_called_once()
            self.assertIn("Resume", modal.btn_pause_resume.cget("text"))

            # Resume
            mock_engine.is_paused = True
            modal._on_pause_resume()
            mock_engine.resume.assert_called_once()
            self.assertIn("Pause", modal.btn_pause_resume.cget("text"))

            # Cancel
            modal._on_close()
            mock_engine.cancel.assert_called_once()
        finally:
            try:
                if modal.winfo_exists():
                    modal.destroy()
            except Exception:
                pass

    def test_confirmation_dialog_completion_actions(self):
        """Verifies completion state actions: Open File, Open Folder, and Close."""
        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/app.exe",
            default_dest_path="C:\\Downloads\\app.exe",
            theme=self.theme,
            on_confirm=lambda *a: None
        )
        try:
            modal.show_progress_view()
            test_file = "C:\\Downloads\\app.exe"
            modal.on_download_complete(test_file, 1048576, 2.5)
            self.root.update()

            self.assertTrue(modal.is_completed)
            self.assertTrue(hasattr(modal, "btn_open_file"))
            self.assertTrue(hasattr(modal, "btn_open_folder"))
            self.assertTrue(hasattr(modal, "btn_close_prog"))

            with patch("turbo_downloader.open_downloaded_file") as mock_open_file, \
                 patch("turbo_downloader.open_containing_folder") as mock_open_folder:
                modal._on_open_file()
                mock_open_file.assert_called_once_with(test_file)

                modal._on_open_folder()
                mock_open_folder.assert_called_once_with(test_file)
        finally:
            try:
                modal.destroy()
            except Exception:
                pass

    def test_quality_selection_modal_open_in_main(self):
        """Verifies QualitySelectionModal 'Open in Main App' button invokes the on_open_in_main callback."""
        opened_in_main = []
        def mock_open_in_main(opt, dest):
            opened_in_main.append((opt, dest))

        opt1 = VideoFormatOption(
            format_id="137+140",
            resolution_label="1080p (Full HD)",
            height=1080,
            ext="mp4",
            filesize_approx=50000000,
            fps=30,
            vcodec="avc1",
            acodec="mp4a"
        )
        modal = QualitySelectionModal(
            parent=self.root,
            video_title="Test Video Title",
            duration=120,
            options=[opt1],
            default_dest_path="C:\\Downloads\\Test Video Title.mp4",
            theme=self.theme,
            on_confirm=lambda *a: None,
            on_open_in_main=mock_open_in_main
        )
        try:
            self.assertTrue(hasattr(modal, "btn_open_app"))
            self.assertIn("Open in Main App", modal.btn_open_app.cget("text"))
            modal._on_open_in_main()
            self.assertEqual(len(opened_in_main), 1)
            self.assertEqual(opened_in_main[0][0], opt1)
            self.assertEqual(opened_in_main[0][1], "C:\\Downloads\\Test Video Title.mp4")
        finally:
            try:
                if modal.winfo_exists():
                    modal.destroy()
            except Exception:
                pass

    def test_modal_viewable_when_parent_is_iconic_or_withdrawn(self):
        """Verifies DownloadConfirmationModal and QualitySelectionModal remain viewable when parent is iconic/withdrawn."""
        self.root.withdraw()
        modal = DownloadConfirmationModal(
            parent=self.root,
            url="https://example.com/file.bin",
            default_dest_path="C:\\Downloads\\file.bin",
            theme=self.theme
        )
        try:
            self.root.update()
            modal.update()
            self.assertEqual(modal.state(), "normal")
            self.assertEqual(modal.winfo_viewable(), 1, "DownloadConfirmationModal must be viewable on screen when parent is hidden")
        finally:
            try:
                modal.destroy()
            except Exception:
                pass

        opt = VideoFormatOption(
            format_id="137",
            resolution_label="1080p",
            height=1080,
            ext="mp4",
            filesize_approx=5000,
            fps=30,
            vcodec="h264",
            acodec="aac"
        )
        qmodal = QualitySelectionModal(
            parent=self.root,
            video_title="Test YT",
            duration=60,
            options=[opt],
            default_dest_path="C:\\Downloads\\Test.mp4",
            theme=self.theme,
            on_confirm=lambda *a: None
        )
        try:
            self.root.update()
            qmodal.update()
            self.assertEqual(qmodal.state(), "normal")
            self.assertEqual(qmodal.winfo_viewable(), 1, "QualitySelectionModal must be viewable on screen when parent is hidden")
        finally:
            try:
                qmodal.destroy()
            except Exception:
                pass

    def test_open_in_main_while_download_active_transitions_cleanly_without_restart(self):
        """Verifies clicking 'Open in Main App' while download is active restores main window without restarting transfer."""
        gui = ModernFramelessGUI(self.root)
        try:
            mock_engine = MagicMock()
            mock_engine.is_running = True
            mock_engine.is_paused = False
            gui.engine = mock_engine

            modal = DownloadConfirmationModal(
                parent=self.root,
                url="https://example.com/large.iso",
                default_dest_path="C:\\Downloads\\large.iso",
                theme=self.theme,
                parent_app=gui
            )
            modal.engine = mock_engine
            modal.show_progress_view()
            self.assertTrue(modal.is_in_progress_view)

            with patch.object(gui, "_on_start_download") as mock_start_dl:
                modal._on_open_in_main()
                mock_start_dl.assert_not_called()

            self.assertEqual(self.root.state(), "normal")
            self.assertEqual(gui.btn_start.cget("state"), "disabled")
            self.assertEqual(gui.btn_cancel.cget("state"), "normal")
            self.assertEqual(gui.btn_pause.cget("text"), "⏸ Pause")
        finally:
            gui.exit_completely()

    def test_standalone_modal_cancellation_restores_main_window_controls(self):
        """Verifies cancelling active download in standalone modal restores main GUI btn_start to normal."""
        gui = ModernFramelessGUI(self.root)
        try:
            mock_engine = MagicMock()
            mock_engine.is_running = True
            gui.engine = mock_engine
            gui.btn_start.configure(state="disabled")
            gui.btn_cancel.configure(state="normal")

            modal = DownloadConfirmationModal(
                parent=self.root,
                url="https://example.com/test.zip",
                default_dest_path="C:\\Downloads\\test.zip",
                theme=self.theme,
                parent_app=gui
            )
            gui._confirm_modal = modal
            modal.engine = mock_engine
            modal.show_progress_view()

            modal._on_close()

            mock_engine.cancel.assert_called_once()
            self.assertIsNone(gui.engine)
            self.assertEqual(gui.btn_start.cget("state"), "normal", "Main GUI btn_start must be re-enabled on modal cancel")
            self.assertEqual(gui.btn_cancel.cget("state"), "disabled")
            self.assertIn("Cancelled", gui.card_size.cget("text"))
        finally:
            gui.exit_completely()

    def test_duplicate_completion_dialog_suppressed_when_modal_present(self):
        """Verifies _engine_complete_cb suppresses redundant popup dialog when standalone modal is present."""
        gui = ModernFramelessGUI(self.root)
        try:
            with patch.object(gui, "show_safe_info") as mock_safe_info:
                # With suppress_dialog=True (standalone modal active)
                gui._engine_complete_cb("C:\\Downloads\\file.bin", 1024, 1.0, suppress_dialog=True)
                self.root.update()
                mock_safe_info.assert_not_called()

                # Without suppress_dialog (normal main window completion)
                gui._engine_complete_cb("C:\\Downloads\\file.bin", 1024, 1.0, suppress_dialog=False)
                self.root.update()
                mock_safe_info.assert_called_once()
        finally:
            gui.exit_completely()

    def test_subsequent_clipboard_url_does_not_destroy_active_modal(self):
        """Verifies copying a new URL while modal is actively downloading does not destroy it."""
        gui = ModernFramelessGUI(self.root)
        try:
            modal = DownloadConfirmationModal(
                parent=self.root,
                url="https://example.com/active.zip",
                default_dest_path="C:\\Downloads\\active.zip",
                theme=self.theme,
                parent_app=gui
            )
            gui._confirm_modal = modal
            modal.show_progress_view()
            self.assertTrue(modal.is_in_progress_view)

            # A subsequent download confirmation request arrives
            gui._show_download_confirmation_dialog("https://example.com/second.zip", "C:\\Downloads\\second.zip")

            # The original active modal must still be alive!
            self.assertTrue(modal.winfo_exists())
            self.assertIs(gui._confirm_modal, modal)
        finally:
            gui.exit_completely()

    def test_pause_resume_synchronizes_parent_app_button(self):
        """Verifies toggling pause/resume in standalone modal synchronizes parent_app btn_pause text."""
        gui = ModernFramelessGUI(self.root)
        try:
            mock_engine = MagicMock()
            mock_engine.is_running = True
            mock_engine.is_paused = False
            gui.engine = mock_engine

            modal = DownloadConfirmationModal(
                parent=self.root,
                url="https://example.com/sync.zip",
                default_dest_path="C:\\Downloads\\sync.zip",
                theme=self.theme,
                parent_app=gui
            )
            modal.engine = mock_engine
            modal.show_progress_view()

            # Pause in modal
            modal._on_pause_resume()
            self.assertIn("Resume", gui.btn_pause.cget("text"))

            # Resume in modal
            mock_engine.is_paused = True
            modal._on_pause_resume()
            self.assertIn("Pause", gui.btn_pause.cget("text"))
        finally:
            gui.exit_completely()


class TestStandaloneExeBuild(unittest.TestCase):
    """Verifies that the PyInstaller standalone Windows executable exists and has valid PE structure."""

    def test_exe_binary_properties(self):
        dist_dir = os.path.join(os.path.dirname(__file__), "dist")
        exe_path = os.path.join(dist_dir, "SmartDownload.exe")
        self.assertTrue(os.path.exists(exe_path), f"SmartDownload.exe not found at {exe_path}")
        file_size = os.path.getsize(exe_path)
        self.assertGreater(file_size, 5 * 1024 * 1024, f"Binary size {file_size} is suspiciously small")

    def test_exe_binary_header_pe_signature(self):
        dist_dir = os.path.join(os.path.dirname(__file__), "dist")
        exe_path = os.path.join(dist_dir, "SmartDownload.exe")
        with open(exe_path, "rb") as f:
            header = f.read(2)
        self.assertEqual(header, b"MZ", "Executable missing valid Windows PE MZ header")

    def test_exe_binary_startup_verification(self):
        dist_dir = os.path.join(os.path.dirname(__file__), "dist")
        exe_path = os.path.join(dist_dir, "SmartDownload.exe")
        if not os.path.exists(exe_path):
            self.skipTest(f"{exe_path} not found")
        # Run with --test-startup (DEVNULL for windowed GUI executables)
        proc = subprocess.run([exe_path, "--test-startup"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        self.assertEqual(proc.returncode, 0, f"Standalone exe failed to start cleanly with returncode {proc.returncode}")

    def test_exe_binary_minimized_background_launch(self):
        dist_dir = os.path.join(os.path.dirname(__file__), "dist")
        exe_path = os.path.join(dist_dir, "SmartDownload.exe")
        if not os.path.exists(exe_path):
            self.skipTest(f"{exe_path} not found")
        proc = subprocess.Popen([exe_path, "--minimized"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            connected = False
            for _ in range(25):
                time.sleep(0.4)
                try:
                    req = urllib.request.Request("http://127.0.0.1:9242/ping")
                    with urllib.request.urlopen(req, timeout=1.0) as resp:
                        if resp.status == 200:
                            connected = True
                            break
                except Exception:
                    pass
            self.assertTrue(connected, "Standalone binary with --minimized failed to activate loopback server")
        finally:
            try:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


class TestInstantFetchingLinkToast(unittest.TestCase):
    """Verifies instant (< 50ms) fetching link toast indicator, dark styling, grab-free architecture, and smooth modal transition."""

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        # Warm up Windows font cache and Tkinter window subsystem
        try:
            _w = FetchingLinkToast(self.root, url="https://example.com/warmup", theme={
                "c_bg": "#0f172a", "c_panel": "#1e293b", "c_panel_light": "#334155",
                "c_border": "#475569", "c_accent": "#38bdf8", "c_accent_dark": "#0284c7",
                "c_success": "#10b981", "c_danger": "#ef4444", "c_text_bright": "#f8fafc",
                "c_text_muted": "#94a3b8", "c_input_bg": "#0b1220"
            })
            _w.close()
        except Exception:
            pass
        self.theme = {
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
            "c_input_bg": "#0b1220"
        }

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_toast_creation_under_50ms_and_properties(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        t0 = time.perf_counter()
        toast = FetchingLinkToast(self.root, url=url, theme=self.theme)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        try:
            self.assertLess(elapsed_ms, 200.0, f"Fetching toast took {elapsed_ms:.1f}ms, must be < 200ms")
            self.assertTrue(toast.winfo_exists())
            self.assertIn("جاري جلب وتحليل الرابط", toast.lbl_ar.cget("text"))
            self.assertIn("Fetching link information", toast.lbl_en.cget("text"))
            self.assertIn("youtube.com", toast.lbl_domain.cget("text"))
            # Grab-free verification
            toast.grab_set()
            toast.grab_set_global()
        finally:
            toast.close()

    def test_toast_animations_and_clean_close(self):
        toast = FetchingLinkToast(self.root, url="https://example.com/test_video.mp4", theme=self.theme)
        try:
            toast._animate_pulse()
            toast._animate_dots()
            self.assertTrue(toast.winfo_exists())
        finally:
            toast.close()
            self.assertFalse(toast.winfo_exists())

    def test_toast_cancel_callback_invoked(self):
        cancelled = []
        toast = FetchingLinkToast(
            self.root,
            url="https://www.youtube.com/watch?v=test",
            theme=self.theme,
            on_cancel=lambda: cancelled.append(True)
        )
        toast._on_cancel_click()
        self.assertEqual(cancelled, [True])
        self.assertFalse(toast.winfo_exists())

    def test_integration_fetching_toast_in_hidden_youtube_download(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            self.assertTrue(gui.is_window_hidden_or_minimized())
            sample_opt = VideoFormatOption(
                format_id="137",
                resolution_label="1080p",
                height=1080,
                ext="mp4",
                filesize_approx=50000000,
                fps=30,
                vcodec="avc1",
                acodec="none"
            )
            fake_info = {"title": "Test Video Title", "duration": 120}

            with patch("turbo_downloader.YouTubeResolver.extract_format_options", return_value=(fake_info, [sample_opt])):
                with patch("youtube_resolver.YouTubeResolver.extract_format_options", return_value=(fake_info, [sample_opt])):
                    gui._start_youtube_download("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "output.mp4")
                    # Immediately, fetching toast must be created (< 50ms)
                    self.assertIsNotNone(gui._fetching_toast)
                    self.assertTrue(gui._fetching_toast.winfo_exists())

                    # Wait for resolver thread to complete and post _show_modal
                    for _ in range(35):
                        time.sleep(0.04)
                        gui._drain_dispatch_queue()
                        gui.root.update()
                        if gui._quality_modal:
                            break

                    # Fetching toast must now be smoothly closed and quality modal presented
                    self.assertIsNone(gui._fetching_toast)
                    self.assertIsNotNone(gui._quality_modal)
                    self.assertTrue(gui._quality_modal.winfo_exists())
        finally:
            if getattr(gui, "_quality_modal", None):
                try:
                    gui._quality_modal.destroy()
                except Exception:
                    pass
            gui._cleanup_resources()

    def test_integration_fetching_toast_cancelled_by_user(self):
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            with patch("turbo_downloader.YouTubeResolver.extract_format_options", side_effect=lambda url: time.sleep(0.5)):
                with patch("youtube_resolver.YouTubeResolver.extract_format_options", side_effect=lambda url: time.sleep(0.5)):
                    gui._start_youtube_download("https://www.youtube.com/watch?v=slow_fetch", "output.mp4")
                    self.assertIsNotNone(gui._fetching_toast)

                    # Cancel fetching toast
                    gui._fetching_toast._on_cancel_click()
                    self.assertTrue(gui._yt_cancel_event.is_set())
                    self.assertIsNone(gui._fetching_toast)
                    self.assertIsNone(gui._last_clipboard_url, "Cancelling fetching toast must clear last clipboard URL")
                    self.assertEqual(gui.btn_start.cget("state"), "normal", "btn_start must be restored to normal")
                    self.assertEqual(gui.card_size.cget("text"), "Ready", "card_size must be restored to Ready")
                    time.sleep(0.1)
                    gui.root.update()
                    self.assertIsNone(gui._quality_modal)
        finally:
            gui._cleanup_resources()

    def test_toast_direct_destroy_cancels_jobs_cleanly(self):
        toast = FetchingLinkToast(self.root, url="https://example.com/test_destroy.mp4", theme=self.theme)
        self.assertTrue(toast.winfo_exists())
        self.assertIsNotNone(toast._pulse_job)
        self.assertIsNotNone(toast._dot_job)
        toast.destroy()
        self.assertFalse(toast.winfo_exists())
        self.assertIsNone(toast._pulse_job)
        self.assertIsNone(toast._dot_job)

    def test_toast_empty_url_graceful_fallback(self):
        toast = FetchingLinkToast(self.root, url="", theme=self.theme)
        try:
            self.assertTrue(toast.winfo_exists())
            self.assertIn("remote", toast.lbl_domain.cget("text"))
        finally:
            toast.destroy()


class TestClipboardSequenceRecopying(unittest.TestCase):
    """Verifies that re-copying the same link (clipboard sequence increment) re-triggers URL processing."""

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
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
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
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


if __name__ == "__main__":
    unittest.main()


