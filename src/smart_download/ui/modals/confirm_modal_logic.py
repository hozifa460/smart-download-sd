"""
ConfirmModalLogicMixin: Background probing, link refreshing, and mini-engine download handlers.
"""
from __future__ import annotations

import os
import sys
import time
import threading
import urllib.parse
from typing import Optional, Callable, Dict, Any, Tuple

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception:
    tk = filedialog = messagebox = None  # type: ignore

from ...config import get_base_downloads_dir, set_setting
from ...locales.i18n import tr
from ...utils.url_utils import parse_speed_limit, derive_download_filename
from ...utils.file_ops import (
    CATEGORY_SUBFOLDERS, get_file_category_and_icon,
    open_downloaded_file, open_containing_folder, resolve_categorized_path,
)
from ...core.engine import TurboDownloadEngine
from ...core.history import DownloadHistoryManager
from ...services.youtube_service import extract_media_platform, sanitize_filename
from ...utils.tk_helpers import _detach_photo_tk


class ConfirmModalLogicMixin:
    """Mixin providing download confirmation modal logic, handlers, and mini-engine controls."""

    def get_max_connections(self) -> int:
        if hasattr(self, "combo_threads"):
            try:
                val = int(str(self.combo_threads.get()).split()[0])
                return max(1, min(val, 32))
            except Exception:
                pass
        return self.default_connections or 8

    def get_speed_limit_bytes(self) -> float:
        if hasattr(self, "combo_speed"):
            try:
                return parse_speed_limit(self.combo_speed.get())
            except Exception:
                pass
        return float(self.default_speed_limit or 0.0)

    def attach_engine(self, engine: Any):
        """Attaches an active download engine to this modal for controls and metrics."""
        self.engine = engine

    def show_progress_view(self):
        """Transitions modal interface into standalone compact download progress view."""
        self.is_in_progress_view = True
        self.title(f"Downloading: {self.file_name} — Smart Download")
        self.frame_confirmation.pack_forget()
        self.frame_progress.pack(fill=tk.BOTH, expand=True)

        self.lbl_prog_filename.configure(text=self.file_name)
        cat, icon = get_file_category_and_icon(self.file_name)
        self.lbl_prog_cat.configure(text=f"{icon}  {cat}")
        self.lbl_prog_threads.configure(text=f"Threads: {self.get_max_connections()} Max")

        # Compact size
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        prog_w = min(int(580 * self.dpi_scale), max(500, int(sw * 0.90)))
        prog_h = min(int(320 * self.dpi_scale), max(270, int(sh * 0.70)))
        try:
            cur_x = self.winfo_x()
            cur_y = self.winfo_y()
            if 0 <= cur_x <= 1 and 0 <= cur_y <= 1:
                cur_x = max(0, (sw - prog_w) // 2)
                cur_y = max(0, (sh - prog_h) // 2)
        except Exception:
            cur_x = max(0, (sw - prog_w) // 2)
            cur_y = max(0, (sh - prog_h) // 2)
        pos_x = f"+{int(cur_x)}" if int(cur_x) >= 0 else f"{int(cur_x)}"
        pos_y = f"+{int(cur_y)}" if int(cur_y) >= 0 else f"{int(cur_y)}"
        self.geometry(f"{prog_w}x{prog_h}{pos_x}{pos_y}")
        self._draw_modal_progress(0.0)

    def _draw_modal_progress(self, pct: float):
        try:
            self._last_pct = float(pct)
            if not hasattr(self, "canvas_prog") or not self.canvas_prog.winfo_exists():
                return
            self.canvas_prog.delete("all")
            w = self.canvas_prog.winfo_width()
            if w <= 1:
                w = int(500 * self.dpi_scale)
            h = self.canvas_prog.winfo_height() or int(24 * self.dpi_scale)

            # Background track
            self.canvas_prog.create_rectangle(0, 0, w, h, fill=self.c_input_bg, outline=self.c_border)

            # Progress fill
            fill_w = max(0.0, min(float(w), (pct / 100.0) * float(w)))
            if fill_w > 0:
                fill_color = self.c_success if pct >= 100.0 else self.c_accent_dark
                line_color = "#34d399" if pct >= 100.0 else self.c_accent
                self.canvas_prog.create_rectangle(0, 0, fill_w, h, fill=fill_color, outline="")
                self.canvas_prog.create_line(0, 1, fill_w, 1, fill=line_color)

            # Percentage text overlay
            text_color = "white" if fill_w > (w * 0.45) else self.c_text_bright
            self.canvas_prog.create_text(w // 2, h // 2, text=f"{pct:.1f}%", font=("Segoe UI", 9, "bold"), fill=text_color)
        except Exception:
            pass

    def update_progress(self, downloaded: int, total: int, speed: float, eta: str, active_chunks: int = 1):
        """Thread-safe update of live download progress bar, speed, size, and ETA."""
        if threading.current_thread() != threading.main_thread():
            try:
                if self.winfo_exists():
                    self.after(0, lambda: self.update_progress(downloaded, total, speed, eta, active_chunks))
            except Exception:
                pass
            return

        pct = (downloaded / total * 100.0) if total > 0 else 0.0
        self._draw_modal_progress(pct)

        # Format speed
        if speed >= 1024 * 1024:
            speed_str = f"{speed / (1024*1024):.2f} MB/s"
        elif speed >= 1024:
            speed_str = f"{speed / 1024:.1f} KB/s"
        else:
            speed_str = f"{int(speed)} B/s"

        # Format sizes
        def _fmt(b):
            if b >= 1024 * 1024 * 1024:
                return f"{b / (1024**3):.2f} GB"
            if b >= 1024 * 1024:
                return f"{b / (1024**2):.1f} MB"
            if b >= 1024:
                return f"{b / 1024:.1f} KB"
            return f"{b} B"

        if total > 0:
            size_str = f"Transferred: {_fmt(downloaded)} / {_fmt(total)} ({pct:.1f}%)"
        else:
            size_str = f"Transferred: {_fmt(downloaded)} (Streaming...)"

        try:
            self.lbl_prog_size.configure(text=size_str)
            self.lbl_prog_speed.configure(text=f"Speed: {speed_str}")
            self.lbl_prog_eta.configure(text=f"Time Left: {eta}")
            self.lbl_prog_threads.configure(text=f"Threads: {active_chunks} Active")
            if not (self.engine and getattr(self.engine, "is_paused", False)):
                self.lbl_status.configure(text=tr("modal_status_downloading", "Status: Downloading..."), fg=self.c_accent)
        except Exception:
            pass

    def on_download_complete(self, dest_path: str, total_bytes: int, elapsed: float):
        """Thread-safe transition to completion view with Open File, Open Folder, and Close buttons."""
        if threading.current_thread() != threading.main_thread():
            try:
                if self.winfo_exists():
                    self.after(0, lambda: self.on_download_complete(dest_path, total_bytes, elapsed))
            except Exception:
                pass
            return

        self.dest_path = dest_path
        self.is_completed = True
        self._draw_modal_progress(100.0)
        try:
            self.lbl_status.configure(text=tr("modal_status_complete", "✅ Download Complete!"), fg=self.c_success)

            def _fmt(b):
                if b >= 1024 * 1024 * 1024:
                    return f"{b / (1024**3):.2f} GB"
                if b >= 1024 * 1024:
                    return f"{b / (1024**2):.1f} MB"
                if b >= 1024:
                    return f"{b / 1024:.1f} KB"
                return f"{b} B"

            avg_speed = (total_bytes / elapsed) if elapsed > 0 else 0
            if avg_speed >= 1024 * 1024:
                avg_str = f"{avg_speed / (1024*1024):.2f} MB/s"
            else:
                avg_str = f"{avg_speed / 1024:.1f} KB/s"

            self.lbl_prog_size.configure(text=f"Total: {_fmt(total_bytes)} in {elapsed:.1f}s")
            self.lbl_prog_speed.configure(text=f"Avg Speed: {avg_str}")
            self.lbl_prog_eta.configure(text="Time Left: 00:00:00")

            # Swap buttons to completion action buttons
            self.btn_pause_resume.pack_forget()
            self.btn_cancel_prog.pack_forget()
            self.btn_open_app_prog.pack_forget()

            self.btn_close_prog.pack(side=tk.RIGHT, padx=(6, 0))
            self.btn_open_folder.pack(side=tk.RIGHT, padx=(6, 0))
            self.btn_open_file.pack(side=tk.RIGHT)
        except Exception:
            pass

        try:
            hm = getattr(self, "history_manager", None)
            if not hm and self.parent_app:
                hm = getattr(self.parent_app, "history_manager", None)
            if not hm:
                hm = DownloadHistoryManager()
            hm.add_or_update_entry(
                url=self.url,
                file_path=dest_path,
                size_bytes=total_bytes,
                status="Completed",
                elapsed_sec=elapsed
            )
            if self.parent_app and hasattr(self.parent_app, "_refresh_history_table"):
                self.parent_app._refresh_history_table()
        except Exception:
            pass

    def on_download_error(self, err_msg: str):
        """Thread-safe display of download failure message."""
        if threading.current_thread() != threading.main_thread():
            try:
                if self.winfo_exists():
                    self.after(0, lambda: self.on_download_error(err_msg))
            except Exception:
                pass
            return
        try:
            self.lbl_status.configure(text=f"❌ Error: {err_msg}", fg=self.c_danger)
            self.btn_pause_resume.configure(state="disabled")
        except Exception:
            pass

        try:
            hm = getattr(self, "history_manager", None)
            if not hm and self.parent_app:
                hm = getattr(self.parent_app, "history_manager", None)
            if not hm:
                hm = DownloadHistoryManager()
            hm.add_or_update_entry(
                url=self.url,
                file_path=self.dest_path or (self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ""),
                size_bytes=0,
                status="Failed",
                elapsed_sec=0.0
            )
            if self.parent_app and hasattr(self.parent_app, "_refresh_history_table"):
                self.parent_app._refresh_history_table()
        except Exception:
            pass

    def _on_dest_key_release(self, event=None):
        cur = self.entry_dest.get().strip()
        if cur:
            fn = os.path.basename(cur)
            if hasattr(self, "lbl_filename_val"):
                self.lbl_filename_val.configure(text=fn)
            cat, icon = get_file_category_and_icon(fn)
            if hasattr(self, "lbl_category_val"):
                self.lbl_category_val.configure(text=f"{icon}  {cat}")

    def _on_browse(self):
        cur = self.entry_dest.get().strip()
        base_dl = getattr(self.parent_app, "_get_base_downloads_dir", get_base_downloads_dir)()
        init_dir = os.path.dirname(cur) if cur else base_dl
        init_file = os.path.basename(cur) if cur else (self.file_name or "download.bin")
        if not os.path.isdir(init_dir): init_dir = base_dl
        chosen = filedialog.asksaveasfilename(parent=self, title="Select Destination", initialdir=init_dir, initialfile=init_file)
        if chosen:
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, chosen)
            fn = os.path.basename(chosen)
            if hasattr(self, "lbl_filename_val"): self.lbl_filename_val.configure(text=fn)
            cat, icon = get_file_category_and_icon(fn)
            if hasattr(self, "lbl_category_val"): self.lbl_category_val.configure(text=f"{icon}  {cat}")
            try:
                cd = os.path.dirname(os.path.abspath(chosen))
                if getattr(self.parent_app, "auto_categorize_folders", True) and os.path.basename(cd).lower() in {s.lower() for s in CATEGORY_SUBFOLDERS.values()}:
                    cd = os.path.dirname(cd)
                set_setting("last_download_dir", cd)
            except Exception: pass

    def _call_on_confirm(self, dest: str, max_conn: int = 8, speed_limit: float = 0.0):
        if not self.on_confirm:
            return
        try:
            import inspect
            sig = inspect.signature(self.on_confirm)
            if len(sig.parameters) == 1:
                self.on_confirm(dest)
            else:
                self.on_confirm(dest, max_conn, speed_limit)
        except Exception:
            try:
                self.on_confirm(dest, max_conn, speed_limit)
            except TypeError:
                try:
                    self.on_confirm(dest)
                except Exception:
                    pass

    def _on_start_in_window(self):
        """Action 1: Starts download inside this window, keeping main window hidden."""
        final_dest = self.entry_dest.get().strip() or self.dest_path
        self.dest_path = final_dest
        self.file_name = os.path.basename(final_dest)
        conn_count = self.get_max_connections()
        speed_limit = self.get_speed_limit_bytes()
        self._confirmed = True
        self.show_progress_view()

        if self.on_start_in_window:
            try:
                self.on_start_in_window(final_dest, conn_count, speed_limit, self)
            except Exception:
                pass
        elif self.on_confirm:
            self._call_on_confirm(final_dest, conn_count, speed_limit)
        else:
            if not self.engine:
                self.engine = TurboDownloadEngine(
                    url=self.url,
                    destination_path=final_dest,
                    max_connections=conn_count,
                    rate_limit_bytes_per_sec=speed_limit,
                    on_progress=self.update_progress,
                    on_complete=self.on_download_complete,
                    on_error=self.on_download_error
                )
                self.engine.start()

    def _on_open_in_main(self):
        """Action 2: Restores main application window, populates task, and closes modal."""
        final_dest = self.entry_dest.get().strip() or self.dest_path
        conn_count = self.get_max_connections()
        speed_limit = self.get_speed_limit_bytes()
        self._confirmed = True

        is_running_now = self.is_in_progress_view or bool(self.engine and getattr(self.engine, "is_running", False))

        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

        if is_running_now:
            # Transfer already active in background engine. Do NOT restart or wipe!
            if self.parent_app:
                try:
                    self.parent_app.restore_window()
                    if hasattr(self.parent_app, "root") and self.parent_app.root:
                        try:
                            self.parent_app.root.lift()
                            self.parent_app.root.focus_force()
                        except Exception:
                            pass
                    # Sync buttons to active engine state
                    if hasattr(self.parent_app, "btn_pause") and self.engine:
                        if getattr(self.engine, "is_paused", False):
                            self.parent_app.btn_pause.configure(text=tr("btn_resume", "▶ Resume"), bg=getattr(self.parent_app, "c_warning", "#f59e0b"), state="normal")
                        else:
                            self.parent_app.btn_pause.configure(text=tr("btn_pause", "|| Pause"), bg=getattr(self.parent_app, "c_panel_light", "#334155"), state="normal")
                    if hasattr(self.parent_app, "btn_cancel"):
                        self.parent_app.btn_cancel.configure(state="normal")
                    if hasattr(self.parent_app, "btn_start"):
                        self.parent_app.btn_start.configure(state="disabled")
                    self.parent_app.log(f"[GUI] Active download transferred to main window: {self.file_name}")
                except Exception:
                    pass
            elif self.master and hasattr(self.master, "restore_window"):
                try:
                    self.master.restore_window()
                except Exception:
                    pass
            return

        if self.on_open_in_main:
            try:
                self.on_open_in_main(final_dest, conn_count, speed_limit)
            except Exception:
                pass
        elif self.parent_app:
            try:
                self.parent_app.restore_window()
                p = self.parent_app
                p.entry_url.delete(0, tk.END); p.entry_url.insert(0, self.url)
                p.entry_dest.delete(0, tk.END); p.entry_dest.insert(0, final_dest)
                try: p.conn_var.set(str(conn_count))
                except Exception: pass
                if speed_limit > 0:
                    try:
                        p.entry_custom_speed.delete(0, tk.END)
                        p.entry_custom_speed.insert(0, str(int(speed_limit / 1024.0)))
                    except Exception: pass
                if hasattr(p, "btn_start"): p.btn_start.configure(state="normal")
                if hasattr(p, "btn_pause"): p.btn_pause.configure(state="disabled")
                if hasattr(p, "btn_cancel"): p.btn_cancel.configure(state="disabled")
                if hasattr(p, "card_size"): p.card_size.configure(text=tr("status_ready", "Ready"))
            except Exception:
                pass
        elif self.master:
            try:
                if hasattr(self.master, "restore_window"):
                    self.master.restore_window()
                elif hasattr(self.master, "deiconify"):
                    self.master.deiconify()
            except Exception:
                pass

    def _on_start(self):
        """Default start handler for Enter key and backward compatibility."""
        if self.on_start_in_window:
            self._on_start_in_window()
        else:
            final_dest = self.entry_dest.get().strip() or self.dest_path
            self.dest_path = final_dest
            conn_count = self.get_max_connections()
            speed_limit = self.get_speed_limit_bytes()
            self._confirmed = True
            try:
                self.grab_release()
            except Exception:
                pass
            if self.on_confirm:
                self._call_on_confirm(final_dest, conn_count, speed_limit)
            try:
                self.destroy()
            except Exception:
                pass

    def _on_pause_resume(self):
        if not self.engine:
            return
        if getattr(self.engine, "is_paused", False):
            try:
                self.engine.resume()
            except Exception:
                pass
            self.btn_pause_resume.configure(text=tr("btn_pause", "|| Pause"), bg=self.c_panel_light)
            self.lbl_status.configure(text=f"{tr('col_chunk_status', 'Status')}: {tr('status_in_progress', 'Downloading...')}", fg=self.c_accent)
            if self.parent_app and hasattr(self.parent_app, "btn_pause"):
                try:
                    self.parent_app.btn_pause.configure(text=tr("btn_pause", "|| Pause"), bg=getattr(self.parent_app, "c_panel_light", "#334155"))
                except Exception:
                    pass
        else:
            try:
                self.engine.pause()
            except Exception:
                pass
            self.btn_pause_resume.configure(text=tr("btn_resume", "▶ Resume"), bg=self.c_success)
            self.lbl_status.configure(text=f"{tr('col_chunk_status', 'Status')}: {tr('status_paused', 'Paused')}", fg=self.c_warning)
            if self.parent_app and hasattr(self.parent_app, "btn_pause"):
                try:
                    self.parent_app.btn_pause.configure(text=tr("btn_resume", "▶ Resume"), bg=getattr(self.parent_app, "c_warning", "#f59e0b"))
                except Exception:
                    pass

    def _on_open_file(self):
        open_downloaded_file(self.dest_path)

    def _on_open_folder(self):
        open_containing_folder(self.dest_path)

    def grab_set(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def grab_set_global(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def destroy(self):
        try: self.withdraw()
        except Exception: pass
        for job_attr in ("_idle_job", "_topmost_job"):
            job = getattr(self, job_attr, None)
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                setattr(self, job_attr, None)
        if hasattr(self, "_modal_icon_photo"):
            _detach_photo_tk(self._modal_icon_photo)
            self._modal_icon_photo = None
        try:
            self.grab_release()
        except Exception:
            pass
        if self.parent_app and getattr(self.parent_app, "_confirm_modal", None) is self:
            self.parent_app._confirm_modal = None
        super().destroy()

    def _on_close(self):
        """Action 3: Clean cancellation without starting download."""
        self._confirmed = False
        was_running = False
        if hasattr(self, "engine") and self.engine:
            was_running = getattr(self.engine, "is_running", False)
            try:
                self.engine.cancel()
            except Exception:
                pass

        if self.parent_app:
            try:
                if hasattr(self.parent_app, "clear_last_clipboard_url"):
                    self.parent_app.clear_last_clipboard_url()
                if getattr(self.parent_app, "_confirm_modal", None) is self:
                    self.parent_app._confirm_modal = None
                if was_running:
                    self.parent_app.engine = None
                    self.parent_app.btn_start.configure(state="normal")
                    self.parent_app.btn_pause.configure(state="disabled", text=tr("btn_pause", "|| Pause"))
                    self.parent_app.btn_cancel.configure(state="disabled")
                    self.parent_app.card_size.configure(text=tr("status_cancelled", "Cancelled"))
                    self.parent_app.log(f"[CLIPBOARD] Standalone download cancelled: {self.file_name}")
            except Exception:
                pass

        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass


