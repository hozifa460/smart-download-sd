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
        self.c_bg = "#0f172a"          # Slate 900
        self.c_panel = "#1e293b"       # Slate 800
        self.c_panel_light = "#334155" # Slate 700
        self.c_border = "#475569"      # Slate 600
        self.c_accent = "#38bdf8"      # Sky 400
        self.c_accent_dark = "#0284c7" # Sky 600
        self.c_success = "#10b981"     # Emerald 500
        self.c_warning = "#f59e0b"     # Amber 500
        self.c_danger = "#ef4444"      # Red 500
        self.c_text_bright = "#f8fafc" # Slate 50
        self.c_text_muted = "#94a3b8"  # Slate 400
        self.c_input_bg = "#090d16"

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
                self.style.configure(
                    "Custom.Treeview",
                    background=self.c_panel,
                    foreground=self.c_text_bright,
                    fieldbackground=self.c_panel,
                    borderwidth=0,
                    rowheight=max(26, int(28 * getattr(self, "dpi_scale", 1.0))),
                    font=("Segoe UI", 9)
                )
                self.style.configure(
                    "Custom.Treeview.Heading",
                    background=self.c_panel_light,
                    foreground=self.c_accent,
                    font=("Segoe UI", 9, "bold"),
                    relief="flat"
                )
                self.style.map("Custom.Treeview.Heading", background=[('active', self.c_border)])
                self.style.map("Custom.Treeview", background=[('selected', self.c_accent_dark)])

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
            except Exception:
                pass

    def _theme_dict(self) -> Dict[str, str]:
        """Returns active theme dictionary for modals and child widgets."""
        return {
            "c_bg": getattr(self, "c_bg", "#0f172a"),
            "c_panel": getattr(self, "c_panel", "#1e293b"),
            "c_panel_light": getattr(self, "c_panel_light", "#334155"),
            "c_border": getattr(self, "c_border", "#475569"),
            "c_accent": getattr(self, "c_accent", "#38bdf8"),
            "c_accent_dark": getattr(self, "c_accent_dark", "#0284c7"),
            "c_success": getattr(self, "c_success", "#10b981"),
            "c_warning": getattr(self, "c_warning", "#f59e0b"),
            "c_danger": getattr(self, "c_danger", "#ef4444"),
            "c_text_bright": getattr(self, "c_text_bright", "#f8fafc"),
            "c_text_muted": getattr(self, "c_text_muted", "#94a3b8"),
            "c_input_bg": getattr(self, "c_input_bg", "#090d16")
        }


__all__ = ["ThemeControllerMixin"]
