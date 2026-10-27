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

        # Case 3: Audio tag with copy counter
        path3 = os.path.join(self.tmp_dir, "Podcast (2) [Audio].mp3")
        res3 = apply_media_filename_tags(path3, quality_label="1080p", ext="mp4")
        self.assertEqual(os.path.basename(res3), "Podcast [1080p].mp4")


if __name__ == "__main__":
    unittest.main()
