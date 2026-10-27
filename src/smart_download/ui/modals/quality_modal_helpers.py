"""
Helper functions and banner builder for QualitySelectionModal (quality_modal_helpers.py).
Provides track attachment, destination path resolution, and embedded preview banner creation.
"""
import os
import tkinter as tk
from typing import Optional, Dict, Any, List

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
    if cb_sub:
        mode_fn = getattr(cb_sub, "get_selected_mode", None)
        sub_mode = mode_fn() if callable(mode_fn) else getattr(cb_sub, "_selected_mode", "hard_burn")
    selected_option.subtitle_embed_mode = sub_mode or "hard_burn"
    if subtitle_tracks and cb_sub:
        idx = cb_sub.current()
        if 0 < idx < len(subtitle_tracks):
            selected_option.selected_subtitle_track = subtitle_tracks[idx]
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
            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            clean_title = sanitize_filename(video_title)
            ext = getattr(selected_option, "ext", "mp4") if selected_option else "mp4"
            final_dest = os.path.join(downloads_dir, f"{clean_title}.{ext}")

    if selected_option:
        is_sub_burned = getattr(selected_option, "subtitle_embed_mode", "") == "hard_burn"
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

    disp_title = video_title if len(video_title) <= 75 else video_title[:72] + "..."
    lbl_title = tk.Label(title_row, text=disp_title, font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_bright, anchor="w")
    lbl_title.pack(side=tk.LEFT, fill=tk.X, expand=True)

    dur_mins, dur_secs = duration // 60, duration % 60
    dur_str = f"{dur_mins:02d}:{dur_secs:02d}" if duration > 0 else "Live / Unknown"
    meta_text = f"Duration: {dur_str}  •  Formats: {options_count}  •  Live Dubbing & Subtitles Ready"
    tk.Label(left_box, text=meta_text, font=("Segoe UI", 8), bg=c_panel, fg=c_text_muted, anchor="w").pack(fill=tk.X, pady=(3, 0))

    btn_preview = tk.Button(
        banner,
        text=tr("btn_preview_video", "🎬 Live Video & Dubbing Preview"),
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
