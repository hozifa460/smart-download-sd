"""
Unit tests verifying concurrent re-download path uniqueness,
history preservation, completion deduplication, and quality tag stripping.
"""
import os
import sys
import tempfile
import unittest

# Ensure src/ and repo root are in sys.path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from smart_download.utils.file_ops import (
    generate_unique_destination_path,
    apply_media_filename_tags,
)
from smart_download.core.history import DownloadHistoryManager


class TestConcurrentRedownloadAndTags(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.hist_file = os.path.join(self.tmp_dir, "test_hist.json")
        self.mgr = DownloadHistoryManager(history_file=self.hist_file)

    def tearDown(self):
        import shutil
        if os.path.isdir(self.tmp_dir):
            try:
                shutil.rmtree(self.tmp_dir)
            except Exception:
                pass

    def test_second_download_in_progress_assigns_unique_path_and_preserves_both(self):
        """
        Starting a second download of the same video while the first download is 'In Progress'
        assigns a unique (1) path and preserves BOTH entries in DownloadHistoryManager.
        """
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        dest1 = os.path.join(self.tmp_dir, "Rick Astley [1080p].mp4")

        # 1. First download starts as 'In Progress'
        self.mgr.add_or_update_entry(
            url=url,
            file_path=dest1,
            size_bytes=15000000,
            status="In Progress",
            elapsed_sec=0.0
        )
        self.assertEqual(len(self.mgr.get_entries()), 1)

        # 2. Get active/queued paths
        active_paths = self.mgr.get_active_or_queued_paths()
        self.assertIn(dest1, active_paths)

        # 3. User attempts to download same video again: generate_unique_destination_path must detect active path
        dest2 = generate_unique_destination_path(dest1, reserved_paths=active_paths)
        expected_dest2 = os.path.join(self.tmp_dir, "Rick Astley [1080p] (1).mp4")
        self.assertEqual(os.path.normcase(os.path.abspath(dest2)), os.path.normcase(os.path.abspath(expected_dest2)))

        # 4. Enqueue second download in history
        self.mgr.add_or_update_entry(
            url=url,
            file_path=dest2,
            size_bytes=15000000,
            status="Queued",
            elapsed_sec=0.0
        )

        # Both entries must be preserved in DownloadHistoryManager!
        entries = self.mgr.get_entries()
        self.assertEqual(len(entries), 2)
        paths = {os.path.normcase(e["file_path"]): e["status"] for e in entries}
        self.assertEqual(paths.get(os.path.normcase(dest1)), "In Progress")
        self.assertEqual(paths.get(os.path.normcase(dest2)), "Queued")

        # 5. When the second download later completes, both remain present
        self.mgr.add_or_update_entry(
            url=url,
            file_path=dest2,
            size_bytes=15000000,
            status="Completed",
            elapsed_sec=12.5
        )
        entries = self.mgr.get_entries()
        self.assertEqual(len(entries), 2)
        paths = {os.path.normcase(e["file_path"]): e["status"] for e in entries}
        self.assertEqual(paths.get(os.path.normcase(dest1)), "In Progress")
        self.assertEqual(paths.get(os.path.normcase(dest2)), "Completed")

    def test_completing_download_with_yt_modal_does_not_create_duplicates(self):
        """
        Completing a download where both yt_modal and download_controller completion callbacks fire
        does NOT create duplicate 'Completed' entries for the same file path.
        """
        url = "https://www.youtube.com/watch?v=xyz987"
        dest = os.path.join(self.tmp_dir, "Demo [720p].mp4")

        # Initial 'In Progress' entry
        self.mgr.add_or_update_entry(
            url=url,
            file_path=dest,
            size_bytes=5000000,
            status="In Progress",
            elapsed_sec=0.0
        )
        self.assertEqual(len(self.mgr.get_entries()), 1)

        # First completion hook (e.g. yt_modal.on_download_complete)
        self.mgr.add_or_update_entry(
            url=url,
            file_path=dest,
            size_bytes=5120000,
            status="Completed",
            elapsed_sec=4.2
        )
        self.assertEqual(len(self.mgr.get_entries()), 1)
        self.assertEqual(self.mgr.get_entries()[0]["status"], "Completed")

        # Second completion hook fired concurrently or immediately after (e.g. _engine_complete_cb)
        self.mgr.add_or_update_entry(
            url=url,
            file_path=dest,
            size_bytes=5120000,
            status="Completed",
            elapsed_sec=4.2
        )
        # MUST NOT create a duplicate entry!
        self.assertEqual(len(self.mgr.get_entries()), 1)
        self.assertEqual(self.mgr.get_entries()[0]["status"], "Completed")

    def test_apply_media_filename_tags_strips_counter_before_applying_quality(self):
        """
        apply_media_filename_tags strips trailing (1), (2) before appending [720p],
        so quality changes never produce 'Title (1) [720p].mp4' or 'Title (1) (1) [1080p].mp4'.
        """
        # Case 1: Switching quality on a file that had a (1) counter
        path1 = os.path.join(self.tmp_dir, "My Video (1).mp4")
        res1 = apply_media_filename_tags(path1, quality_label="720p (HD)")
        self.assertEqual(os.path.basename(res1), "My Video [720p].mp4")

        # Case 2: Switching quality on a file with older quality tag and (1) counter
        path2 = os.path.join(self.tmp_dir, "Documentary (1) [1080p].mp4")
        res2 = apply_media_filename_tags(path2, quality_label="4K (UHD)", is_sub_burned=True)
        self.assertEqual(os.path.basename(res2), "Documentary [4K] [Sub].mp4")

        # Case 4: Multiple repeating copy counters (1) (2)
        path4 = os.path.join(self.tmp_dir, "Podcast (1) (2) [Audio].mp3")
        res4 = apply_media_filename_tags(path4, quality_label="720p", ext="mp4")
        self.assertEqual(os.path.basename(res4), "Podcast [720p].mp4")

    def test_allow_resume_does_not_collide_with_candidate_parts(self):
        """
        When allow_resume_existing_parts=True, if dest_path already exists as a completed file,
        a generated candidate like (1) must NOT overwrite existing (1).sd_parts.
        """
        dest = os.path.join(self.tmp_dir, "archive.zip")
        with open(dest, "wb") as f:
            f.write(b"finished zip content")

        # Simulate existing parts for candidate (1)
        cand1_parts = os.path.join(self.tmp_dir, "archive (1).zip.sd_parts")
        os.makedirs(cand1_parts, exist_ok=True)

        # Generating unique path with allow_resume_existing_parts=True should skip candidate (1) and return (2)
        unique = generate_unique_destination_path(dest, allow_resume_existing_parts=True)
        self.assertEqual(os.path.basename(unique), "archive (2).zip")

    def test_enqueue_download_alias_and_queueing(self):
        """
        Verifies enqueue_download alias exists on DownloadControllerMixin
        and queues downloads with unique destination paths when engine is active.
        """
        from smart_download.ui.controllers.download_controller import DownloadControllerMixin
        from unittest.mock import MagicMock

        class MockApp(DownloadControllerMixin):
            def __init__(self, hist_mgr):
                self.history_manager = hist_mgr
                self.engine = MagicMock()
                self.engine.is_running = True
                self._download_queue = []
                self.log = MagicMock()
                self._refresh_history_table = MagicMock()

        app = MockApp(self.mgr)
        self.assertTrue(hasattr(app, "enqueue_download"))
        self.assertEqual(app.enqueue_download, app.queue_download)

        # Enqueue download while engine is running
        target = os.path.join(self.tmp_dir, "data.bin")
        app.enqueue_download("https://example.com/data.bin", target, max_conn=4, bytes_limit=1024.0)

        self.assertEqual(len(app._download_queue), 1)
        q_url, q_dest, q_conn, q_lim = app._download_queue[0]
        self.assertEqual(q_url, "https://example.com/data.bin")
        self.assertEqual(q_dest, target)
        self.assertEqual(q_conn, 4)
        self.assertEqual(q_lim, 1024.0)

    def test_queue_progression_after_stream_coordinator_completion(self):
        """
        Verifies queue progression when engine/coordinator finishes Download #1
        while Download #2 is queued (Download #2 transitions to 'In Progress' and is not re-queued).
        """
        from smart_download.ui.controllers.download_controller import DownloadControllerMixin
        from unittest.mock import MagicMock

        class MockApp(DownloadControllerMixin):
            def __init__(self, hist_mgr):
                self.history_manager = hist_mgr
                self.engine = MagicMock()
                self.engine.is_running = True
                self.engine._is_running = True
                self._download_queue = []
                self._active_download_url = "https://example.com/file1.zip"
                self.log = MagicMock()
                self._refresh_history_table = MagicMock()
                self.dispatch_to_main_thread = lambda f: f()
                self.btn_start = MagicMock()
                self.btn_pause = MagicMock()
                self.btn_cancel = MagicMock()
                self.status_label = MagicMock()
                self._draw_main_progress = MagicMock()
                self._refresh_chunk_displays = MagicMock()
                self.c_panel_light = "#334155"
                self.c_text_muted = "#94a3b8"
                self.root = MagicMock()
                self.root.winfo_exists.return_value = True
                self.root.after.side_effect = lambda ms, cb: cb()
                self.started_downloads = []

            def _start_download_with_engine(self, url, dest, max_conn=8, bytes_limit=0.0):
                self.started_downloads.append((url, dest, max_conn, bytes_limit))
                self.engine = MagicMock()
                self.engine.is_running = True
                self.engine._is_running = True
                self.history_manager.add_or_update_entry(
                    url=url, file_path=dest, size_bytes=0, status="In Progress"
                )

        app = MockApp(self.mgr)
        dest1 = os.path.join(self.tmp_dir, "file1.zip")
        self.mgr.add_or_update_entry(url="https://example.com/file1.zip", file_path=dest1, size_bytes=1000, status="In Progress")

        # Enqueue Download #2
        dest2 = os.path.join(self.tmp_dir, "file2.zip")
        app.enqueue_download("https://example.com/file2.zip", dest2, max_conn=4, bytes_limit=2048.0)
        self.assertEqual(len(app._download_queue), 1)

        # Now Download #1 completes, calling app._engine_complete_cb
        app._engine_complete_cb(dest1, 1000, 2.5, suppress_dialog=True)

        # 1. Download #2 was popped from queue and started
        self.assertEqual(len(app._download_queue), 0)
        self.assertEqual(len(app.started_downloads), 1)
        self.assertEqual(app.started_downloads[0][0], "https://example.com/file2.zip")
        self.assertEqual(app.started_downloads[0][1], dest2)

        # 2. In history manager, Download #2 is now 'In Progress'
        dest2_entry = [e for e in self.mgr.get_entries() if e["file_path"] == dest2][0]
        self.assertEqual(dest2_entry["status"], "In Progress")

    def test_queue_progression_with_stream_coordinator_queued_media_task(self):
        """
        Verifies queue progression when StreamDownloadCoordinator finishes Download #1
        while Download #2 is queued as a media stream task via _launch_stream_coordinator.
        Download #2 must transition from 'Queued' to 'In Progress' and NOT be re-queued.
        """
        from smart_download.ui.controllers.download_controller import DownloadControllerMixin
        from smart_download.ui.controllers.youtube_download_controller import YouTubeDownloadControllerMixin
        from unittest.mock import MagicMock, patch

        class MockMediaApp(DownloadControllerMixin, YouTubeDownloadControllerMixin):
            def __init__(self, hist_mgr):
                self.history_manager = hist_mgr
                self.engine = MagicMock()
                self.engine.is_running = True
                self.engine._is_running = True
                self._download_queue = []
                self._active_download_url = "https://youtube.com/watch?v=vid1"
                self.log = MagicMock()
                self._refresh_history_table = MagicMock()
                self.dispatch_to_main_thread = lambda f: f()
                self.btn_start = MagicMock()
                self.btn_pause = MagicMock()
                self.btn_cancel = MagicMock()
                self.entry_dest = MagicMock()
                self.entry_url = MagicMock()
                self.status_label = MagicMock()
                self._draw_main_progress = MagicMock()
                self._refresh_chunk_displays = MagicMock()
                self.c_panel_light = "#334155"
                self.c_text_muted = "#94a3b8"
                self.root = MagicMock()
                self.root.winfo_exists.return_value = True
                self.root.after.side_effect = lambda ms, cb: cb()

        app = MockMediaApp(self.mgr)
        dest1 = os.path.join(self.tmp_dir, "Video 1 [1080p].mp4")
        self.mgr.add_or_update_entry(url="https://youtube.com/watch?v=vid1", file_path=dest1, size_bytes=1000, status="In Progress")

        # Now queue Download #2 via _launch_stream_coordinator while Download #1 is running
        mock_info2 = MagicMock()
        mock_info2.webpage_url = "https://youtube.com/watch?v=vid2"
        mock_info2.video_size = 5000
        mock_info2.audio_size = 1000
        dest2 = os.path.join(self.tmp_dir, "Video 2 [1080p].mp4")

        with patch("smart_download.ui.controllers.youtube_download_controller.StreamDownloadCoordinator") as mock_coord_cls:
            mock_coord_instance = MagicMock()
            mock_coord_instance.is_running = True
            mock_coord_cls.return_value = mock_coord_instance

            app._launch_stream_coordinator(mock_info2, dest2, max_conn=8, bytes_limit=0.0)

            # Verifying Download #2 was queued, NOT started yet
            self.assertEqual(len(app._download_queue), 1)
            dest2_entry = [e for e in self.mgr.get_entries() if e["file_path"] == dest2][0]
            self.assertEqual(dest2_entry["status"], "Queued")
            self.assertFalse(mock_coord_instance.start.called)

            # Now Download #1 completes, triggering _engine_complete_cb
            app._engine_complete_cb(dest1, 1000, 3.0, suppress_dialog=True)

            # Verifying Download #2 was popped from queue and started
            self.assertEqual(len(app._download_queue), 0)
            self.assertTrue(mock_coord_instance.start.called)
            self.assertIs(app.engine, mock_coord_instance)

            # Verifying in history manager, Download #2 is now 'In Progress'
            dest2_entry_after = [e for e in self.mgr.get_entries() if e["file_path"] == dest2][0]
            self.assertEqual(dest2_entry_after["status"], "In Progress")

    def test_on_start_download_with_media_url_invokes_youtube_download_even_if_engine_busy(self):
        """
        Verifies that calling _on_start_download with a media URL while an engine is running
        routes to _start_youtube_download and does NOT bypass it to enqueue direct download.
        """
        from smart_download.ui.controllers.download_controller import DownloadControllerMixin
        from unittest.mock import MagicMock

        class MockApp(DownloadControllerMixin):
            def __init__(self, hist_mgr):
                self.history_manager = hist_mgr
                self.engine = MagicMock()
                self.engine.is_running = True
                self.engine._is_running = True
                self._download_queue = []
                self.log = MagicMock()
                self._refresh_history_table = MagicMock()
                self.entry_url = MagicMock()
                self.entry_url.get.return_value = "https://www.youtube.com/watch?v=media123"
                self.entry_dest = MagicMock()
                self.entry_dest.get.return_value = "C:\\Downloads\\video.mp4"
                self.cb_connections = MagicMock()
                self.cb_connections.get.return_value = "8"
                self.conn_var = MagicMock()
                self.conn_var.get.return_value = "8"
                self.speed_slider = MagicMock()
                self.speed_slider.get.return_value = 0
                self.entry_custom_speed = MagicMock()
                self.entry_custom_speed.get.return_value = ""
                self.called_yt = []
                self.called_enqueue = []

            def _start_youtube_download(self, url, dest, *args, **kwargs):
                self.called_yt.append((url, dest))

            def enqueue_download(self, url, dest, max_conn=8, bytes_limit=0.0):
                self.called_enqueue.append((url, dest))

        app = MockApp(self.mgr)
        app._on_start_download()

        self.assertEqual(len(app.called_yt), 1)
        self.assertEqual(app.called_yt[0][0], "https://www.youtube.com/watch?v=media123")
        self.assertEqual(len(app.called_enqueue), 0)

    def test_show_cached_quality_modal_isolates_format_options_and_unique_destination(self):
        """
        Verifies _show_cached_quality_modal clones VideoFormatOption instances and generates
        unique (1) destination when the same media option is opened concurrently.
        """
        from smart_download.ui.panels.media_options_bar import MediaOptionsBarMixin
        from smart_download.services.youtube_models import VideoFormatOption
        from unittest.mock import MagicMock, patch

        class MockWindow(MediaOptionsBarMixin):
            def __init__(self, hist_mgr, tmp_dir):
                self.history_manager = hist_mgr
                self.tmp_dir = tmp_dir
                self.log = MagicMock()
                self.root = MagicMock()
                self.winfo_viewable = MagicMock(return_value=True)
                self.wm_state = MagicMock(return_value="normal")
                self.created_modals = []

        win = MockWindow(self.mgr, self.tmp_dir)

        opt = VideoFormatOption(
            format_id="137",
            resolution_label="1080p",
            height=1080,
            ext="mp4",
            filesize_approx=10000000,
            video_url="https://googlevideo.com/vid",
            audio_url="https://googlevideo.com/aud"
        )
        dest1 = os.path.join(self.tmp_dir, "My Video [1080p].mp4")
        ctx = {
            "url": "https://www.youtube.com/watch?v=cached123",
            "title": "My Video",
            "info": {"title": "My Video", "duration": 120},
            "options": [opt],
            "default_dest": dest1
        }

        modal_instances = []
        def mock_modal(**kwargs):
            m = MagicMock()
            m.kwargs = kwargs
            modal_instances.append(m)
            return m

        with patch("smart_download.ui.panels.media_options_bar.QualitySelectionModal", side_effect=mock_modal):
            win._show_cached_quality_modal(ctx)
            self.assertEqual(len(modal_instances), 1)
            first_opts = modal_instances[0].kwargs["options"]
            self.assertIsNot(first_opts[0], opt)
            self.assertEqual(first_opts[0].resolution_label, "1080p")
            first_dest = modal_instances[0].kwargs["default_dest_path"]
            self.assertTrue(first_dest.endswith("My Video [1080p].mp4"))

            self.mgr.add_or_update_entry(
                url=ctx["url"],
                file_path=first_dest,
                size_bytes=10000000,
                status="In Progress"
            )

            win._show_cached_quality_modal(ctx)
            self.assertEqual(len(modal_instances), 2)
            second_opts = modal_instances[1].kwargs["options"]
            self.assertIsNot(second_opts[0], opt)
            self.assertIsNot(second_opts[0], first_opts[0])
            second_dest = modal_instances[1].kwargs["default_dest_path"]
            self.assertTrue(second_dest.endswith("My Video [1080p] (1).mp4"))

    def test_download_subtitle_as_srt_cookie_fallback_on_429(self):
        """
        Verifies download_subtitle_as_srt falls back to extracting browser cookies
        when direct fetch returns HTTP 429.
        """
        from smart_download.services.subtitle_processor import download_subtitle_as_srt
        from unittest.mock import MagicMock, patch

        sub_track = {
            "sub_id": "ar",
            "language": "ar",
            "url": "https://www.youtube.com/api/timedtext?v=test&lang=ar",
            "ext": "vtt"
        }
        video_file = os.path.join(self.tmp_dir, "test_video.mp4")
        with open(video_file, "wb") as f:
            f.write(b"mp4")

        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.content = b"WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nCookie Subtitle\n"

        def mock_requests_get(url, **kwargs):
            if kwargs.get("cookies") is not None:
                return mock_resp_200
            return mock_resp_429

        mock_cookiejar = MagicMock()

        with patch("requests.get", side_effect=mock_requests_get), \
             patch("smart_download.services.subtitle_processor.detect_installed_cookie_browsers", return_value=["chrome"]), \
             patch("yt_dlp.cookies.extract_cookies_from_browser", return_value=mock_cookiejar):
            srt_path = download_subtitle_as_srt(sub_track, video_file)
            self.assertIsNotNone(srt_path)
            self.assertTrue(os.path.isfile(srt_path))
            with open(srt_path, "r", encoding="utf-8-sig") as sf:
                content = sf.read()
            self.assertIn("Cookie Subtitle", content)
            self.assertIn("00:00:01,000 --> 00:00:03,000", content)


if __name__ == "__main__":
    unittest.main()
