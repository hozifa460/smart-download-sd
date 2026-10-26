"""
Download history SQLite persistence and management.
"""
import os
import sqlite3
import time
import threading
import json
from typing import List, Dict, Any, Optional

from ..config import get_config_dir
from ..utils.url_utils import derive_download_filename
from ..utils.file_ops import get_file_category_and_icon

class DownloadHistoryManager:
    """Thread-safe persistent storage and query manager for completed, paused, and failed downloads."""

    def __init__(self, history_file: Optional[str] = None, max_entries: int = 500):
        self._lock = threading.RLock()
        self.max_entries = int(max_entries)
        if history_file:
            self.history_file = history_file
        else:
            self.history_file = os.path.join(get_config_dir(), "download_history.json")
        self._entries: List[Dict[str, Any]] = []
        self._load_entries()

    def _load_entries(self):
        with self._lock:
            if not os.path.isfile(self.history_file):
                self._entries = []
                return
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._entries = data
                    else:
                        self._entries = []
            except Exception:
                self._entries = []

    def _save_entries(self) -> bool:
        with self._lock:
            try:
                dir_path = os.path.dirname(os.path.abspath(self.history_file))
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)
                tmp_file = f"{self.history_file}.tmp_{os.getpid()}_{int(time.time() * 1000)}"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(self._entries, f, indent=2)
                os.replace(tmp_file, self.history_file)
                return True
            except Exception:
                try:
                    if 'tmp_file' in locals() and os.path.exists(tmp_file):
                        os.remove(tmp_file)
                except Exception:
                    pass
                try:
                    with open(self.history_file, "w", encoding="utf-8") as f:
                        json.dump(self._entries, f, indent=2)
                    return True
                except Exception:
                    return False

    def add_or_update_entry(
        self,
        url: str,
        file_path: str,
        size_bytes: int = 0,
        status: str = "Completed",
        elapsed_sec: float = 0.0
    ) -> Dict[str, Any]:
        with self._lock:
            norm_path = os.path.abspath(file_path) if file_path else ""
            norm_path_case = os.path.normcase(norm_path) if norm_path else ""
            raw_url = str(url or "").strip()
            filename = os.path.basename(norm_path) if norm_path else derive_download_filename(raw_url)
            if not filename:
                filename = "download.bin"

            category, icon = get_file_category_and_icon(filename or raw_url)
            if filename.lower().endswith(".bin"):
                category, icon = "General", "📥"

            try:
                calc_size = int(size_bytes or 0)
            except Exception:
                calc_size = 0
            if calc_size <= 0 and norm_path and os.path.isfile(norm_path):
                try:
                    calc_size = os.path.getsize(norm_path)
                except Exception:
                    calc_size = 0

            try:
                elapsed_val = float(elapsed_sec or 0.0)
            except Exception:
                elapsed_val = 0.0

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

            match_idx = -1
            matched_id = None
            old_entry = None
            for idx, entry in enumerate(self._entries):
                e_path = entry.get("file_path", "")
                e_url = entry.get("url", "")
                e_fn = entry.get("filename", "")
                e_status = str(entry.get("status", "")).strip()
                e_path_norm = os.path.normcase(os.path.abspath(e_path)) if e_path else ""

                if norm_path_case and e_path_norm and e_path_norm == norm_path_case:
                    # If existing entry is Completed, do not pop or replace it when a new download
                    # is starting, queued, or paused. Only update if the existing entry is incomplete.
                    if e_status in ("Completed", "مكتمل") and status in ("Queued", "In Progress", "Paused"):
                        continue
                    match_idx = idx
                    matched_id = entry.get("id")
                    old_entry = entry
                    break

                if raw_url and e_url == raw_url and filename and e_fn == filename:
                    if e_status not in ("Completed", "مكتمل") and (not norm_path_case or not e_path_norm or e_path_norm == norm_path_case):
                        match_idx = idx
                        matched_id = entry.get("id")
                        old_entry = entry
                        break


            if match_idx >= 0 and old_entry:
                self._entries.pop(match_idx)
                entry_id = matched_id or old_entry.get("id") or f"dl_{int(time.time() * 1000)}_{len(self._entries)}"
                final_size = calc_size if calc_size > 0 else old_entry.get("size_bytes", 0)
                final_elapsed = elapsed_val if elapsed_val > 0 else float(old_entry.get("elapsed_sec", 0.0))
                final_path = norm_path or old_entry.get("file_path", "")
                final_url = raw_url or old_entry.get("url", "")
            else:
                entry_id = f"dl_{int(time.time() * 1000)}_{len(self._entries)}"
                final_size = calc_size
                final_elapsed = elapsed_val
                final_path = norm_path
                final_url = raw_url

            record = {
                "id": entry_id,
                "filename": filename,
                "file_path": final_path,
                "url": final_url,
                "size_bytes": final_size,
                "category": category,
                "icon": icon,
                "status": status,
                "timestamp": timestamp,
                "elapsed_sec": final_elapsed,
            }
            self._entries.insert(0, record)
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[:self.max_entries]

            self._save_entries()
            return dict(record)

    def get_entries(self, category_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if not category_filter or category_filter.strip().lower() in ("all", "all categories", "كافة التصنيفات", "الكل", ""):
                return [dict(e) for e in self._entries]
            cat_clean = category_filter.strip().lower()
            cat_aliases = {
                "music": "audio",
                "audio": "audio",
                "صوتيات": "audio",
                "صوت": "audio",
                "video": "video",
                "videos": "video",
                "فيديو": "video",
                "مرئي": "video",
                "image": "images",
                "images": "images",
                "صور": "images",
                "صورة": "images",
                "document": "documents",
                "documents": "documents",
                "مستندات": "documents",
                "وثائق": "documents",
                "program": "programs",
                "programs": "programs",
                "برامج": "programs",
                "تطبيقات": "programs",
                "compressed": "compressed",
                "مضغوط": "compressed",
                "أرشيف": "compressed",
                "general": "general",
                "عام": "general",
            }
            target_cat = cat_aliases.get(cat_clean, cat_clean)
            res = []
            for e in self._entries:
                item_cat = str(e.get("category", "")).strip().lower()
                norm_item_cat = cat_aliases.get(item_cat, item_cat)
                if item_cat == cat_clean or norm_item_cat == target_cat:
                    res.append(dict(e))
            return res

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            str_id = str(entry_id)
            for e in self._entries:
                if str(e.get("id")) == str_id:
                    return dict(e)
            return None

    def remove_entry(self, entry_id: str, delete_file: bool = False) -> bool:
        with self._lock:
            str_id = str(entry_id)
            target = None
            for e in self._entries:
                if str(e.get("id")) == str_id:
                    target = e
                    break
            if not target:
                return False
            self._entries.remove(target)
            if delete_file:
                fp = target.get("file_path", "")
                if fp and os.path.isfile(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
            self._save_entries()
            return True

    def clear_history(self) -> bool:
        with self._lock:
            self._entries.clear()
            self._save_entries()
            return True

