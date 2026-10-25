"""
InstallerWizardGUI / InstallerGUI: Sleek modern Tkinter wizard for Smart Download setup & uninstaller.
"""
import os
import sys
import threading
import subprocess
import weakref
from typing import Dict, List, Optional, Callable, Any

from .installer_ops import (
    APP_NAME,
    APP_ID,
    APP_VERSION,
    DEFAULT_INSTALL_DIR,
    find_payload_sources,
    enable_high_dpi_awareness,
    install_application,
    uninstall_application,
)

class InstallerGUI:
    """Modern dark-themed Tkinter installer and uninstaller interface."""

    def __init__(self, root, mode: str = "install", target_dir: str = DEFAULT_INSTALL_DIR):
        self.root = root
        self.mode = mode  # "install" or "uninstall"
        self.target_dir = target_dir
        self.launch_after = True

        enable_high_dpi_awareness()

        # Modern Dark Color Palette
        self.BG_MAIN = "#18191c"
        self.BG_CARD = "#222428"
        self.BG_INPUT = "#131417"
        self.TEXT_MAIN = "#ffffff"
        self.TEXT_MUTED = "#9da5b4"
        self.ACCENT = "#0078d4"
        self.ACCENT_HOVER = "#106ebe"
        self.SUCCESS = "#00c853"
        self.DANGER = "#e81123"
        self.BORDER = "#333842"

        self.root.title(f"{APP_NAME} Setup" if mode == "install" else f"{APP_NAME} Uninstall")
        self.root.configure(bg=self.BG_MAIN)
        self.root.resizable(False, False)

        # High DPI Window Size
        scale = 1.0
        try:
            dpi = self.root.winfo_fpixels('1i')
            scale = max(1.0, dpi / 96.0)
        except Exception:
            pass
        self.scale = scale

        width = int(580 * scale)
        height = int(460 * scale)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - width) // 2
        y = (sh - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # Set Window Icon
        sources = find_payload_sources()
        ico = sources.get("app_icon.ico", "")
        if ico and os.path.isfile(ico):
            try:
                self.root.iconbitmap(ico)
            except Exception:
                pass

        self.is_running = False
        self._closing = False
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        try:
            self.root.bind("<Destroy>", self._on_root_destroyed, add="+")
        except Exception:
            pass
        self._build_ui()

    def _on_root_destroyed(self, event=None):
        if event is None or getattr(event, "widget", None) == self.root:
            for attr in ("var_dir", "var_desktop", "var_startmenu", "var_startup", "var_browser", "var_launch"):
                v = getattr(self, attr, None)
                if v is not None and hasattr(v, "_tk"):
                    v._tk = None

    def _on_window_close(self):
        if getattr(self, "is_running", False):
            return
        self._closing = True
        try:
            self.root.destroy()
        except Exception:
            pass

    def _build_ui(self):
        import tkinter as tk
        from tkinter import ttk

        # Custom ttk styles
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.Horizontal.TProgressbar",
                        troughcolor=self.BG_CARD,
                        background=self.ACCENT,
                        lightcolor=self.ACCENT,
                        darkcolor=self.ACCENT,
                        bordercolor=self.BORDER)

        self.container = tk.Frame(self.root, bg=self.BG_MAIN)
        self.container.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        # Header Frame
        header = tk.Frame(self.container, bg=self.BG_MAIN)
        header.pack(fill=tk.X, pady=(0, 16))

        title_text = f"Install {APP_NAME}" if self.mode == "install" else f"Uninstall {APP_NAME}"
        lbl_title = tk.Label(header, text=title_text, font=("Segoe UI", 16, "bold"),
                             bg=self.BG_MAIN, fg=self.TEXT_MAIN)
        lbl_title.pack(anchor="w")

        sub_text = "Fast, Resumable Multi-Chunk Download Accelerator" if self.mode == "install" \
            else "Cleanly remove application, browser integration, and shortcuts"
        lbl_sub = tk.Label(header, text=sub_text, font=("Segoe UI", 9),
                           bg=self.BG_MAIN, fg=self.TEXT_MUTED)
        lbl_sub.pack(anchor="w", pady=(2, 0))

        # Dynamic Content Frame
        self.content_frame = tk.Frame(self.container, bg=self.BG_CARD, bd=1, relief="solid")
        self.content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 16))

        if self.mode == "install":
            self._render_install_options()
        else:
            self._render_uninstall_options()

        # Footer Frame
        self.footer = tk.Frame(self.container, bg=self.BG_MAIN)
        self.footer.pack(fill=tk.X)

        self.btn_cancel = tk.Button(self.footer, text="Cancel", font=("Segoe UI", 9),
                                    bg=self.BG_CARD, fg=self.TEXT_MAIN, activebackground=self.BORDER,
                                    activeforeground=self.TEXT_MAIN, bd=0, padx=16, pady=6,
                                    cursor="hand2", command=self.root.destroy)
        self.btn_cancel.pack(side=tk.RIGHT, padx=(8, 0))

        action_btn_text = "Install Now" if self.mode == "install" else "Uninstall"
        action_color = self.ACCENT if self.mode == "install" else self.DANGER
        self.btn_action = tk.Button(self.footer, text=action_btn_text, font=("Segoe UI", 9, "bold"),
                                    bg=action_color, fg="#ffffff", activebackground=self.ACCENT_HOVER,
                                    activeforeground="#ffffff", bd=0, padx=20, pady=6,
                                    cursor="hand2", command=self._start_action)
        self.btn_action.pack(side=tk.RIGHT)

    def _render_install_options(self):
        import tkinter as tk
        from tkinter import filedialog

        for w in self.content_frame.winfo_children():
            w.destroy()

        pad_f = tk.Frame(self.content_frame, bg=self.BG_CARD)
        pad_f.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # Destination Folder
        lbl_dir = tk.Label(pad_f, text="Destination Folder (User-Level / Zero UAC Elevation):",
                           font=("Segoe UI", 9, "bold"), bg=self.BG_CARD, fg=self.TEXT_MAIN)
        lbl_dir.pack(anchor="w", pady=(0, 6))

        dir_box = tk.Frame(pad_f, bg=self.BG_INPUT, bd=1, relief="solid")
        dir_box.pack(fill=tk.X, pady=(0, 14))

        self.var_dir = tk.StringVar(value=self.target_dir)
        self.entry_dir = tk.Entry(dir_box, textvariable=self.var_dir, font=("Segoe UI", 9),
                                  bg=self.BG_INPUT, fg=self.TEXT_MAIN, insertbackground=self.TEXT_MAIN,
                                  bd=0, relief="flat")
        self.entry_dir.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=6)

        def _browse():
            chosen = filedialog.askdirectory(initialdir=self.var_dir.get(), title="Select Install Folder")
            if chosen:
                self.var_dir.set(chosen)

        btn_browse = tk.Button(dir_box, text="Browse...", font=("Segoe UI", 8),
                               bg=self.BORDER, fg=self.TEXT_MAIN, bd=0, padx=10, pady=2,
                               cursor="hand2", command=_browse)
        btn_browse.pack(side=tk.RIGHT, padx=4, pady=3)

        # Options Checkboxes
        self.var_desktop = tk.BooleanVar(value=True)
        self.var_startmenu = tk.BooleanVar(value=True)
        self.var_startup = tk.BooleanVar(value=True)
        self.var_browser = tk.BooleanVar(value=True)
        self.var_launch = tk.BooleanVar(value=True)

        for text, var in [
            ("Create Desktop Shortcut", self.var_desktop),
            ("Create Start Menu Shortcut", self.var_startmenu),
            ("Start Smart Download on Windows startup (Silent background)", self.var_startup),
            ("Enable Chrome & Microsoft Edge Browser Integration", self.var_browser),
            (f"Launch {APP_NAME} after installation", self.var_launch)
        ]:
            cb = tk.Checkbutton(pad_f, text=text, variable=var, font=("Segoe UI", 9),
                                bg=self.BG_CARD, fg=self.TEXT_MAIN, selectcolor=self.BG_INPUT,
                                activebackground=self.BG_CARD, activeforeground=self.TEXT_MAIN,
                                bd=0, highlightthickness=0)
            cb.pack(anchor="w", pady=3)

    def _render_uninstall_options(self):
        import tkinter as tk
        for w in self.content_frame.winfo_children():
            w.destroy()

        pad_f = tk.Frame(self.content_frame, bg=self.BG_CARD)
        pad_f.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)

        lbl_warn = tk.Label(pad_f, text=f"Are you sure you want to completely uninstall {APP_NAME}?",
                            font=("Segoe UI", 11, "bold"), bg=self.BG_CARD, fg=self.TEXT_MAIN, wraplength=480, justify="left")
        lbl_warn.pack(anchor="w", pady=(0, 12))

        desc = (
            f"This will remove the application from:\n{self.target_dir}\n\n"
            "It will also:\n"
            "• Unregister Chrome & Microsoft Edge Native Messaging Host\n"
            "• Remove Desktop and Start Menu shortcuts\n"
            "• Remove Windows 'Installed Apps' entry"
        )
        lbl_desc = tk.Label(pad_f, text=desc, font=("Segoe UI", 9),
                            bg=self.BG_CARD, fg=self.TEXT_MUTED, justify="left")
        lbl_desc.pack(anchor="w")

    def _render_progress_screen(self):
        import tkinter as tk
        from tkinter import ttk

        for w in self.content_frame.winfo_children():
            w.destroy()

        pad_f = tk.Frame(self.content_frame, bg=self.BG_CARD)
        pad_f.pack(fill=tk.BOTH, expand=True, padx=24, pady=32)

        title = "Installing..." if self.mode == "install" else "Uninstalling..."
        lbl_st = tk.Label(pad_f, text=title, font=("Segoe UI", 12, "bold"),
                          bg=self.BG_CARD, fg=self.TEXT_MAIN)
        lbl_st.pack(anchor="w", pady=(0, 12))

        self.progress_bar = ttk.Progressbar(pad_f, orient="horizontal", mode="determinate",
                                            style="Dark.Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))

        self.lbl_detail = tk.Label(pad_f, text="Initializing...", font=("Segoe UI", 9),
                                   bg=self.BG_CARD, fg=self.TEXT_MUTED)
        self.lbl_detail.pack(anchor="w")

    def _render_completed_screen(self, success: bool, message: str, exe_path: str = ""):
        import tkinter as tk

        for w in self.content_frame.winfo_children():
            w.destroy()

        pad_f = tk.Frame(self.content_frame, bg=self.BG_CARD)
        pad_f.pack(fill=tk.BOTH, expand=True, padx=24, pady=36)

        color = self.SUCCESS if success else self.DANGER
        header = "Completed Successfully!" if success else "Operation Failed"
        lbl_h = tk.Label(pad_f, text=header, font=("Segoe UI", 15, "bold"),
                         bg=self.BG_CARD, fg=color)
        lbl_h.pack(anchor="w", pady=(0, 10))

        lbl_m = tk.Label(pad_f, text=message, font=("Segoe UI", 9),
                         bg=self.BG_CARD, fg=self.TEXT_MAIN, wraplength=480, justify="left")
        lbl_m.pack(anchor="w", pady=(0, 16))

        # Update Buttons
        self.btn_cancel.pack_forget()
        self.btn_action.config(text="Finish", bg=self.ACCENT, command=lambda: self._on_finish(exe_path))

    def _start_action(self):
        self.is_running = True
        self.btn_action.config(state="disabled")
        self.btn_cancel.config(state="disabled")
        target = self.var_dir.get().strip() if self.mode == "install" else self.target_dir
        create_desktop = bool(self.var_desktop.get()) if self.mode == "install" else False
        create_start_menu = bool(self.var_startmenu.get()) if self.mode == "install" else False
        register_browser = bool(self.var_browser.get()) if self.mode == "install" else False
        register_startup = bool(self.var_startup.get()) if self.mode == "install" else False
        if self.mode == "install":
            self.launch_after = bool(self.var_launch.get())
        self._render_progress_screen()

        import weakref
        weak_self = weakref.ref(self)

        def _bg_worker():
            def _cb(pct, msg):
                g = weak_self()
                if g is not None and not getattr(g, "_closing", False):
                    try:
                        g.root.after(0, lambda: (weak_self() and weak_self()._update_progress(pct, msg)))
                    except Exception:
                        pass

            try:
                if self.mode == "install":
                    res = install_application(
                        target_dir=target,
                        create_desktop=create_desktop,
                        create_start_menu=create_start_menu,
                        register_browser=register_browser,
                        register_startup=register_startup,
                        progress_cb=_cb
                    )
                    g = weak_self()
                    if g is not None and not getattr(g, "_closing", False):
                        g.root.after(0, lambda: (weak_self() and weak_self()._render_completed_screen(
                            res.get("success", False),
                            f"{APP_NAME} has been successfully installed on your computer.",
                            res.get("exe_path", "")
                        )))
                    del g
                else:
                    res = uninstall_application(
                        target_dir=target,
                        progress_cb=_cb
                    )
                    g = weak_self()
                    if g is not None and not getattr(g, "_closing", False):
                        g.root.after(0, lambda: (weak_self() and weak_self()._render_completed_screen(
                            res.get("success", False),
                            f"{APP_NAME} has been completely removed from your computer."
                        )))
                    del g
            finally:
                g = weak_self()
                if g is not None:
                    g.is_running = False
                del g

        threading.Thread(target=_bg_worker, daemon=True).start()

    def _update_progress(self, pct: float, msg: str):
        try:
            self.progress_bar["value"] = int(pct * 100)
            self.lbl_detail.config(text=msg)
        except Exception:
            pass

    def _on_finish(self, exe_path: str):
        if self.mode == "install" and self.launch_after and exe_path and os.path.isfile(exe_path):
            try:
                subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
            except Exception:
                pass
        self.root.destroy()




InstallerWizardGUI = InstallerGUI
