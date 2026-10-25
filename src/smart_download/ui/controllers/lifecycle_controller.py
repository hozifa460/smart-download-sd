"""
WindowLifecycleMixin: Resource cleanup, tray minimization, and clean application shutdown.
"""
import ctypes

from smart_download.i18n import LocalizationManager, tr
from smart_download.utils import _detach_photo_tk
from smart_download.services import IS_WINDOWS, SW_HIDE

from .dialog_controller import DialogControllerMixin


class WindowLifecycleMixin(DialogControllerMixin):
    """Provides resource cleanup, tray minimization, and clean application shutdown."""

    def _on_root_destroyed(self, event):
        if event.widget == self.root:
            self._cleanup_resources()

    def _cleanup_resources(self):
        self._closing = True
        try:
            LocalizationManager.get_instance().unregister_observer(self._update_ui_language)
        except Exception:
            pass
        if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
            try:
                self._yt_cancel_event.set()
            except Exception:
                pass
        if hasattr(self, "engine") and self.engine:
            try:
                for cb_attr in ("on_progress", "on_chunk_update", "on_log", "on_complete", "on_error"):
                    if hasattr(self.engine, cb_attr):
                        setattr(self.engine, cb_attr, None)
                if getattr(self.engine, "is_running", False):
                    if hasattr(self.engine, "safe_shutdown"):
                        self.engine.safe_shutdown()
                    else:
                        self.engine.cancel()
            except Exception:
                pass
        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.stop()
            except Exception:
                pass
        if hasattr(self, "_clipboard_job") and self._clipboard_job:
            try:
                self.root.after_cancel(self._clipboard_job)
            except Exception:
                pass
            self._clipboard_job = None
        if hasattr(self, "_refresh_job") and self._refresh_job:
            try:
                self.root.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        if hasattr(self, "_bg_notify_job") and self._bg_notify_job:
            try:
                self.root.after_cancel(self._bg_notify_job)
            except Exception:
                pass
            self._bg_notify_job = None
        if hasattr(self, "_update_check_job") and self._update_check_job:
            try:
                self.root.after_cancel(self._update_check_job)
            except Exception:
                pass
            self._update_check_job = None
        if hasattr(self, "_log_jobs") and self._log_jobs:
            for j in list(self._log_jobs):
                try:
                    self.root.after_cancel(j)
                except Exception:
                    pass
            self._log_jobs.clear()
        if hasattr(self, "bridge_server") and self.bridge_server:
            try:
                self.bridge_server.stop()
            except Exception:
                pass
            self.bridge_server = None
        if hasattr(self, "_confirm_modal") and self._confirm_modal:
            try:
                if self._confirm_modal.winfo_exists():
                    self._confirm_modal.destroy()
            except Exception:
                pass
            self._confirm_modal = None
        if hasattr(self, "_quality_modal") and self._quality_modal:
            try:
                if self._quality_modal.winfo_exists():
                    self._quality_modal.destroy()
            except Exception:
                pass
            self._quality_modal = None
        if hasattr(self, "_refresh_modal") and self._refresh_modal:
            try:
                if self._refresh_modal.winfo_exists():
                    self._refresh_modal.destroy()
            except Exception:
                pass
            self._refresh_modal = None
        if hasattr(self, "_active_modal_dialog") and self._active_modal_dialog:
            try:
                if self._active_modal_dialog.winfo_exists():
                    self._active_modal_dialog.destroy()
            except Exception:
                pass
            self._active_modal_dialog = None
        if hasattr(self, "_update_modal") and self._update_modal:
            try:
                if hasattr(self._update_modal, "_cancel_event"):
                    self._update_modal._cancel_event.set()
                if self._update_modal.winfo_exists():
                    self._update_modal.destroy()
            except Exception:
                pass
            self._update_modal = None
        if hasattr(self, "_close_fetching_toast") and callable(self._close_fetching_toast):
            self._close_fetching_toast()
        if hasattr(self, "_dismiss_bg_toast") and callable(self._dismiss_bg_toast):
            self._dismiss_bg_toast()
        if hasattr(self, "style") and self.style is not None:
            _detach_photo_tk(self.style)
            self.style = None
        for var_name in ("conn_var", "limit_preset_var"):
            if hasattr(self, var_name):
                _detach_photo_tk(getattr(self, var_name))
        for photo_attr in ("_app_icon_photo", "_title_icon_photo"):
            if hasattr(self, photo_attr):
                _detach_photo_tk(getattr(self, photo_attr))
                setattr(self, photo_attr, None)
        if hasattr(self, "_restore_idle_job") and self._restore_idle_job:
            try:
                self.root.after_cancel(self._restore_idle_job)
            except Exception:
                pass
            self._restore_idle_job = None
        if hasattr(self, "_browser_integration_dlg") and self._browser_integration_dlg:
            try:
                if hasattr(self._browser_integration_dlg, "_browser_icon_photo"):
                    _detach_photo_tk(self._browser_integration_dlg._browser_icon_photo)
                    self._browser_integration_dlg._browser_icon_photo = None
                if self._browser_integration_dlg.winfo_exists():
                    self._browser_integration_dlg.destroy()
            except Exception:
                pass
            self._browser_integration_dlg = None
        self._update_dlg_startup_ui = None
        self._update_dlg_tray_ui = None
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def _on_close(self, force_exit: bool = False):
        """
        Handles the window close button '✕' or WM_DELETE_WINDOW protocol.
        If minimize_to_tray is True (default) and force_exit is False,
        minimizes/hides the window to the Windows System Tray while keeping
        the clipboard sniffer and loopback server running.
        Otherwise, executes a clean application exit.
        """
        if not force_exit and getattr(self, "minimize_to_tray", True):
            self.minimize_to_tray_action()
            return

        self.exit_completely()

    def minimize_to_tray_action(self):
        """Hides the main window to the Windows System Tray while keeping background services alive."""
        try:
            self.root.withdraw()
        except Exception:
            pass

        if IS_WINDOWS:
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
            except Exception:
                pass

        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.start()
            except Exception:
                pass

        if hasattr(self, "log") and callable(self.log):
            self.log("[SYSTEM TRAY] Application minimized to system tray. Clipboard sniffer & browser bridge remain active.")

    def exit_completely(self):
        """Cleanly terminates the application, background threads, servers, and system tray icons."""
        self._closing = True
        if hasattr(self, "_yt_cancel_event"):
            self._yt_cancel_event.set()
        if hasattr(self, "_quality_modal") and self._quality_modal:
            try:
                if self._quality_modal.winfo_exists():
                    try:
                        self._quality_modal.grab_release()
                    except Exception:
                        pass
                    self._quality_modal.destroy()
            except Exception:
                pass
            self._quality_modal = None
        if hasattr(self, "_confirm_modal") and self._confirm_modal:
            try:
                if self._confirm_modal.winfo_exists():
                    try:
                        self._confirm_modal.grab_release()
                    except Exception:
                        pass
                    self._confirm_modal.destroy()
            except Exception:
                pass
            self._confirm_modal = None
        if hasattr(self, "_update_modal") and self._update_modal:
            try:
                if hasattr(self._update_modal, "_cancel_event"):
                    self._update_modal._cancel_event.set()
                if self._update_modal.winfo_exists():
                    self._update_modal.destroy()
            except Exception:
                pass
            self._update_modal = None
        if hasattr(self, "_active_modal_dialog") and self._active_modal_dialog:
            try:
                if self._active_modal_dialog.winfo_exists():
                    try:
                        self._active_modal_dialog.grab_release()
                    except Exception:
                        pass
                    self._active_modal_dialog.destroy()
            except Exception:
                pass
            self._active_modal_dialog = None

        def _do_exit():
            engine = getattr(self, "engine", None)
            if engine and getattr(engine, "is_running", False):
                try:
                    dl_url = (engine.url if getattr(engine, "url", None) else (self.entry_url.get() if hasattr(self, "entry_url") else "")).strip()
                    dl_dest = (engine.dest_path if getattr(engine, "dest_path", None) else (self.entry_dest.get() if hasattr(self, "entry_dest") else "")).strip()
                    if dl_url and dl_dest and hasattr(self, "history_manager") and self.history_manager:
                        self.history_manager.add_or_update_entry(
                            url=dl_url,
                            file_path=dl_dest,
                            size_bytes=getattr(engine, "total_size", 0) or 0,
                            status="Paused",
                            elapsed_sec=0.0
                        )
                except Exception:
                    pass
                try:
                    engine.safe_shutdown()
                except Exception:
                    pass
            self._cleanup_resources()
            try:
                if hasattr(self, "root") and self.root and self.root.winfo_exists():
                    self.root.destroy()
            except Exception:
                pass

        active_engine = getattr(self, "engine", None)
        if active_engine and getattr(active_engine, "is_running", False):
            if hasattr(self, "restore_window") and callable(self.restore_window):
                self.restore_window()
            self.ask_safe_yesno(
                tr("dialog_exit_title", "Exit Confirmation"),
                tr("dialog_exit_msg", "A download is currently active. Stop and exit completely?"),
                on_yes=_do_exit
            )
            return
        _do_exit()


__all__ = ["WindowLifecycleMixin", "DialogControllerMixin"]
