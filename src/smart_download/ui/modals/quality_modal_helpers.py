"""
Helper functions and banner builder for QualitySelectionModal (quality_modal_helpers.py).
Provides track attachment, destination path resolution, and embedded preview banner creation.
"""
from __future__ import annotations

import os
try:
    import tkinter as tk
except Exception:
    tk = None  # type: ignore
from typing import Optional, Dict, Any, List

from ...config import get_base_downloads_dir, get_resource_path
from ...locales.i18n import tr
from ...utils.file_ops import apply_media_filename_tags, generate_unique_destination_path
from ...services.youtube_models import extract_media_platform, sanitize_filename


def attach_selected_tracks_to_option(
    selected_option: Optional[Any],
    audio_tracks: List[Dict[str, Any]],
    cb_audio: Optional[Any],
    subtitle_tracks: List[Dict[str, Any]],
    cb_sub: Optional[Any]
) -> None:
    """Attaches active audio dubbing track, subtitle track, and delivery mode to the selected option."""
    if not selected_option:
        return
    if audio_tracks and cb_audio:
        idx = cb_audio.current()
        if 0 <= idx < len(audio_tracks):
            selected_option.selected_audio_track = audio_tracks[idx]
    sub_mode = "hard_burn"
    sub_pos = "bottom"
    if cb_sub:
        mode_fn = getattr(cb_sub, "get_selected_mode", None)
        sub_mode = mode_fn() if callable(mode_fn) else getattr(cb_sub, "_selected_mode", "hard_burn")
        pos_fn = getattr(cb_sub, "get_selected_pos", None)
        sub_pos = pos_fn() if callable(pos_fn) else getattr(cb_sub, "_selected_pos", "bottom")
    selected_option.subtitle_embed_mode = sub_mode or "hard_burn"
    selected_option.subtitle_position = sub_pos or "bottom"
    if subtitle_tracks and cb_sub:
        idx = cb_sub.current()
        if idx <= 0 and len(subtitle_tracks) > 1 and getattr(cb_sub, "_user_touched_mode", False):
            ar_idx = next(
                (i for i, s in enumerate(subtitle_tracks) if i > 0 and str(s.get("language", "")).lower().startswith("ar")),
                None
            )
            idx = ar_idx if ar_idx is not None else 1
            try:
                cb_sub.current(idx)
            except Exception:
                pass
        if 0 < idx < len(subtitle_tracks):
            selected_option.selected_subtitle_track = subtitle_tracks[idx]
        else:
            selected_option.selected_subtitle_track = None
    else:
        selected_option.selected_subtitle_track = None


def resolve_final_dest(
    entry_dest: Any,
    dest_path: str,
    video_title: str,
    selected_option: Optional[Any],
    parent_app: Optional[Any] = None,
    master: Optional[Any] = None
) -> str:
    """Resolves and sanitizes the final destination file path with quality and subtitle tags."""
    final_dest = entry_dest.get().strip() if hasattr(entry_dest, "get") else ""
    if not final_dest:
        if dest_path:
            base, _ = os.path.splitext(dest_path)
            ext = getattr(selected_option, "ext", "mp4") if selected_option else "mp4"
            final_dest = f"{base}.{ext}"
        else:
            downloads_dir = getattr(parent_app, "_get_base_downloads_dir", get_base_downloads_dir)()
            clean_title = sanitize_filename(video_title)
            ext = getattr(selected_option, "ext", "mp4") if selected_option else "mp4"
            final_dest = os.path.join(downloads_dir, f"{clean_title}.{ext}")

    if selected_option:
        has_sub = bool(getattr(selected_option, "selected_subtitle_track", None))
        is_sub_burned = (getattr(selected_option, "subtitle_embed_mode", "") == "hard_burn") and has_sub
        final_dest = apply_media_filename_tags(
            final_dest,
            quality_label=getattr(selected_option, "resolution_label", ""),
            is_sub_burned=is_sub_burned,
            ext=getattr(selected_option, "ext", "mp4")
        )

    hm = getattr(parent_app, "history_manager", None) or getattr(master, "history_manager", None)
    reserved = hm.get_active_or_queued_paths() if hm else None
    return generate_unique_destination_path(final_dest, reserved_paths=reserved)


