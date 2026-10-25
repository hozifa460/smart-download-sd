"""
Performance metrics cards and main progress canvas panel mixin for Smart Download (SD).
"""
try:
    import tkinter as tk
except Exception:
    tk = None  # type: ignore

from smart_download.i18n import tr


class MetricsPanelMixin:
    """Provides overall progress bar canvas and real-time metric cards (speed, size, ETA, connections)."""

    def _build_metrics_card(self, parent):
        """Overall progress bar and 4 real-time metric cards."""
        card = tk.Frame(parent, bg=self.c_panel, padx=14, pady=10, relief="flat", highlightbackground=self.c_border, highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 10))

        # Main Progress Canvas
        prog_height = max(22, int(24 * getattr(self, "dpi_scale", 1.0)))
        self.canvas_prog = tk.Canvas(card, height=prog_height, bg=self.c_input_bg, highlightthickness=0)
        self.canvas_prog.pack(fill=tk.X, pady=(0, 10))
        self._draw_main_progress(0.0)

        # 4 Metric Cards Grid
        grid_frame = tk.Frame(card, bg=self.c_panel)
        grid_frame.pack(fill=tk.X)
        for i in range(4):
            grid_frame.columnconfigure(i, weight=1, uniform="metric")

        # 1. Download Speed
        self.card_speed = self._create_metric_box(grid_frame, 0, tr("metric_speed"), "0.0 KB/s")
        self.lbl_t_speed = self.card_speed.master.lbl_t
        # 2. Downloaded / Total
        self.card_size = self._create_metric_box(grid_frame, 1, tr("metric_total_size"), "0 B / 0 B (0%)")
        self.lbl_t_size = self.card_size.master.lbl_t
        # 3. ETA
        self.card_eta = self._create_metric_box(grid_frame, 2, tr("metric_eta"), "--:--:--")
        self.lbl_t_eta = self.card_eta.master.lbl_t
        # 4. Connections
        self.card_threads = self._create_metric_box(grid_frame, 3, tr("metric_threads"), "0 / 0 Threads")
        self.lbl_t_threads = self.card_threads.master.lbl_t

    def _create_metric_box(self, parent, col, title, initial_value):
        frame = tk.Frame(parent, bg=self.c_bg, padx=10, pady=8, highlightbackground=self.c_border, highlightthickness=1)
        frame.grid(row=0, column=col, padx=4, sticky="nsew")

        lbl_t = tk.Label(frame, text=title, font=("Segoe UI", 8, "bold"), bg=self.c_bg, fg=self.c_text_muted)
        lbl_t.pack(anchor="w")
        frame.lbl_t = lbl_t

        lbl_v = tk.Label(frame, text=initial_value, font=("Segoe UI", 11, "bold"), bg=self.c_bg, fg=self.c_text_bright)
        lbl_v.pack(anchor="w", pady=(2, 0))
        frame.lbl_v = lbl_v
        return lbl_v

    def _draw_main_progress(self, pct: float):
        if not hasattr(self, "canvas_prog") or not self.canvas_prog:
            return
        w = self.canvas_prog.winfo_width()
        if w <= 1:
            w = getattr(self, "width", 800) - 64
        h = self.canvas_prog.winfo_height() or max(22, int(24 * getattr(self, "dpi_scale", 1.0)))
        sig = (w, h, round(pct, 1))
        if getattr(self, "_last_main_prog_sig", None) == sig:
            return
        self._last_main_prog_sig = sig
        self.canvas_prog.delete("all")

        c_input_bg = getattr(self, "c_input_bg", "#090d16")
        c_border = getattr(self, "c_border", "#475569")
        c_accent_dark = getattr(self, "c_accent_dark", "#0284c7")
        c_accent = getattr(self, "c_accent", "#38bdf8")
        c_text_bright = getattr(self, "c_text_bright", "#f8fafc")

        # Background track
        self.canvas_prog.create_rectangle(0, 0, w, h, fill=c_input_bg, outline=c_border)

        # Progress fill
        fill_w = max(0.0, min(float(w), (pct / 100.0) * float(w)))
        if fill_w > 0:
            self.canvas_prog.create_rectangle(0, 0, fill_w, h, fill=c_accent_dark, outline="")
            self.canvas_prog.create_line(0, 1, fill_w, 1, fill=c_accent)

        # Percentage text overlay
        text_color = "white" if fill_w > (w * 0.45) else c_text_bright
        self.canvas_prog.create_text(w // 2, h // 2, text=f"{pct:.1f}%", font=("Segoe UI", 9, "bold"), fill=text_color)


__all__ = ["MetricsPanelMixin"]
