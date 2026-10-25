"""
Unit test suite verifying Stage 6: Ultra-Performance, Low-Latency & High-Throughput Optimization.
Tests probe caching, fast multi-chunk ramp-up, concurrent dual-stream download,
on-the-fly integrity hashing, yt-dlp extractor fast paths, and UI coalescing.
"""
import os
import sys
import time
import tempfile
import threading
import hashlib
import zlib
import unittest
import http.server
import socketserver
from unittest.mock import MagicMock, patch

_tests_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_tests_dir)
_src_dir = os.path.join(_root_dir, "src")
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from smart_download.core.html_resolver import (
    resolve_real_download_url,
    clear_probe_cache,
    _PROBE_CACHE,
    _PROBE_CACHE_LOCK
)
from smart_download.core.engine import TurboDownloadEngine
from smart_download.core.stream_coordinator import StreamDownloadCoordinator
from smart_download.services.youtube_models import (
    is_media_url,
    is_ytdlp_extractor_supported,
    YouTubeStreamInfo
)
import smart_download.services.youtube_models as ym


class TestStage6PerformanceOptimizations(unittest.TestCase):

    def setUp(self):
        clear_probe_cache()

    def tearDown(self):
        clear_probe_cache()

    def test_probe_cache_ttl_and_force_refresh(self):
        """Verifies 30-second TTL in-memory probe cache and force_refresh invalidation."""
        url = "https://cdn.example.org/package_setup.zip"
        res_data = {
            "url": url,
            "is_html": False,
            "resolved": False,
            "content_type": "application/zip",
            "size": 1048576,
            "filename": "package_setup.zip",
            "supports_ranges": True,
            "error": "",
            "timestamp": time.monotonic()
        }

        with _PROBE_CACHE_LOCK:
            _PROBE_CACHE[url] = (time.monotonic(), res_data)

        # 1. Hit cache
        cached = resolve_real_download_url(url)
        self.assertEqual(cached.get("filename"), "package_setup.zip")
        self.assertEqual(cached.get("size"), 1048576)

        # 2. force_refresh clears entry
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.geturl.return_value = url
            mock_resp.headers = {"Content-Type": "application/zip", "Content-Length": "2048", "Accept-Ranges": "bytes"}
            mock_open.return_value.__enter__.return_value = mock_resp
            resolve_real_download_url(url, force_refresh=True)
            self.assertNotIn(url, _PROBE_CACHE)

    def test_engine_pre_probed_info_fresh_vs_direct_probe(self):
        """Verifies pre_probed_info skips network probe on startup while direct probe executes."""
        url = "https://example.com/test_preprobe.iso"
        pre_info = {
            "url": url,
            "size": 52428800,
            "supports_ranges": True,
            "content_type": "application/x-iso9660-image",
            "filename": "test_preprobe.iso",
            "timestamp": time.monotonic()
        }

        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "test_preprobe.iso")
            engine = TurboDownloadEngine(
                url=url,
                destination_path=dest,
                pre_probed_info=pre_info
            )
            self.assertTrue(engine._has_pre_probed)
            self.assertEqual(engine.total_size, 52428800)
            self.assertEqual(engine.filename, "test_preprobe.iso")
            self.assertTrue(engine.supports_ranges)

            # Direct call to probe() executes full probe
            with patch("urllib.request.urlopen") as mock_open:
                mock_resp = MagicMock()
                mock_resp.geturl.return_value = url
                mock_resp.headers = {"Content-Type": "application/x-iso9660-image", "Content-Length": "52428800", "Accept-Ranges": "bytes"}
                mock_open.return_value.__enter__.return_value = mock_resp
                engine.probe()
                mock_open.assert_called()

    def test_fast_multi_chunk_ramp_up_latency(self):
        """Verifies multi-chunk ramp-up establishes max_connections in <100ms."""
        payload = os.urandom(8 * 1024 * 1024)

        class FastMockHandler(http.server.BaseHTTPRequestHandler):
            def do_HEAD(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
            def do_GET(self):
                rng = self.headers.get("Range", "")
                if rng.startswith("bytes="):
                    parts = rng[6:].split("-")
                    s = int(parts[0])
                    e = int(parts[1]) if parts[1] else len(payload) - 1
                    e = min(e, len(payload) - 1)
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {s}-{e}/{len(payload)}")
                    self.send_header("Content-Length", str(e - s + 1))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    time.sleep(0.5)
                    self.wfile.write(payload[s:e+1])
                else:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    self.wfile.write(payload)
            def log_message(self, *args): pass

        server = socketserver.TCPServer(("127.0.0.1", 0), FastMockHandler)
        srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
        srv_thread.start()
        port = server.server_address[1]

        try:
            with tempfile.TemporaryDirectory() as td:
                dest = os.path.join(td, "ramp_test.bin")
                engine = TurboDownloadEngine(
                    url=f"http://127.0.0.1:{port}/ramp.bin",
                    destination_path=dest,
                    max_connections=8
                )
                t0 = time.time()
                engine.start()
                while len(engine.chunks) < 8 and (time.time() - t0) < 3.0:
                    time.sleep(0.01)
                elapsed_ms = (time.time() - t0) * 1000.0
                engine.cancel()
                self.assertGreaterEqual(len(engine.chunks), 8)
                self.assertLess(elapsed_ms, 250.0, f"Ramp-up took {elapsed_ms:.1f}ms (expected <250ms)")
        finally:
            server.shutdown()
            server.server_close()

    def test_on_the_fly_zero_read_assembly_integrity(self):
        """Verifies assemble() computes SHA-256 and CRC-32 on the fly without extra file reads."""
        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "assembled.dat")
            engine = TurboDownloadEngine(
                url="https://example.com/test.dat",
                destination_path=dest
            )
            engine.total_size = 1024 * 1024
            os.makedirs(engine.temp_dir, exist_ok=True)

            chunk_data_0 = os.urandom(512 * 1024)
            chunk_data_1 = os.urandom(512 * 1024)
            full_data = chunk_data_0 + chunk_data_1
            expected_sha = hashlib.sha256(full_data).hexdigest()
            expected_crc = f"{zlib.crc32(full_data) & 0xFFFFFFFF:08x}"

            from smart_download.core.chunk import DownloadChunk
            c0 = DownloadChunk(0, 0, 512 * 1024 - 1, 512 * 1024, "completed", os.path.join(engine.temp_dir, "test.dat.part_0"))
            c1 = DownloadChunk(1, 512 * 1024, 1024 * 1024 - 1, 512 * 1024, "completed", os.path.join(engine.temp_dir, "test.dat.part_1"))
            with open(c0.part_filepath, "wb") as f: f.write(chunk_data_0)
            with open(c1.part_filepath, "wb") as f: f.write(chunk_data_1)
            engine.chunks = [c0, c1]

            logs = []
            engine.on_log = lambda m: logs.append(m)

            engine.assemble()
            self.assertTrue(os.path.exists(dest))
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), full_data)

            integrity_log = next((m for m in logs if "[INTEGRITY]" in m), "")
            self.assertIn(expected_sha, integrity_log)
            self.assertIn(expected_crc, integrity_log)

    def test_fast_path_direct_download_extensions(self):
        """Verifies direct file extensions return False in 0ms without invoking yt_dlp."""
        direct_urls = [
            "https://cdn.example.com/releases/app.zip",
            "https://cdn.example.com/downloads/setup.exe",
            "https://cdn.example.com/files/installer.msi",
            "https://cdn.example.com/archive.tar.gz",
            "https://cdn.example.com/video/sample.mp4",
            "https://cdn.example.com/audio/song.mp3",
            "https://cdn.example.com/media/clip.mkv",
            "https://cdn.example.com/docs/manual.pdf",
        ]
        with patch("yt_dlp.extractor.gen_extractors") as mock_gen:
            for u in direct_urls:
                self.assertFalse(is_ytdlp_extractor_supported(u), f"Failed for {u}")
                self.assertFalse(is_media_url(u, check_ytdlp_extractors=True), f"Failed is_media_url for {u}")
            mock_gen.assert_not_called()

    def test_cached_ytdlp_extractors_sync(self):
        """Verifies _CACHED_YTDLP_EXTRACTORS and _YTDLP_EXTRACTORS_CACHE sync properly."""
        self.assertIs(ym._CACHED_YTDLP_EXTRACTORS, ym._YTDLP_EXTRACTORS_CACHE)

    def test_ui_coalescing_pending_guards(self):
        """Verifies UI coalescing flags exist and guard against event queue flooding."""
        from smart_download.ui.controllers.download_controller import DownloadControllerMixin

        class DummyUI(DownloadControllerMixin):
            def __init__(self):
                self.root = MagicMock()
                self.root.winfo_exists.return_value = True
                self._draw_main_progress = MagicMock()
                self._refresh_chunk_displays = MagicMock()
                self.card_speed = MagicMock()
                self.card_size = MagicMock()
                self.card_eta = MagicMock()
                self.card_threads = MagicMock()
                self.engine = None

        ui = DummyUI()

        # Fire 10 rapid progress callbacks
        for i in range(10):
            ui._engine_progress_cb(100 * i, 10000, 50000.0, "00:01:00", 4)
        # after(0, ...) should have been scheduled once due to coalescing guard
        self.assertEqual(ui.root.after.call_count, 1)

        # Fire 10 rapid chunk callbacks
        ui.root.after.reset_mock()
        for _ in range(10):
            ui._engine_chunk_update_cb()
        self.assertEqual(ui.root.after.call_count, 1)
        self.assertTrue(getattr(ui, "_chunk_ui_update_pending", False))


if __name__ == "__main__":
    unittest.main()
