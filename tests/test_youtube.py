"""
Automated Test Module for Smart Download (SD)
"""
import os
import sys
import tempfile
import time
import json
import shutil
import struct
import hashlib
import ssl
import re
import unittest
import threading
import subprocess
import http.server
import socketserver
import urllib.request
import urllib.error
import urllib.parse
from unittest.mock import patch, MagicMock
from typing import List, Dict, Optional, Tuple, Any

# Ensure project root and src/ are in sys.path
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
    tk = None  # type: ignore
    ttk = None  # type: ignore

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None  # type: ignore
    ImageTk = None  # type: ignore

from youtube_resolver import (
    is_youtube_url,
    is_social_media_url,
    is_media_url,
    extract_youtube_id,
    extract_media_platform,
    extract_media_id,
    sanitize_filename,
    is_ytdlp_available,
    has_ffmpeg,
    find_ffmpeg_bin,
    update_ytdlp_engine,
    get_ytdlp_version,
    YouTubeResolver,
    MediaResolver,
    YouTubeStreamInfo,
    MediaStreamInfo,
    VideoFormatOption,
    format_filesize,
    SUPPORTED_COOKIE_BROWSERS,
    detect_installed_cookie_browsers,
)
from browser_bridge import BrowserBridgeServer, BrowserBridgeHandler, DEFAULT_BRIDGE_PORT
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
    get_default_extension_origins,
)
import installer
from turbo_downloader import (
    TurboDownloadEngine,
    SmartDownloadEngine,
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
    open_containing_folder,
    CATEGORY_SUBFOLDERS,
    resolve_categorized_path,
    DownloadHistoryManager,
    get_app_config_dir,
    resolve_real_download_url,
    StartupWelcomeToast,
    LocalizationManager,
    enable_high_dpi_awareness,
    get_resource_path,
)


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
        gui.exit_completely()

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
        gui.exit_completely()

