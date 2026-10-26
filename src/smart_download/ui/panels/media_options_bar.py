"""
MediaOptionsBarMixin: Main-window media format, dubbing audio, and subtitle options bar.
Provides dynamic Quality, Audio track, Subtitle track, and Subtitle mode selectors directly in the GUI.
"""
import os
import threading
from typing import Optional, Dict, Any, List

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore

from smart_download.i18n import tr
from smart_download.config import get_setting, set_setting
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
from ..modals.video_preview_modal import VideoPreviewModal


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

        self.lbl_main_quality = tk.Label(
            row1, text=tr("lbl_main_quality", "🎞️ Quality:"),
            font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=12, anchor="w"
        )
        self.lbl_main_quality.pack(side=tk.LEFT)

        self.cb_main_quality = ttk.Combobox(row1, state="readonly", font=("Segoe UI", 8), width=24)
        self.cb_main_quality.pack(side=tk.LEFT, padx=(4, 12))
        self.cb_main_quality.bind("<<ComboboxSelected>>", self._on_main_quality_changed)

        self.lbl_main_audio = tk.Label(
            row1, text=tr("lbl_main_audio", "🎙️ Audio:"),
            font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=10, anchor="w"
        )
        self.lbl_main_audio.pack(side=tk.LEFT)

        self.cb_main_audio = ttk.Combobox(row1, state="readonly", font=("Segoe UI", 8), width=22)
        self.cb_main_audio.pack(side=tk.LEFT, padx=(4, 8))

        self.btn_reopen_quality = tk.Button(
            row1,
            text=tr("btn_media_quality_options", "🎞️ خيارات الجودة والترجمة"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=8,
            pady=2,
            command=self._reopen_media_quality_modal
        )
        self.btn_reopen_quality.pack(side=tk.RIGHT)

        self.btn_media_preview = tk.Button(
            row1,
            text=tr("btn_live_preview", "▶️ معاينة"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=8,
            pady=2,
            command=self._open_media_preview
        )
        self.btn_media_preview.pack(side=tk.RIGHT, padx=(0, 6))

        # Row 2: Subtitles (Combobox), Subtitle Delivery Mode (Combobox)
        row2 = tk.Frame(self.media_options_frame, bg=self.c_panel)
        row2.pack(fill=tk.X, pady=(2, 2))

        self.lbl_main_sub = tk.Label(
            row2, text=tr("lbl_main_sub", "💬 Subtitles:"),
            font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=12, anchor="w"
        )
        self.lbl_main_sub.pack(side=tk.LEFT)

        self.cb_main_sub = ttk.Combobox(row2, state="readonly", font=("Segoe UI", 8), width=24)
        self.cb_main_sub.pack(side=tk.LEFT, padx=(4, 12))
        self.cb_main_sub.bind("<<ComboboxSelected>>", self._on_main_sub_changed)

        self.lbl_main_sub_mode = tk.Label(
            row2, text=tr("lbl_main_sub_mode", "⚙️ Sub Mode:"),
            font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=10, anchor="w"
        )
        self.lbl_main_sub_mode.pack(side=tk.LEFT)

        sub_mode_labels = [
            tr("sub_mode_soft", "ملف منفصل + دمج سريع (MP4)"),
            tr("sub_mode_srt_only", "ملف ترجمة منفصل فقط (.srt)"),
            tr("sub_mode_burn", "ملف منفصل + طباعة بالفيديو (Burn-in)"),
        ]
        self.cb_main_sub_mode = ttk.Combobox(row2, values=sub_mode_labels, state="disabled", font=("Segoe UI", 8), width=24)
        self.cb_main_sub_mode.current(0)
        self.cb_main_sub_mode.pack(side=tk.LEFT, padx=(4, 8))
        self.cb_main_sub_mode.bind("<<ComboboxSelected>>", self._on_main_sub_mode_changed)

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
        sel_opt = selected_opt or selected_option or (self._main_media_options[0] if self._main_media_options else None)

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
        sel_idx = 0
        if sel_opt and sel_opt in self._main_media_options:
            sel_idx = self._main_media_options.index(sel_opt)
        if q_vals:
            self.cb_main_quality.current(sel_idx)

        # 2. Populate Audio Combobox
        a_vals = [t.get("label", "") for t in self._main_audio_tracks]
        self.cb_main_audio.configure(values=a_vals)
        if a_vals:
            self.cb_main_audio.current(0)

        # 3. Populate Subtitles Combobox
        s_vals = [s.get("label", "") for s in self._main_subtitle_tracks]
        self.cb_main_sub.configure(values=s_vals)
        sub_idx = 0
        if sel_opt and getattr(sel_opt, "selected_subtitle_track", None) in self._main_subtitle_tracks:
            sub_idx = self._main_subtitle_tracks.index(sel_opt.selected_subtitle_track)
        if s_vals:
            self.cb_main_sub.current(sub_idx)

        # 4. Mode Selection
        mode = getattr(sel_opt, "subtitle_embed_mode", None) or get_setting("subtitle_embed_mode", "soft_embed")
        if mode in self._main_sub_mode_codes:
            self.cb_main_sub_mode.current(self._main_sub_mode_codes.index(mode))
        else:
            self.cb_main_sub_mode.current(0)

        if sub_idx > 0:
            self.cb_main_sub_mode.configure(state="readonly")
        else:
            self.cb_main_sub_mode.configure(state="disabled")

    def hide_main_media_bar(self):
        """Hides the Media Settings Bar frame when switching to non-media URLs."""
        if hasattr(self, "media_options_frame"):
            try:
                self.media_options_frame.pack_forget()
            except Exception:
                pass

    def _on_main_quality_changed(self, event=None):
        """Dynamically updates the destination filename extension when user picks a different quality."""
        if not getattr(self, "_main_media_options", None):
            return
        idx = self.cb_main_quality.current()
        if 0 <= idx < len(self._main_media_options):
            opt = self._main_media_options[idx]
            cur = self.entry_dest.get().strip()
            if cur:
                base, _ = os.path.splitext(cur)
                ext = opt.ext if str(opt.ext).startswith(".") else f".{opt.ext}"
                self.entry_dest.delete(0, tk.END)
                self.entry_dest.insert(0, f"{base}{ext}")

    def _on_main_sub_changed(self, event=None):
        """Enables or disables subtitle mode combobox based on selected subtitle."""
        idx = self.cb_main_sub.current()
        if idx > 0:
            self.cb_main_sub_mode.configure(state="readonly")
        else:
            self.cb_main_sub_mode.configure(state="disabled")

    def _on_main_sub_mode_changed(self, event=None):
        """Saves chosen mode and auto-selects subtitle track 1 if user chose a mode with None selected."""
        cur_idx = self.cb_main_sub_mode.current()
        if 0 <= cur_idx < len(self._main_sub_mode_codes):
            chosen = self._main_sub_mode_codes[cur_idx]
            try:
                set_setting("subtitle_embed_mode", chosen)
            except Exception:
                pass
        if self.cb_main_sub.current() <= 0 and len(self._main_subtitle_tracks) > 1:
            self.cb_main_sub.current(1)
            self.cb_main_sub_mode.configure(state="readonly")

    def _get_cached_media_context(self, url: str) -> Optional[Dict[str, Any]]:
        """Retrieves cached media options context by full URL or extracted video ID for 0ms reopen."""
        if not url:
            return None
        cache = getattr(self, "_media_context_cache", None)
        if cache and isinstance(cache, dict):
            if url in cache:
                return cache[url]
            clean_url = url.split("&")[0].strip() if "?" in url else url.strip()
            if clean_url in cache:
                return cache[clean_url]
            for k, ctx in cache.items():
                info = ctx.get("info") or {}
                vid = info.get("id") or info.get("display_id")
                if vid and (str(vid) in url or str(vid) == url):
                    return ctx
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
            return

        ctx = self._get_cached_media_context(url)
        if not ctx:
            ctx = getattr(self, "_pending_media_context", None) or getattr(self, "_last_media_context", None)
        if ctx and ctx.get("options"):
            self._show_cached_quality_modal(ctx)
            return

        if hasattr(self, "_start_youtube_download"):
            self._start_youtube_download(url, dest)

    def _open_media_preview(self):
        """Opens live video, audio, and subtitle preview modal from current media bar state."""
        ctx = getattr(self, "_pending_media_context", None) or getattr(self, "_last_media_context", None)
        if not ctx:
            return
        info = ctx.get("info") or {}
        options = getattr(self, "_main_media_options", ctx.get("options", []))
        audio_tracks = getattr(self, "_main_audio_tracks", ctx.get("audio_tracks", []))
        subtitle_tracks = getattr(self, "_main_subtitle_tracks", ctx.get("subtitle_tracks", []))

        sel_opt = ctx.get("selected_option")
        if hasattr(self, "cb_main_quality") and options:
            q_idx = self.cb_main_quality.current()
            if 0 <= q_idx < len(options):
                sel_opt = options[q_idx]

        sel_audio = None
        if hasattr(self, "cb_main_audio") and audio_tracks:
            a_idx = self.cb_main_audio.current()
            if 0 <= a_idx < len(audio_tracks):
                sel_audio = audio_tracks[a_idx]

        sel_sub = None
        if hasattr(self, "cb_main_sub") and subtitle_tracks:
            s_idx = self.cb_main_sub.current()
            if 0 <= s_idx < len(subtitle_tracks):
                sel_sub = subtitle_tracks[s_idx]

        stream_url = ""
        if sel_opt:
            stream_url = getattr(sel_opt, "url", "") or ""
        if not stream_url:
            stream_url = ctx.get("url") or ""

        if getattr(self, "_preview_modal", None) and self._preview_modal.winfo_exists():
            try: self._preview_modal.lift(); self._preview_modal.focus_force(); return
            except Exception: pass

        theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
        self._preview_modal = VideoPreviewModal(
            parent=self.root,
            video_title=info.get("title") or "Media Preview",
            duration=int(info.get("duration") or 0),
            media_url=stream_url,
            selected_option=sel_opt,
            selected_audio=sel_audio,
            selected_subtitle=sel_sub,
            theme=theme_dict,
            on_download_now=self._start_pending_media_download
        )

    def _show_cached_quality_modal(self, ctx: Dict[str, Any]):
        """Displays QualitySelectionModal instantaneously from cached metadata context."""
        info = ctx["info"]
        options = ctx["options"]
        raw_title = info.get("title") or "Video"
        duration = int(info.get("duration") or 0)
        theme_dict = self._theme_dict() if hasattr(self, "_theme_dict") else {}
        dest = self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ctx.get("final_dest", "")
        resolver = ctx.get("resolver")
        if not resolver and hasattr(self, "log"):
            resolver = YouTubeResolver(
                on_log=self.log,
                cookies_from_browser=getattr(self, "cookies_browser", "auto"),
                cookies_file=getattr(self, "cookies_file", "")
            )

        def _on_confirm(selected_opt: VideoFormatOption, final_dest: str):
            self._quality_modal = None
            if hasattr(self, "clear_last_clipboard_url"):
                self.clear_last_clipboard_url()
            stream_info = resolver.build_stream_info(info, selected_opt) if resolver else None
            try:
                max_conn = int(self.conn_var.get())
            except Exception:
                max_conn = 8
            try:
                kb_lim = float(self.entry_custom_speed.get().strip())
            except Exception:
                kb_lim = 0.0
            if stream_info and hasattr(self, "_launch_stream_coordinator"):
                self._launch_stream_coordinator(stream_info, final_dest, max_conn, kb_lim * 1024.0)

        def _on_open_in_main(selected_opt: VideoFormatOption, final_dest: str):
            self._quality_modal = None
            if hasattr(self, "clear_last_clipboard_url"):
                self.clear_last_clipboard_url()
            if hasattr(self, "restore_window"):
                self.restore_window()
            try:
                self.entry_url.delete(0, tk.END)
                self.entry_url.insert(0, ctx["url"])
                self.entry_dest.delete(0, tk.END)
                self.entry_dest.insert(0, final_dest)
            except Exception:
                pass
            ctx["selected_option"] = selected_opt
            ctx["final_dest"] = final_dest
            self.populate_main_media_bar(
                info, options, ctx.get("audio_tracks", []), ctx.get("subtitle_tracks", []), selected_option=selected_opt
            )
            try:
                self.btn_start.configure(state="normal")
                self.btn_pause.configure(state="disabled")
                self.btn_cancel.configure(state="disabled")
                self.card_size.configure(text=tr("status_ready", "Ready"))
            except Exception:
                pass

        def _on_cancel():
            self._quality_modal = None

        if hasattr(self, "_quality_modal") and self._quality_modal:
            try:
                if self._quality_modal.winfo_exists():
                    self._quality_modal.destroy()
            except Exception:
                pass
            self._quality_modal = None

        self._quality_modal = QualitySelectionModal(
            parent=self.root,
            video_title=raw_title,
            duration=duration,
            options=options,
            default_dest_path=dest,
            theme=theme_dict,
            on_confirm=_on_confirm,
            on_cancel=_on_cancel,
            on_open_in_main=_on_open_in_main,
            parent_app=self,
            audio_tracks=ctx.get("audio_tracks", []),
            subtitle_tracks=ctx.get("subtitle_tracks", [])
        )

    def _start_pending_media_download(self):
        """Starts media download directly using the selections made in the Main Window Media Bar."""
        ctx = getattr(self, "_pending_media_context", None)
        if not ctx:
            return

        options = getattr(self, "_main_media_options", ctx.get("options", []))
        audio_tracks = getattr(self, "_main_audio_tracks", ctx.get("audio_tracks", []))
        subtitle_tracks = getattr(self, "_main_subtitle_tracks", ctx.get("subtitle_tracks", []))
        info = ctx.get("info", {})
        resolver = ctx.get("resolver")

        selected_opt = ctx.get("selected_option")
        if hasattr(self, "cb_main_quality") and options:
            q_idx = self.cb_main_quality.current()
            if 0 <= q_idx < len(options):
                selected_opt = options[q_idx]
        if selected_opt is None and options:
            selected_opt = options[0]

        if selected_opt:
            if hasattr(self, "cb_main_audio") and audio_tracks:
                a_idx = self.cb_main_audio.current()
                if 0 <= a_idx < len(audio_tracks):
                    selected_opt.selected_audio_track = audio_tracks[a_idx]

            sub_mode = "soft_embed"
            if hasattr(self, "cb_main_sub_mode"):
                m_idx = self.cb_main_sub_mode.current()
                if 0 <= m_idx < len(self._main_sub_mode_codes):
                    sub_mode = self._main_sub_mode_codes[m_idx]
            selected_opt.subtitle_embed_mode = sub_mode

            if hasattr(self, "cb_main_sub") and subtitle_tracks:
                s_idx = self.cb_main_sub.current()
                if s_idx <= 0 and len(subtitle_tracks) > 1 and sub_mode == "hard_burn":
                    s_idx = 1
                    try: self.cb_main_sub.current(1)
                    except Exception: pass
                if 0 <= s_idx < len(subtitle_tracks):
                    selected_opt.selected_subtitle_track = subtitle_tracks[s_idx]

        final_dest = (self.entry_dest.get().strip() if hasattr(self, "entry_dest") else "") or ctx.get("final_dest", "")
        try: max_conn = int(self.conn_var.get())
        except Exception: max_conn = 8
        try: kb_lim = float(self.entry_custom_speed.get().strip())
        except Exception: kb_lim = 0.0
        bytes_limit = kb_lim * 1024.0 if kb_lim > 0 else 0.0

        if not resolver and hasattr(self, "log"):
            resolver = YouTubeResolver(
                on_log=self.log,
                cookies_from_browser=getattr(self, "cookies_browser", "auto"),
                cookies_file=getattr(self, "cookies_file", "")
            )
        stream_info = resolver.build_stream_info(info, selected_opt) if resolver else None
        self._last_media_context = dict(ctx)
        self._last_media_context["selected_option"] = selected_opt
        self._last_media_context["final_dest"] = final_dest
        self._pending_media_context = None

        if stream_info and hasattr(self, "_launch_stream_coordinator"):
            self._launch_stream_coordinator(stream_info, final_dest, max_conn, bytes_limit)


__all__ = ["MediaOptionsBarMixin"]
