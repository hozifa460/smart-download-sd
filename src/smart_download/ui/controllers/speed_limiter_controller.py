"""
Speed limiter controller mixin for Smart Download (SD).
"""
try:
    import tkinter as tk
except Exception:
    tk = None  # type: ignore

from smart_download.i18n import tr
from smart_download.config import get_setting, set_setting


class SpeedLimiterControllerMixin:
    """Provides bandwidth speed limit configuration, presets, and dynamic slider throttling."""

    def _on_slider_moved(self, val_str):
        """Dynamic slider movement throttles engine in real-time."""
        try:
            kb_val = int(float(val_str))
        except ValueError:
            return

        c_success = getattr(self, "c_success", "#10b981")
        c_warning = getattr(self, "c_warning", "#f59e0b")

        if kb_val <= 0:
            unlimited_label = tr("lbl_unlimited", "Unlimited")
            if hasattr(self, "lbl_slider_val") and self.lbl_slider_val:
                self.lbl_slider_val.configure(text=f"{unlimited_label} (0 KB/s)", fg=c_success)
            if hasattr(self, "lbl_active_limit") and self.lbl_active_limit:
                self.lbl_active_limit.configure(text=tr("lbl_current_unlimited", "● Current: Unlimited"), fg=c_success)
            if hasattr(self, "limit_preset_var") and self.limit_preset_var:
                self.limit_preset_var.set(unlimited_label)
            if hasattr(self, "speed_preset_var") and self.speed_preset_var:
                self.speed_preset_var.set(unlimited_label)
            bytes_sec = 0.0
            try:
                set_setting("speed_limit_preset", "Unlimited")
                set_setting("custom_speed_limit_kbps", 0)
            except Exception:
                pass
        else:
            if kb_val >= 1024:
                disp = f"{kb_val / 1024.0:.1f} MB/s ({kb_val:,} KB/s)"
                active_disp = tr("lbl_current_limit", "● Current: {limit}").format(limit=f"{kb_val / 1024.0:.2f} MB/s")
            else:
                disp = f"{kb_val} KB/s"
                active_disp = tr("lbl_current_limit", "● Current: {limit}").format(limit=f"{kb_val} KB/s")
            if hasattr(self, "lbl_slider_val") and self.lbl_slider_val:
                self.lbl_slider_val.configure(text=disp, fg=c_warning)
            if hasattr(self, "lbl_active_limit") and self.lbl_active_limit:
                self.lbl_active_limit.configure(text=active_disp, fg=c_warning)
            bytes_sec = kb_val * 1024.0
            try:
                set_setting("custom_speed_limit_kbps", kb_val)
                preset_name = "Custom"
                reverse_mapping = {128: "128 KB/s", 256: "256 KB/s", 512: "512 KB/s", 1024: "1 MB/s", 2048: "2 MB/s", 5120: "5 MB/s", 10240: "10 MB/s", 20480: "20 MB/s"}
                if kb_val in reverse_mapping:
                    preset_name = reverse_mapping[kb_val]
                if hasattr(self, "limit_preset_var") and self.limit_preset_var:
                    self.limit_preset_var.set(preset_name)
                if hasattr(self, "speed_preset_var") and self.speed_preset_var:
                    self.speed_preset_var.set(preset_name)
                set_setting("speed_limit_preset", preset_name)
            except Exception:
                pass

        self.speed_limit = bytes_sec

        # Sync entry box without triggering infinite callback
        if hasattr(self, "entry_custom_speed") and tk and self.entry_custom_speed:
            self.entry_custom_speed.delete(0, tk.END)
            self.entry_custom_speed.insert(0, str(kb_val))

        engine = getattr(self, "engine", None)
        if engine and getattr(engine, "is_running", False):
            engine.set_speed_limit(bytes_sec)

    def _on_preset_selected(self, event=None):
        var = getattr(self, "speed_preset_var", None) or getattr(self, "limit_preset_var", None)
        if not var:
            return
        val = var.get()
        mapping = {
            "Unlimited": 0,
            "بدون حد": 0,
            tr("lbl_unlimited", "Unlimited"): 0,
            "128 KB/s": 128,
            "256 KB/s": 256,
            "512 KB/s": 512,
            "1 MB/s": 1024,
            "1.0 MB/s": 1024,
            "2 MB/s": 2048,
            "2.0 MB/s": 2048,
            "5 MB/s": 5120,
            "5.0 MB/s": 5120,
            "10 MB/s": 10240,
            "10.0 MB/s": 10240,
            "20 MB/s": 20480,
            "20.0 MB/s": 20480,
        }
        if val in mapping:
            target_kb = mapping[val]
            saved_name = "Unlimited" if target_kb == 0 else val
            try:
                set_setting("speed_limit_preset", saved_name)
            except Exception:
                pass
            if hasattr(self, "entry_custom_speed") and tk:
                self.entry_custom_speed.delete(0, tk.END)
                self.entry_custom_speed.insert(0, str(target_kb))
            if hasattr(self, "slider_speed"):
                self.slider_speed.set(target_kb)
            self._apply_speed_limit()
        elif val == "Custom":
            try:
                set_setting("speed_limit_preset", "Custom")
            except Exception:
                pass
            if hasattr(self, "entry_custom_speed"):
                self.entry_custom_speed.focus_set()

    def _on_speed_preset_change(self, event=None):
        return self._on_preset_selected(event)

    def _apply_speed_limit(self):
        """Applies speed limit dynamically to active engine."""
        try:
            kb_val = float(self.entry_custom_speed.get().strip())
        except ValueError:
            if hasattr(self, "show_safe_warning") and callable(self.show_safe_warning):
                self.show_safe_warning("Invalid Speed", "Please enter a valid numeric speed limit in KB/s.")
            return

        kb_val = max(0.0, kb_val)
        bytes_sec = kb_val * 1024.0 if kb_val > 0 else 0.0
        self.speed_limit = bytes_sec

        if bytes_sec <= 0:
            unlimited_label = tr("lbl_unlimited", "Unlimited")
            if hasattr(self, "lbl_active_limit"):
                self.lbl_active_limit.configure(text=tr("lbl_current_unlimited", "● Current: Unlimited"), fg=self.c_success)
            if hasattr(self, "lbl_slider_val"):
                self.lbl_slider_val.configure(text=f"{unlimited_label} (0 KB/s)", fg=self.c_success)
            if hasattr(self, "limit_preset_var"):
                self.limit_preset_var.set(unlimited_label)
            if hasattr(self, "speed_preset_var"):
                self.speed_preset_var.set(unlimited_label)
            if hasattr(self, "slider_speed"):
                self.slider_speed.set(0)
            try:
                set_setting("speed_limit_preset", "Unlimited")
                set_setting("custom_speed_limit_kbps", 0)
            except Exception:
                pass
        else:
            if bytes_sec >= 1024 * 1024:
                disp = f"{bytes_sec / (1024*1024):.2f} MB/s"
            else:
                disp = f"{bytes_sec / 1024:.0f} KB/s"
            if hasattr(self, "lbl_active_limit"):
                self.lbl_active_limit.configure(text=tr("lbl_current_limit", "● Current: {limit}").format(limit=disp), fg=self.c_warning)
            if hasattr(self, "lbl_slider_val"):
                self.lbl_slider_val.configure(text=disp, fg=self.c_warning)
            if hasattr(self, "slider_speed"):
                self.slider_speed.set(min(20480, int(kb_val)))
            try:
                set_setting("custom_speed_limit_kbps", int(kb_val))
                if hasattr(self, "limit_preset_var") and self.limit_preset_var:
                    set_setting("speed_limit_preset", self.limit_preset_var.get())
            except Exception:
                pass

        engine = getattr(self, "engine", None)
        if engine and getattr(engine, "is_running", False):
            engine.set_speed_limit(bytes_sec)


__all__ = ["SpeedLimiterControllerMixin"]