def build_preview_header_banner(
    parent_frame: tk.Frame,
    theme: Dict[str, str],
    video_title: str,
    duration: int,
    options_count: int,
    video_url: str,
    on_preview_cmd: Any
) -> tuple[tk.Frame, tk.Button]:
    """Creates a compact embedded Preview Header Banner showing platform, title, and preview button."""
    c_bg, c_panel = theme["c_bg"], theme["c_panel"]
    c_panel_light, c_border = theme["c_panel_light"], theme["c_border"]
    c_accent, c_accent_dark = theme["c_accent"], theme["c_accent_dark"]
    c_text_bright, c_text_muted = theme["c_text_bright"], theme["c_text_muted"]

    platform = extract_media_platform(video_url)
    plat_lower = platform.lower()
    plat_bg = "#475569"
    if "youtube" in plat_lower: plat_bg = "#ef4444"
    elif "tiktok" in plat_lower: plat_bg = "#ec4899"
    elif "instagram" in plat_lower: plat_bg = "#a855f7"
    elif "twitter" in plat_lower or "x" in plat_lower: plat_bg = "#0284c7"
    elif "facebook" in plat_lower: plat_bg = "#2563eb"

    banner = tk.Frame(parent_frame, bg=c_panel, padx=12, pady=10, highlightbackground=c_border, highlightthickness=1)
    banner.pack(fill=tk.X, pady=(0, 10))

    left_box = tk.Frame(banner, bg=c_panel)
    left_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    title_row = tk.Frame(left_box, bg=c_panel)
    title_row.pack(fill=tk.X)

    lbl_plat = tk.Label(
        title_row,
        text=f" {platform.upper()} ",
        font=("Segoe UI", 8, "bold"),
        bg=plat_bg,
        fg="white",
        padx=4,
        pady=1
    )
    lbl_plat.pack(side=tk.LEFT, padx=(0, 8))

    clean_title = "".join(c for c in (video_title or "") if ord(c) <= 0xFFFF and c != "\ufffd")
    disp_title = clean_title if len(clean_title) <= 75 else clean_title[:72] + "..."
    lbl_title = tk.Label(title_row, text=disp_title, font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_bright, anchor="w")
    lbl_title.pack(side=tk.LEFT, fill=tk.X, expand=True)

    dur_mins, dur_secs = duration // 60, duration % 60
    dur_str = f"{dur_mins:02d}:{dur_secs:02d}" if duration > 0 else "Live / Unknown"
    meta_text = f"Duration: {dur_str}  •  Formats: {options_count}  •  Live Dubbing & Subtitles Ready"
    tk.Label(left_box, text=meta_text, font=("Segoe UI", 8), bg=c_panel, fg=c_text_muted, anchor="w").pack(fill=tk.X, pady=(3, 0))

    btn_preview = tk.Button(
        banner,
        text=tr("btn_preview_video", "▶ Live Video & Dubbing Preview"),
        font=("Segoe UI", 9, "bold"),
        bg=c_accent_dark,
        fg="white",
        relief="flat",
        activebackground=c_accent,
        activeforeground="white",
        cursor="hand2",
        padx=12,
        pady=5,
        command=on_preview_cmd
    )
    btn_preview.pack(side=tk.RIGHT, padx=(8, 0))

    return banner, btn_preview


