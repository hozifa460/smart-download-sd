"""
Automated Test Module for Smart Download (SD)
"""
import os, sys, tempfile, time, json, shutil, struct, hashlib, ssl, re, unittest, threading, subprocess
import http.server, socketserver, urllib.request, urllib.error, urllib.parse
from unittest.mock import patch, MagicMock
from typing import List, Dict, Optional, Tuple, Any

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

os.environ["SD_DISABLE_SYSTEM_TRAY"] = "1"
os.environ["SD_DISABLE_STARTUP_TOAST"] = "1"
os.environ["SD_DISABLE_AUTO_UPDATE"] = "1"
os.environ["SD_LANGUAGE"] = "en"
if not os.environ.get("SD_CONFIG_DIR"):
    _sd_test_cfg = os.path.join(tempfile.gettempdir(), "sd_test_isolated_cfg")
    os.makedirs(_sd_test_cfg, exist_ok=True)
    os.environ["SD_CONFIG_DIR"] = _sd_test_cfg

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk, ttk = None, None

from youtube_resolver import *
from browser_bridge import BrowserBridgeServer, BrowserBridgeHandler, DEFAULT_BRIDGE_PORT
from native_messaging_host import read_message, send_message, handle_payload
from register_browser import *
import installer
from turbo_downloader import *


def setUpModule():
    os.environ["SD_LANGUAGE"] = "en"
    try:
        set_setting("language", "en")
        LocalizationManager.reset_instance("en")
    except Exception:
        pass


def tearDownModule():
    try:
        LocalizationManager.reset_instance()
    except Exception:
        pass

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
            self.assertIn(passed_opts.get("socket_timeout"), (8, 12))
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

