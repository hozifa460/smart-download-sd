"""
Tests for Windows High-DPI Awareness, UI Scaling, and Application Assets
"""
import os
import tempfile
os.environ["SD_DISABLE_SYSTEM_TRAY"] = "1"
os.environ["SD_DISABLE_STARTUP_TOAST"] = "1"
os.environ["SD_DISABLE_AUTO_UPDATE"] = "1"
os.environ["SD_LANGUAGE"] = "en"
if not os.environ.get("SD_CONFIG_DIR"):
    _sd_test_cfg = os.path.join(tempfile.gettempdir(), "sd_test_isolated_cfg")
    os.makedirs(_sd_test_cfg, exist_ok=True)
    os.environ["SD_CONFIG_DIR"] = _sd_test_cfg

import sys
import unittest
import tkinter as tk
from PIL import Image

import turbo_downloader
from turbo_downloader import (
    enable_high_dpi_awareness,
    get_resource_path,
    ModernFramelessGUI,
    SafeModalDialog,
    QualitySelectionModal,
    LocalizationManager,
    set_setting
)


def setUpModule():
    os.environ["SD_LANGUAGE"] = "en"
    try:
        set_setting("language", "en")
        LocalizationManager.reset_instance("en")
    except Exception:
        pass


def tearDownModule():
    try:
        LocalizationManager.reset_instance()
    except Exception:
        pass


class TestDPIAndAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        enable_high_dpi_awareness()

    def test_enable_high_dpi_awareness_idempotent(self):
        """Verify calling enable_high_dpi_awareness multiple times does not raise or crash."""
        try:
            enable_high_dpi_awareness()
            enable_high_dpi_awareness()
        except Exception as e:
            self.fail(f"enable_high_dpi_awareness raised unexpectedly: {e}")

    def test_app_icon_ico_exists_and_multiresolution(self):
        """Verify app_icon.ico contains all required Windows standard & high-DPI resolutions."""
        ico_path = get_resource_path("app_icon.ico")
        self.assertTrue(os.path.isfile(ico_path), f"app_icon.ico missing at {ico_path}")
        with Image.open(ico_path) as im:
            self.assertEqual(im.format, "ICO")
            sizes = im.info.get("sizes")
            self.assertIsNotNone(sizes)
            expected = {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}
            self.assertTrue(expected.issubset(sizes), f"Expected sizes {expected} not in {sizes}")

    def test_app_icon_png_exists_and_hires(self):
        """Verify app_icon.png is 256x256 RGBA."""
        png_path = get_resource_path("app_icon.png")
        self.assertTrue(os.path.isfile(png_path), f"app_icon.png missing at {png_path}")
        with Image.open(png_path) as im:
            self.assertEqual(im.size, (256, 256))
            self.assertEqual(im.mode, "RGBA")

    def test_extension_icons_exist(self):
        """Verify extension icons (16, 48, 128) are present and valid."""
        for sz in [16, 48, 128]:
            p = os.path.join("extension", "icons", f"icon{sz}.png")
            self.assertTrue(os.path.isfile(p), f"Extension icon missing: {p}")
            with Image.open(p) as im:
                self.assertEqual(im.size, (sz, sz))

    def test_gui_dpi_scaling_attributes(self):
        """Verify ModernFramelessGUI calculates dpi and dpi_scale properly."""
        root = tk.Tk()
        gui = ModernFramelessGUI(root)
        try:
            self.assertTrue(hasattr(gui, "dpi"))
            self.assertTrue(hasattr(gui, "dpi_scale"))
            self.assertGreaterEqual(gui.dpi, 72.0)
            self.assertGreaterEqual(gui.dpi_scale, 1.0)
            self.assertGreaterEqual(gui.width, 850)
            self.assertGreaterEqual(gui.height, 650)
            # Verify canvas heights scaled
            self.assertGreaterEqual(int(gui.canvas_prog.cget("height")), 22)
            self.assertGreaterEqual(int(gui.canvas_chunks.cget("height")), 30)
        finally:
            gui._cleanup_resources()
            try:
                root.destroy()
            except Exception:
                pass

    def test_safe_modal_dpi_scaling(self):
        """Verify SafeModalDialog dimensions scale with DPI."""
        root = tk.Tk()
        try:
            dlg = SafeModalDialog(root, title="Test Modal", message="Test Message", dialog_type="info")
            root.update()
            self.assertTrue(dlg.winfo_exists())
            self.assertGreater(dlg.winfo_width(), 0)
            self.assertGreater(dlg.winfo_height(), 0)
            dlg._on_ok()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_quality_modal_dpi_scaling_and_icon(self):
        """Verify QualitySelectionModal geometry and icon setup."""
        from turbo_downloader import VideoFormatOption
        root = tk.Tk()
        options = [
            VideoFormatOption(format_id="18", resolution_label="360p", height=360, ext="mp4", filesize_approx=1000000)
        ]
        theme = {
            "c_bg": "#0f172a",
            "c_panel": "#1e293b",
            "c_panel_light": "#334155",
            "c_border": "#475569",
            "c_accent": "#38bdf8",
            "c_accent_dark": "#0284c7",
            "c_success": "#10b981",
            "c_text_bright": "#f8fafc",
            "c_text_muted": "#94a3b8",
            "c_input_bg": "#090d16"
        }
        try:
            modal = QualitySelectionModal(root, "Test Video", 120, options, "test.mp4", theme, lambda opt, dest: None)
            root.update()
            self.assertTrue(modal.winfo_exists())
            self.assertGreaterEqual(modal.winfo_width(), 500)
            self.assertGreaterEqual(modal.winfo_height(), 400)
            modal._on_close()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_browser_integration_dialog_dpi_scaling_and_icon(self):
        """Verify _open_browser_integration_dialog opens with scaled geometry and closes cleanly."""
        root = tk.Tk()
        gui = ModernFramelessGUI(root)
        try:
            gui._open_browser_integration_dialog()
            root.update()
            # Find the toplevel
            top = None
            for child in root.winfo_children():
                if isinstance(child, tk.Toplevel):
                    top = child
                    break
            self.assertIsNotNone(top, "Browser integration dialog toplevel not found")
            self.assertTrue(top.winfo_exists())
            self.assertGreaterEqual(top.winfo_width(), 550)
            self.assertGreaterEqual(top.winfo_height(), 450)
            top.destroy()
        finally:
            gui._cleanup_resources()
            try:
                root.destroy()
            except Exception:
                pass

    def test_treeview_column_scaling_and_typography(self):
        """Verify treeview columns scale with dpi_scale."""
        root = tk.Tk()
        gui = ModernFramelessGUI(root)
        try:
            expected_range_w = max(200, int(250 * gui.dpi_scale))
            actual_w = gui.tree_chunks.column("range", "width")
            self.assertEqual(actual_w, expected_range_w)
            self.assertEqual(gui.txt_log.cget("font"), "Consolas 9")
        finally:
            gui._cleanup_resources()
            try:
                root.destroy()
            except Exception:
                pass

    def test_throttle_slider_scaling(self):
        """Verify dynamic slider length and width scale with DPI."""
        root = tk.Tk()
        gui = ModernFramelessGUI(root)
        try:
            expected_len = max(20, int(22 * gui.dpi_scale))
            expected_w = max(14, int(16 * gui.dpi_scale))
            self.assertEqual(int(gui.slider_speed.cget("sliderlength")), expected_len)
            self.assertEqual(int(gui.slider_speed.cget("width")), expected_w)
        finally:
            gui._cleanup_resources()
            try:
                root.destroy()
            except Exception:
                pass

    def test_resource_cleanup_on_destroy_event(self):
        """Verify destroying root directly automatically triggers _cleanup_resources and closes bridge server."""
        root = tk.Tk()
        gui = ModernFramelessGUI(root)
        server = gui.bridge_server
        self.assertTrue(server.is_running)
        root.destroy()
        self.assertTrue(gui._closing)
        self.assertIsNone(gui._refresh_job)
        self.assertFalse(server.is_running)

if __name__ == "__main__":
    unittest.main()
