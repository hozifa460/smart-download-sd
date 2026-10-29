"""
Theme palette and TTK style controller mixin for Smart Download (SD).
"""
from typing import Dict

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore


class ThemeControllerMixin:
    """Provides application theme color palette initialization and theme dictionary generation."""

    def _init_theme(self):
        """Palette and styling definitions."""
        self.c_bg = "#0b1120"
        self.c_panel = "#131c31"
        self.c_panel_light = "#1e293b"
        self.c_border = "#283548"
        self.c_accent = "#38bdf8"      # Sky 400
        self.c_accent_dark = "#0284c7" # Sky 600
        self.c_success = "#10b981"     # Emerald 500
        self.c_warning = "#f59e0b"     # Amber 500
        self.c_danger = "#ef4444"      # Red 500
        self.c_text_bright = "#f8fafc" # Slate 50
        self.c_text_muted = "#94a3b8"  # Slate 400
        self.c_input_bg = "#090e1a"

        if hasattr(self, "root") and self.root:
            try:
                self.root.configure(bg=self.c_bg)
            except Exception:
                pass

        if ttk and hasattr(self, "root") and self.root:
            try:
                self.style = ttk.Style(self.root)
                self.style.theme_use("clam")

                # Treeview styling
                row_h = max(26, int(26 * getattr(self, "dpi_scale", 1.0)))
                for tv_name in ("Custom.Treeview", "Treeview"):
                    self.style.configure(
                        tv_name,
                        background=self.c_panel,
                        foreground=self.c_text_bright,
                        fieldbackground=self.c_panel,
                        borderwidth=0,
                        rowheight=row_h,
                        font=("Segoe UI", 9)
                    )
                    self.style.map(tv_name, background=[('selected', self.c_accent_dark)])
                for hd_name in ("Custom.Treeview.Heading", "Treeview.Heading"):
                    self.style.configure(
                        hd_name,
                        background="#1a2639",
                        foreground=self.c_accent,
                        font=("Segoe UI", 9, "bold"),
                        padding=(6, 5),
                        relief="flat"
                    )
                    self.style.map(hd_name, background=[('active', self.c_border)])

                # Notebook tabs
                self.style.configure("Custom.TNotebook", background=self.c_panel, borderwidth=0)
                self.style.configure(
                    "Custom.TNotebook.Tab",
                    background=self.c_panel_light,
                    foreground=self.c_text_bright,
                    padding=[14, 5],
                    font=("Segoe UI", 9, "bold")
                )
                self.style.map(
                    "Custom.TNotebook.Tab",
                    background=[("selected", self.c_accent_dark)],
                    foreground=[("selected", self.c_text_bright)]
                )

                # Dark styling for TCombobox
                self.style.configure(
                    "TCombobox",
                    fieldbackground=self.c_input_bg,
                    background=self.c_panel_light,
                    foreground=self.c_text_bright,
                    arrowcolor=self.c_accent,
                    bordercolor=self.c_border,
                    lightcolor=self.c_border,
                    darkcolor=self.c_input_bg,
                    insertcolor=self.c_text_bright,
                    padding=4,
                )
                self.style.map(
                    "TCombobox",
                    fieldbackground=[("readonly", self.c_input_bg), ("disabled", self.c_bg)],
                    selectbackground=[("readonly", self.c_input_bg)],
                    selectforeground=[("readonly", self.c_text_bright)],
                    background=[("active", self.c_border), ("readonly", self.c_panel_light)],
                    foreground=[("readonly", self.c_text_bright), ("disabled", self.c_text_muted)],
                    arrowcolor=[("active", self.c_text_bright), ("readonly", self.c_accent)],
                )
                try:
                    self.root.option_add("*TCombobox*Listbox.background", self.c_panel)
                    self.root.option_add("*TCombobox*Listbox.foreground", self.c_text_bright)
                    self.root.option_add("*TCombobox*Listbox.selectBackground", self.c_accent_dark)
                    self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
                    self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 9))
                except Exception:
                    pass

                # Dark styling for Scrollbars
                for sb_style in ("Vertical.TScrollbar", "Horizontal.TScrollbar", "TScrollbar"):
                    self.style.configure(
                        sb_style,
                        background=self.c_panel_light,
                        troughcolor=self.c_bg,
                        bordercolor=self.c_bg,
                        arrowcolor=self.c_text_muted,
                        lightcolor=self.c_panel_light,
                        darkcolor=self.c_panel_light,
                        gripcount=0,
                        relief="flat",
                    )
                    self.style.map(
                        sb_style,
                        background=[("active", self.c_accent_dark), ("pressed", self.c_accent)],
                        arrowcolor=[("active", self.c_text_bright)],
                    )
            except Exception:
                pass

    def _theme_dict(self) -> Dict[str, str]:
        """Returns active theme dictionary for modals and child widgets."""
        return {
            "c_bg": getattr(self, "c_bg", "#0b1120"),
            "c_panel": getattr(self, "c_panel", "#131c31"),
            "c_panel_light": getattr(self, "c_panel_light", "#1e293b"),
            "c_border": getattr(self, "c_border", "#283548"),
            "c_accent": getattr(self, "c_accent", "#38bdf8"),
            "c_accent_dark": getattr(self, "c_accent_dark", "#0284c7"),
            "c_success": getattr(self, "c_success", "#10b981"),
            "c_warning": getattr(self, "c_warning", "#f59e0b"),
            "c_danger": getattr(self, "c_danger", "#ef4444"),
            "c_text_bright": getattr(self, "c_text_bright", "#f8fafc"),
            "c_text_muted": getattr(self, "c_text_muted", "#94a3b8"),
            "c_input_bg": getattr(self, "c_input_bg", "#090e1a")
        }

    def _setup_styles(self):
        """Public alias configuring theme color palette and TTK widgets."""
        self._init_theme()


__all__ = ["ThemeControllerMixin"]
