"""
HistoryPanelMixin: Download history table, context menu, and action handlers.
"""
import os
import sys
import time
import threading
from typing import Optional, Dict, Any, List

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore

from ...locales.i18n import tr
from ...utils.file_ops import open_downloaded_file, open_containing_folder, generate_unique_destination_path
from ...services.youtube_service import format_filesize, is_media_url


class HistoryPanelMixin:
    """
    Mixin providing download history table display, context menu,
    and history item lifecycle actions.
    """

    def _build_history_context_menu(self):
        """Constructs right-click context menu for download history."""
        self.history_context_menu = tk.Menu(
            self.tree_history,
            tearoff=0,
            bg=self.c_panel,
            fg=self.c_text_bright,
            activebackground=self.c_accent_dark,
            activeforeground="white",
            relief="flat",
            bd=1
        )
        self.history_context_menu.add_command(
            label=tr("ctx_open_file", "↗ Open File"),
            command=self._history_open_selected_file
        )
        self.history_context_menu.add_command(
            label=tr("ctx_open_folder", "⋯ Open Containing Folder"),
            command=self._history_open_selected_folder
        )
        self.history_context_menu.add_separator()
        self.history_context_menu.add_command(
            label=tr("ctx_copy_url", "⎘ Copy URL"),
            command=self._history_copy_selected_url
        )
        self.history_context_menu.add_command(
            label=tr("ctx_resume_retry", "↻ Resume / Retry"),
            command=self._history_redownload_selected
        )
        self.history_context_menu.add_command(
            label=tr("ctx_redownload_quality", "⚙ Re-Download with Different Quality"),
            command=self._history_redownload_with_quality
        )
        self.history_context_menu.add_separator()
        self.history_context_menu.add_command(
            label=tr("ctx_remove_history", "✕ Remove from History"),
            command=self._history_remove_selected
        )

    def _show_history_context_menu(self, event):
        """Displays right-click context menu on history treeview."""
        self._build_history_context_menu()
        try:
            iid = self.tree_history.identify_row(event.y)
            if iid:
                self.tree_history.selection_set(iid)
                self.tree_history.focus(iid)
        except Exception:
            pass
        try:
            self.history_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.history_context_menu.grab_release()
            except Exception:
                pass

    def _refresh_history_table(self, force: bool = False):
        """Refreshes tree_history items according to selected filter."""
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
                try:
                    self.root.after(0, lambda: self._refresh_history_table(force))
                except Exception:
                    pass
            return

        if not hasattr(self, "tree_history") or not hasattr(self, "history_manager"):
            return
        cat_filter = "All Categories"
        if hasattr(self, "combo_history_filter"):
            cat_filter = self.combo_history_filter.get() or "All Categories"
        entries = self.history_manager.get_entries(category_filter=cat_filter)

        sig = (cat_filter, len(entries), tuple((e.get("id"), e.get("status"), e.get("size_bytes")) for e in entries[:25]))
        if not force and getattr(self, "_last_hist_sig", None) == sig:
            return
        self._last_hist_sig = sig

        cur_sel = self.tree_history.selection()
        selected_id = cur_sel[0] if cur_sel else None

        for item in self.tree_history.get_children():
            self.tree_history.delete(item)

        for idx, e in enumerate(entries):
            eid = str(e.get("id") or f"dl_{idx}_{int(time.time() * 1000)}")
            if self.tree_history.exists(eid):
                eid = f"{eid}_{idx}"
            cat_display = f"{e.get('icon', '')} {e.get('category', 'General')}".strip()
            fn = e.get("filename", "")
            size_bytes = e.get("size_bytes", 0)
            size_str = format_filesize(size_bytes) if size_bytes > 0 else "—"
            status = e.get("status", "Completed")
            date_str = e.get("timestamp", "")
            fp = e.get("file_path", "")
            self.tree_history.insert("", tk.END, iid=eid, values=(cat_display, fn, size_str, status, date_str, fp))

        if selected_id and self.tree_history.exists(selected_id):
            self.tree_history.selection_set(selected_id)
            self.tree_history.focus(selected_id)

    def _history_open_selected_file(self):
        sel = self.tree_history.selection()
        if not sel:
            return
        entry = self.history_manager.get_entry(sel[0])
        if entry and entry.get("file_path"):
            fp = entry["file_path"]
            if os.path.exists(fp):
                open_downloaded_file(fp)
            else:
                parts_dir = fp + ".sd_parts"
                status = str(entry.get("status", "")).strip()
                if os.path.isdir(parts_dir) or status in ("Paused", "In Progress", "Failed"):
                    self.ask_safe_yesno(
                        tr("dialog_resume_incomplete_title", "Resume Incomplete Download"),
                        tr("dialog_resume_incomplete_msg", "This file is paused or incomplete. Would you like to resume downloading now?"),
                        on_yes=self._history_redownload_selected
                    )
                else:
                    self.log(f"[HISTORY] File not found on disk: {fp}")
                    if hasattr(self, "show_safe_warning"):
                        msg = tr("dialog_not_found_msg", "The downloaded file does not exist at:\n{path}").format(path=fp)
                        self.show_safe_warning(tr("dialog_not_found_title", "File Not Found"), msg)

    def _history_open_selected_folder(self):
        sel = self.tree_history.selection()
        if not sel:
            return
        entry = self.history_manager.get_entry(sel[0])
        if entry and entry.get("file_path"):
            open_containing_folder(entry["file_path"])

    def _history_copy_selected_url(self):
        sel = self.tree_history.selection()
        if not sel:
            return
        entry = self.history_manager.get_entry(sel[0])
        if entry and entry.get("url"):
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(entry["url"])
                self.log(f"[HISTORY] Copied URL to clipboard: {entry['url']}")
            except Exception:
                pass

    def _redownload_different_quality(self):
        """Alias for re-downloading selected history item with different quality/settings."""
        self._history_redownload_with_quality()

    def _history_redownload_with_quality(self):
        """Re-downloads selected entry allowing quality and format selection."""
        self._history_redownload_selected(with_quality=True)

    def _history_redownload_selected(self, with_quality: bool = False):
        """Loads selected history entry into URL/Destination and triggers download or quality modal."""
        sel = self.tree_history.selection()
        if not sel:
            return
        entry_id = sel[0]
        entry = self.history_manager.get_entry(entry_id)
        if not entry:
            return
        url = entry.get("url", "").strip()
        file_path = entry.get("file_path", "").strip()
        if not url:
            return

        # Check if the stored URL is an expired googlevideo stream URL from an older session
        if "googlevideo.com" in url.lower():
            cached_ctx = self._get_cached_media_context(url) if hasattr(self, "_get_cached_media_context") else None
            recovered_url = None
            if cached_ctx and cached_ctx.get("url") and "googlevideo.com" not in cached_ctx["url"].lower():
                recovered_url = cached_ctx["url"]
            elif entry.get("webpage_url") and "googlevideo.com" not in entry["webpage_url"].lower():
                recovered_url = entry["webpage_url"]

            if recovered_url:
                url = recovered_url
                entry["url"] = recovered_url
            else:
                if hasattr(self, "show_error_dialog"):
                    self.show_error_dialog(
                        tr("err_expired_googlevideo_title", "Expired Video Stream Link"),
                        tr(
                            "err_expired_googlevideo_msg",
                            "This history entry contains an expired temporary stream URL from an older session.\n\nPlease enter the original YouTube/video link (e.g. https://www.youtube.com/watch?v=...) to redownload with different settings."
                        )
                    )
                elif hasattr(self, "log"):
                    self.log("[HISTORY] Cannot redownload expired googlevideo.com stream URL. Please provide original media URL.")
                return

        status = str(entry.get("status", "")).strip().lower()
        can_resume = (status in ("paused", "failed", "متوقف مؤقتاً", "فشل")) and not with_quality
        reserved = self.history_manager.get_active_or_queued_paths() if (hasattr(self, "history_manager") and self.history_manager) else None

        is_busy = bool(self.engine and getattr(self.engine, "is_running", False))

        if with_quality or is_media_url(url):
            clean_dest = file_path
            if file_path:
                d_dir, d_file = os.path.split(file_path)
                d_base, d_ext = os.path.splitext(d_file)
                import re
                d_clean_base = re.sub(r'\s*\(\d+\)$', '', d_base).strip()
                clean_dest = os.path.join(d_dir, f"{d_clean_base}{d_ext}")

            if not is_busy:
                if hasattr(self, "entry_url"):
                    self.entry_url.delete(0, tk.END)
                    self.entry_url.insert(0, url)
                if clean_dest and hasattr(self, "entry_dest"):
                    self.entry_dest.delete(0, tk.END)
                    self.entry_dest.insert(0, clean_dest)
                elif hasattr(self, "_on_url_change"):
                    self._on_url_change()
                if hasattr(self, "notebook"):
                    try:
                        self.notebook.select(0)
                    except Exception:
                        pass

            ctx = self._get_cached_media_context(url) if hasattr(self, "_get_cached_media_context") else None
            if ctx and ctx.get("options") and hasattr(self, "_show_cached_quality_modal"):
                self._show_cached_quality_modal(ctx, preferred_dest=clean_dest)
                return
            if hasattr(self, "_start_youtube_download"):
                self._start_youtube_download(url, clean_dest or file_path or (self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ""))
                return

        unique_dest = generate_unique_destination_path(file_path, allow_resume_existing_parts=can_resume, reserved_paths=reserved) if file_path else ""
        if hasattr(self, "entry_url"):
            self.entry_url.delete(0, tk.END)
            self.entry_url.insert(0, url)
        if unique_dest and hasattr(self, "entry_dest"):
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, unique_dest)
        elif hasattr(self, "_on_url_change"):
            self._on_url_change()
        if hasattr(self, "notebook"):
            try:
                self.notebook.select(0)
            except Exception:
                pass

        self._on_start_download()

    def _history_remove_selected(self, delete_file: bool = False):
        sel = self.tree_history.selection()
        if not sel:
            return
        for entry_id in sel:
            self.history_manager.remove_entry(entry_id, delete_file=delete_file)
        self._refresh_history_table()

    def _history_clear_all(self):
        self.history_manager.clear_history()
        self._refresh_history_table()
