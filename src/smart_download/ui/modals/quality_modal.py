"""
QualitySelectionModal: Interactive video/audio resolution and stream format picker.
Includes compact embedded preview banner and support for unified VidMate-style preview.
"""
import os
import sys
try:
    import tkinter as tk
    from tkinter import ttk, filedialog
except Exception:
    tk = ttk = filedialog = None  # type: ignore
from typing import Optional, Callable, Dict, Any, List

from ...config import get_resource_path, get_base_downloads_dir
from ...locales.i18n import tr
from ...utils.file_ops import (
    CATEGORY_SUBFOLDERS,
    resolve_categorized_path,
    apply_media_filename_tags,
)
from ...services.youtube_service import VideoFormatOption, format_filesize
from ...utils.tk_helpers import _detach_photo_tk, animate_window_open, animate_window_close
from .quality_modal_helpers import (
    attach_selected_tracks_to_option,
    resolve_final_dest,
    build_preview_header_banner,
    resolve_preferred_option_index,
)

_BaseToplevel = tk.Toplevel if tk is not None else object

class QualitySelectionModal(_BaseToplevel):
    """Modern dark-themed modal dialog for choosing video quality, audio dubbing, and subtitle options."""

    def __init__(
        self,
        parent: Any,
        video_title: str,
        duration: int,
        options: List[VideoFormatOption],
        default_dest_path: str,
        theme: Dict[str, str],
        on_confirm: Callable[[VideoFormatOption, str], None],
        on_cancel: Optional[Callable[[], None]] = None,
        on_open_in_main: Optional[Callable[[VideoFormatOption, str], None]] = None,
        parent_app: Optional[Any] = None,
        audio_tracks: Optional[List[Dict[str, Any]]] = None,
        subtitle_tracks: Optional[List[Dict[str, Any]]] = None,
        video_url: str = "",
        raw_info: Optional[Dict[str, Any]] = None
    ):
        super().__init__(parent)
        self.video_title = str(video_title or "YouTube Video")
        self.duration = int(duration or 0)
        self.options = options or []
        self.dest_path = str(default_dest_path or "")
        self.theme = theme
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.on_open_in_main = on_open_in_main
        self.parent_app = parent_app
        self.audio_tracks = audio_tracks or []
        self.subtitle_tracks = subtitle_tracks or []
        self.video_url = str(video_url or "")
        self.raw_info = raw_info or {}
        self.cb_audio = None
        self.cb_sub = None
        init_idx = resolve_preferred_option_index(self.options)
        self.selected_option: Optional[VideoFormatOption] = self.options[init_idx] if (self.options and 0 <= init_idx < len(self.options)) else (self.options[0] if self.options else None)
        self._confirmed = False

        self.title(tr("modal_quality_title", "Select Video Quality — Smart Download"))
        self.configure(bg=self.theme["c_bg"])

        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        dpi_scale = max(1.0, dpi / 96.0)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        dlg_w, dlg_h = min(int(740 * dpi_scale), max(640, int(sw * 0.92))), min(int(620 * dpi_scale), max(520, int(sh * 0.88)))
        try:
            px, py = parent.winfo_x(), parent.winfo_y()
            pw, ph = parent.winfo_width() or dlg_w, parent.winfo_height() or dlg_h
            x, y = max(0, px + (pw - dlg_w) // 2), max(0, py + (ph - dlg_h) // 2)
            self.transient(parent)
        except Exception:
            x, y = max(0, (sw - dlg_w) // 2), max(0, (sh - dlg_h) // 2)
        self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
        self.minsize(min(640, dlg_w), min(520, dlg_h))

        ico_path, png_path = get_resource_path("app_icon.ico"), get_resource_path("app_icon.png")
        if os.path.isfile(ico_path):
            try: self.iconbitmap(ico_path)
            except Exception: pass
        if os.path.isfile(png_path):
            try:
                from PIL import ImageTk
                self._modal_icon_photo = ImageTk.PhotoImage(file=png_path)
                self.iconphoto(True, self._modal_icon_photo)
            except Exception: pass

        self._build_ui()
        animate_window_open(self, duration_ms=130)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())

        self._topmost_job = None
        self._idle_job = None
        try:
            self.lift()
            self.attributes("-topmost", True)
            self._topmost_job = self.after(250, lambda: self.attributes("-topmost", False) if self.winfo_exists() else None)
            self._idle_job = self.after_idle(lambda: (self.lift(), self.focus_force()) if self.winfo_exists() else None)
        except Exception:
            pass

    def _build_ui(self):
        c_bg, c_panel = self.theme["c_bg"], self.theme["c_panel"]
        c_panel_light, c_border = self.theme["c_panel_light"], self.theme["c_border"]
        c_accent, c_accent_dark = self.theme["c_accent"], self.theme["c_accent_dark"]
        c_success, c_text_bright = self.theme["c_success"], self.theme["c_text_bright"]
        c_text_muted, c_input_bg = self.theme["c_text_muted"], self.theme["c_input_bg"]

        outer = tk.Frame(self, bg=c_border, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        body = tk.Frame(outer, bg=c_bg, padx=16, pady=14)
        body.pack(fill=tk.BOTH, expand=True)

        lbl_head = tk.Label(body, text=tr("modal_quality_header", "🎥 SELECT VIDEO RESOLUTION & QUALITY"), font=("Segoe UI", 11, "bold"), bg=c_bg, fg=c_accent)
        lbl_head.pack(anchor="w", pady=(0, 6))

        # Compact embedded Preview Header Banner
        self.card_info, self.btn_banner_preview = build_preview_header_banner(
            parent_frame=body,
            theme=self.theme,
            video_title=self.video_title,
            duration=self.duration,
            options_count=len(self.options),
            video_url=self.video_url,
            on_preview_cmd=self._on_preview_video
        )

        table_frame = tk.Frame(body, bg=c_panel, highlightbackground=c_border, highlightthickness=1)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ("res", "ext", "size", "fps", "mode")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8, selectmode="browse", style="Custom.Treeview")

        for col, txt, anc, w in (
            ("res", tr("modal_col_res", "Resolution / Quality"), "w", 170),
            ("ext", tr("modal_col_ext", "Format"), "center", 70),
            ("size", tr("modal_col_size", "Est. Size"), "e", 100),
            ("fps", tr("modal_col_fps", "FPS"), "center", 55),
            ("mode", tr("modal_col_type", "Stream Details"), "w", 250),
        ):
            self.tree.heading(col, text=txt, anchor=anc)
            self.tree.column(col, width=w, anchor=anc)

        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._row_to_opt: Dict[str, VideoFormatOption] = {}
        for idx, opt in enumerate(self.options):
            iid = f"opt_{idx}"
            self._row_to_opt[iid] = opt
            fps_str = str(opt.fps) if opt.fps > 0 else "—"
            size_str = format_filesize(opt.filesize_approx)
            vals = (opt.resolution_label, opt.ext.upper(), size_str, fps_str, opt.note)
            self.tree.insert("", tk.END, iid=iid, values=vals)

        if self.options:
            init_idx = resolve_preferred_option_index(self.options)
            first_iid = f"opt_{init_idx}"
            self.tree.selection_set(first_iid)
            self.tree.focus(first_iid)
            self.tree.see(first_iid)
            self.after_idle(lambda: self.tree.see(first_iid) if self.winfo_exists() else None)
            if first_iid in self._row_to_opt:
                self.selected_option = self._row_to_opt[first_iid]

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-Button-1>", self._on_tree_double_click)

        # Audio & Subtitle selection row
        if self.audio_tracks or self.subtitle_tracks:
            from ...services.youtube_tracks import build_audio_subtitle_row
            self.cb_audio, self.cb_sub = build_audio_subtitle_row(
                body, self.theme, self.audio_tracks, self.subtitle_tracks
            )

        card_dest = tk.Frame(body, bg=c_panel, padx=12, pady=8, highlightbackground=c_border, highlightthickness=1)
        card_dest.pack(fill=tk.X, pady=(0, 12))

        lbl_dest = tk.Label(card_dest, text=tr("modal_save_to", "Save As:"), font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_bright)
        lbl_dest.pack(side=tk.LEFT)

        self.entry_dest = tk.Entry(card_dest, font=("Segoe UI", 9), bg=c_input_bg, fg=c_text_bright, insertbackground=c_accent, relief="flat")
        self.entry_dest.insert(0, self.dest_path)
        self.entry_dest.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8), ipady=3)

        if self.cb_sub and hasattr(self.cb_sub, "_mode_var"):
            def _on_sub_mode_modal_changed(*_):
                if hasattr(self, "entry_dest") and self.selected_option:
                    sub_mode = getattr(self.cb_sub, "_selected_mode", "soft_embed")
                    if hasattr(self.cb_sub, "get_selected_mode"): sub_mode = self.cb_sub.get_selected_mode()
                    cur = self.entry_dest.get().strip()
                    has_sub = bool(getattr(self.selected_option, "selected_subtitle_track", None))
                    updated = apply_media_filename_tags(
                        cur, quality_label=self.selected_option.resolution_label,
                        is_sub_burned=(sub_mode == "hard_burn") and has_sub, ext=self.selected_option.ext
                    )
                    self.entry_dest.delete(0, tk.END)
                    self.entry_dest.insert(0, updated)
                    if self.dest_path: self.dest_path = updated
            try: self.cb_sub._mode_var.trace_add("write", _on_sub_mode_modal_changed)
            except Exception:
                try: self.cb_sub._mode_var.trace("w", _on_sub_mode_modal_changed)
                except Exception: pass

        btn_browse = tk.Button(
            card_dest,
            text=tr("modal_btn_browse", "⋯ Browse..."),
            font=("Segoe UI", 8),
            bg=c_panel_light,
            fg=c_text_bright,
            relief="flat",
            activebackground=c_accent_dark,
            cursor="hand2",
            command=self._on_browse
        )
        btn_browse.pack(side=tk.RIGHT)
        if getattr(self, "options", None) and (first_iid != "opt_0" or (self.selected_option and f"[{self.selected_option.resolution_label}]" not in self.dest_path and "[" in self.dest_path)):
            self._on_tree_select(None)

        # Bottom Buttons
        btn_row = tk.Frame(body, bg=c_bg)
        btn_row.pack(fill=tk.X)

        self.btn_download = tk.Button(
            btn_row,
            text=tr("modal_btn_start_quality", "⚡ Download Selected Quality"),
            font=("Segoe UI", 9, "bold"),
            bg=c_success,
            fg="white",
            relief="flat",
            activebackground="#059669",
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._on_download
        )
        self.btn_download.pack(side=tk.LEFT)

        self.btn_download_mp3: Optional[tk.Button] = None
        has_audio = any(opt.is_audio_only for opt in self.options)
        if has_audio:
            self.btn_download_mp3 = tk.Button(
                btn_row,
                text=tr("modal_download_mp3", "🎵 Download MP3"),
                font=("Segoe UI", 9, "bold"),
                bg=c_accent_dark,
                fg="white",
                relief="flat",
                activebackground=c_accent,
                cursor="hand2",
                padx=16,
                pady=6,
                command=self._on_download_mp3
            )
            self.btn_download_mp3.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_preview_video = tk.Button(
            btn_row,
            text=tr("btn_preview_video", "🎬 Preview Video"),
            font=("Segoe UI", 9, "bold"),
            bg=c_panel_light,
            fg=c_accent,
            relief="flat",
            activebackground=c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=14,
            pady=6,
            command=self._on_preview_video
        )
        self.btn_preview_video.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_cancel = tk.Button(
            btn_row,
            text=tr("modal_btn_cancel", "✕ Cancel"),
            font=("Segoe UI", 9, "bold"),
            bg=c_panel_light,
            fg=c_text_muted,
            relief="flat",
            activebackground=c_border,
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._on_close
        )
        self.btn_cancel.pack(side=tk.RIGHT)

        self.btn_open_app = tk.Button(
            btn_row,
            text=tr("modal_btn_open_in_main", "📋 Open in Main App"),
            font=("Segoe UI", 9),
            bg=c_panel_light,
            fg=c_text_bright,
            relief="flat",
            activebackground=c_border,
            cursor="hand2",
            padx=14,
            pady=6,
            command=self._on_open_in_main
        )
        self.btn_open_app.pack(side=tk.RIGHT, padx=(0, 8))

    def _on_download_mp3(self):
        """One-click download as universal MP3 audio."""
        mp3_opt = next((o for o in self.options if o.is_audio_only and o.ext.lower() == "mp3"), None)
        if not mp3_opt:
            mp3_opt = next((o for o in self.options if o.is_audio_only), None)
        if not mp3_opt:
            return

        self.selected_option = mp3_opt
        for iid, opt in self._row_to_opt.items():
            if opt == mp3_opt:
                self.tree.selection_set(iid)
                self.tree.focus(iid)
                break

        cur_path = self.entry_dest.get().strip()
        target_path = cur_path or self.dest_path
        if target_path:
            base, _ = os.path.splitext(target_path)
            parent_dir = os.path.dirname(target_path)
            parent_base = os.path.basename(os.path.normpath(parent_dir)) if parent_dir else ""
            new_ext = ".mp3"
            sub_low = {v.lower() for v in CATEGORY_SUBFOLDERS.values()}
            if parent_base in CATEGORY_SUBFOLDERS.values() or parent_base.lower() in sub_low:
                updated_dest = resolve_categorized_path(parent_dir, os.path.basename(base) + new_ext, auto_categorize=True, create_dir=False)
            else:
                updated_dest = base + new_ext
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, updated_dest)
            self.dest_path = updated_dest

        self._on_download()

    def _on_tree_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if item and item in self._row_to_opt:
            self.tree.selection_set(item)
            self.selected_option = self._row_to_opt[item]
            self._on_tree_select(None)
        self._on_preview_video()

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        opt = self._row_to_opt.get(iid)
        if not opt:
            return
        self.selected_option = opt
        if event is not None and opt:
            try:
                from ...config import set_setting
                val_h = -1 if getattr(opt, "is_audio_only", False) else getattr(opt, "height", 0)
                set_setting("preferred_video_height", val_h)
            except Exception: pass

        cur_path = self.entry_dest.get().strip()
        target_path = cur_path or self.dest_path
        if target_path:
            sub_mode = "soft_embed"
            if hasattr(self, "cb_sub") and self.cb_sub:
                mode_fn = getattr(self.cb_sub, "get_selected_mode", None)
                sub_mode = mode_fn() if callable(mode_fn) else getattr(self.cb_sub, "_selected_mode", "soft_embed")
            has_sub = bool(getattr(opt, "selected_subtitle_track", None))
            updated_dest = apply_media_filename_tags(
                target_path,
                quality_label=opt.resolution_label,
                is_sub_burned=(sub_mode == "hard_burn") and has_sub,
                ext=opt.ext.lower()
            )
            parent_dir = os.path.dirname(updated_dest)
            parent_base = os.path.basename(os.path.normpath(parent_dir)) if parent_dir else ""
            subfolders_lower = {v.lower() for v in CATEGORY_SUBFOLDERS.values()}
            if parent_base in CATEGORY_SUBFOLDERS.values() or parent_base.lower() in subfolders_lower:
                updated_dest = resolve_categorized_path(parent_dir, os.path.basename(updated_dest), auto_categorize=True, create_dir=False)
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, updated_dest)
            if self.dest_path:
                self.dest_path = updated_dest

    def _on_browse(self):
        cur = self.entry_dest.get().strip()
        init_dir = os.path.dirname(cur) if cur else (getattr(self.parent_app, "_get_base_downloads_dir", get_base_downloads_dir)())
        init_file = os.path.basename(cur) if cur else "download.mp4"
        chosen = filedialog.asksaveasfilename(parent=self, title="Save Video As", initialdir=init_dir, initialfile=init_file)
        if chosen:
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, chosen)
            self.dest_path = chosen
            try:
                from ...config import set_setting
                cd = os.path.dirname(os.path.abspath(chosen))
                if getattr(self.parent_app, "auto_categorize_folders", True) and os.path.basename(cd).lower() in {s.lower() for s in CATEGORY_SUBFOLDERS.values()}:
                    cd = os.path.dirname(cd)
                set_setting("last_download_dir", cd)
            except Exception: pass

    def _attach_selected_tracks(self):
        attach_selected_tracks_to_option(self.selected_option, self.audio_tracks, self.cb_audio, self.subtitle_tracks, self.cb_sub)

    def _resolve_final_dest(self) -> str:
        return resolve_final_dest(self.entry_dest, self.dest_path, self.video_title, self.selected_option, self.parent_app, self.master)

    def _on_download(self):
        if not self.selected_option:
            return
        self._attach_selected_tracks()
        final_dest = self._resolve_final_dest()
        self._confirmed = True
        try: self.grab_release()
        except Exception: pass
        try: self.destroy()
        except Exception: pass
        self.on_confirm(self.selected_option, final_dest)

    def _on_preview_video(self):
        """Launches in-app VidMate-style preview with live dubbing, subtitles, and control bridge."""
        if not self.selected_option:
            return
        self._attach_selected_tracks()
        sel_sub = getattr(self.selected_option, "selected_subtitle_track", getattr(self.selected_option, "subtitle_track", None))
        if not sel_sub and hasattr(self, "cb_sub") and self.cb_sub and self.subtitle_tracks:
            idx = self.cb_sub.current()
            if 0 <= idx < len(self.subtitle_tracks):
                sel_sub = self.subtitle_tracks[idx]

        sel_audio = getattr(self.selected_option, "selected_audio_track", None)
        if not sel_audio and hasattr(self, "cb_audio") and self.cb_audio and self.audio_tracks:
            idx = self.cb_audio.current()
            if 0 <= idx < len(self.audio_tracks):
                sel_audio = self.audio_tracks[idx]

        q_idx = self.options.index(self.selected_option) if (self.selected_option and self.selected_option in self.options) else 0
        sub_pos = self.cb_sub.get_selected_pos() if (hasattr(self, "cb_sub") and self.cb_sub and hasattr(self.cb_sub, "get_selected_pos")) else "bottom"
        try:
            from .video_preview_modal import open_video_preview
            open_video_preview(
                parent=self,
                url=self.video_url,
                video_title=self.video_title,
                stream_info=self.selected_option,
                info_dict=self.raw_info,
                selected_sub_track=sel_sub,
                theme=self.theme,
                selected_audio_track=sel_audio,
                options=self.options,
                audio_tracks=self.audio_tracks,
                subtitle_tracks=self.subtitle_tracks,
                default_dest_path=self.entry_dest.get().strip() or self.dest_path,
                on_confirm=self.on_confirm,
                on_open_in_main=self.on_open_in_main,
                on_cancel=self.on_cancel,
                parent_app=self.parent_app,
                modal_ref=self,
                use_bridge=True,
                subtitle_embed_mode=getattr(self.selected_option, "subtitle_embed_mode", "hard_burn"),
                selected_q_idx=q_idx,
                subtitle_position=sub_pos,
            )
        except Exception:
            pass

    def launch_unified_preview(self):
        """Public helper to launch the unified preview and settings interface directly."""
        self._on_preview_video()

    def _on_open_in_main(self):
        if not self.selected_option:
            return
        self._attach_selected_tracks()
        has_sub = bool(getattr(self.selected_option, "selected_subtitle_track", None))
        is_sub_burned = (getattr(self.selected_option, "subtitle_embed_mode", "") == "hard_burn") and has_sub
        res_lbl = str(getattr(self.selected_option, "resolution_label", "") or "")
        import re
        has_tag = bool(re.search(r'(\d{3,4}p|4K|8K|Audio|MP3|M4A)', res_lbl, re.IGNORECASE))
        if has_tag or ("[" in (self.dest_path or "")) or ("[" in (self.entry_dest.get() or "")) or is_sub_burned:
            final_dest = self._resolve_final_dest()
        else:
            final_dest = self.entry_dest.get().strip() or self.dest_path
        self._confirmed = True
        try: self.grab_release()
        except Exception: pass
        try: self.destroy()
        except Exception: pass
        if self.on_open_in_main:
            try: self.on_open_in_main(self.selected_option, final_dest)
            except Exception: pass
        else:
            target = self.parent_app or self.master
            if target and hasattr(target, "restore_window"):
                try: target.restore_window()
                except Exception: pass

    def grab_set(self): pass
    def grab_set_global(self): pass

    def destroy(self):
        try: self.withdraw()
        except Exception: pass
        for a in ("_idle_job", "_topmost_job"):
            j = getattr(self, a, None)
            if j:
                try: self.after_cancel(j)
                except Exception: pass
                setattr(self, a, None)
        if hasattr(self, "_modal_icon_photo"):
            _detach_photo_tk(self._modal_icon_photo)
            self._modal_icon_photo = None
        try: self.grab_release()
        except Exception: pass
        if self.parent_app and getattr(self.parent_app, "_quality_modal", None) is self:
            self.parent_app._quality_modal = None
        super().destroy()

    def _on_close(self):
        if self.parent_app and getattr(self.parent_app, "_quality_modal", None) is self:
            self.parent_app._quality_modal = None
        def _cleanup():
            self.destroy()
            for host in (self.parent_app, self.master):
                if host and hasattr(host, "clear_last_clipboard_url"):
                    try: host.clear_last_clipboard_url()
                    except Exception: pass
            if self.on_cancel:
                try: self.on_cancel()
                except Exception: pass
        animate_window_close(self, on_done=_cleanup)
