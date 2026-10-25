"""
Update check and toast notification controller mixin for Smart Download (SD).
"""
import os
import sys
import threading
import weakref
from typing import Optional, Callable, Dict, Any

try:
    import tkinter as tk
except Exception:
    tk = None  # type: ignore

from smart_download.i18n import tr
from smart_download.config import get_setting, APP_VERSION
from smart_download.services import AppAutoUpdater, YtDlpAutoUpdater, get_ytdlp_version
from smart_download.ui.modals.toasts import StartupWelcomeToast, FetchingLinkToast
from smart_download.ui.modals.update_modal import AppUpdateModal


class UpdateControllerMixin:
    """Provides background and manual update checks for the app and yt-dlp, plus toast notifications."""

    def _show_background_startup_notification(self):
        """Displays Windows startup welcome toast when running in background on boot."""
        if getattr(self, "_closing", False):
            return
        if not getattr(self, "_start_hidden", False) and not getattr(self, "_was_started_hidden", False):
            return
        if os.environ.get("SD_DISABLE_STARTUP_TOAST") == "1":
            return
        if not get_setting("show_startup_toast", True):
            return

        try:
            self._dismiss_bg_toast()
            self._bg_toast = StartupWelcomeToast(
                self.root,
                parent_app=self,
                theme=self._theme_dict(),
                duration_ms=4000
            )
        except Exception:
            pass

    def _show_background_toast(self, message: str):
        """Displays a brief, non-intrusive dark-themed toast notification at the bottom-right corner."""
        try:
            self._dismiss_bg_toast()

            toast = tk.Toplevel(self.root)
            self._bg_toast = toast
            toast.overrideredirect(True)
            toast.configure(bg=self.c_border)
            try:
                toast.attributes("-topmost", True)
            except Exception:
                pass

            try:
                dpi = float(self.root.winfo_fpixels('1i')) if self.root.winfo_exists() else 96.0
            except Exception:
                dpi = 96.0
            scale = max(1.0, dpi / 96.0)

            w = int(370 * scale)
            h = int(76 * scale)
            sw = toast.winfo_screenwidth()
            sh = toast.winfo_screenheight()
            x = max(0, sw - w - int(24 * scale))
            y = max(0, sh - h - int(48 * scale))
            toast.geometry(f"{w}x{h}+{x}+{y}")

            inner = tk.Frame(toast, bg=self.c_panel, padx=12, pady=10)
            inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

            lbl_ico = tk.Label(inner, text="🚀", font=("Segoe UI", 16), bg=self.c_panel, fg=self.c_accent)
            lbl_ico.pack(side=tk.LEFT, padx=(0, 10))

            text_frame = tk.Frame(inner, bg=self.c_panel)
            text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            lbl_t = tk.Label(text_frame, text="Smart Download (SD)", font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_accent, anchor="w")
            lbl_t.pack(anchor="w")

            lbl_m = tk.Label(text_frame, text=message, font=("Segoe UI", 8), bg=self.c_panel, fg=self.c_text_bright, anchor="w")
            lbl_m.pack(anchor="w")

            btn_close = tk.Label(inner, text="✕", font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_muted, cursor="hand2")
            btn_close.pack(side=tk.RIGHT, padx=(4, 0))
            btn_close.bind("<Button-1>", lambda e: self._dismiss_bg_toast())

            # Auto-dismiss after 3200ms
            toast._dismiss_job = toast.after(3200, self._dismiss_bg_toast)
        except Exception:
            pass

    def _dismiss_bg_toast(self):
        """Safely dismisses the background notification toast."""
        if hasattr(self, "_bg_toast") and self._bg_toast:
            try:
                if hasattr(self._bg_toast, "_close"):
                    self._bg_toast._close()
                elif hasattr(self._bg_toast, "_dismiss_job") and self._bg_toast._dismiss_job:
                    try:
                        self._bg_toast.after_cancel(self._bg_toast._dismiss_job)
                    except Exception:
                        pass
                    self._bg_toast._dismiss_job = None
                if self._bg_toast and hasattr(self._bg_toast, "winfo_exists") and self._bg_toast.winfo_exists():
                    self._bg_toast.destroy()
            except Exception:
                pass
            self._bg_toast = None

    def _show_fetching_toast(self, url: str, on_cancel: Optional[Callable[[], None]] = None) -> Optional[FetchingLinkToast]:
        """Displays instantaneous (< 50ms) sleek dark-themed fetching indicator toast."""
        self._close_fetching_toast()
        try:
            def _handle_cancel():
                self.log(f"[FETCHING] Link analysis cancelled by user for: {url}")
                if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
                    self._yt_cancel_event.set()
                if callable(on_cancel):
                    try:
                        on_cancel()
                    except Exception:
                        pass
                self._fetching_toast = None
                self.clear_last_clipboard_url()
                try:
                    self.btn_start.configure(state="normal")
                    self.btn_pause.configure(state="disabled")
                    self.btn_cancel.configure(state="disabled")
                    self.card_size.configure(text=tr("status_ready", "Ready"))
                except Exception:
                    pass

            self._fetching_toast = FetchingLinkToast(
                parent=self.root,
                url=url,
                theme=self._theme_dict(),
                on_cancel=_handle_cancel,
                parent_app=self
            )
            return self._fetching_toast
        except Exception as e:
            self.log(f"[FETCHING] Failed to display fetching toast: {e}")
            return None

    def _close_fetching_toast(self):
        """Safely closes active fetching indicator toast."""
        if hasattr(self, "_fetching_toast") and self._fetching_toast:
            try:
                self._fetching_toast.close()
            except Exception:
                pass
            self._fetching_toast = None

    def _start_auto_update_check(self):
        """Runs a non-blocking background check for yt-dlp and Smart Download updates on startup."""
        self._update_check_job = None
        if getattr(self, "_closing", False) or os.environ.get("SD_DISABLE_AUTO_UPDATE") == "1":
            return

        weak_self = weakref.ref(self)

        def _safe_log(msg: str):
            g = weak_self()
            if g is not None and not getattr(g, "_closing", False):
                g.log(msg)

        def _worker():
            g = weak_self()
            if g is None or getattr(g, "_closing", False):
                return
            del g
            try:
                # 1. Silently check & update yt-dlp engine in background
                YtDlpAutoUpdater(on_log=_safe_log).update()
            except Exception:
                pass
            g = weak_self()
            if g is None or getattr(g, "_closing", False):
                return
            del g
            try:
                # 2. Check GitHub Releases for newer Smart Download (SD) version
                info = AppAutoUpdater(current_version=APP_VERSION, on_log=_safe_log).check_for_update()
                g = weak_self()
                if g is not None and info.get("update_available") and not getattr(g, "_closing", False):
                    latest = info.get("latest_version", "")
                    g.log(f"[UPDATER] New Smart Download version v{latest} is available (current: v{APP_VERSION}).")
                    g.dispatch_to_main_thread(lambda: (weak_self() and weak_self()._show_update_dialog(info)))
                del g
            except Exception:
                pass

        t = threading.Thread(target=_worker, daemon=True, name="AutoUpdateCheckThread")
        t.start()

    def check_for_updates_manual(self):
        """Triggered manually by user clicking '🔄 Check for Updates'."""
        if getattr(self, "_closing", False):
            return
        self.log("[UPDATER] Checking for Smart Download and yt-dlp updates...")
        if hasattr(self, "btn_check_updates") and self.btn_check_updates:
            try:
                if self.btn_check_updates.winfo_exists():
                    self.btn_check_updates.configure(text=tr("btn_checking_updates", "⏳ Checking..."), state="disabled")
            except Exception:
                pass

        weak_self = weakref.ref(self)

        def _safe_log(msg: str):
            g = weak_self()
            if g is not None and not getattr(g, "_closing", False):
                g.log(msg)

        def _worker():
            app_info = AppAutoUpdater(current_version=APP_VERSION, on_log=_safe_log).check_for_update()
            yt_res = None
            try:
                yt_updater = YtDlpAutoUpdater(on_log=_safe_log)
                yt_info = yt_updater.check_for_update()
                if yt_info.get("update_available"):
                    yt_res = yt_updater.update()
                else:
                    yt_res = {
                        "updated": False,
                        "version": yt_info.get("latest_version") or yt_info.get("current_version", get_ytdlp_version()),
                    }
            except Exception:
                yt_res = {"updated": False, "version": get_ytdlp_version()}

            def _on_done():
                g = weak_self()
                if g is None or getattr(g, "_closing", False):
                    return
                if hasattr(g, "btn_check_updates") and g.btn_check_updates:
                    try:
                        if g.btn_check_updates.winfo_exists():
                            g.btn_check_updates.configure(text=tr("btn_check_updates", "🔄 Check for Updates"), state="normal")
                    except Exception:
                        pass

                if app_info.get("update_available"):
                    g._show_update_dialog(app_info)
                    return

                if app_info.get("error"):
                    g.show_safe_error(
                        "Update Check Failed",
                        f"Could not check GitHub Releases for updates:\n\n{app_info.get('error')}"
                    )
                    return

                yt_ver = (yt_res or {}).get("version") or (yt_res or {}).get("new_version") or get_ytdlp_version()
                if (yt_res or {}).get("updated"):
                    yt_line = f"🎬 YouTube Engine (yt-dlp): Updated to v{yt_ver} ✅"
                else:
                    yt_line = f"🎬 YouTube Engine (yt-dlp): v{yt_ver} (Up to Date ✅)"

                g.show_safe_info(
                    "Up to Date ✅",
                    f"You are running the latest version of Smart Download (SD)!\n\n"
                    f"🚀 Application Version: v{APP_VERSION}\n"
                    f"{yt_line}"
                )

            g = weak_self()
            if g is not None and not getattr(g, "_closing", False):
                g.dispatch_to_main_thread(_on_done)
            del g

        t = threading.Thread(target=_worker, daemon=True, name="ManualUpdateCheckThread")
        t.start()

    def _show_update_dialog(self, update_info: Dict[str, Any]) -> Optional[AppUpdateModal]:
        """Displays the non-intrusive dark-themed AppUpdateModal when a newer version is found."""
        if getattr(self, "_closing", False):
            return None
        try:
            if not hasattr(self, "root") or not self.root or not self.root.winfo_exists():
                return None
        except Exception:
            return None

        if hasattr(self, "_update_modal") and self._update_modal:
            try:
                if self._update_modal.winfo_exists():
                    self._update_modal.destroy()
            except Exception:
                pass
            self._update_modal = None

        self._update_modal = AppUpdateModal(
            parent=self.root,
            update_info=update_info,
            theme=self._theme_dict(),
            parent_app=self,
            on_log=self.log,
            on_exit_app=lambda: self._on_close(force_exit=True)
        )
        return self._update_modal