class TestSocialMediaDetectionAndSanitization(unittest.TestCase):
    """Verifies recognition and platform identification for social media URLs."""

    def test_social_media_url_detection(self):
        valid_cases = [
            # TikTok
            ("https://www.tiktok.com/@username/video/7123456789012345678", "TikTok"),
            ("https://vt.tiktok.com/ZS1234567/", "TikTok"),
            ("https://vm.tiktok.com/ZM1234567/", "TikTok"),
            ("https://www.tiktok.com/t/ZT1234567/", "TikTok"),
            ("http://m.tiktok.com/v/7123456789012345678", "TikTok"),
            # Instagram
            ("https://www.instagram.com/reel/C1234567890/", "Instagram"),
            ("https://www.instagram.com/p/B1234567890/", "Instagram"),
            ("https://instagram.com/stories/user/1234567890/", "Instagram"),
            ("https://instagr.am/p/B1234567890/", "Instagram"),
            ("https://www.instagram.com/tv/C1234567890/", "Instagram"),
            # Facebook
            ("https://www.facebook.com/watch/?v=1234567890", "Facebook"),
            ("https://www.facebook.com/reel/1234567890", "Facebook"),
            ("https://fb.watch/aBcDeFgHiJ/", "Facebook"),
            ("https://www.facebook.com/page/videos/1234567890/", "Facebook"),
            ("https://facebook.com/share/v/xyz123/", "Facebook"),
            ("https://facebook.com/share/r/abc456/", "Facebook"),
            # Twitter / X
            ("https://twitter.com/jack/status/20", "Twitter / X"),
            ("https://x.com/elonmusk/status/1234567890123456789", "Twitter / X"),
            ("https://mobile.twitter.com/user/status/987654321", "Twitter / X"),
            # Reddit, Vimeo, Dailymotion, Pinterest
            ("https://reddit.com/r/videos/comments/123abc/title/", "Reddit"),
            ("https://v.redd.it/abcdef123456", "Reddit"),
            ("https://vimeo.com/123456789", "Vimeo"),
            ("https://dailymotion.com/video/x8abcde", "Dailymotion"),
            ("https://dai.ly/x8abcde", "Dailymotion"),
            ("https://www.pinterest.com/pin/123456789012345678/", "Pinterest"),
            ("https://pin.it/1234567", "Pinterest"),
        ]

        for url, expected_plat in valid_cases:
            self.assertTrue(is_social_media_url(url), f"Failed is_social_media_url: {url}")
            self.assertTrue(is_media_url(url), f"Failed is_media_url: {url}")
            self.assertEqual(extract_media_platform(url), expected_plat, f"Platform mismatch for {url}")

    def test_social_media_url_negatives(self):
        negative_cases = [
            "https://google.com",
            "https://facebook.com/settings",
            "https://facebook.com/friends",
            "https://twitter.com/home",
            "https://instagram.com/explore",
            "https://tiktok.com/@username",
            "https://speed.cloudflare.com/__down?bytes=50000000",
            "https://example.com/file.mp4",
            "",
            "   ",
            None
        ]
        for url in negative_cases:
            self.assertFalse(is_social_media_url(url), f"False positive is_social_media_url: {url}")

    def test_extract_media_id(self):
        self.assertEqual(extract_media_id("https://www.tiktok.com/@user/video/7123456789"), "7123456789")
        self.assertEqual(extract_media_id("https://vt.tiktok.com/ZS1234567/"), "ZS1234567")
        self.assertEqual(extract_media_id("https://www.instagram.com/reel/C1234567890/"), "C1234567890")
        self.assertEqual(extract_media_id("https://x.com/user/status/123456789"), "123456789")
        self.assertEqual(extract_media_id("https://fb.watch/aBcDeFgHiJ/"), "aBcDeFgHiJ")
        self.assertEqual(extract_media_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertIsNone(extract_media_id("https://google.com"))

class TestSocialMediaResolverAndExtraction(unittest.TestCase):
    """Verifies media extraction for TikTok, Instagram, Facebook, and Twitter/X using mock yt-dlp metadata."""

    def test_tiktok_mock_extraction(self):
        """Simulates vertical TikTok video format extraction."""
        mock_info = {
            "id": "7123456789012345678",
            "title": "Amazing TikTok dance video #trending",
            "duration": 35,
            "thumbnail": "https://p16-sign-va.tiktokcdn.com/thumb.jpg",
            "webpage_url": "https://www.tiktok.com/@creator/video/7123456789012345678",
            "formats": [
                {
                    "format_id": "download_addr-0",
                    "ext": "mp4",
                    "width": 1080,
                    "height": 1920,
                    "vcodec": "h264",
                    "acodec": "aac",
                    "protocol": "https",
                    "url": "https://v16-webapp-prime.tiktok.com/video/tos/useast2a/mock.mp4",
                    "filesize": 8500000
                }
            ]
        }

        with patch("yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = mock_info

            resolver = YouTubeResolver()
            stream_info = resolver.resolve("https://www.tiktok.com/@creator/video/7123456789012345678")

            self.assertTrue(stream_info.is_progressive)
            self.assertEqual(stream_info.platform, "TikTok")
            self.assertIn("Amazing TikTok dance video #trending", stream_info.title)
            self.assertIn("tiktok.com", stream_info.video_url)
            self.assertIn("1080p Vertical", stream_info.video_resolution)

    def test_instagram_mock_extraction(self):
        """Simulates Instagram Reel progressive extraction."""
        mock_info = {
            "id": "C1234567890",
            "title": "Beautiful Sunset Reel",
            "duration": 15,
            "webpage_url": "https://www.instagram.com/reel/C1234567890/",
            "formats": [
                {
                    "format_id": "dash-hd",
                    "ext": "mp4",
                    "height": 1080,
                    "width": 1080,
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "protocol": "https",
                    "url": "https://scontent.cdninstagram.com/v/mock_ig.mp4",
                    "filesize": 4200000
                }
            ]
        }

        with patch("yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = mock_info

            resolver = YouTubeResolver()
            stream_info = resolver.resolve("https://www.instagram.com/reel/C1234567890/")

            self.assertTrue(stream_info.is_progressive)
            self.assertEqual(stream_info.platform, "Instagram")
            self.assertEqual(stream_info.video_resolution, "1080p")
            self.assertEqual(stream_info.clean_filename, "Beautiful Sunset Reel.mp4")

    def test_facebook_mock_extraction(self):
        """Simulates Facebook video extraction with SD and HD formats."""
        mock_info = {
            "id": "1234567890",
            "title": "Interesting Facebook Documentary Clip",
            "duration": 240,
            "webpage_url": "https://www.facebook.com/watch/?v=1234567890",
            "formats": [
                {
                    "format_id": "hd",
                    "ext": "mp4",
                    "height": 720,
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "protocol": "https",
                    "url": "https://video.faly1-1.fna.fbcdn.net/mock_hd.mp4",
                    "filesize": 25000000
                },
                {
                    "format_id": "sd",
                    "ext": "mp4",
                    "height": 360,
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "protocol": "https",
                    "url": "https://video.faly1-1.fna.fbcdn.net/mock_sd.mp4",
                    "filesize": 10000000
                }
            ]
        }

        with patch("yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = mock_info

            resolver = YouTubeResolver()
            info, options = resolver.extract_format_options("https://www.facebook.com/watch/?v=1234567890")

            self.assertGreaterEqual(len(options), 2)
            self.assertEqual(options[0].height, 720)
            self.assertEqual(options[1].height, 360)

    def test_twitter_mock_extraction(self):
        """Simulates Twitter/X post video extraction."""
        mock_info = {
            "id": "1234567890123456789",
            "title": "Breaking News Update Video",
            "duration": 45,
            "webpage_url": "https://x.com/user/status/1234567890123456789",
            "formats": [
                {
                    "format_id": "http-1080",
                    "ext": "mp4",
                    "height": 720,
                    "vcodec": "h264",
                    "acodec": "aac",
                    "protocol": "https",
                    "url": "https://video.twimg.com/ext_tw_video/mock_720.mp4",
                    "filesize": 6000000
                }
            ]
        }

        with patch("yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = mock_info

            resolver = YouTubeResolver()
            stream_info = resolver.resolve("https://x.com/user/status/1234567890123456789")

            self.assertEqual(stream_info.platform, "Twitter / X")
            self.assertTrue(stream_info.is_progressive)
            self.assertEqual(stream_info.clean_filename, "Breaking News Update Video.mp4")

    def test_social_media_dual_stream_merge_extraction(self):
        """Simulates social media platform with split video and audio streams (e.g. Reddit v.redd.it)."""
        mock_info = {
            "id": "mock_reddit_id",
            "title": "Viral Reddit Clip",
            "duration": 60,
            "webpage_url": "https://reddit.com/r/videos/comments/123abc/viral_clip/",
            "formats": [
                {
                    "format_id": "DASH_1080",
                    "ext": "mp4",
                    "height": 1080,
                    "vcodec": "h264",
                    "acodec": "none",
                    "protocol": "https",
                    "url": "https://v.redd.it/mock/DASH_1080.mp4",
                    "filesize": 15000000
                },
                {
                    "format_id": "DASH_audio",
                    "ext": "m4a",
                    "height": 0,
                    "vcodec": "none",
                    "acodec": "aac",
                    "protocol": "https",
                    "url": "https://v.redd.it/mock/DASH_audio.mp4",
                    "filesize": 2000000
                }
            ]
        }

        with patch("yt_dlp.YoutubeDL") as MockYDL, patch("youtube_resolver.has_ffmpeg", return_value=True):
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = mock_info

            resolver = YouTubeResolver()
            stream_info = resolver.resolve("https://reddit.com/r/videos/comments/123abc/viral_clip/")

            self.assertFalse(stream_info.is_progressive)
            self.assertEqual(stream_info.video_resolution, "1080p")
            self.assertIsNotNone(stream_info.audio_url)
            self.assertEqual(stream_info.platform, "Reddit")

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


if __name__ == "__main__":
    unittest.main()
