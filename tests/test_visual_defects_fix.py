"""
Unit tests for visual defects fix:
1. TTK styles dark borders and no 3D bevels (TNotebook, Treeview, TFrame).
2. Rate limiter slider dark border (no white outline).
3. Clean BMP Unicode glyphs in UI and locales.
4. Arabic speed limiter preset localization ("بدون حد" / "Unlimited").
5. Polished dashboard metric cards.
"""
import unittest
import tkinter as tk
from tkinter import ttk
import json
import os

from smart_download.locales.i18n import LocalizationManager, tr, set_current_language
from smart_download.ui.main_window import ModernFramelessGUI
from smart_download.utils.speed_utils import parse_speed_limit


class TestVisualDefectsFix(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.loc = LocalizationManager.get_instance()
        self.loc.set_language("en")

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_part1_ttk_dark_borders_and_bevels(self):
        """Verifies TNotebook, Treeview, and TFrame have no white 3D bevels."""
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            # Check TNotebook
            nb_conf = gui.style.configure("TNotebook")
            self.assertEqual(nb_conf.get("background"), gui.c_bg)
            self.assertEqual(nb_conf.get("bordercolor"), gui.c_border)
            self.assertEqual(nb_conf.get("lightcolor"), gui.c_bg)
            self.assertEqual(nb_conf.get("darkcolor"), gui.c_bg)
            self.assertEqual(nb_conf.get("borderwidth"), 0)

            # Check TNotebook.Tab
            tab_conf = gui.style.configure("TNotebook.Tab")
            self.assertEqual(tab_conf.get("background"), gui.c_panel)
            self.assertEqual(tab_conf.get("bordercolor"), gui.c_border)
            self.assertEqual(tab_conf.get("lightcolor"), gui.c_panel)
            self.assertEqual(tab_conf.get("darkcolor"), gui.c_panel)

            # Check Treeview
            tv_conf = gui.style.configure("Treeview")
            self.assertEqual(tv_conf.get("background"), gui.c_input_bg)
            self.assertEqual(tv_conf.get("bordercolor"), gui.c_border)
            self.assertEqual(tv_conf.get("lightcolor"), gui.c_border)
            self.assertEqual(tv_conf.get("darkcolor"), gui.c_border)
            self.assertEqual(tv_conf.get("relief"), "flat")

            # Check Treeview.Heading
            hd_conf = gui.style.configure("Treeview.Heading")
            self.assertEqual(hd_conf.get("background"), "#182338")
            self.assertEqual(hd_conf.get("lightcolor"), "#182338")
            self.assertEqual(hd_conf.get("darkcolor"), "#182338")
            self.assertEqual(hd_conf.get("relief"), "flat")

            # Check TFrame
            tf_conf = gui.style.configure("TFrame")
            self.assertEqual(tf_conf.get("background"), gui.c_panel)
            self.assertEqual(tf_conf.get("bordercolor"), gui.c_border)
            self.assertEqual(tf_conf.get("lightcolor"), gui.c_panel)
            self.assertEqual(tf_conf.get("darkcolor"), gui.c_panel)

            # Check TNotebook.client and Notebook.client
            cl_conf = gui.style.configure("TNotebook.client")
            self.assertEqual(cl_conf.get("background"), gui.c_panel)
            self.assertEqual(cl_conf.get("bordercolor"), gui.c_border)
            self.assertEqual(cl_conf.get("lightcolor"), gui.c_panel)
            self.assertEqual(cl_conf.get("darkcolor"), gui.c_panel)

            cl_base = gui.style.configure("Notebook.client")
            self.assertEqual(cl_base.get("background"), gui.c_panel)
            self.assertEqual(cl_base.get("bordercolor"), gui.c_border)

            # Check Treeview layout (stripped 3D field border)
            tv_layout = gui.style.layout("Treeview")
            self.assertEqual(tv_layout, [("Treeview.treearea", {"sticky": "nswe"})])
            tv_custom_layout = gui.style.layout("Custom.Treeview")
            self.assertEqual(tv_custom_layout, [("Custom.Treeview.treearea", {"sticky": "nswe"})])

            # Check notebook tab frame 1px border
            tab0 = gui.root.nametowidget(gui.notebook.tabs()[0])
            self.assertEqual(tab0.cget("highlightthickness"), 1)
            self.assertEqual(tab0.cget("highlightbackground"), gui.c_border)
            self.assertEqual(tab0.cget("bd"), 0)

            # Check inputs panel label widths (Part 1 fix)
            self.assertEqual(gui.lbl_url.cget("width"), 14)
            self.assertEqual(gui.lbl_dest.cget("width"), 14)
        finally:
            gui.exit_completely()

    def test_part2_speed_slider_dark_border(self):
        """Verifies tk.Scale slider has no white/grey border."""
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            slider = gui.slider_speed
            self.assertEqual(slider.cget("highlightthickness"), 1)
            self.assertEqual(slider.cget("highlightbackground"), gui.c_border)
            self.assertEqual(slider.cget("highlightcolor"), gui.c_accent)
            self.assertEqual(slider.cget("bd"), 0)
            self.assertEqual(slider.cget("relief"), "flat")
            self.assertEqual(slider.cget("sliderrelief"), "flat")
            self.assertEqual(slider.cget("bg"), gui.c_panel)
            self.assertEqual(slider.cget("troughcolor"), gui.c_input_bg)
        finally:
            gui.exit_completely()

    def test_part3_clean_bmp_glyphs(self):
        """Verifies broken Tcl/Tk supplementary-plane emojis are eliminated."""
        # Check ar.json and en.json for banned SMP emojis
        banned = ["\u23f8", "\u23f9", "\U0001f504", "\U0001f4ca", "\U0001f39e"]  # ⏸, ⏹, 🔄, 📊, 🎞
        main_window_keys = [
            "lbl_live_throttle_slider",
            "btn_paste",
            "btn_browse",
            "btn_sniffer_active",
            "btn_sniffer_paused",
            "btn_auto_cat_on",
            "btn_auto_cat_off",
            "btn_cookies_prefix",
            "btn_startup_on",
            "btn_startup_off",
            "btn_browser",
            "btn_lang_toggle",
            "btn_pause",
            "btn_pause_all",
            "ctx_pause_download",
            "btn_hist_open",
            "btn_hist_folder",
            "btn_hist_remove",
            "btn_hist_clear",
            "btn_clear_completed",
            "ctx_remove_history",
            "ctx_copy_download_url",
        ]
        for lang, path in [("ar", "src/smart_download/locales/ar.json"), ("en", "src/smart_download/locales/en.json")]:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, val in data.items():
                for b in banned:
                    self.assertNotIn(b, val, f"Banned emoji {b!r} found in {lang}.json key '{k}': '{val}'")

            # Verify specific required BMP glyphs
            self.assertIn("||", data["btn_pause"])
            self.assertIn("||", data["btn_pause_all"])
            self.assertIn("✕", data["btn_cancel"])
            self.assertIn("↻", data["btn_refresh_url"])
            self.assertIn("⚙", data["btn_quality_reopen"])
            self.assertIn("▦", data["lbl_chunk_vis_title"])
            self.assertIn("▦", data["tab_chunks"])
            self.assertIn("▤", data["tab_logs"])
            self.assertIn("☰", data["tab_history"])
            self.assertIn("↻", data["btn_check_updates"])
            self.assertIn("↻", data["btn_hist_redownload"])
            self.assertIn("||", data["ctx_pause_download"])
            self.assertIn("✕", data["ctx_cancel_download"])
            self.assertIn("↻", data["ctx_resume_retry"])
            self.assertIn("↻", data["ctx_refresh_address"])
            self.assertIn("✕", data["browser_btn_stop_server"])
            self.assertIn("↻", data["browser_btn_reregister"])

            # Verify that none of the main window keys contain supplementary-plane characters
            for mk in main_window_keys:
                self.assertIn(mk, data, f"Key '{mk}' missing from {lang}.json")
                for ch in data[mk]:
                    self.assertLessEqual(
                        ord(ch),
                        0xFFFF,
                        f"Supplementary-plane char {ch!r} (U+{ord(ch):04X}) found in {lang}.json key '{mk}'"
                    )

    def test_part4_speed_limiter_localization(self):
        """Verifies speed limiter dropdown options localize and switch seamlessly."""
        self.loc.set_language("ar")
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            # First preset must be "بدون حد" in Arabic
            values_ar = gui.combo_speed["values"]
            self.assertEqual(values_ar[0], "بدون حد")
            self.assertEqual(gui.speed_preset_var.get(), "بدون حد")
            self.assertEqual(gui.speed_limit, 0.0)

            # Test parse_speed_limit
            self.assertEqual(parse_speed_limit("بدون حد"), 0.0)
            self.assertEqual(parse_speed_limit("Unlimited"), 0.0)

            # Switch language to English
            gui.btn_lang_toggle.invoke()
            self.assertEqual(self.loc.get_language(), "en")
            values_en = gui.combo_speed["values"]
            self.assertEqual(values_en[0], "Unlimited")
            self.assertEqual(gui.speed_preset_var.get(), "Unlimited")
            self.assertEqual(gui.speed_limit, 0.0)

            # Switch back to Arabic
            gui.btn_lang_toggle.invoke()
            self.assertEqual(self.loc.get_language(), "ar")
            self.assertEqual(gui.speed_preset_var.get(), "بدون حد")

            # Selecting "بدون حد" via preset event
            gui.speed_preset_var.set("بدون حد")
            gui._on_speed_preset_change()
            self.assertEqual(gui.speed_limit, 0.0)
            self.assertEqual(gui.slider_speed.get(), 0)

            # Selecting "1 MB/s"
            gui.speed_preset_var.set("1 MB/s")
            gui._on_speed_preset_change()
            self.assertEqual(gui.speed_limit, 1024 * 1024.0)
            self.assertEqual(gui.slider_speed.get(), 1024)

            # Selecting "بدون حد" again
            gui.speed_preset_var.set("بدون حد")
            gui._on_speed_preset_change()
            self.assertEqual(gui.speed_limit, 0.0)
            self.assertEqual(gui.slider_speed.get(), 0)
        finally:
            gui.exit_completely()

    def test_part5_metric_cards_styling(self):
        """Verifies 4 dashboard metric cards styling and colors."""
        gui = ModernFramelessGUI(self.root, start_hidden=True)
        try:
            # 4 cards
            cards = [gui.card_speed, gui.card_size, gui.card_eta, gui.card_threads]
            for i, card in enumerate(cards):
                box = card.master
                self.assertEqual(box.cget("bg"), "#0d1526")
                self.assertEqual(box.cget("highlightthickness"), 1)
                self.assertEqual(box.cget("highlightbackground"), gui.c_border)

                lbl_t = box.lbl_t
                self.assertEqual(lbl_t.cget("bg"), "#0d1526")
                self.assertEqual(lbl_t.cget("fg"), gui.c_text_muted)

                self.assertEqual(card.cget("bg"), "#0d1526")
                if i == 0:
                    # Speed card highlighted in accent color
                    self.assertEqual(card.cget("fg"), gui.c_accent)
                else:
                    self.assertEqual(card.cget("fg"), gui.c_text_bright)
        finally:
            gui.exit_completely()

    def test_part6_headless_guard(self):
        """Verifies tk_helpers and controls_panel gracefully handle headless tk=None environments."""
        import sys
        import subprocess
        import smart_download.utils.tk_helpers as tkh
        import smart_download.ui.panels.controls_panel as cp
        self.assertTrue(hasattr(tkh, "_safe_winfo_exists"))
        self.assertTrue(issubclass(cp._StateButton, (tk.Button, object)))

        cmd = [
            sys.executable,
            "-c",
            "import sys; sys.modules['tkinter'] = None; import turbo_downloader; "
            "from smart_download.utils import tk_helpers; from smart_download.ui.panels import controls_panel; "
            "assert controls_panel._BaseButton is object; assert tk_helpers._ORIG_MISC_DESTROY is None; "
            "print('HEADLESS_OK')"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Headless import failed: {res.stderr}")
        self.assertIn("HEADLESS_OK", res.stdout)


if __name__ == "__main__":
    unittest.main()
