"""
VideoPreviewModal: Live Video, Audio Dubbing & Real-time Subtitle Preview player.
"""
import os
import sys
from typing import Optional, Callable, Dict, Any, List

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore

from ...i18n import tr
from ...utils.tk_helpers import animate_window_open, animate_window_close, _detach_photo_tk
from ...services.preview_service import PreviewSession, SubtitleCue, fetch_cues_for_track


def _fmt_time(sec: float) -> str:
    """Formats seconds into MM:SS or HH:MM:SS string."""
    s = int(max(0, sec))
    h = s // 3600
    m = (s % 3600) // 60
    secs = s % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{secs:02d}"
    return f"{m:02d}:{secs:02d}"


class VideoPreviewModal(tk.Toplevel):
    """
    Sleek themed preview player dialog displaying stream quality, audio track,
    live subtitle overlay, seek timeline, and one-click download trigger.
    """

    def __init__(
        self,
        parent: Optional[tk.Tk],
        video_title: str,
        duration: int,
        media_url: str = "",
        selected_option: Optional[Any] = None,
        selected_audio: Optional[Dict[str, Any]] = None,
        selected_subtitle: Optional[Dict[str, Any]] = None,
        theme: Optional[Dict[str, str]] = None,
        on_download_now: Optional[Callable[[], None]] = None,
        cues: Optional[List[SubtitleCue]] = None,
        use_ffplay: bool = True
    ):
        super().__init__(parent)
        self.video_title = str(video_title or "Media Preview")
        self.duration = max(0, int(duration or 0))
        self.media_url = media_url
        self.selected_option = selected_option
        self.selected_audio = selected_audio or {}
        self.selected_subtitle = selected_subtitle or {}
        self.theme = theme or {}
        self.on_download_now_cb = on_download_now

        self.c_bg = self.theme.get("c_bg", "#0f172a")
        self.c_panel = self.theme.get("c_panel", "#1e293b")
        self.c_panel_light = self.theme.get("c_panel_light", "#334155")
        self.c_border = self.theme.get("c_border", "#475569")
        self.c_accent = self.theme.get("c_accent", "#38bdf8")
        self.c_accent_dark = self.theme.get("c_accent_dark", "#0284c7")
        self.c_success = self.theme.get("c_success", "#10b981")
        self.c_danger = self.theme.get("c_danger", "#ef4444")
        self.c_text_bright = self.theme.get("c_text_bright", "#f8fafc")
        self.c_text_muted = self.theme.get("c_text_muted", "#94a3b8")

        self.title(tr("preview_title", "Live Media & Subtitle Preview"))
        self.configure(bg=self.c_bg)

        # Parse or fetch cues if not provided directly
        parsed_cues = cues if cues is not None else fetch_cues_for_track(self.selected_subtitle)
        self.session = PreviewSession(
            media_url=self.media_url,
            duration=self.duration,
            cues=parsed_cues,
            on_time_update=self._on_session_time_update,
            on_state_change=self._on_session_state_change,
            use_ffplay=use_ffplay
        )

        self._user_seeking = False
        self._build_ui()
        self._center_window(parent)
        animate_window_open(self, duration_ms=130)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<space>", lambda e: self._toggle_play())

        # Start playback
        self.session.start()

    def _center_window(self, parent):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w, h = 680, 460
        if parent and parent.winfo_exists():
            try:
                px, py = parent.winfo_x(), parent.winfo_y()
                pw, ph = parent.winfo_width(), parent.winfo_height()
                x = max(0, px + (pw - w) // 2)
                y = max(0, py + (ph - h) // 2)
            except Exception:
                x = max(0, (sw - w) // 2)
                y = max(0, (sh - h) // 2)
        else:
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(580, 380)

    def _build_ui(self):
        container = tk.Frame(self, bg=self.c_bg, padx=14, pady=12)
        container.pack(fill=tk.BOTH, expand=True)

        # Title & Badges Row
        title_sub = self.video_title if len(self.video_title) <= 65 else self.video_title[:62] + "..."
        lbl_title = tk.Label(
            container, text=title_sub, font=("Segoe UI", 10, "bold"),
            bg=self.c_bg, fg=self.c_text_bright, anchor="w"
        )
        lbl_title.pack(fill=tk.X, pady=(0, 6))

        # Badges frame
        f_badges = tk.Frame(container, bg=self.c_bg)
        f_badges.pack(fill=tk.X, pady=(0, 10))

        # Quality badge
        q_label = getattr(self.selected_option, "resolution_label", "") or "Auto Quality"
        ext = getattr(self.selected_option, "ext", "mp4").upper()
        self._create_badge(f_badges, f"🎞️ {q_label} ({ext})", self.c_accent_dark)

        # Audio badge
        a_lbl = self.selected_audio.get("label") or self.selected_audio.get("name") or "Default Audio"
        self._create_badge(f_badges, f"🎙️ {a_lbl}", "#475569")

        # Subtitle badge
        s_lbl = self.selected_subtitle.get("label") or self.selected_subtitle.get("name") or "No Subtitles"
        self._create_badge(f_badges, f"💬 {s_lbl}", "#334155")

        # Live Subtitle Overlay Box (Screen simulator)
        self.screen_frame = tk.Frame(
            container, bg="#050811", highlightbackground=self.c_border,
            highlightthickness=1, height=180
        )
        self.screen_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.screen_frame.pack_propagate(False)

        lbl_screen_header = tk.Label(
            self.screen_frame, text="LIVE SUBTITLE DISPLAY",
            font=("Segoe UI", 7, "bold"), bg="#050811", fg="#64748b"
        )
        lbl_screen_header.pack(anchor="nw", padx=8, pady=4)

        self.lbl_subtitle_cue = tk.Label(
            self.screen_frame,
            text="",
            font=("Segoe UI", 12, "bold"),
            bg="#050811",
            fg="#facc15",
            wraplength=580,
            justify="center"
        )
        self.lbl_subtitle_cue.pack(expand=True, fill=tk.BOTH, padx=12, pady=12)

        # Timeline & Seek bar
        f_timeline = tk.Frame(container, bg=self.c_bg)
        f_timeline.pack(fill=tk.X, pady=(0, 8))

        self.lbl_time = tk.Label(
            f_timeline, text=f"00:00 / {_fmt_time(self.duration)}",
            font=("Consolas", 9), bg=self.c_bg, fg=self.c_text_muted, width=16, anchor="w"
        )
        self.lbl_time.pack(side=tk.LEFT)

        max_sec = self.duration if self.duration > 0 else 100
        self.scale_seek = ttk.Scale(
            f_timeline, from_=0, to=max_sec, orient=tk.HORIZONTAL,
            command=self._on_scale_drag
        )
        self.scale_seek.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.scale_seek.bind("<ButtonPress-1>", lambda e: self._set_user_seeking(True))
        self.scale_seek.bind("<ButtonRelease-1>", self._on_scale_release)

        # Controls Toolbar
        f_controls = tk.Frame(container, bg=self.c_bg)
        f_controls.pack(fill=tk.X, pady=(0, 4))

        # Seek -10s
        self.btn_seek_back = tk.Button(
            f_controls, text="⏪ -10s", font=("Segoe UI", 8, "bold"),
            bg=self.c_panel, fg=self.c_text_bright, relief="flat", padx=8, pady=4,
            command=lambda: self.session.seek(-10.0)
        )
        self.btn_seek_back.pack(side=tk.LEFT, padx=(0, 4))

        # Play / Pause
        self.btn_play_pause = tk.Button(
            f_controls, text="⏸ Pause", font=("Segoe UI", 8, "bold"),
            bg=self.c_panel, fg=self.c_accent, relief="flat", padx=10, pady=4,
            command=self._toggle_play
        )
        self.btn_play_pause.pack(side=tk.LEFT, padx=(0, 4))

        # Seek +30s
        self.btn_seek_fwd = tk.Button(
            f_controls, text="⏩ +30s", font=("Segoe UI", 8, "bold"),
            bg=self.c_panel, fg=self.c_text_bright, relief="flat", padx=8, pady=4,
            command=lambda: self.session.seek(30.0)
        )
        self.btn_seek_fwd.pack(side=tk.LEFT, padx=(0, 4))

        # Stop
        self.btn_stop = tk.Button(
            f_controls, text="⏹ Stop", font=("Segoe UI", 8, "bold"),
            bg=self.c_panel, fg=self.c_danger, relief="flat", padx=8, pady=4,
            command=self.session.stop
        )
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 12))

        # Download Now button
        self.btn_dl_now = tk.Button(
            f_controls,
            text=tr("btn_download_now", "📥 Download Now with These Settings"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_success,
            fg="#ffffff",
            activebackground="#059669",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self._on_download_now
        )
        self.btn_dl_now.pack(side=tk.RIGHT)

        # Close button
        btn_close = tk.Button(
            f_controls, text="✕", font=("Segoe UI", 8, "bold"),
            bg=self.c_panel, fg=self.c_text_muted, relief="flat", padx=8, pady=4,
            command=self._on_close
        )
        btn_close.pack(side=tk.RIGHT, padx=(0, 6))

    def _create_badge(self, parent, text: str, bg_color: str):
        badge = tk.Label(
            parent, text=text, font=("Segoe UI", 7, "bold"),
            bg=bg_color, fg="#ffffff", padx=6, pady=2
        )
        badge.pack(side=tk.LEFT, padx=(0, 6))

    def _set_user_seeking(self, val: bool):
        self._user_seeking = val

    def _on_scale_drag(self, val):
        if self._user_seeking:
            try:
                cur = float(val)
                self.lbl_time.configure(text=f"{_fmt_time(cur)} / {_fmt_time(self.duration)}")
            except Exception:
                pass

    def _on_scale_release(self, event):
        self._user_seeking = False
        try:
            target = float(self.scale_seek.get())
            self.session.seek_to(target)
        except Exception:
            pass

    def _toggle_play(self):
        if self.session.is_playing:
            self.session.pause()
        else:
            self.session.play()

    def _on_session_time_update(self, current_time: float, active_cue: str):
        if not self.winfo_exists():
            return
        self.after_idle(self._apply_time_update, current_time, active_cue)

    def _apply_time_update(self, current_time: float, active_cue: str):
        if not self.winfo_exists():
            return
        if not self._user_seeking:
            try:
                self.scale_seek.set(current_time)
                self.lbl_time.configure(text=f"{_fmt_time(current_time)} / {_fmt_time(self.duration)}")
            except Exception:
                pass
        try:
            self.lbl_subtitle_cue.configure(text=active_cue)
        except Exception:
            pass

    def _on_session_state_change(self, is_playing: bool):
        if not self.winfo_exists():
            return
        self.after_idle(self._apply_state_change, is_playing)

    def _apply_state_change(self, is_playing: bool):
        if not self.winfo_exists():
            return
        try:
            txt = "⏸ Pause" if is_playing else "▶ Play"
            self.btn_play_pause.configure(text=txt)
        except Exception:
            pass

    def _on_download_now(self):
        self.session.stop()
        cb = self.on_download_now_cb
        animate_window_close(self, on_done=lambda: (self.destroy(), cb() if cb else None))

    def _on_close(self):
        self.session.stop()
        animate_window_close(self, on_done=self.destroy)

    def destroy(self):
        if hasattr(self, "session"):
            try:
                self.session.stop()
            except Exception:
                pass
        super().destroy()


__all__ = ["VideoPreviewModal"]
