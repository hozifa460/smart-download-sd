"""
URL and destination inputs panel mixin for Smart Download (SD).
"""
import os

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    tk = None  # type: ignore
    filedialog = None  # type: ignore

from smart_download.i18n import tr
from smart_download.utils import CATEGORY_SUBFOLDERS, resolve_categorized_path, derive_download_filename
from .controls_panel import ControlsPanelMixin


class InputsPanelMixin(ControlsPanelMixin):
    """Builds and manages the URL and destination inputs card. Inherits ControlsPanelMixin."""

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

        if hasattr(self, "_build_media_options_bar"):
            self._build_media_options_bar(card)

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
        if not filedialog:
            return
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


__all__ = ["InputsPanelMixin", "ControlsPanelMixin"]
