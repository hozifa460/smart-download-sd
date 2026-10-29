"""
Controls and action buttons panel mixin for Smart Download (SD).
"""
try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore

from smart_download.i18n import tr
from smart_download.config import get_setting, set_setting
from smart_download.ui.components.tooltip import ToolTip


_BaseButton = tk.Button if tk is not None else object


class _StateButton(_BaseButton):
    """Button subclass that automatically shifts background and foreground according to state."""

    def __init__(self, master=None, active_bg=None, disabled_bg=None, active_fg="#ffffff", disabled_fg="#64748b", **kwargs):
        self._active_bg = active_bg
        self._disabled_bg = disabled_bg
        self._active_fg = active_fg
        self._disabled_fg = disabled_fg
        initial_state = kwargs.get("state", "normal")
        if "bg" not in kwargs:
            kwargs["bg"] = self._disabled_bg if initial_state == "disabled" else self._active_bg
        if "fg" not in kwargs:
            kwargs["fg"] = self._disabled_fg if initial_state == "disabled" else self._active_fg
        if "disabledforeground" not in kwargs and self._disabled_fg:
            kwargs["disabledforeground"] = self._disabled_fg
        super().__init__(master, **kwargs)

    def configure(self, cnf=None, **kwargs):
        if cnf is not None:
            if isinstance(cnf, dict):
                kwargs = {**cnf, **kwargs}
                cnf = None
            else:
                return super().configure(cnf, **kwargs)
        if "state" in kwargs:
            st = kwargs["state"]
            if "bg" not in kwargs:
                if st == "disabled" and self._disabled_bg:
                    kwargs["bg"] = self._disabled_bg
                elif st == "normal" and self._active_bg:
                    kwargs["bg"] = self._active_bg
            if "fg" not in kwargs:
                if st == "disabled" and self._disabled_fg:
                    kwargs["fg"] = self._disabled_fg
                elif st == "normal" and self._active_fg:
                    kwargs["fg"] = self._active_fg
        return super().configure(**kwargs)

    config = configure


