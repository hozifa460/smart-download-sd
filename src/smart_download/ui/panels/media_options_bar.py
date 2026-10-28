"""
MediaOptionsBarMixin: Main-window media format, dubbing audio, and subtitle options bar.
Provides dynamic Quality, Audio track, Subtitle track, and Subtitle mode selectors directly in the GUI.
"""
import os
import copy
import threading
from typing import Optional, Dict, Any, List

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore

from smart_download.i18n import tr
from smart_download.config import get_setting, set_setting, get_base_downloads_dir
from smart_download.utils.file_ops import (
    apply_media_filename_tags,
    generate_unique_destination_path,
)
from smart_download.services.youtube_service import (
    VideoFormatOption,
    YouTubeResolver,
    format_filesize,
    sanitize_filename,
    is_media_url,
)
from smart_download.services.youtube_tracks import (
    extract_audio_tracks,
    extract_subtitle_tracks,
)
from ..modals.quality_modal import QualitySelectionModal
from ..modals.confirm_modal import DownloadConfirmationModal
from ..modals.quality_modal_helpers import resolve_preferred_option_index


class MediaOptionsBarMixin:
    """
    Mixin providing the Main Window Media Settings Bar.
    Enables users to adjust Quality, Audio dubbing, Subtitles, and Subtitle delivery mode
    directly from the main application window and re-download media with different settings.
    """

    def _build_media_options_bar(self, parent_card):
        """Constructs sleek themed frame for video quality, dubbing, and subtitle settings."""
        if tk is None or ttk is None:
            return

        self.media_options_frame = tk.Frame(parent_card, bg=self.c_panel)
        # Initially not packed; shown when media format options are populated
        self._main_media_options: List[VideoFormatOption] = []
        self._main_audio_tracks: List[Dict[str, Any]] = []
        self._main_subtitle_tracks: List[Dict[str, Any]] = []
        self._main_sub_mode_codes = ["soft_embed", "srt_only", "hard_burn"]
        self._pending_media_context: Optional[Dict[str, Any]] = None
        self._last_yt_info: Optional[Dict[str, Any]] = None

        # Row 1: Quality (Combobox), Audio/Dubbing (Combobox), Reopen Modal Button
        row1 = tk.Frame(self.media_options_frame, bg=self.c_panel)
        row1.pack(fill=tk.X, pady=(4, 2))
        self.lbl_main_quality = tk.Label(row1, text=tr("lbl_main_quality", "🎞️ Quality:"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=10, anchor="w")
        self.cb_main_quality = ttk.Combobox(row1, state="readonly", font=("Segoe UI", 8), width=22)
        self.lbl_main_quality.pack(side=tk.LEFT); self.cb_main_quality.pack(side=tk.LEFT, padx=(4, 10))
        self.cb_main_quality.bind("<<ComboboxSelected>>", self._on_main_quality_changed)

        self.lbl_main_audio = tk.Label(row1, text=tr("lbl_main_audio", "🎙️ Audio:"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=8, anchor="w")
        self.cb_main_audio = ttk.Combobox(row1, state="readonly", font=("Segoe UI", 8), width=20)
        self.lbl_main_audio.pack(side=tk.LEFT); self.cb_main_audio.pack(side=tk.LEFT, padx=(4, 8))
        self.cb_main_audio.bind("<<ComboboxSelected>>", self._on_main_audio_changed)

        self.btn_main_preview = tk.Button(row1, text=tr("btn_preview_short", "🎬 Preview"), font=("Segoe UI", 8, "bold"), bg=self.c_panel_light, fg=self.c_accent, relief="flat", activebackground=self.c_accent_dark, activeforeground="white", cursor="hand2", padx=8, pady=2, command=self._open_main_media_preview)
        self.btn_main_preview.pack(side=tk.RIGHT, padx=(4, 0))
        self.btn_reopen_quality = tk.Button(row1, text=tr("btn_media_quality_options", "🎞️ خيارات الجودة والترجمة"), font=("Segoe UI", 8, "bold"), bg=self.c_panel_light, fg=self.c_accent, relief="flat", activebackground=self.c_accent_dark, activeforeground="white", cursor="hand2", padx=8, pady=2, command=self._reopen_media_quality_modal)
        self.btn_reopen_quality.pack(side=tk.RIGHT, padx=(0, 4))

        # Row 2: Subtitles (Combobox), Subtitle Delivery Mode (Combobox), Subtitle Position (Combobox)
        row2 = tk.Frame(self.media_options_frame, bg=self.c_panel)
        row2.pack(fill=tk.X, pady=(2, 2))
        self.lbl_main_sub = tk.Label(row2, text=tr("lbl_main_sub", "💬 Subtitles:"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=10, anchor="w")
        self.cb_main_sub = ttk.Combobox(row2, state="readonly", font=("Segoe UI", 8), width=22)
        self.lbl_main_sub.pack(side=tk.LEFT); self.cb_main_sub.pack(side=tk.LEFT, padx=(4, 10))
        self.cb_main_sub.bind("<<ComboboxSelected>>", self._on_main_sub_changed)

        self.lbl_main_sub_mode = tk.Label(row2, text=tr("lbl_main_sub_mode", "⚙️ Mode:"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=7, anchor="w")
        sub_mode_labels = [tr("sub_mode_soft", "دمج ناعم"), tr("sub_mode_srt_only", "ملف ترجمة"), tr("sub_mode_burn", "حرق دائم (Burn-in)")]
        self.cb_main_sub_mode = ttk.Combobox(row2, values=sub_mode_labels, state="disabled", font=("Segoe UI", 8), width=18)
        self.cb_main_sub_mode.current(0)
        self.lbl_main_sub_mode.pack(side=tk.LEFT); self.cb_main_sub_mode.pack(side=tk.LEFT, padx=(4, 8))
        self.cb_main_sub_mode.bind("<<ComboboxSelected>>", self._on_main_sub_mode_changed)

        self.lbl_main_sub_pos = tk.Label(row2, text=tr("lbl_main_sub_pos", "📍 Pos:"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=6, anchor="w")
        self._main_sub_pos_codes = ["bottom", "middle", "top"]
        pos_labels = [tr("sub_pos_bottom", "أسفل (Bottom)"), tr("sub_pos_middle", "وسط (Middle)"), tr("sub_pos_top", "أعلى (Top)")]
        self.cb_main_sub_pos = ttk.Combobox(row2, values=pos_labels, state="readonly", font=("Segoe UI", 8), width=13)
        self.cb_main_sub_pos.current(0)
        self.lbl_main_sub_pos.pack(side=tk.LEFT); self.cb_main_sub_pos.pack(side=tk.LEFT, padx=(4, 8))
        self.cb_main_sub_pos.bind("<<ComboboxSelected>>", self._on_main_sub_pos_changed)

    def populate_main_media_bar(
        self,
        info: Optional[Dict[str, Any]] = None,
        options: Optional[List[VideoFormatOption]] = None,
        audio_tracks: Optional[List[Dict[str, Any]]] = None,
        subtitle_tracks: Optional[List[Dict[str, Any]]] = None,
        selected_option: Optional[VideoFormatOption] = None,
        url: Optional[str] = None,
        dest: Optional[str] = None,
        selected_opt: Optional[VideoFormatOption] = None,
        resolver: Optional[Any] = None,
        **kwargs
    ):
        """Displays and populates the Main Window Media Settings Bar with resolved formats."""
        if not hasattr(self, "media_options_frame"):
            return

        self._main_media_info = info or {}
        self._main_media_options = list(options or [])
        self._main_audio_tracks = list(audio_tracks or [])
        self._main_subtitle_tracks = list(subtitle_tracks or [])
        self._last_yt_info = info
        explicit_opt = selected_opt or selected_option
        if explicit_opt and explicit_opt in self._main_media_options:
            sel_idx = self._main_media_options.index(explicit_opt)
            sel_opt = explicit_opt
        else:
            sel_idx = resolve_preferred_option_index(self._main_media_options)
            sel_opt = self._main_media_options[sel_idx] if (self._main_media_options and 0 <= sel_idx < len(self._main_media_options)) else None

        media_url = url or (self.entry_url.get().strip() if hasattr(self, "entry_url") else "")
        final_dest = dest or (self.entry_dest.get().strip() if hasattr(self, "entry_dest") else "")
        self._pending_media_context = {
            "url": media_url,
            "info": info or {},
            "options": self._main_media_options,
            "audio_tracks": self._main_audio_tracks,
            "subtitle_tracks": self._main_subtitle_tracks,
            "selected_option": sel_opt,
            "resolver": resolver,
            "final_dest": final_dest
        }
        self._last_media_context = dict(self._pending_media_context)
        self._cache_media_context(media_url, self._pending_media_context)

        # Show frame in layout
        self.media_options_frame.pack(fill=tk.X, pady=(4, 2))

        # 1. Populate Quality Combobox
        q_vals = []
        for opt in self._main_media_options:
            fs = getattr(opt, "filesize_approx", 0) or getattr(opt, "filesize", 0)
            sz = format_filesize(fs) if fs else "~"
            res_lbl = getattr(opt, "resolution_label", "") or getattr(opt, "resolution_name", "Video")
            ext = getattr(opt, "ext", "mp4").upper()
            q_vals.append(f"{res_lbl} ({ext}) — {sz}")
        self.cb_main_quality.configure(values=q_vals)
        if q_vals and 0 <= sel_idx < len(q_vals):
            self.cb_main_quality.current(sel_idx)

        # 2. Populate Audio Combobox
        a_vals = [t.get("label", "") for t in self._main_audio_tracks]
        self.cb_main_audio.configure(values=a_vals)
        a_idx, pref_a = 0, get_setting("preferred_audio_lang", "original")
        if pref_a and pref_a != "original":
            for i, t in enumerate(self._main_audio_tracks):
                if str(t.get("language", "")).lower().startswith(pref_a.lower()):
                    a_idx = i; break
        if a_vals:
            self.cb_main_audio.current(a_idx)

        # 3. Populate Subtitles Combobox
        s_vals = [s.get("label", "") for s in self._main_subtitle_tracks]
        self.cb_main_sub.configure(values=s_vals)
        sub_idx, pref_s = 0, get_setting("preferred_subtitle_lang", "none")
        if sel_opt and getattr(sel_opt, "selected_subtitle_track", None) in self._main_subtitle_tracks:
            sub_idx = self._main_subtitle_tracks.index(sel_opt.selected_subtitle_track)
        elif pref_s and pref_s != "none":
            for i, s in enumerate(self._main_subtitle_tracks):
                if i > 0 and str(s.get("language", "")).lower().startswith(pref_s.lower()):
                    sub_idx = i; break
        if s_vals:
            self.cb_main_sub.current(sub_idx)

        # 4. Mode Selection
        mode = getattr(sel_opt, "subtitle_embed_mode", None) or get_setting("subtitle_embed_mode", "soft_embed")
        self.cb_main_sub_mode.current(self._main_sub_mode_codes.index(mode) if mode in self._main_sub_mode_codes else 0)

        # 5. Position Selection
        pos = getattr(sel_opt, "subtitle_position", None) or get_setting("subtitle_position", "bottom")
        if hasattr(self, "cb_main_sub_pos") and self.cb_main_sub_pos:
            self.cb_main_sub_pos.current(self._main_sub_pos_codes.index(pos) if pos in self._main_sub_pos_codes else 0)

        mode_st = "readonly" if len(self._main_subtitle_tracks) > 1 else "disabled"
        if hasattr(self, "cb_main_sub_mode") and self.cb_main_sub_mode: self.cb_main_sub_mode.configure(state=mode_st)
        pos_st = "readonly" if sub_idx > 0 else "disabled"
        if hasattr(self, "cb_main_sub_pos") and self.cb_main_sub_pos: self.cb_main_sub_pos.configure(state=pos_st)

    def hide_main_media_bar(self):
        """Hides the Media Settings Bar frame when switching to non-media URLs."""
        if hasattr(self, "media_options_frame"):
            try:
                self.media_options_frame.pack_forget()
            except Exception:
                pass

    def _on_main_quality_changed(self, event=None):
        """Dynamically updates destination filename extension and quality tag when user picks a different quality."""
        if not getattr(self, "_main_media_options", None):
            return
        idx = self.cb_main_quality.current()
        if 0 <= idx < len(self._main_media_options):
            opt = self._main_media_options[idx]
            if event is not None:
                h = getattr(opt, "height", 0) or 0
                if h > 0:
                    try: set_setting("preferred_video_height", h)
                    except Exception: pass
            cur = self.entry_dest.get().strip()
            if cur:
                sub_mode = "soft_embed"
                if hasattr(self, "cb_main_sub_mode") and hasattr(self, "_main_sub_mode_codes"):
                    m_idx = self.cb_main_sub_mode.current()
                    if 0 <= m_idx < len(self._main_sub_mode_codes):
                        sub_mode = self._main_sub_mode_codes[m_idx]
                updated = apply_media_filename_tags(cur, quality_label=opt.resolution_label, is_sub_burned=(sub_mode == "hard_burn"), ext=opt.ext)
                self.entry_dest.delete(0, tk.END); self.entry_dest.insert(0, updated)

    def _on_main_audio_changed(self, event=None):
        """Persists preferred audio language when user selects a different audio track."""
        if event is not None and getattr(self, "_main_audio_tracks", None):
            idx = self.cb_main_audio.current()
            if 0 <= idx < len(self._main_audio_tracks):
                track = self._main_audio_tracks[idx]
                lang = track.get("language") or ("original" if idx == 0 else "")
                if lang:
                    try: set_setting("preferred_audio_lang", lang)
                    except Exception: pass

    def _on_main_sub_changed(self, event=None):
        """Enables or disables subtitle mode combobox based on selected subtitle."""
        idx = self.cb_main_sub.current()
        has_s = len(getattr(self, "_main_subtitle_tracks", [])) > 1
        self.cb_main_sub_mode.configure(state="readonly" if has_s else "disabled")
        self.cb_main_sub_pos.configure(state="readonly" if idx > 0 else "disabled")
        if event is not None:
            if idx > 0 and idx < len(self._main_subtitle_tracks):
                lang = self._main_subtitle_tracks[idx].get("language") or "none"
                try: set_setting("preferred_subtitle_lang", lang)
                except Exception: pass
            else:
                try: set_setting("preferred_subtitle_lang", "none")
                except Exception: pass

    def _on_main_sub_mode_changed(self, event=None):
        """Saves chosen mode, auto-selects Arabic/first subtitle track if None, and reflects [Sub] tag."""
        cur_idx = self.cb_main_sub_mode.current()
        chosen = "soft_embed"
        if 0 <= cur_idx < len(self._main_sub_mode_codes):
            chosen = self._main_sub_mode_codes[cur_idx]
            try:
                set_setting("subtitle_embed_mode", chosen)
            except Exception:
                pass
        if self.cb_main_sub.current() <= 0 and len(self._main_subtitle_tracks) > 1:
            ar_idx = next((i for i, s in enumerate(self._main_subtitle_tracks) if i > 0 and str(s.get("language", "")).lower().startswith("ar")), None)
            target_idx = ar_idx if ar_idx is not None else 1
            self.cb_main_sub.current(target_idx)
            self.cb_main_sub_mode.configure(state="readonly")
            self.cb_main_sub_pos.configure(state="readonly")
        cur = self.entry_dest.get().strip()
        if cur and getattr(self, "_main_media_options", None):
            q_idx = self.cb_main_quality.current() if hasattr(self, "cb_main_quality") else 0
            opt = self._main_media_options[q_idx] if (0 <= q_idx < len(self._main_media_options)) else None
            ql = opt.resolution_label if opt else None
            ext = opt.ext if opt else None
            updated = apply_media_filename_tags(cur, quality_label=ql, is_sub_burned=(chosen == "hard_burn"), ext=ext)
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, updated)

    def _on_main_sub_pos_changed(self, event=None):
        """Persists selected subtitle position."""
        cur_idx = self.cb_main_sub_pos.current()
        if 0 <= cur_idx < len(self._main_sub_pos_codes):
            pos = self._main_sub_pos_codes[cur_idx]
            if event is not None:
                try: set_setting("subtitle_position", pos)
                except Exception: pass


    def _get_cached_media_context(self, url: str) -> Optional[Dict[str, Any]]:
        """Retrieves cached media options context by full URL or extracted video ID for 0ms reopen."""
        if not url: return None
        cache = getattr(self, "_media_context_cache", None)
        if cache and isinstance(cache, dict):
            if url in cache: return cache[url]
            clean_url = url.split("&")[0].strip() if "?" in url else url.strip()
            if clean_url in cache: return cache[clean_url]
            for k, ctx in cache.items():
                info = ctx.get("info") or {}
                vid = info.get("id") or info.get("display_id")
                if vid and (str(vid) in url or str(vid) == url): return ctx
        for ctx_attr in ("_pending_media_context", "_last_media_context"):
            ctx = getattr(self, ctx_attr, None)
            if ctx and isinstance(ctx, dict):
                ctx_url = ctx.get("url") or ""
                info = ctx.get("info") or {}
                vid = info.get("id") or info.get("display_id")
                if (ctx_url and (ctx_url == url or ctx_url.split("&")[0] == url.split("&")[0])) or (vid and (str(vid) in url or str(vid) == url)):
                    return ctx
        return None

    def _cache_media_context(self, url: str, ctx: Dict[str, Any]):
        """Caches media format context by full URL and extracted video ID for 0ms reopen."""
        if not hasattr(self, "_media_context_cache") or self._media_context_cache is None:
            self._media_context_cache = {}
        if url:
            self._media_context_cache[url] = ctx
            clean_url = url.split("&")[0].strip() if "?" in url else url.strip()
            self._media_context_cache[clean_url] = ctx
        info = ctx.get("info") or {}
        vid = info.get("id") or info.get("display_id")
        if vid:
            self._media_context_cache[str(vid)] = ctx
            self._media_context_cache[f"https://www.youtube.com/watch?v={vid}"] = ctx
            self._media_context_cache[f"https://youtu.be/{vid}"] = ctx

    def _reopen_media_quality_modal(self):
        """Opens or re-opens QualitySelectionModal so user can reconfigure quality and subtitles."""
        url = self.entry_url.get().strip() if hasattr(self, "entry_url") else ""
        dest = self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ""
        if not url:
            if hasattr(self, "show_toast"):
                self.show_toast(tr("err_empty_url", "Please enter a valid URL first!"), icon="⚠️")
            elif hasattr(self, "log"):
                self.log(tr("err_empty_url", "Please enter a valid URL first!"))
            return

        ctx = self._get_cached_media_context(url)
        if not ctx:
            ctx = getattr(self, "_pending_media_context", None) or getattr(self, "_last_media_context", None)
            if ctx and ctx.get("url") != url:
                ctx = None
        if ctx and ctx.get("options"):
            self._show_cached_quality_modal(ctx)
            return

        if hasattr(self, "_start_youtube_download"):
            self._start_youtube_download(url, dest)

    def _show_cached_quality_modal(self, ctx: Dict[str, Any], preferred_dest: Optional[str] = None):
        """Displays QualitySelectionModal instantaneously from cached metadata context."""
        info, options = ctx["info"], [copy.copy(o) for o in ctx.get("options", [])]
        raw_title, duration = info.get("title") or "Video", int(info.get("duration") or 0)
        theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
        clean_title = sanitize_filename(raw_title)
        cached_opt = ctx.get("selected_option")
        first_opt = cached_opt if (cached_opt and cached_opt in options) else (options[resolve_preferred_option_index(options)] if options else None)
        first_ext = first_opt.ext if first_opt else "mp4"
        first_lbl = first_opt.resolution_label if first_opt else ""

        base_dl = self._get_base_downloads_dir() if hasattr(self, "_get_base_downloads_dir") else get_base_downloads_dir()
        target_dest = preferred_dest if (preferred_dest and clean_title.lower() in os.path.basename(preferred_dest).lower()) else (ctx.get("final_dest") or preferred_dest or os.path.join(base_dl, f"{clean_title}.{first_ext}"))
        initial_dest = apply_media_filename_tags(target_dest, quality_label=first_lbl, is_sub_burned=False, ext=first_ext)
        reserved = self.history_manager.get_active_or_queued_paths() if getattr(self, "history_manager", None) else None
        dest = generate_unique_destination_path(initial_dest, reserved_paths=reserved)
        resolver = ctx.get("resolver") or (YouTubeResolver(on_log=self.log, cookies_from_browser=getattr(self, "cookies_browser", "auto"), cookies_file=getattr(self, "cookies_file", "")) if hasattr(self, "log") else None)

        def _on_confirm(selected_opt: VideoFormatOption, final_dest: str):
            self._quality_modal = None
            if hasattr(self, "clear_last_clipboard_url"): self.clear_last_clipboard_url()
            stream_info = resolver.build_stream_info(info, selected_opt) if resolver else None
            try: max_conn = int(self.conn_var.get())
            except Exception: max_conn = 8
            try: kb_lim = float(self.entry_custom_speed.get().strip())
            except Exception: kb_lim = 0.0
            yt_modal = DownloadConfirmationModal(parent=self.root, url=ctx.get("url", ""), default_dest_path=final_dest, theme=self._theme_dict(), parent_app=self, show_progress_immediately=True) if getattr(self, "is_window_hidden_or_minimized", lambda: False)() else None
            if stream_info and hasattr(self, "_launch_stream_coordinator"):
                self._launch_stream_coordinator(stream_info, final_dest, max_conn, kb_lim * 1024.0, yt_modal=yt_modal)

        def _on_open_in_main(selected_opt: VideoFormatOption, final_dest: str):
            self._quality_modal = None
            if hasattr(self, "clear_last_clipboard_url"): self.clear_last_clipboard_url()
            if hasattr(self, "restore_window"): self.restore_window()
            try:
                self.entry_url.delete(0, tk.END); self.entry_url.insert(0, ctx["url"])
                self.entry_dest.delete(0, tk.END); self.entry_dest.insert(0, final_dest)
            except Exception: pass
            ctx["selected_option"], ctx["final_dest"] = selected_opt, final_dest
            self.populate_main_media_bar(info, options, ctx.get("audio_tracks", []), ctx.get("subtitle_tracks", []), selected_option=selected_opt)
            try:
                self.btn_start.configure(state="normal"); self.btn_pause.configure(state="disabled")
                self.btn_cancel.configure(state="disabled"); self.card_size.configure(text=tr("status_ready", "Ready"))
            except Exception: pass

        if hasattr(self, "_quality_modal") and self._quality_modal:
            try:
                if self._quality_modal.winfo_exists(): self._quality_modal.destroy()
            except Exception: pass
            self._quality_modal = None

        self._quality_modal = QualitySelectionModal(
            parent=self.root, video_title=raw_title, duration=duration, options=options, default_dest_path=dest,
            theme=theme_dict, on_confirm=_on_confirm, on_cancel=lambda: setattr(self, "_quality_modal", None),
            on_open_in_main=_on_open_in_main, parent_app=self, audio_tracks=ctx.get("audio_tracks", []),
            subtitle_tracks=ctx.get("subtitle_tracks", []), video_url=ctx.get("url", ""), raw_info=info
        )

    def _open_main_media_preview(self):
        """Launches in-app VidMate-style preview directly from the Main Window Media Bar."""
        ctx = getattr(self, "_pending_media_context", None) or {}
        url = ctx.get("url") or (self.entry_url.get().strip() if hasattr(self, "entry_url") else "")
        info = ctx.get("info") or getattr(self, "_last_yt_info", {}) or {}
        raw_title = info.get("title") or ctx.get("title") or "Video Preview"
        opts = getattr(self, "_main_media_options", ctx.get("options", []))
        auds = getattr(self, "_main_audio_tracks", ctx.get("audio_tracks", []))
        subs = getattr(self, "_main_subtitle_tracks", ctx.get("subtitle_tracks", []))
        q_idx = self.cb_main_quality.current() if (hasattr(self, "cb_main_quality") and opts and 0 <= self.cb_main_quality.current() < len(opts)) else 0
        sel_opt = opts[q_idx] if (opts and 0 <= q_idx < len(opts)) else None
        sel_aud = auds[self.cb_main_audio.current()] if hasattr(self, "cb_main_audio") and auds and 0 <= self.cb_main_audio.current() < len(auds) else None
        sel_sub = subs[self.cb_main_sub.current()] if hasattr(self, "cb_main_sub") and subs and 0 <= self.cb_main_sub.current() < len(subs) else None
        theme_d = getattr(self, "_theme_dict", None) or ({"c_bg": self.c_bg, "c_panel": self.c_panel, "c_panel_light": self.c_panel_light, "c_border": self.c_border, "c_accent": self.c_accent, "c_accent_dark": self.c_accent_dark, "c_success": self.c_success, "c_text_bright": self.c_text_bright, "c_text_muted": self.c_text_muted, "c_input_bg": self.c_input_bg} if hasattr(self, "c_bg") else {})
        dest_p = (self.entry_dest.get().strip() if hasattr(self, "entry_dest") else "") or (self.dest_input.get().strip() if hasattr(self, "dest_input") else "")
        sel_mode = self._main_sub_mode_codes[self.cb_main_sub_mode.current()] if (hasattr(self, "cb_main_sub_mode") and hasattr(self, "_main_sub_mode_codes") and 0 <= self.cb_main_sub_mode.current() < len(self._main_sub_mode_codes)) else "hard_burn"
        sel_pos = self._main_sub_pos_codes[self.cb_main_sub_pos.current()] if (hasattr(self, "cb_main_sub_pos") and hasattr(self, "_main_sub_pos_codes") and 0 <= self.cb_main_sub_pos.current() < len(self._main_sub_pos_codes)) else "bottom"

        def _sync_ui(opt, dst):
            if opt and opts and hasattr(self, "cb_main_quality"):
                for i, o in enumerate(opts):
                    if o == opt or getattr(o, "format_id", None) == getattr(opt, "format_id", None):
                        self.cb_main_quality.current(i); break
            sel_a = getattr(opt, "selected_audio_track", None)
            if auds and sel_a and hasattr(self, "cb_main_audio"):
                for i, a in enumerate(auds):
                    if a == sel_a or a.get("track_id") == sel_a.get("track_id"):
                        self.cb_main_audio.current(i); break
            sel_s = getattr(opt, "selected_subtitle_track", None)
            if subs and hasattr(self, "cb_main_sub"):
                for i, s in enumerate(subs):
                    if (sel_s and (s == sel_s or s.get("sub_id") == sel_s.get("sub_id"))) or (not sel_s and i == 0):
                        self.cb_main_sub.current(i)
                        if hasattr(self, "cb_main_sub_mode"): self.cb_main_sub_mode.configure(state="readonly" if len(subs) > 1 else "disabled")
                        if hasattr(self, "cb_main_sub_pos"): self.cb_main_sub_pos.configure(state="readonly" if i > 0 else "disabled")
                        break
            sm = getattr(opt, "subtitle_embed_mode", None)
            if sm and hasattr(self, "cb_main_sub_mode") and hasattr(self, "_main_sub_mode_codes") and sm in self._main_sub_mode_codes:
                self.cb_main_sub_mode.current(self._main_sub_mode_codes.index(sm))
            sp = getattr(opt, "subtitle_position", None)
            if sp and hasattr(self, "cb_main_sub_pos") and hasattr(self, "_main_sub_pos_codes") and sp in self._main_sub_pos_codes:
                self.cb_main_sub_pos.current(self._main_sub_pos_codes.index(sp))
            if dst and hasattr(self, "entry_dest") and self.entry_dest and tk:
                self.entry_dest.delete(0, tk.END); self.entry_dest.insert(0, dst)
            ctx["selected_option"] = opt
            if dst: ctx["final_dest"] = dst

        def _on_preview_confirm(selected_opt, final_dest):
            _sync_ui(selected_opt, final_dest)
            try: max_conn = int(self.conn_var.get())
            except Exception: max_conn = 8
            try: bytes_limit = max(0.0, float(self.entry_custom_speed.get().strip())) * 1024.0
            except Exception: bytes_limit = 0.0
            resolver = ctx.get("resolver") or (YouTubeResolver(on_log=self.log, cookies_from_browser=getattr(self, "cookies_browser", "auto"), cookies_file=getattr(self, "cookies_file", "")) if hasattr(self, "log") else None)
            stream_info = resolver.build_stream_info(info, selected_opt) if resolver else None
            self._last_media_context = {**dict(ctx), "selected_option": selected_opt, "final_dest": final_dest}
            self._pending_media_context = None
            if stream_info and hasattr(self, "_launch_stream_coordinator"):
                self._launch_stream_coordinator(stream_info, final_dest, max_conn, bytes_limit)

        try:
            from ..modals.video_preview_modal import open_video_preview
            open_video_preview(
                parent=self.root if hasattr(self, "root") else None, url=url, video_title=raw_title,
                stream_info=sel_opt, info_dict=info, selected_sub_track=sel_sub, theme=theme_d,
                selected_audio_track=sel_aud, options=opts, audio_tracks=auds, subtitle_tracks=subs,
                default_dest_path=dest_p, on_confirm=_on_preview_confirm,
                on_open_in_main=lambda opt, dst: _sync_ui(opt, dst),
                parent_app=self, on_log=self.log if hasattr(self, "log") else print,
                subtitle_embed_mode=sel_mode, selected_q_idx=q_idx, subtitle_position=sel_pos,
            )
        except Exception as e:
            if hasattr(self, "log"): self.log(f"[PREVIEW ERROR] {e}")

    def _start_pending_media_download(self):
        """Starts media download directly using the selections made in the Main Window Media Bar."""
        ctx = getattr(self, "_pending_media_context", None)
        if not ctx:
            return

        options = getattr(self, "_main_media_options", ctx.get("options", []))
        audio_tracks = getattr(self, "_main_audio_tracks", ctx.get("audio_tracks", []))
        subtitle_tracks = getattr(self, "_main_subtitle_tracks", ctx.get("subtitle_tracks", []))
        info, resolver = ctx.get("info", {}), ctx.get("resolver")

        selected_opt = ctx.get("selected_option")
        if hasattr(self, "cb_main_quality") and options:
            q_idx = self.cb_main_quality.current()
            if 0 <= q_idx < len(options):
                selected_opt = options[q_idx]
        if selected_opt is None and options:
            selected_opt = options[0]

        if selected_opt:
            if hasattr(self, "cb_main_audio") and audio_tracks and 0 <= self.cb_main_audio.current() < len(audio_tracks):
                selected_opt.selected_audio_track = audio_tracks[self.cb_main_audio.current()]
            sub_mode = self._main_sub_mode_codes[self.cb_main_sub_mode.current()] if (hasattr(self, "cb_main_sub_mode") and 0 <= self.cb_main_sub_mode.current() < len(self._main_sub_mode_codes)) else "soft_embed"
            selected_opt.subtitle_embed_mode = sub_mode
            sub_pos = self._main_sub_pos_codes[self.cb_main_sub_pos.current()] if (hasattr(self, "cb_main_sub_pos") and hasattr(self, "_main_sub_pos_codes") and 0 <= self.cb_main_sub_pos.current() < len(self._main_sub_pos_codes)) else "bottom"
            selected_opt.subtitle_position = sub_pos

            if hasattr(self, "cb_main_sub") and subtitle_tracks:
                s_idx = self.cb_main_sub.current()
                if 0 < s_idx < len(subtitle_tracks):
                    selected_opt.selected_subtitle_track = subtitle_tracks[s_idx]
                else:
                    selected_opt.selected_subtitle_track = None

        final_dest = (self.entry_dest.get().strip() if hasattr(self, "entry_dest") else "") or ctx.get("final_dest", "")
        if selected_opt:
            is_sub = (getattr(selected_opt, "subtitle_embed_mode", "") == "hard_burn")
            final_dest = apply_media_filename_tags(final_dest, quality_label=selected_opt.resolution_label, is_sub_burned=is_sub, ext=selected_opt.ext)
        reserved = self.history_manager.get_active_or_queued_paths() if (hasattr(self, "history_manager") and self.history_manager) else None
        final_dest = generate_unique_destination_path(final_dest, reserved_paths=reserved)

        try: max_conn = int(self.conn_var.get())
        except Exception: max_conn = 8
        try: bytes_limit = max(0.0, float(self.entry_custom_speed.get().strip())) * 1024.0
        except Exception: bytes_limit = 0.0

        if not resolver and hasattr(self, "log"):
            resolver = YouTubeResolver(on_log=self.log, cookies_from_browser=getattr(self, "cookies_browser", "auto"), cookies_file=getattr(self, "cookies_file", ""))
        stream_info = resolver.build_stream_info(info, selected_opt) if resolver else None
        self._last_media_context = {**dict(ctx), "selected_option": selected_opt, "final_dest": final_dest}
        self._pending_media_context = None

        if stream_info and hasattr(self, "_launch_stream_coordinator"):
            self._launch_stream_coordinator(stream_info, final_dest, max_conn, bytes_limit)


__all__ = ["MediaOptionsBarMixin"]
