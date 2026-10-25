"""
Inputs and speed limiter panel mixin for Smart Download (SD).
"""
import os
try:
    import tkinter as tk
    from tkinter import ttk, filedialog
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore
    filedialog = None  # type: ignore

from smart_download.i18n import tr
from smart_download.utils import CATEGORY_SUBFOLDERS, resolve_categorized_path, derive_download_filename
from smart_download.ui.components.tooltip import ToolTip


class InputsPanelMixin:
    """Builds and manages the URL/destination inputs card and speed limiter controls card."""

    def _build_inputs_card(self, parent):
        """URL & File Destination inputs."""
        card = tk.Frame(parent, bg=self.c_panel, padx=14, pady=10, relief="flat", highlightbackground=self.c_border, highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 10))

        # URL Row
        url_row = tk.Frame(card, bg=self.c_panel)
        url_row.pack(fill=tk.X, pady=2)

        self.lbl_url = tk.Label(url_row, text=tr("lbl_url"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=13, anchor="w")
        self.lbl_url.pack(side=tk.LEFT)

        default_url = "https://speed.cloudflare.com/__down?bytes=50000000"  # 50MB benchmark file
        self.entry_url = tk.Entry(url_row, font=("Segoe UI", 9), bg=self.c_input_bg, fg=self.c_text_bright, insertbackground=self.c_accent, relief="flat")
        self.entry_url.insert(0, default_url)
        self.entry_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8), ipady=3)
        self.entry_url.bind("<KeyRelease>", lambda e: self._on_url_change())

        self.btn_paste = tk.Button(url_row, text=tr("btn_paste"), font=("Segoe UI", 8), bg=self.c_panel_light, fg=self.c_text_bright, relief="flat", activebackground=self.c_accent_dark, cursor="hand2", command=self._paste_url)
        self.btn_paste.pack(side=tk.RIGHT)

        self.btn_refresh_url = tk.Button(url_row, text=tr("btn_refresh_url"), font=("Segoe UI", 8), bg=self.c_panel_light, fg=self.c_accent, relief="flat", activebackground=self.c_accent_dark, cursor="hand2", command=self._open_refresh_link_dialog)
        self.btn_refresh_url.pack(side=tk.RIGHT, padx=(0, 6))

        # Destination Row
        dest_row = tk.Frame(card, bg=self.c_panel)
        dest_row.pack(fill=tk.X, pady=(6, 2))

        self.lbl_dest = tk.Label(dest_row, text=tr("lbl_dest"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=13, anchor="w")
        self.lbl_dest.pack(side=tk.LEFT)

        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        default_fn = "cloudflare_50mb.bin"
        if getattr(self, "auto_categorize_folders", True):
            default_dest = resolve_categorized_path(downloads_dir, default_fn, auto_categorize=True)
        else:
            default_dest = os.path.join(downloads_dir, default_fn)
        self.entry_dest = tk.Entry(dest_row, font=("Segoe UI", 9), bg=self.c_input_bg, fg=self.c_text_bright, insertbackground=self.c_accent, relief="flat")
        self.entry_dest.insert(0, default_dest)
        self.entry_dest.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8), ipady=3)

        self.btn_browse = tk.Button(dest_row, text=tr("btn_browse"), font=("Segoe UI", 8), bg=self.c_panel_light, fg=self.c_text_bright, relief="flat", activebackground=self.c_accent_dark, cursor="hand2", command=self._browse_destination)
        self.btn_browse.pack(side=tk.RIGHT)

    def _paste_url(self):
        try:
            clipboard = self.root.clipboard_get()
            if clipboard:
                self.entry_url.delete(0, tk.END)
                self.entry_url.insert(0, clipboard.strip())
                self._on_url_change()
        except Exception:
            pass

    def _browse_destination(self):
        path = filedialog.asksaveasfilename(
            title="Select Destination File",
            initialdir=os.path.dirname(self.entry_dest.get()) or os.path.expanduser("~"),
            initialfile=os.path.basename(self.entry_dest.get()) or "download.bin"
        )
        if path:
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, path)

    def _is_downloads_or_category_subfolder(self, dest_dir: str, downloads_dir: str) -> bool:
        """Checks if dest_dir is either the base downloads_dir or one of its category subfolders."""
        if not dest_dir or not downloads_dir:
            return False
        norm_dest = os.path.normcase(os.path.abspath(dest_dir))
        norm_dl = os.path.normcase(os.path.abspath(downloads_dir))
        if norm_dest == norm_dl:
            return True
        if os.path.dirname(norm_dest) == norm_dl:
            base = os.path.basename(norm_dest)
            subfolders_lower = {s.lower() for s in CATEGORY_SUBFOLDERS.values()}
            if base in subfolders_lower:
                return True
        return False

    def _on_url_change(self, *args):
        """Updates default destination path based on the current URL if not actively transferring."""
        if hasattr(self, "engine") and self.engine and getattr(self.engine, "is_running", False):
            return
        if not hasattr(self, "entry_url") or not hasattr(self, "entry_dest"):
            return
        url = self.entry_url.get().strip()
        if not url:
            return
        fn = derive_download_filename(url)
        cur_dest = self.entry_dest.get().strip()
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        dest_dir = os.path.dirname(cur_dest) if cur_dest else downloads_dir
        if not os.path.isdir(dest_dir):
            dest_dir = downloads_dir
        if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
            new_dest = resolve_categorized_path(downloads_dir, fn, auto_categorize=True)
        else:
            new_dest = os.path.join(dest_dir, fn)
        self.entry_dest.delete(0, tk.END)
        self.entry_dest.insert(0, new_dest)

    def _build_limiter_and_actions_card(self, parent):
        """Configuration options: Speed Limiter (Presets + Custom + Dynamic Slider) & Action Buttons."""
        card = tk.Frame(parent, bg=self.c_panel, padx=14, pady=10, relief="flat", highlightbackground=self.c_border, highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 10))

        # Row 1: Max Connections + Bandwidth Presets + Custom Entry
        row1 = tk.Frame(card, bg=self.c_panel)
        row1.pack(fill=tk.X, pady=2)

        # Max Connections
        self.lbl_conn = tk.Label(row1, text=tr("lbl_threads"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_bright)
        self.lbl_conn.pack(side=tk.LEFT)

        self.conn_var = tk.StringVar(value="8")
        conn_combo = ttk.Combobox(row1, textvariable=self.conn_var, values=["1", "2", "4", "8", "16", "24", "32"], width=4, state="readonly")
        conn_combo.pack(side=tk.LEFT, padx=(4, 16))

        # Speed Limiter controls
        self.lbl_limit = tk.Label(row1, text=tr("lbl_speed_limiter"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_accent)
        self.lbl_limit.pack(side=tk.LEFT)

        self.limit_preset_var = tk.StringVar(value="Unlimited")
        self.preset_options = [
            "Unlimited",
            "128 KB/s",
            "256 KB/s",
            "512 KB/s",
            "1.0 MB/s",
            "2.0 MB/s",
            "5.0 MB/s",
            "10.0 MB/s",
            "20.0 MB/s",
            "Custom"
        ]
        preset_combo = ttk.Combobox(row1, textvariable=self.limit_preset_var, values=self.preset_options, width=12, state="readonly")
        preset_combo.pack(side=tk.LEFT, padx=(4, 8))
        preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        # Custom entry
        self.lbl_custom = tk.Label(row1, text=tr("lbl_custom_speed"), font=("Segoe UI", 8), bg=self.c_panel, fg=self.c_text_muted)
        self.lbl_custom.pack(side=tk.LEFT)

        self.entry_custom_speed = tk.Entry(row1, font=("Segoe UI", 9), width=7, bg=self.c_input_bg, fg=self.c_text_bright, insertbackground=self.c_accent, relief="flat")
        self.entry_custom_speed.insert(0, "0")
        self.entry_custom_speed.pack(side=tk.LEFT, padx=(4, 6), ipady=1)
        self.entry_custom_speed.bind("<Return>", lambda e: self._apply_speed_limit())

        self.btn_apply_speed = tk.Button(row1, text=tr("btn_apply_limit"), font=("Segoe UI", 8, "bold"), bg=self.c_accent_dark, fg="white", relief="flat", activebackground=self.c_accent, cursor="hand2", command=self._apply_speed_limit)
        self.btn_apply_speed.pack(side=tk.LEFT, padx=(2, 16))

        # Active limit status indicator
        self.lbl_active_limit = tk.Label(row1, text=tr("lbl_current_unlimited", "● Current: Unlimited"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_success)
        self.lbl_active_limit.pack(side=tk.LEFT)

        # Row 2: Dynamic Rate Limiter Slider (0 KB/s to 20,480 KB/s)
        row_slider = tk.Frame(card, bg=self.c_panel)
        row_slider.pack(fill=tk.X, pady=(6, 2))

        self.lbl_slider_title = tk.Label(row_slider, text=tr("lbl_live_throttle_slider"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted)
        self.lbl_slider_title.pack(side=tk.LEFT, padx=(0, 8))

        slider_len = max(20, int(22 * getattr(self, "dpi_scale", 1.0)))
        slider_w = max(14, int(16 * getattr(self, "dpi_scale", 1.0)))
        self.slider_speed = tk.Scale(
            row_slider,
            from_=0,
            to=20480,  # 0 to 20 MB/s in KB/s
            orient=tk.HORIZONTAL,
            showvalue=False,
            bg=self.c_panel,
            troughcolor=self.c_input_bg,
            activebackground=self.c_accent,
            highlightthickness=0,
            relief="flat",
            sliderlength=slider_len,
            width=slider_w,
            command=self._on_slider_moved
        )
        self.slider_speed.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ToolTip(self.slider_speed, "tip_speed_slider")

        self.lbl_slider_val = tk.Label(row_slider, text=f"{tr('lbl_unlimited', 'Unlimited')} (0 KB/s)", font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent, width=18, anchor="w")
        self.lbl_slider_val.pack(side=tk.RIGHT)

        # Row 3: Action Buttons (Start, Pause, Cancel)
        row2 = tk.Frame(card, bg=self.c_panel)
        row2.pack(fill=tk.X, pady=(10, 2))

        self.btn_start = tk.Button(
            row2,
            text=tr("btn_start", "▶ Start Download"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_success,
            fg="white",
            relief="flat",
            activebackground="#059669",
            cursor="hand2",
            padx=14,
            pady=4,
            command=self._on_start_download
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_pause = tk.Button(
            row2,
            text=tr("btn_pause", "⏸ Pause"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_border,
            cursor="hand2",
            padx=14,
            pady=4,
            state="disabled",
            command=self._on_pause_resume
        )
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_cancel = tk.Button(
            row2,
            text=tr("btn_cancel", "⏹ Cancel"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_danger,
            fg="white",
            relief="flat",
            activebackground="#dc2626",
            cursor="hand2",
            padx=14,
            pady=4,
            state="disabled",
            command=self._on_cancel_download
        )
        self.btn_cancel.pack(side=tk.LEFT)

        self.btn_refresh_link = tk.Button(
            row2,
            text=tr("btn_refresh_url", "🔄 Refresh Link"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self._open_refresh_link_dialog
        )
        self.btn_refresh_link.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_browser = tk.Button(
            row2,
            text=tr("btn_browser", "🌐 Settings & Integration"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            cursor="hand2",
            padx=12,
            pady=4,
            command=self._open_browser_integration_dialog
        )
        self.btn_browser.pack(side=tk.RIGHT)

        self.btn_clipboard_sniffer = tk.Button(
            row2,
            text="📋 Sniffer: Active",
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_success,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self.toggle_clipboard_sniffer
        )
        self.btn_clipboard_sniffer.pack(side=tk.RIGHT, padx=(0, 8))
        ToolTip(self.btn_clipboard_sniffer, "tip_sniffer")

        self.btn_startup = tk.Button(
            row2,
            text=tr("btn_startup_off", "🚀 Boot: OFF"),
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self.toggle_startup_setting
        )
        self.btn_startup.pack(side=tk.RIGHT, padx=(0, 8))
        ToolTip(self.btn_startup, "tip_startup")
        self._update_startup_btn()

        self.btn_cookies = tk.Button(
            row2,
            text=self._get_cookies_btn_text(),
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self.cycle_cookies_setting
        )
        self.btn_cookies.pack(side=tk.RIGHT, padx=(0, 8))
        self._update_cookies_btn()

        self.btn_auto_cat = tk.Button(
            row2,
            text="📁 Auto-Sort: ON" if getattr(self, "auto_categorize_folders", True) else "📁 Auto-Sort: OFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bg=self.c_panel_light if getattr(self, "auto_categorize_folders", True) else self.c_panel,
            fg=self.c_success if getattr(self, "auto_categorize_folders", True) else self.c_text_muted,
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self.toggle_auto_categorize
        )
        self.btn_auto_cat.pack(side=tk.RIGHT, padx=(0, 8))
        ToolTip(self.btn_auto_cat, "tip_auto_cat")
        self._update_auto_cat_btn()