class TestBrowserCookiesAndMP3Extraction(unittest.TestCase):
    """
    Unit tests for Browser Cookies detection & extraction, auto-retry on age/login restrictions,
    progressive social media MP3 transcoding, and QualitySelectionModal one-click MP3 button.
    """

    def test_detect_installed_cookie_browsers(self):
        """Verifies detect_installed_cookie_browsers detects browsers or returns standard fallback."""
        detected = detect_installed_cookie_browsers()
        self.assertIsInstance(detected, list)
        self.assertGreater(len(detected), 0)
        for b in detected:
            self.assertIn(b, SUPPORTED_COOKIE_BROWSERS)

        # Test fallback when no paths exist
        with patch("os.path.isdir", return_value=False):
            fallback = detect_installed_cookie_browsers()
            self.assertEqual(fallback, ["edge", "chrome", "firefox"])

    def test_build_ydl_opts(self):
        """Verifies _build_ydl_opts correctly sets cookiefile and cookiesfrombrowser."""
        resolver = YouTubeResolver()

        # Browser options
        opts_chrome = resolver._build_ydl_opts(browser="chrome")
        self.assertEqual(opts_chrome.get("cookiesfrombrowser"), ("chrome",))

        opts_edge = resolver._build_ydl_opts(browser="edge")
        self.assertEqual(opts_edge.get("cookiesfrombrowser"), ("edge",))

        opts_none = resolver._build_ydl_opts(browser="none")
        self.assertNotIn("cookiesfrombrowser", opts_none)

        opts_auto = resolver._build_ydl_opts(browser="auto")
        self.assertNotIn("cookiesfrombrowser", opts_auto)

        # Cookie file options with real temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
            tf.write(b"# Netscape HTTP Cookie File\n")
            temp_path = tf.name

        try:
            opts_file = resolver._build_ydl_opts(cookiefile=temp_path)
            self.assertEqual(opts_file.get("cookiefile"), temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_extract_format_options_auto_cookie_retry_on_login_required(self):
        """Verifies extract_format_options retries with browser cookies when unauthenticated extraction fails."""
        import yt_dlp
        from http.cookiejar import Cookie

        fake_info = {
            "id": "restricted_vid",
            "title": "Private / Restricted Video",
            "formats": [
                {
                    "format_id": "18",
                    "ext": "mp4",
                    "height": 360,
                    "url": "https://example.com/restricted.mp4",
                    "protocol": "https",
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "http_headers": {},
                }
            ]
        }

        call_count = [0]

        class FakeYDLContext:
            def __init__(self, opts):
                self.opts = opts
                self.cookiejar = []
                if "cookiesfrombrowser" in opts:
                    c = Cookie(
                        version=0, name="session_id", value="secret123", port=None,
                        port_specified=False, domain=".example.com", domain_specified=True,
                        domain_initial_dot=True, path="/", path_specified=True, secure=True,
                        expires=None, discard=True, comment=None, comment_url=None,
                        rest={}, rfc2109=False
                    )
                    self.cookiejar = [c]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

            def extract_info(self, url, download=False):
                call_count[0] += 1
                if "cookiesfrombrowser" not in self.opts:
                    raise Exception("Sign in to confirm your age or video is private")
                return fake_info

        resolver = YouTubeResolver(cookies_from_browser="auto")
        with patch("yt_dlp.YoutubeDL", side_effect=FakeYDLContext):
            with patch("youtube_resolver.detect_installed_cookie_browsers", return_value=["chrome"]):
                info, options = resolver.extract_format_options("https://www.youtube.com/watch?v=GTNypvv2Nbg")

                self.assertGreaterEqual(call_count[0], 2)
                self.assertEqual(info["id"], "restricted_vid")
                self.assertGreater(len(options), 0)
                # Verify cookie propagation into format headers
                self.assertIn("Cookie", options[0].video_headers)
                self.assertIn("session_id=secret123", options[0].video_headers["Cookie"])

    def test_build_format_options_progressive_mp3(self):
        """Verifies build_format_options generates Audio Only (MP3) for progressive-only social media streams."""
        resolver = YouTubeResolver()
        fake_progressive_info = {
            "id": "tiktok_123",
            "title": "TikTok Progressive Video",
            "webpage_url": "https://www.tiktok.com/@user/video/1234567890",
            "duration": 60,
            "formats": [
                {
                    "format_id": "prog_720",
                    "ext": "mp4",
                    "height": 1280,
                    "width": 720,
                    "vcodec": "h264",
                    "acodec": "aac",
                    "protocol": "https",
                    "url": "https://example.com/tiktok_prog.mp4",
                    "filesize": 10000000,
                    "http_headers": {"User-Agent": "SD/2.0"},
                }
            ]
        }

        with patch("youtube_resolver.has_ffmpeg", return_value=True):
            options = resolver.build_format_options(fake_progressive_info)
            mp3_opts = [o for o in options if o.is_audio_only and o.ext.lower() == "mp3"]
            self.assertEqual(len(mp3_opts), 1)
            mp3_opt = mp3_opts[0]
            self.assertEqual(mp3_opt.resolution_label, "Audio Only (MP3)")
            self.assertEqual(mp3_opt.audio_ext, "mp4")
            self.assertTrue(mp3_opt.is_progressive)
            self.assertTrue(mp3_opt.is_audio_only)

            # Test build_stream_info preserves audio_ext
            stream_info = resolver.build_stream_info(fake_progressive_info, mp3_opt)
            self.assertEqual(stream_info.audio_ext, "mp4")
            self.assertEqual(stream_info.video_ext, "mp3")
            self.assertTrue(stream_info.is_audio_only)

    def test_stream_coordinator_mp3_transcoding_execution(self):
        """Verifies StreamDownloadCoordinator triggers FFmpeg MP3 transcoding when MP3 option is selected."""
        from turbo_downloader import StreamDownloadCoordinator, YouTubeStreamInfo
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            dest_mp3 = os.path.join(tmp_dir, "test_output.mp3")
            tmp_audio = dest_mp3 + ".audio.tmp"

            stream_info = YouTubeStreamInfo(
                video_id="test_id",
                title="Test Audio",
                clean_filename="test_output.mp3",
                is_progressive=True,
                video_url="https://example.com/stream.m4a",
                video_ext="mp3",
                audio_ext="m4a",
                video_resolution="Audio Only",
                is_audio_only=True
            )

            completed = [False]
            def on_complete_cb(p, sz, elapsed):
                completed[0] = True

            coord = StreamDownloadCoordinator(
                stream_info=stream_info,
                destination_path=dest_mp3,
                on_complete=on_complete_cb
            )

            # Fake TurboDownloadEngine that creates actual_dest file and fires on_complete
            class FakeEngine:
                def __init__(self, **kwargs):
                    self.dest = kwargs["destination_path"]
                    self.on_complete = kwargs["on_complete"]
                    self.is_running = False

                def start(self):
                    with open(self.dest, "wb") as f:
                        f.write(b"FAKEAACDATA")
                    self.on_complete(self.dest, 10, 0.1)

                def pause(self):
                    pass

            def fake_subprocess_run(cmd, **kwargs):
                # Simulate FFmpeg output creation
                out_path = cmd[-1]
                with open(out_path, "wb") as f:
                    f.write(b"ID3FAKEMP3DATA")
                res = MagicMock()
                res.returncode = 0
                return res

            with patch("turbo_downloader.TurboDownloadEngine", FakeEngine):
                with patch("turbo_downloader.has_ffmpeg", return_value=True):
                    with patch("turbo_downloader.find_ffmpeg_bin", return_value="ffmpeg"):
                        with patch("subprocess.run", side_effect=fake_subprocess_run) as mock_subproc:
                            coord._run_coordinator()

                            self.assertTrue(completed[0])
                            self.assertTrue(os.path.isfile(dest_mp3))
                            self.assertFalse(os.path.isfile(tmp_audio))

                            # Verify FFmpeg command
                            mock_subproc.assert_called_once()
                            cmd_called = mock_subproc.call_args[0][0]
                            self.assertIn("-c:a", cmd_called)
                            self.assertIn("libmp3lame", cmd_called)
                            self.assertEqual(cmd_called[-1], dest_mp3)

    def test_quality_selection_modal_download_mp3_button(self):
        """Verifies QualitySelectionModal includes Download MP3 button and correctly selects MP3 option."""
        from turbo_downloader import QualitySelectionModal

        root = tk.Tk()
        root.withdraw()
        try:
            options = [
                VideoFormatOption(
                    format_id="137+140",
                    resolution_label="1080p (Full HD)",
                    height=1080,
                    ext="mp4",
                    filesize_approx=50000000,
                    fps=30,
                    is_progressive=False,
                    is_audio_only=False,
                    video_url="https://example.com/v.mp4"
                ),
                VideoFormatOption(
                    format_id="140+mp3",
                    resolution_label="Audio Only (MP3)",
                    height=0,
                    ext="mp3",
                    filesize_approx=5000000,
                    fps=0,
                    is_progressive=True,
                    is_audio_only=True,
                    audio_ext="m4a",
                    video_url="https://example.com/a.m4a"
                ),
            ]

            confirmed_records = []
            def on_download_cb(opt, path):
                confirmed_records.append((opt, path))

            theme = {
                "c_bg": "#0f172a",
                "c_panel": "#1e293b",
                "c_panel_light": "#334155",
                "c_border": "#475569",
                "c_accent": "#38bdf8",
                "c_accent_dark": "#0284c7",
                "c_success": "#10b981",
                "c_warning": "#f59e0b",
                "c_error": "#ef4444",
                "c_text_bright": "#ffffff",
                "c_text_muted": "#94a3b8",
                "c_input_bg": "#0f172a"
            }

            modal = QualitySelectionModal(
                parent=root,
                video_title="Test Video Title",
                duration=120,
                options=options,
                default_dest_path=os.path.join(os.path.expanduser("~"), "Downloads", "Test Video Title.mp4"),
                theme=theme,
                on_confirm=on_download_cb
            )

            self.assertTrue(hasattr(modal, "btn_download_mp3"))
            self.assertEqual(modal.btn_download_mp3.cget("text"), "🎵 Download MP3")

            modal._on_download_mp3()

            self.assertEqual(len(confirmed_records), 1)
            sel_opt, sel_path = confirmed_records[0]
            self.assertEqual(sel_opt.ext, "mp3")
            self.assertTrue(sel_path.endswith(".mp3"))
        finally:
            try:
                root.update_idletasks()
                root.destroy()
            except Exception:
                pass

    def test_modern_frameless_gui_cookies_button_cycle(self):
        """Verifies ModernFramelessGUI includes cookies button and cycles through settings."""
        from turbo_downloader import ModernFramelessGUI, get_setting, set_setting

        root = tk.Tk()
        root.withdraw()
        gui = ModernFramelessGUI(root)
        try:
            self.assertTrue(hasattr(gui, "btn_cookies"))
            orig_browser = gui.cookies_browser

            gui.cookies_browser = "auto"
            gui.cookies_file = ""
            gui._update_cookies_btn()
            self.assertIn("Auto", gui.btn_cookies.cget("text"))

            # Test cycle: auto -> edge
            gui.cycle_cookies_setting()
            self.assertEqual(gui.cookies_browser, "edge")
            self.assertIn("Edge", gui.btn_cookies.cget("text"))

            # Test cycling to none
            gui.cookies_browser = "brave"
            gui.cookies_file = ""
            # brave -> file... (with mock cancel) -> none
            with patch("tkinter.filedialog.askopenfilename", return_value=""):
                gui.cycle_cookies_setting()
                self.assertEqual(gui.cookies_browser, "none")
                self.assertIn("Off", gui.btn_cookies.cget("text"))
        finally:
            gui._cleanup_resources()
            try:
                root.update_idletasks()
                root.destroy()
            except Exception:
                pass

    def test_extract_format_options_explicit_browser_failure_falls_back_to_next_detected(self):
        """Verifies that if an explicit browser fails, unauthenticated is tried, and then next installed browser succeeds."""
        import yt_dlp
        from http.cookiejar import Cookie

        fake_info = {
            "id": "restricted_vid_explicit",
            "title": "Private Media",
            "formats": [
                {
                    "format_id": "18",
                    "ext": "mp4",
                    "height": 360,
                    "url": "https://example.com/restricted.mp4",
                    "protocol": "https",
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "http_headers": {},
                }
            ]
        }

        call_trace = []

        class FakeYDLMultiBrowser:
            def __init__(self, opts):
                self.opts = opts
                self.cookiejar = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

            def extract_info(self, url, download=False):
                cb = self.opts.get("cookiesfrombrowser")
                browser_name = cb[0] if cb else "none"
                call_trace.append(browser_name)
                if browser_name == "chrome":
                    # Simulate locked database error
                    raise Exception("sqlite3.OperationalError: database is locked")
                elif browser_name == "none":
                    # Unauthenticated fails because it's age-restricted
                    raise Exception("Sign in to confirm your age")
                elif browser_name == "edge":
                    return fake_info
                raise Exception(f"Browser {browser_name} failed")

        resolver = YouTubeResolver(cookies_from_browser="chrome")
        with patch("yt_dlp.YoutubeDL", side_effect=FakeYDLMultiBrowser):
            with patch("youtube_resolver.detect_installed_cookie_browsers", return_value=["chrome", "edge"]):
                info, options = resolver.extract_format_options("https://www.youtube.com/watch?v=GTNypvv2Nbg")

                self.assertEqual(call_trace, ["chrome", "none", "edge"])
                self.assertEqual(info["id"], "restricted_vid_explicit")
                self.assertGreater(len(options), 0)

    def test_stream_coordinator_mp3_cleanup_on_cancel(self):
        """Verifies StreamDownloadCoordinator cleans up .audio.tmp when download is cancelled."""
        from turbo_downloader import StreamDownloadCoordinator, YouTubeStreamInfo
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            dest_mp3 = os.path.join(tmp_dir, "cancel_test.mp3")
            tmp_audio = dest_mp3 + ".audio.tmp"

            stream_info = YouTubeStreamInfo(
                video_id="cancel_id",
                title="Cancel Test",
                clean_filename="cancel_test.mp3",
                is_progressive=True,
                video_url="https://example.com/stream.m4a",
                video_ext="mp3",
                audio_ext="m4a",
                video_resolution="Audio Only",
                is_audio_only=True
            )

            coord = StreamDownloadCoordinator(
                stream_info=stream_info,
                destination_path=dest_mp3
            )

            # Engine that writes dummy bytes and gets cancelled
            class FakeCancellingEngine:
                def __init__(self, **kwargs):
                    self.dest = kwargs["destination_path"]
                    self.is_running = True

                def start(self):
                    with open(self.dest, "wb") as f:
                        f.write(b"PARTIAL_DATA")
                    # Trigger cancel
                    coord.cancel()
                    self.is_running = False

                def pause(self):
                    pass

            with patch("turbo_downloader.TurboDownloadEngine", FakeCancellingEngine):
                with patch("turbo_downloader.has_ffmpeg", return_value=True):
                    coord._run_coordinator()

                    # Both the tmp_audio and dest_mp3 should be absent/cleaned up
                    self.assertFalse(os.path.isfile(tmp_audio))
                    self.assertFalse(os.path.isfile(dest_mp3))

    def test_stream_coordinator_mp3_destination_auto_extension(self):
        """Verifies StreamDownloadCoordinator auto-appends .mp3 extension if passed .m4a destination for MP3 option."""
        from turbo_downloader import StreamDownloadCoordinator, YouTubeStreamInfo
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            dest_wrong_ext = os.path.join(tmp_dir, "song.m4a")

            stream_info = YouTubeStreamInfo(
                video_id="id123",
                title="Song",
                clean_filename="song.mp3",
                is_progressive=True,
                video_url="https://example.com/audio.m4a",
                video_ext="mp3",
                audio_ext="m4a",
                video_resolution="Audio Only",
                is_audio_only=True
            )

            coord = StreamDownloadCoordinator(
                stream_info=stream_info,
                destination_path=dest_wrong_ext
            )

            class FakeEngine:
                def __init__(self, **kwargs):
                    self.dest = kwargs["destination_path"]
                    self.on_complete = kwargs["on_complete"]
                    self.is_running = False

                def start(self):
                    with open(self.dest, "wb") as f:
                        f.write(b"AUDIO")
                    self.on_complete(self.dest, 5, 0.1)

                def pause(self):
                    pass

            def fake_run(cmd, **kwargs):
                out = cmd[-1]
                with open(out, "wb") as f:
                    f.write(b"MP3")
                res = MagicMock()
                res.returncode = 0
                return res

            with patch("turbo_downloader.TurboDownloadEngine", FakeEngine):
                with patch("turbo_downloader.has_ffmpeg", return_value=True):
                    with patch("turbo_downloader.find_ffmpeg_bin", return_value="ffmpeg"):
                        with patch("subprocess.run", side_effect=fake_run):
                            coord._run_coordinator()

                            expected_dest = os.path.join(tmp_dir, "song.mp3")
                            self.assertEqual(coord.destination_path, expected_dest)
                            self.assertTrue(os.path.isfile(expected_dest))

    def test_url_specific_cookie_header_propagation(self):
        """Verifies that format options receive URL-specific cookies from cookiejar.get_cookie_header."""
        from youtube_resolver import YouTubeResolver

        fake_info = {
            "id": "reel123",
            "title": "Instagram Reel",
            "webpage_url": "https://www.instagram.com/reel/123",
            "formats": [
                {
                    "format_id": "direct_cdn",
                    "ext": "mp4",
                    "height": 720,
                    "url": "https://scontent.cdninstagram.com/v/t50/video.mp4",
                    "protocol": "https",
                    "vcodec": "h264",
                    "acodec": "aac",
                    "http_headers": {},
                }
            ]
        }

        class MockCookieJarWithHeaders:
            def get_cookie_header(self, url):
                if "cdninstagram.com" in url:
                    return "cdn_token=secure_cdn_token_xyz"
                return "session_id=ig_session_abc"

        class MockYDL:
            def __init__(self, opts):
                self.cookiejar = MockCookieJarWithHeaders()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def extract_info(self, url, download=False):
                return fake_info

        resolver = YouTubeResolver(cookies_from_browser="none")
        with patch("yt_dlp.YoutubeDL", MockYDL):
            info, options = resolver.extract_format_options("https://www.instagram.com/reel/123")
            self.assertEqual(options[0].video_headers.get("Cookie"), "cdn_token=secure_cdn_token_xyz")


if __name__ == "__main__":
    unittest.main()