class ControlsPanelMixin:
    """Configuration options: Speed Limiter (Presets + Custom + Dynamic Slider) & Action Buttons."""

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

        saved_conn = str(get_setting("max_connections", 8))
        self.conn_var = tk.StringVar(value=saved_conn)
        conn_combo = ttk.Combobox(row1, textvariable=self.conn_var, values=["1", "2", "4", "8", "16", "24", "32"], width=4, state="readonly")
        conn_combo.pack(side=tk.LEFT, padx=(4, 16))
        conn_combo.bind("<<ComboboxSelected>>", self._on_conn_changed)

        # Speed Limiter controls
        self.lbl_limit = tk.Label(row1, text=tr("lbl_speed_limiter"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_accent)
        self.lbl_limit.pack(side=tk.LEFT)

        unlimited_val = tr("lbl_unlimited", "Unlimited")
        presets = [unlimited_val, "512 KB/s", "1 MB/s", "2 MB/s", "5 MB/s", "10 MB/s", "20 MB/s"]
        self.preset_options = [
            unlimited_val,
            "128 KB/s",
            "256 KB/s",
            "512 KB/s",
            "1 MB/s",
            "1.0 MB/s",
            "2 MB/s",
            "2.0 MB/s",
            "5 MB/s",
            "5.0 MB/s",
            "10 MB/s",
            "10.0 MB/s",
            "20 MB/s",
            "20.0 MB/s",
            "Custom"
        ]
        saved_preset = str(get_setting("speed_limit_preset", "Unlimited") or "Unlimited")
        if saved_preset in ("Unlimited", "بدون حد"):
            saved_preset = unlimited_val
        elif saved_preset not in self.preset_options:
            saved_preset = unlimited_val
        self.speed_preset_var = tk.StringVar(value=saved_preset)
        self.limit_preset_var = self.speed_preset_var
        self.combo_speed = ttk.Combobox(row1, textvariable=self.speed_preset_var, values=presets, width=12, state="readonly")
        preset_combo = self.combo_speed
        self.preset_combo = preset_combo
        preset_combo.pack(side=tk.LEFT, padx=(4, 8))
        preset_combo.bind("<<ComboboxSelected>>", self._on_speed_preset_change)

        # Custom entry
        self.lbl_custom = tk.Label(row1, text=tr("lbl_custom_speed"), font=("Segoe UI", 8), bg=self.c_panel, fg=self.c_text_muted)
        self.lbl_custom.pack(side=tk.LEFT)

        try:
            saved_kbps = int(get_setting("custom_speed_limit_kbps", 0) or 0)
        except Exception:
            saved_kbps = 0
        self.entry_custom_speed = tk.Entry(
            row1,
            font=("Segoe UI", 9),
            width=7,
            bg=self.c_input_bg,
            fg=self.c_text_bright,
            insertbackground=self.c_accent,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=self.c_border,
            highlightcolor=self.c_accent,
        )
        self.entry_custom_speed.insert(0, str(saved_kbps))
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
            fg=self.c_text_bright,
            troughcolor=self.c_input_bg,
            activebackground=self.c_accent,
            highlightthickness=1,
            highlightbackground=self.c_border,
            highlightcolor=self.c_accent,
            bd=0,
            relief="flat",
            sliderrelief="flat",
            sliderlength=slider_len,
            width=slider_w,
            command=self._on_slider_moved
        )
        self.slider_speed.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ToolTip(self.slider_speed, "tip_speed_slider")

        self.lbl_slider_val = tk.Label(row_slider, text=f"{tr('lbl_unlimited', 'Unlimited')} (0 KB/s)", font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent, width=18, anchor="w")
        self.lbl_slider_val.pack(side=tk.RIGHT)

        if saved_kbps > 0 or saved_preset not in ("Unlimited", "بدون حد", unlimited_val):
            preset_map = {
                "Unlimited": 0, "بدون حد": 0, unlimited_val: 0,
                "128 KB/s": 128, "256 KB/s": 256, "512 KB/s": 512,
                "1 MB/s": 1024, "1.0 MB/s": 1024, "2 MB/s": 2048, "2.0 MB/s": 2048,
                "5 MB/s": 5120, "5.0 MB/s": 5120, "10 MB/s": 10240, "10.0 MB/s": 10240,
                "20 MB/s": 20480, "20.0 MB/s": 20480,
            }
            if saved_kbps == 0 and saved_preset in preset_map and preset_map[saved_preset] > 0:
                saved_kbps = preset_map[saved_preset]
                self.entry_custom_speed.delete(0, tk.END)
                self.entry_custom_speed.insert(0, str(saved_kbps))
            if hasattr(self, "_apply_speed_limit") and callable(self._apply_speed_limit):
                self._apply_speed_limit()
            else:
                self.speed_limit = saved_kbps * 1024.0
                if hasattr(self, "slider_speed"):
                    self.slider_speed.set(min(20480, saved_kbps))
                if saved_kbps > 0:
                    disp = f"{saved_kbps / 1024.0:.1f} MB/s ({saved_kbps:,} KB/s)" if saved_kbps >= 1024 else f"{saved_kbps} KB/s"
                    if hasattr(self, "lbl_active_limit"):
                        self.lbl_active_limit.configure(text=tr("lbl_current_limit", "● Current: {limit}").format(limit=disp), fg=self.c_warning)
                    if hasattr(self, "lbl_slider_val"):
                        self.lbl_slider_val.configure(text=disp, fg=self.c_warning)

        # Primary Transfer Controls Row (Row 1)
        row_transfers = tk.Frame(card, bg=self.c_panel)
        row_transfers.pack(fill=tk.X, pady=(10, 4))

        self.btn_start = _StateButton(
            row_transfers,
            text=tr("btn_start", "▶ Start Download"),
            font=("Segoe UI", 9, "bold"),
            active_bg="#059669",
            disabled_bg="#1e293b",
            activebackground="#10b981",
            disabledforeground="#64748b",
            relief="flat",
            cursor="hand2",
            padx=14,
            pady=4,
            state="normal",
            command=self._on_start_download
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_pause = _StateButton(
            row_transfers,
            text=tr("btn_pause", "|| Pause"),
            font=("Segoe UI", 9, "bold"),
            active_bg=self.c_panel_light,
            disabled_bg="#182234",
            activebackground=self.c_border,
            disabledforeground="#64748b",
            relief="flat",
            cursor="hand2",
            padx=14,
            pady=4,
            state="disabled",
            command=self._on_pause_resume
        )
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_cancel = _StateButton(
            row_transfers,
            text=tr("btn_cancel", "✕ Cancel"),
            font=("Segoe UI", 9, "bold"),
            active_bg=self.c_danger,
            disabled_bg="#182234",
            activebackground="#dc2626",
            disabledforeground="#64748b",
            relief="flat",
            cursor="hand2",
            padx=14,
            pady=4,
            state="disabled",
            command=self._on_cancel_download
        )
        self.btn_cancel.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_refresh_link = tk.Button(
            row_transfers,
            text=tr("btn_refresh_url", "↻ Refresh Link"),
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
        self.btn_refresh_link.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_quality_main = tk.Button(
            row_transfers,
            text=tr("btn_quality_reopen", "⚙ Quality / Audio & Subs"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self._reopen_media_quality_modal if hasattr(self, "_reopen_media_quality_modal") else lambda: None
        )
        self.btn_quality_main.pack(side=tk.LEFT)

        # Quick Toggles & Integration Row (Row 2)
        row_toggles = tk.Frame(card, bg=self.c_panel)
        row_toggles.pack(fill=tk.X, pady=(4, 2))

        self.btn_clipboard_sniffer = tk.Button(
            row_toggles,
            text=tr("btn_sniffer_active", "● Sniffer: Active"),
            font=("Segoe UI", 8, "bold"),
            bg="#0f292a",
            fg=self.c_success,
            highlightbackground="#10b981",
            highlightthickness=1,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self.toggle_clipboard_sniffer
        )
        self.btn_clipboard_sniffer.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_sniffer = self.btn_clipboard_sniffer
        ToolTip(self.btn_clipboard_sniffer, "tip_sniffer")

        self.btn_auto_cat = tk.Button(
            row_toggles,
            text=tr("btn_auto_cat_on", "❖ Auto-Sort: ON") if getattr(self, "auto_categorize_folders", True) else tr("btn_auto_cat_off", "❖ Auto-Sort: OFF"),
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            bg="#0f292a" if getattr(self, "auto_categorize_folders", True) else "#182234",
            fg=self.c_success if getattr(self, "auto_categorize_folders", True) else self.c_text_muted,
            highlightbackground="#10b981" if getattr(self, "auto_categorize_folders", True) else self.c_border,
            highlightthickness=1,
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self.toggle_auto_categorize
        )
        self.btn_auto_cat.pack(side=tk.LEFT, padx=(0, 8))
        ToolTip(self.btn_auto_cat, "tip_auto_cat")
        if hasattr(self, "_update_auto_cat_btn") and callable(self._update_auto_cat_btn):
            self._update_auto_cat_btn()

        self.btn_cookies = tk.Button(
            row_toggles,
            text=self._get_cookies_btn_text() if hasattr(self, "_get_cookies_btn_text") else "◆ Cookies: Auto",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            bg="#182234",
            fg=self.c_text_muted,
            highlightbackground=self.c_border,
            highlightthickness=1,
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self.cycle_cookies_setting
        )
        self.btn_cookies.pack(side=tk.LEFT, padx=(0, 8))
        if hasattr(self, "_update_cookies_btn") and callable(self._update_cookies_btn):
            self._update_cookies_btn()

        self.btn_startup = tk.Button(
            row_toggles,
            text=tr("btn_startup_off", "⚡ Boot: OFF"),
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            bg="#182234",
            fg=self.c_text_muted,
            highlightbackground=self.c_border,
            highlightthickness=1,
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self.toggle_startup_setting
        )
        self.btn_startup.pack(side=tk.LEFT, padx=(0, 8))
        ToolTip(self.btn_startup, "tip_startup")
        if hasattr(self, "_update_startup_btn") and callable(self._update_startup_btn):
            self._update_startup_btn()

        self.btn_browser = tk.Button(
            row_toggles,
            text=tr("btn_browser", "⚙ Browser Integration"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            highlightbackground=self.c_border,
            highlightthickness=1,
            relief="flat",
            activebackground=self.c_accent_dark,
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._open_browser_integration_dialog
        )
        self.btn_browser.pack(side=tk.RIGHT)

    def _on_conn_changed(self, event=None):
        """Persists user-selected thread/connection count."""
        try:
            val = int(self.conn_var.get())
            set_setting("max_connections", val)
        except Exception:
            pass

    def _on_speed_preset_change(self, event=None):
        """Handler for speed preset combobox changes. Treats Unlimited, بدون حد, and tr('lbl_unlimited') as 0."""
        if hasattr(self, "_on_preset_selected") and callable(self._on_preset_selected):
            return self._on_preset_selected(event)
        var = getattr(self, "speed_preset_var", None) or getattr(self, "limit_preset_var", None)
        if not var:
            return
        val = str(var.get()).strip()
        if val in ("Unlimited", "بدون حد", tr("lbl_unlimited", "Unlimited")):
            self.speed_limit = 0.0
            if hasattr(self, "slider_speed"):
                self.slider_speed.set(0)
            if hasattr(self, "entry_custom_speed") and tk:
                self.entry_custom_speed.delete(0, tk.END)
                self.entry_custom_speed.insert(0, "0")
            if hasattr(self, "_apply_speed_limit") and callable(self._apply_speed_limit):
                self._apply_speed_limit()


__all__ = ["ControlsPanelMixin"]