def resolve_preferred_option_index(options: List[Any]) -> int:
    """
    Resolves the option index matching the user's preferred video height setting.
    - If preferred_video_height == -1, returns index of first audio-only option (or 0).
    - If preferred_video_height > 0, returns index of exact height match or closest non-audio-only height match.
    - Otherwise returns 0.
    """
    if not options:
        return 0
    try:
        from ...config import get_setting
        raw_val = get_setting("preferred_video_height", 0)
    except Exception:
        try:
            from smart_download.config import get_setting
            raw_val = get_setting("preferred_video_height", 0)
        except Exception:
            raw_val = 0
    try:
        if isinstance(raw_val, str):
            raw_val = raw_val.lower().replace("p", "").strip()
        pref_h = int(raw_val or 0)
    except Exception:
        pref_h = 0

    if pref_h == -1:
        for i, opt in enumerate(options):
            if getattr(opt, "is_audio_only", False):
                return i
        return 0

    if pref_h > 0:
        exact_idx = None
        closest_idx = None
        closest_diff = float("inf")
        for i, opt in enumerate(options):
            if getattr(opt, "is_audio_only", False):
                continue
            h = getattr(opt, "height", 0) or 0
            if h == pref_h:
                return i
            if h > 0:
                diff = abs(h - pref_h)
                if diff < closest_diff:
                    closest_diff = diff
                    closest_idx = i
        if closest_idx is not None:
            return closest_idx
        return 0

    return 0


def build_quality_title_bar(
    modal: Any,
    outer: Any,
    theme: Dict[str, str],
    title: str,
    on_close_cmd: Any
) -> Any:
    """Builds a custom dark frameless title bar matching SafeModalDialog."""
    if tk is None:
        return None
    c_panel = theme.get("c_panel", "#1e293b")
    c_border = theme.get("c_border", "#334155")
    c_accent = theme.get("c_accent", "#38bdf8")
    c_text_bright = theme.get("c_text_bright", "#f8fafc")
    c_text_muted = theme.get("c_text_muted", "#94a3b8")
    c_danger = theme.get("c_danger", "#ef4444")

    title_bar = tk.Frame(outer, bg=c_panel, height=32)
    title_bar.pack(fill=tk.X, side=tk.TOP)

    lbl_app_icon = None
    png_path = get_resource_path("app_icon.png")
    if os.path.isfile(png_path):
        try:
            from PIL import Image, ImageTk
            resamp = getattr(Image, "Resampling", Image).LANCZOS if hasattr(Image, "Resampling") else getattr(Image, "ANTIALIAS", 1)
            img = Image.open(png_path).resize((16, 16), resamp)
            modal._modal_title_photo = ImageTk.PhotoImage(img)
            lbl_app_icon = tk.Label(title_bar, image=modal._modal_title_photo, bg=c_panel)
            lbl_app_icon.pack(side=tk.LEFT, padx=(8, 4), pady=4)
        except Exception:
            pass
    if not lbl_app_icon:
        lbl_app_icon = tk.Label(title_bar, text="⚡", font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_accent)
        lbl_app_icon.pack(side=tk.LEFT, padx=(8, 4), pady=4)

    lbl_win_title = tk.Label(title_bar, text=title, font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_bright, anchor="w")
    lbl_win_title.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 6))

    btn_close = tk.Label(title_bar, text="✕", font=("Segoe UI", 10, "bold"), bg=c_panel, fg=c_text_muted, width=3, cursor="hand2")
    btn_close.pack(side=tk.RIGHT, fill=tk.Y)
    btn_close.bind("<Enter>", lambda e: btn_close.configure(bg=c_danger, fg="white"))
    btn_close.bind("<Leave>", lambda e: btn_close.configure(bg=c_panel, fg=c_text_muted))
    btn_close.bind("<Button-1>", lambda e: on_close_cmd())

    for w in (title_bar, lbl_win_title, lbl_app_icon):
        w.bind("<ButtonPress-1>", modal._on_drag_press)
        w.bind("<B1-Motion>", modal._on_drag_motion)

    sep = tk.Frame(outer, bg=c_border, height=1)
    sep.pack(fill=tk.X, side=tk.TOP)
    return title_bar
