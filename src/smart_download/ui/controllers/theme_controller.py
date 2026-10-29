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
        self.c_text_main = self.c_text_bright
        self.c_input_bg = "#090e1a"

        if hasattr(self, "root") and self.root:
            try:
                self.root.configure(bg=self.c_bg)
            except Exception:
                pass

        self._setup_styles()

    def _setup_styles(self):
        """Configures TTK dark theme styles for Notebook, Treeview, Frames, and Scrollbars."""
        if not (ttk and hasattr(self, "root") and self.root):
            return

        try:
            self.style = ttk.Style(self.root)
            self.style.theme_use("clam")

            # Treeview styling
            row_h = max(26, int(26 * getattr(self, "dpi_scale", 1.0)))
            for tv_name in ("Treeview", "Custom.Treeview"):
                try:
                    self.style.layout(tv_name, [(f"{tv_name}.treearea", {"sticky": "nswe"})])
                except Exception:
                    try:
                        self.style.layout(tv_name, [("Treeview.treearea", {"sticky": "nswe"})])
                    except Exception:
                        pass
                self.style.configure(
                    tv_name,
                    background=self.c_input_bg,
                    foreground=self.c_text_main,
                    fieldbackground=self.c_input_bg,
                    bordercolor=self.c_border,
                    lightcolor=self.c_border,
                    darkcolor=self.c_border,
                    borderwidth=0,
                    relief="flat",
                    rowheight=row_h,
                    font=("Segoe UI", 9),
                )
                self.style.map(
                    tv_name,
                    background=[("selected", self.c_accent_dark)],
                    foreground=[("selected", "#ffffff")],
                )
            for hd_name in ("Treeview.Heading", "Custom.Treeview.Heading"):
                self.style.configure(
                    hd_name,
                    background="#182338",
                    foreground=self.c_accent,
                    bordercolor=self.c_border,
                    lightcolor="#182338",
                    darkcolor="#182338",
                    relief="flat",
                    padding=(8, 6),
                    font=("Segoe UI", 9, "bold"),
                )
                self.style.map(
                    hd_name,
                    background=[("active", self.c_panel_light)],
                    lightcolor=[("active", self.c_panel_light)],
                    darkcolor=[("active", self.c_panel_light)],
                )

            # Notebook tabs
            for nb_name in ("TNotebook", "Custom.TNotebook"):
                self.style.configure(
                    nb_name,
                    background=self.c_bg,
                    bordercolor=self.c_border,
                    lightcolor=self.c_bg,
                    darkcolor=self.c_bg,
                    tabmargins=[0, 2, 0, 0],
                    borderwidth=0,
                )
            for cl_name in ("TNotebook.client", "Custom.TNotebook.client"):
                self.style.configure(
                    cl_name,
                    background=self.c_panel,
                    bordercolor=self.c_border,
                    lightcolor=self.c_panel,
                    darkcolor=self.c_panel,
                )
            for tab_name in ("TNotebook.Tab", "Custom.TNotebook.Tab"):
                self.style.configure(
                    tab_name,
                    background=self.c_panel,
                    foreground=self.c_text_muted,
                    bordercolor=self.c_border,
                    lightcolor=self.c_panel,
                    darkcolor=self.c_panel,
                    focuscolor=self.c_panel,
                    padding=[16, 7],
                    font=("Segoe UI", 9, "bold"),
                )
                self.style.map(
                    tab_name,
                    background=[("selected", self.c_accent_dark), ("active", self.c_panel_light)],
                    foreground=[("selected", "#ffffff"), ("active", self.c_text_bright)],
                    bordercolor=[("selected", self.c_accent_dark), ("active", self.c_border)],
                    lightcolor=[("selected", self.c_accent_dark), ("active", self.c_panel_light)],
                    darkcolor=[("selected", self.c_accent_dark), ("active", self.c_panel_light)],
                )

            # TFrame styling
            self.style.configure(
                "TFrame",
                background=self.c_panel,
                bordercolor=self.c_border,
                lightcolor=self.c_panel,
                darkcolor=self.c_panel,
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
            "c_text_main": getattr(self, "c_text_main", "#f8fafc"),
            "c_input_bg": getattr(self, "c_input_bg", "#090e1a")
        }


__all__ = ["ThemeControllerMixin"]
