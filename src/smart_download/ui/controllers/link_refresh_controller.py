"""
Link refresh controller mixin for Smart Download (SD).
"""
import os
from typing import Dict, Any, Optional

try:
    import tkinter as tk
except Exception:
    tk = None  # type: ignore

from smart_download.i18n import tr
from ..modals.refresh_modal import RefreshLinkModal


class LinkRefreshControllerMixin:
    """Handles expired/stale link refresh dialogs and seamless connection update."""

    def _open_refresh_link_dialog(self):
        """Displays sleek, dark-themed, grab-free Refresh Link modal dialog."""
        engine = getattr(self, "engine", None)
        current_url = ""
        if engine and getattr(engine, "url", None):
            current_url = engine.url
        elif hasattr(self, "entry_url"):
            current_url = self.entry_url.get().strip()

        total_size = 0
        downloaded_bytes = 0
        if engine:
            total_size = getattr(engine, "total_size", 0)
            chunks = getattr(engine, "chunks", [])
            downloaded_bytes = sum(c.downloaded_bytes for c in chunks) if chunks else 0

        dest_path = self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ""
        filename = os.path.basename(dest_path) if dest_path else "download.bin"
        expected_ranges = getattr(engine, "supports_ranges", True) if engine else True

        if hasattr(self, "_refresh_modal") and self._refresh_modal:
            try:
                if self._refresh_modal.winfo_exists():
                    self._refresh_modal.destroy()
            except Exception:
                pass
            self._refresh_modal = None

        theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
        self._refresh_modal = RefreshLinkModal(
            parent=self.root,
            old_url=current_url,
            total_size=total_size,
            downloaded_bytes=downloaded_bytes,
            filename=filename,
            theme=theme_dict,
            on_success=self._on_link_refreshed_success,
            expected_ranges=expected_ranges
        )

    def _on_link_refreshed_success(self, new_url: str, headers: Optional[Dict[str, str]] = None):
        """Callback invoked when user confirms a validated new download URL."""
        try:
            if hasattr(self, "entry_url") and tk:
                self.entry_url.delete(0, tk.END)
                self.entry_url.insert(0, new_url)

            engine = getattr(self, "engine", None)
            c_panel_light = getattr(self, "c_panel_light", "#334155")
            c_accent = getattr(self, "c_accent", "#38bdf8")

            if engine:
                engine.refresh_link(new_url, headers=headers, auto_resume=True)
                if hasattr(self, "btn_start"):
                    self.btn_start.configure(state="disabled")
                if hasattr(self, "btn_pause"):
                    self.btn_pause.configure(state="normal", text=tr("btn_pause", "⏸ Pause"), bg=c_panel_light)
                if hasattr(self, "btn_cancel"):
                    self.btn_cancel.configure(state="normal")
                if hasattr(self, "btn_refresh_link"):
                    self.btn_refresh_link.configure(state="normal", bg=c_panel_light, fg=c_accent)
                if hasattr(self, "log") and callable(self.log):
                    self.log(f"[REFRESH] Link refreshed successfully: {new_url}")
                if hasattr(self, "show_safe_info") and callable(self.show_safe_info):
                    self.show_safe_info(
                        "Link Refreshed Successfully 🔄",
                        f"Download address updated to:\n{new_url}\n\nResuming download seamlessly from existing progress without losing data!"
                    )
            else:
                if hasattr(self, "log") and callable(self.log):
                    self.log(f"[REFRESH] URL updated: {new_url}")
                if hasattr(self, "show_safe_info") and callable(self.show_safe_info):
                    self.show_safe_info("URL Updated", f"Download URL updated to:\n{new_url}\n\nClick '▶ Start Download' to begin.")
        except Exception as e:
            if hasattr(self, "show_safe_error") and callable(self.show_safe_error):
                self.show_safe_error("Refresh Link Failed", f"Could not refresh download link:\n{e}")


__all__ = ["LinkRefreshControllerMixin"]
