"""
Batch and multiple download candidates controller mixin for Smart Download (SD).
"""
import os
import threading
from typing import Dict, Any, List

from smart_download.utils.url_utils import derive_download_filename
from smart_download.utils.file_ops import resolve_categorized_path
from ..modals.candidates_modal import MultipleCandidatesModal


class BatchDownloadControllerMixin:
    """Handles multi-candidate download selection dialogs and batch download queueing."""

    def _show_multiple_candidates_dialog(self, source_url: str, candidates: List[Dict[str, Any]], page_title: str = ""):
        """Displays modern dark-themed modal for choosing among multiple download links."""
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, lambda: self._show_multiple_candidates_dialog(source_url, candidates, page_title))
            return

        if hasattr(self, "_close_fetching_toast") and callable(self._close_fetching_toast):
            self._close_fetching_toast()

        def _on_download_selected(selected: List[Dict[str, Any]]):
            if not selected:
                return
            if len(selected) == 1:
                cand = selected[0]
                dl_url = cand["url"]
                fn = cand.get("filename") or derive_download_filename(dl_url)
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                auto_cat = getattr(self, "auto_categorize_folders", True)
                dest = resolve_categorized_path(downloads_dir, fn, auto_categorize=auto_cat)
                if hasattr(self, "_show_download_confirmation_dialog"):
                    self._show_download_confirmation_dialog(dl_url, dest)
            else:
                self._queue_multiple_candidate_downloads(selected)

        def _on_download_all(all_cands: List[Dict[str, Any]]):
            self._queue_multiple_candidate_downloads(all_cands)

        theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
        modal = MultipleCandidatesModal(
            parent=self.root,
            source_url=source_url,
            candidates=candidates,
            page_title=page_title,
            theme=theme_dict,
            on_download_selected=_on_download_selected,
            on_download_all=_on_download_all,
            parent_app=self
        )
        self._candidates_modal = modal

    def _queue_multiple_candidate_downloads(self, items: List[Dict[str, Any]]):
        """Queues a list of candidate downloads, starting the first one if idle."""
        if not items:
            return
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        auto_cat = getattr(self, "auto_categorize_folders", True)
        try:
            max_conn = int(self.conn_var.get())
        except Exception:
            max_conn = 8
        try:
            kb_limit = float(self.entry_custom_speed.get().strip())
        except Exception:
            kb_limit = 0.0
        bytes_limit = kb_limit * 1024.0 if kb_limit > 0 else 0.0

        if hasattr(self, "log") and callable(self.log):
            self.log(f"[BATCH] Queuing {len(items)} download candidates...")
        for item in items:
            dl_url = item["url"]
            fn = item.get("filename") or derive_download_filename(dl_url)
            dest = resolve_categorized_path(downloads_dir, fn, auto_categorize=auto_cat)
            if hasattr(self, "queue_download"):
                self.queue_download(dl_url, dest, max_conn=max_conn, bytes_limit=bytes_limit)


__all__ = ["BatchDownloadControllerMixin"]
