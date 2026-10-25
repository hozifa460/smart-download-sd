"""
Update check and application updater controller mixin for Smart Download (SD).
"""
import os
import threading
import weakref
from typing import Optional, Dict, Any

from smart_download.i18n import tr
from smart_download.config import APP_VERSION
from smart_download.services import AppAutoUpdater, YtDlpAutoUpdater, get_ytdlp_version
from smart_download.ui.modals.update_modal import AppUpdateModal

from .toast_controller import ToastControllerMixin


class UpdateControllerMixin(ToastControllerMixin):
    """Provides background and manual update checks for the app and yt-dlp."""

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

        theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
        self._update_modal = AppUpdateModal(
            parent=self.root,
            update_info=update_info,
            theme=theme_dict,
            parent_app=self,
            on_log=self.log,
            on_exit_app=lambda: self._on_close(force_exit=True)
        )
        return self._update_modal


__all__ = ["UpdateControllerMixin", "ToastControllerMixin"]
