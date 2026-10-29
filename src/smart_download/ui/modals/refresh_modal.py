"""
RefreshLinkModal: Interactive dialog to renew expired temporary download URLs while preserving chunks.
"""
import os
import sys
import threading
import ssl
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Dict, Any
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from ...config import get_resource_path
from ...locales.i18n import tr
from ..components.base_modal import SafeModalDialog
from ...core.html_resolver import validate_refresh_url
from ...core.chunk import get_permissive_ssl_context
from ...utils.url_utils import derive_download_filename
from ...utils.clipboard import get_clipboard_text
from ...utils.tk_helpers import _detach_photo_tk

class RefreshLinkModal(tk.Toplevel):
    """
    Modern dark-themed TDM-style dialog for updating an expired or forbidden download link:
    - Displays current URL, file name, existing progress preserved, and input for the new URL.
    - Grab-free: strictly avoids grab_set() / grab_set_global() to prevent Win32 message pump traps.
    - High-DPI scaled, centered over parent, and focused.
    - Auto-detects valid URLs on clipboard for instant one-click or auto-pasting.
    - Asynchronously validates the candidate URL with HTTP HEAD/GET Range before committing.
    - Upon success, calls on_success(new_url, headers) to update TurboDownloadEngine and resume downloading.
    """
    def __init__(
        self,
        parent: Optional[tk.Tk],
        old_url: str = "",
        total_size: int = 0,
        downloaded_bytes: int = 0,
        filename: str = "",
        theme: Optional[Dict[str, str]] = None,
        on_success: Optional[Callable[[str, Optional[Dict[str, str]]], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        expected_ranges: bool = True,
        custom_headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(parent)
        self.old_url = str(old_url or "").strip()
        self.total_size = max(0, int(total_size or 0))
        self.downloaded_bytes = max(0, int(downloaded_bytes or 0))
        self.filename = str(filename or "").strip() or derive_download_filename(self.old_url)
        self.on_success = on_success
        self.on_cancel = on_cancel
        self.ssl_context = ssl_context or get_permissive_ssl_context()
        self.expected_ranges = expected_ranges
        self.custom_headers = dict(custom_headers or {})
        self.result_url: Optional[str] = None
        self._confirmed = False

        th = theme or {}
        self.c_bg = th.get("c_bg", "#0f172a")
        self.c_panel = th.get("c_panel", "#1e293b")
        self.c_panel_light = th.get("c_panel_light", "#334155")
        self.c_border = th.get("c_border", "#475569")
        self.c_text_bright = th.get("c_text_bright", "#f8fafc")
        self.c_text_muted = th.get("c_text_muted", "#94a3b8")
        self.c_accent = th.get("c_accent", "#38bdf8")
        self.c_accent_dark = th.get("c_accent_dark", "#0284c7")
        self.c_danger = th.get("c_danger", "#ef4444")
        self.c_success = th.get("c_success", "#10b981")
        self.c_warning = th.get("c_warning", "#f59e0b")
        self.c_input_bg = th.get("c_input_bg", "#0b1220")

        self.title(tr("refresh_modal_title", "↻ Refresh Download Address — Smart Download"))
        self.configure(bg=self.c_bg)

        if parent:
            try:
                self.transient(parent)
            except Exception:
                pass

        # Determine DPI scaling
        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        self.dpi_scale = max(1.0, dpi / 96.0)

        # Center on parent window
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        dlg_w = min(int(640 * self.dpi_scale), max(520, int(sw * 0.88)))
        dlg_h = min(int(440 * self.dpi_scale), max(360, int(sh * 0.80)))
        try:
            if parent and parent.winfo_exists():
                px = parent.winfo_x()
                py = parent.winfo_y()
                pw = parent.winfo_width() or dlg_w
                ph = parent.winfo_height() or dlg_h
            else:
                px, py, pw, ph = 100, 100, dlg_w, dlg_h
        except Exception:
            px, py, pw, ph = 100, 100, dlg_w, dlg_h

        x = max(0, px + (pw - dlg_w) // 2)
        y = max(0, py + (ph - dlg_h) // 2)
        self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
        self.minsize(min(480, dlg_w), min(320, dlg_h))

        # Icons
        ico_path = get_resource_path("app_icon.ico")
        png_path = get_resource_path("app_icon.png")
        if os.path.isfile(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass
        if os.path.isfile(png_path):
            try:
                from PIL import ImageTk
                self._modal_icon_photo = ImageTk.PhotoImage(file=png_path)
                self.iconphoto(True, self._modal_icon_photo)
            except Exception:
                pass

        # Elevate and focus
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self.after(250, lambda: self.attributes("-topmost", False) if self.winfo_exists() else None)
            self._idle_job = self.after_idle(lambda: (self.lift(), self.focus_force()) if self.winfo_exists() else None)
        except Exception:
            pass

        self.parent = parent
        self._pending_ui_action = None

        self._build_ui(dlg_w)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self._poll_pending_ui()

    def _poll_pending_ui(self):
        if getattr(self, "_pending_ui_action", None):
            self.process_pending_events()
        if not getattr(self, "_closing", False):
            try:
                if self.winfo_exists():
                    self._poll_job = self.after(30, self._poll_pending_ui)
            except Exception:
                pass

    def process_pending_events(self):
        """Processes any asynchronous worker callbacks, vital when running outside mainloop() in tests."""
        action = getattr(self, "_pending_ui_action", None)
        if action:
            self._pending_ui_action = None
            try:
                action()
            except Exception:
                pass

    def grab_set(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def grab_set_global(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def destroy(self):
        self._closing = True
        if getattr(self, "_idle_job", None):
            try:
                self.after_cancel(self._idle_job)
            except Exception:
                pass
            self._idle_job = None
        if hasattr(self, "_poll_job") and self._poll_job:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        if hasattr(self, "_modal_icon_photo"):
            _detach_photo_tk(self._modal_icon_photo)
            self._modal_icon_photo = None
        try:
            self.grab_release()
        except Exception:
            pass
        super().destroy()

    def _build_ui(self, dlg_w: int):
        container = tk.Frame(self, bg=self.c_bg, padx=16, pady=12)
        container.pack(fill=tk.BOTH, expand=True)

        # Header Banner
        header = tk.Frame(container, bg=self.c_bg)
        header.pack(fill=tk.X, pady=(0, 10))

        lbl_icon = tk.Label(header, text="↻", font=("Segoe UI", 20, "bold"), bg=self.c_bg, fg=self.c_accent)
        lbl_icon.pack(side=tk.LEFT, padx=(0, 10))

        title_box = tk.Frame(header, bg=self.c_bg)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        lbl_title = tk.Label(
            title_box,
            text=tr("refresh_modal_header", "Refresh Expired Download Address"),
            font=("Segoe UI", 11, "bold"),
            bg=self.c_bg,
            fg=self.c_text_bright,
            anchor="w"
        )
        lbl_title.pack(fill=tk.X)

        lbl_sub = tk.Label(
            title_box,
            text=tr("refresh_modal_sub", "Paste the new active link to continue downloading without losing your downloaded parts."),
            font=("Segoe UI", 8),
            bg=self.c_bg,
            fg=self.c_text_muted,
            anchor="w"
        )
        lbl_sub.pack(fill=tk.X)

        # Preserved State Card
        info_card = tk.Frame(
            container,
            bg=self.c_panel,
            padx=12,
            pady=8,
            relief="flat",
            highlightbackground=self.c_border,
            highlightthickness=1
        )
        info_card.pack(fill=tk.X, pady=(0, 10))

        # File row
        row_fn = tk.Frame(info_card, bg=self.c_panel)
        row_fn.pack(fill=tk.X, pady=2)
        tk.Label(row_fn, text=tr("refresh_modal_filename", "File Name:"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted, width=14, anchor="w").pack(side=tk.LEFT)
        tk.Label(row_fn, text=self.filename, font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_bright, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Progress preserved row
        row_prog = tk.Frame(info_card, bg=self.c_panel)
        row_prog.pack(fill=tk.X, pady=2)
        tk.Label(row_prog, text=tr("refresh_modal_preserved", "Preserved Data:"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted, width=14, anchor="w").pack(side=tk.LEFT)

        if self.total_size > 0:
            pct = min(100.0, (self.downloaded_bytes / self.total_size) * 100.0)
            prog_txt = f"{self.downloaded_bytes / (1024*1024):.2f} MB of {self.total_size / (1024*1024):.2f} MB ({pct:.1f}%) saved on disk"
        else:
            prog_txt = f"{self.downloaded_bytes / (1024*1024):.2f} MB downloaded"
        tk.Label(row_prog, text=f"🛡️ {prog_txt}", font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_success, anchor="w").pack(side=tk.LEFT)

        # Old URL row
        row_old = tk.Frame(info_card, bg=self.c_panel)
        row_old.pack(fill=tk.X, pady=(4, 2))
        tk.Label(row_old, text=tr("refresh_modal_old_addr", "Old Address:"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted, width=14, anchor="w").pack(side=tk.LEFT)

        entry_old = tk.Entry(row_old, font=("Consolas", 8), bg=self.c_input_bg, fg=self.c_text_muted, relief="flat")
        entry_old.insert(0, self.old_url)
        entry_old.configure(state="readonly")
        entry_old.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=1)

        # New URL Input Section
        input_card = tk.Frame(
            container,
            bg=self.c_panel,
            padx=12,
            pady=10,
            relief="flat",
            highlightbackground=self.c_border,
            highlightthickness=1
        )
        input_card.pack(fill=tk.X, pady=(0, 10))

        lbl_new = tk.Label(
            input_card,
            text=tr("refresh_modal_new_url", "New Download URL:"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel,
            fg=self.c_accent,
            anchor="w"
        )
        lbl_new.pack(fill=tk.X, pady=(0, 6))

        new_url_row = tk.Frame(input_card, bg=self.c_panel)
        new_url_row.pack(fill=tk.X)

        self.entry_new_url = tk.Entry(
            new_url_row,
            font=("Segoe UI", 9),
            bg=self.c_input_bg,
            fg=self.c_text_bright,
            insertbackground=self.c_accent,
            relief="flat"
        )
        self.entry_new_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)
        self.entry_new_url.bind("<Return>", lambda e: self._start_validation())
        self.entry_url = self.entry_new_url
        self._check_clipboard = self._check_clipboard_auto_fill

        btn_paste = tk.Button(
            new_url_row,
            text=tr("btn_paste", "📋 Paste"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_accent_dark,
            cursor="hand2",
            padx=8,
            pady=2,
            command=self._paste_clipboard
        )
        btn_paste.pack(side=tk.RIGHT)

        # Auto-detect valid candidate from clipboard
        self._check_clipboard_auto_fill()

        # Status Label Area
        self.lbl_status = tk.Label(
            container,
            text=tr("refresh_modal_status_idle", "Paste the new download link and click Validate & Resume."),
            font=("Segoe UI", 8),
            bg=self.c_bg,
            fg=self.c_text_muted,
            wraplength=max(400, dlg_w - 50),
            justify="left",
            anchor="w"
        )
        self.lbl_status.pack(fill=tk.X, pady=(2, 10))

        # Action Buttons
        btn_row = tk.Frame(container, bg=self.c_bg)
        btn_row.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_validate = tk.Button(
            btn_row,
            text=tr("refresh_modal_btn_validate", "↻ Validate & Resume"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_success,
            fg="white",
            relief="flat",
            activebackground="#059669",
            cursor="hand2",
            padx=14,
            pady=5,
            command=self._start_validation
        )
        self.btn_validate.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_cancel = tk.Button(
            btn_row,
            text=tr("refresh_modal_btn_cancel", "✕ Cancel"),
            font=("Segoe UI", 9),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_border,
            cursor="hand2",
            padx=12,
            pady=5,
            command=self._on_close
        )
        self.btn_cancel.pack(side=tk.LEFT)

    def _check_clipboard_auto_fill(self):
        """Auto-populates new URL entry if clipboard contains a valid download URL different from old."""
        try:
            clip = get_clipboard_text(self)
            if clip:
                clip = clip.strip()
                if (clip.startswith("http://") or clip.startswith("https://")) and clip != self.old_url:
                    self.entry_new_url.delete(0, tk.END)
                    self.entry_new_url.insert(0, clip)
                    self.entry_new_url.select_range(0, tk.END)
        except Exception:
            pass

    def _paste_clipboard(self):
        try:
            clip = get_clipboard_text(self)
            if clip:
                self.entry_new_url.delete(0, tk.END)
                self.entry_new_url.insert(0, clip.strip())
        except Exception:
            pass

    def _set_status(self, msg: str, is_error: bool = False, is_info: bool = False, is_success: bool = False):
        if not self.winfo_exists():
            return
        if is_error:
            col = self.c_danger
        elif is_success:
            col = self.c_success
        elif is_info:
            col = self.c_accent
        else:
            col = self.c_text_muted
        self.lbl_status.configure(text=msg, fg=col)

    def _start_validation(self):
        new_url = self.entry_new_url.get().strip()
        if not new_url:
            self._set_status("Please paste a valid HTTP or HTTPS download link.", is_error=True)
            return
        if not (new_url.startswith("http://") or new_url.startswith("https://")):
            self._set_status("Invalid URL scheme. Link must begin with http:// or https://", is_error=True)
            return

        self.btn_validate.configure(state="disabled", text=tr("refresh_modal_btn_validating", "⏳ Validating..."))
        self.btn_cancel.configure(state="disabled")
        self._set_status("Connecting to remote server and verifying byte ranges...", is_info=True)

        def _worker():
            is_valid, msg, remote_size, ranges_ok = validate_refresh_url(
                new_url=new_url,
                expected_size=self.total_size,
                check_range=self.expected_ranges,
                timeout=12.0,
                ssl_context=self.ssl_context,
                headers=self.custom_headers
            )
            def _ui_done():
                if not self.winfo_exists():
                    return
                if is_valid:
                    self._on_validation_success(new_url, remote_size)
                else:
                    self._on_validation_failure(msg)
            self._pending_ui_action = _ui_done
            try:
                self.after(0, _ui_done)
            except Exception:
                pass

        t = threading.Thread(target=_worker, daemon=True)
        self._validating_thread = t
        t.start()

    def _on_validation_success(self, new_url: str, remote_size: int):
        self._set_status(f"✅ Verified successfully! Remote size: {remote_size:,} bytes. Resuming...", is_success=True)
        self.result_url = new_url
        self._confirmed = True
        if self.on_success:
            try:
                self.on_success(new_url, self.custom_headers)
            except Exception as e:
                self._set_status(f"Error applying update: {e}", is_error=True)
                self.btn_validate.configure(state="normal", text=tr("refresh_modal_btn_validate", "↻ Validate & Resume"))
                self.btn_cancel.configure(state="normal")
                return
        self.destroy()

    def _on_validation_failure(self, err_msg: str):
        self.btn_validate.configure(state="normal", text=tr("refresh_modal_btn_validate", "↻ Validate & Resume"))
        self.btn_cancel.configure(state="normal")
        self._set_status(f"❌ {err_msg}", is_error=True)

    def _on_close(self):
        self._confirmed = False
        self.destroy()
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass


RefreshLinkDialog = RefreshLinkModal

