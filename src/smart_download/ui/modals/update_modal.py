"""
AppUpdateModal: Dialog presenting GitHub Release updates with live download progress and installer launch.
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Dict, Any
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from ...config import get_resource_path, APP_VERSION
from ...locales.i18n import tr
from ..components.base_modal import SafeModalDialog
from ...services.updater_service import AppAutoUpdater
from ...services.youtube_service import format_filesize
from ...utils.tk_helpers import _detach_photo_tk

class AppUpdateModal(tk.Toplevel):
    """
    Sleek, non-blocking, dark-themed application update notification and installer download dialog.
    Displays the new version, release notes summary, live download progress bar, and a one-click
    [⬇ Update Now] button that downloads SmartDownload-Setup.exe and upgrades seamlessly.
    """

    def __init__(
        self,
        parent: tk.Widget,
        update_info: Dict[str, Any],
        theme: Optional[Dict[str, str]] = None,
        parent_app: Optional[Any] = None,
        updater: Optional[AppAutoUpdater] = None,
        on_log: Optional[Callable[[str], None]] = None,
        on_exit_app: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.parent_widget = parent
        self.update_info = update_info or {}
        self.parent_app = parent_app
        self.on_exit_app = on_exit_app
        self.updater = updater or AppAutoUpdater(
            on_log=on_log or getattr(parent_app, "log", None)
        )
        self._cancel_event = threading.Event()
        self._is_downloading = False

        # Grab-free modal (never blocks main thread or other windows)
        self.grab_set = lambda: None
        self.grab_set_global = lambda: None
        self.transient(parent)

        t = theme or {}
        self.c_bg = t.get("c_bg", "#0f172a")
        self.c_panel = t.get("c_panel", "#1e293b")
        self.c_panel_light = t.get("c_panel_light", "#334155")
        self.c_border = t.get("c_border", "#475569")
        self.c_accent = t.get("c_accent", "#38bdf8")
        self.c_accent_dark = t.get("c_accent_dark", "#0284c7")
        self.c_success = t.get("c_success", "#10b981")
        self.c_warning = t.get("c_warning", "#f59e0b")
        self.c_danger = t.get("c_danger", "#ef4444")
        self.c_text_bright = t.get("c_text_bright", "#f8fafc")
        self.c_text_muted = t.get("c_text_muted", "#94a3b8")
        self.c_input_bg = t.get("c_input_bg", "#090d16")

        latest_ver = self.update_info.get("latest_version", APP_VERSION)
        self.title(f"🚀 Update Available — Smart Download (SD) v{latest_ver}")
        self.configure(bg=self.c_bg)

        try:
            dpi = float(self.winfo_fpixels("1i"))
        except Exception:
            dpi = 96.0
        self.dpi_scale = max(1.0, dpi / 96.0)

        dlg_w = int(580 * self.dpi_scale)
        dlg_h = int(450 * self.dpi_scale)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - dlg_w) // 2)
        y = max(0, (sh - dlg_h) // 2)
        self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
        self.minsize(int(500 * self.dpi_scale), int(380 * self.dpi_scale))

        ico_path = get_resource_path("app_icon.ico")
        if os.path.isfile(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()

        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
        except Exception:
            pass

    def _build_ui(self):
        cur_ver = self.update_info.get("current_version", APP_VERSION)
        latest_ver = self.update_info.get("latest_version", APP_VERSION)
        rel_name = self.update_info.get("release_name") or f"Smart Download (SD) v{latest_ver}"
        rel_notes = self.update_info.get("release_notes") or "Bug fixes, extractor updates, and performance improvements."
        inst_size = int(self.update_info.get("installer_size") or 0)

        container = tk.Frame(self, bg=self.c_bg, padx=16, pady=14)
        container.pack(fill=tk.BOTH, expand=True)

        # Header
        lbl_title = tk.Label(
            container,
            text=f"🚀 NEW UPDATE AVAILABLE — v{latest_ver}",
            font=("Segoe UI", 11, "bold"),
            bg=self.c_bg,
            fg=self.c_accent,
            anchor="w"
        )
        lbl_title.pack(fill=tk.X)

        lbl_sub = tk.Label(
            container,
            text=rel_name,
            font=("Segoe UI", 9),
            bg=self.c_bg,
            fg=self.c_text_bright,
            anchor="w"
        )
        lbl_sub.pack(fill=tk.X, pady=(2, 8))

        # Version Badge Card
        badge_card = tk.Frame(
            container,
            bg=self.c_panel,
            padx=12,
            pady=8,
            highlightbackground=self.c_border,
            highlightthickness=1
        )
        badge_card.pack(fill=tk.X, pady=(0, 10))

        size_txt = f"  •  Size: {format_filesize(inst_size)}" if inst_size > 0 else ""
        ver_text = f"Installed: v{cur_ver}   ➔   New Release: v{latest_ver}{size_txt}"
        self.lbl_version_info = tk.Label(
            badge_card,
            text=ver_text,
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel,
            fg=self.c_success,
            anchor="w"
        )
        self.lbl_version_info.pack(fill=tk.X)

        # Release Notes Section
        lbl_notes_hdr = tk.Label(
            container,
            text="📋 Release Notes & Highlights:",
            font=("Segoe UI", 8, "bold"),
            bg=self.c_bg,
            fg=self.c_text_muted,
            anchor="w"
        )
        lbl_notes_hdr.pack(fill=tk.X, pady=(0, 4))

        notes_frame = tk.Frame(
            container,
            bg=self.c_input_bg,
            highlightbackground=self.c_border,
            highlightthickness=1
        )
        notes_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.txt_notes = tk.Text(
            notes_frame,
            bg=self.c_input_bg,
            fg=self.c_text_bright,
            font=("Segoe UI", 9),
            relief="flat",
            wrap="word",
            height=7,
            padx=8,
            pady=6
        )
        scroll_notes = ttk.Scrollbar(notes_frame, orient="vertical", command=self.txt_notes.yview)
        self.txt_notes.configure(yscrollcommand=scroll_notes.set)
        self.txt_notes.insert("1.0", rel_notes)
        self.txt_notes.configure(state="disabled")
        self.txt_notes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_notes.pack(side=tk.RIGHT, fill=tk.Y)

        # Progress Bar & Status
        prog_h = max(18, int(20 * self.dpi_scale))
        self.canvas_prog = tk.Canvas(container, height=prog_h, bg=self.c_input_bg, highlightthickness=0)
        self.canvas_prog.pack(fill=tk.X, pady=(0, 6))
        self._draw_progress(0.0)

        self.lbl_status = tk.Label(
            container,
            text="Click '⬇ Update Now' to download and install the update automatically.",
            font=("Segoe UI", 8),
            bg=self.c_bg,
            fg=self.c_text_muted,
            anchor="w"
        )
        self.lbl_status.pack(fill=tk.X, pady=(0, 10))

        # Action Buttons
        btn_row = tk.Frame(container, bg=self.c_bg)
        btn_row.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_update_now = tk.Button(
            btn_row,
            text="⬇ Update Now (تحديث الآن)",
            font=("Segoe UI", 9, "bold"),
            bg=self.c_success,
            fg="white",
            relief="flat",
            activebackground="#059669",
            cursor="hand2",
            padx=16,
            pady=5,
            command=self._start_update_download
        )
        self.btn_update_now.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_update = self.btn_update_now

        self.btn_later = tk.Button(
            btn_row,
            text="Later (لاحقاً)",
            font=("Segoe UI", 9),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_border,
            cursor="hand2",
            padx=14,
            pady=5,
            command=self._on_close
        )
        self.btn_later.pack(side=tk.LEFT)

    def _draw_progress(self, pct: float):
        try:
            if not self.winfo_exists():
                return
            self.canvas_prog.delete("all")
            w = self.canvas_prog.winfo_width()
            if w <= 1:
                w = int(540 * self.dpi_scale)
            h = self.canvas_prog.winfo_height() or max(18, int(20 * self.dpi_scale))
            self.canvas_prog.create_rectangle(0, 0, w, h, fill=self.c_input_bg, outline=self.c_border)
            fill_w = max(0.0, min(float(w), (pct / 100.0) * float(w)))
            if fill_w > 0:
                self.canvas_prog.create_rectangle(0, 0, fill_w, h, fill=self.c_accent_dark, outline="")
            self.canvas_prog.create_text(w // 2, h // 2, text=f"{pct:.1f}%", font=("Segoe UI", 8, "bold"), fill=self.c_text_bright)
        except Exception:
            pass

    def _start_update_download(self):
        if self._is_downloading:
            return
        installer_url = (
            self.update_info.get("installer_url")
            or self.update_info.get("download_url")
            or self.update_info.get("portable_url")
            or ""
        )
        if not installer_url:
            self.lbl_status.configure(text="❌ No installer download URL found in release assets.", fg=self.c_danger)
            return

        self._is_downloading = True
        self._cancel_event.clear()
        self.btn_update_now.configure(state="disabled", text="⏳ Downloading Update...")
        self.lbl_status.configure(text="Connecting to GitHub Releases...", fg=self.c_accent)

        def _prog_cb(downloaded: int, total: int):
            def _ui():
                if not self.winfo_exists():
                    return
                pct = (downloaded / total * 100.0) if total > 0 else 0.0
                self._draw_progress(pct)
                dl_mb = downloaded / (1024 * 1024)
                if total > 0:
                    tot_mb = total / (1024 * 1024)
                    self.lbl_status.configure(
                        text=f"Downloading update: {dl_mb:.1f} MB / {tot_mb:.1f} MB ({pct:.1f}%)",
                        fg=self.c_accent
                    )
                else:
                    self.lbl_status.configure(
                        text=f"Downloading update: {dl_mb:.1f} MB...",
                        fg=self.c_accent
                    )
            try:
                self.after(0, _ui)
            except Exception:
                pass

        def _worker():
            try:
                installer_path = self.updater.download_update(
                    download_url=installer_url,
                    progress_cb=_prog_cb,
                    cancel_event=self._cancel_event
                )

                def _on_done():
                    if not self.winfo_exists():
                        return
                    self._draw_progress(100.0)
                    self.lbl_status.configure(
                        text="✅ Download complete! Launching installer to upgrade...",
                        fg=self.c_success
                    )
                    exit_cb = self.on_exit_app or (getattr(self.parent_app, "exit_completely", None) if self.parent_app else None)
                    self.updater.apply_update(
                        installer_path=installer_path,
                        silent=True,
                        launch_after=True,
                        exit_callback=exit_cb
                    )
                    try:
                        self.destroy()
                    except Exception:
                        pass

                self.after(0, _on_done)
            except Exception as e:
                def _on_err():
                    self._is_downloading = False
                    if not self.winfo_exists():
                        return
                    self.btn_update_now.configure(state="normal", text="⬇ Update Now (تحديث الآن)")
                    self.lbl_status.configure(text=f"❌ Update failed: {e}", fg=self.c_danger)
                try:
                    self.after(0, _on_err)
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True, name="AppUpdateDownloadThread").start()

    def _on_close(self):
        self._cancel_event.set()
        try:
            self.destroy()
        except Exception:
            pass

