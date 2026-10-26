"""
Subtitle processing, VTT-to-SRT conversion, FFmpeg soft-muxing, and frame burn-in.
Dedicated service for flexible subtitle delivery modes (Stage 8.1).
"""
import os
import re
import sys
import html
import subprocess
import urllib.request
from typing import Dict, List, Optional, Tuple, Callable, Any

try:
    import requests
except ImportError:
    requests = None

try:
    from .youtube_models import find_ffmpeg_bin
except Exception:
    import shutil
    def find_ffmpeg_bin() -> Optional[str]:  # type: ignore
        return shutil.which("ffmpeg")

IS_WINDOWS = sys.platform.startswith("win")

ISO_639_2: Dict[str, str] = {
    "en": "eng", "ar": "ara", "es": "spa", "fr": "fra", "de": "deu", "it": "ita", "pt": "por",
    "ru": "rus", "ja": "jpn", "ko": "kor", "zh": "chi", "zh-hans": "chi", "zh-hant": "chi",
    "hi": "hin", "tr": "tur", "id": "ind", "nl": "nld", "pl": "pol", "vi": "vie", "th": "tha",
    "sv": "swe", "no": "nor", "da": "dan", "fi": "fin",
}


def _format_srt_timestamp(ts: str) -> str:
    """Converts MM:SS.mmm or HH:MM:SS.mmm into standard SRT HH:MM:SS,mmm."""
    parts = ts.strip().split(":")
    if len(parts) == 2:
        h, m, s = "00", parts[0].zfill(2), parts[1]
    elif len(parts) == 3:
        h, m, s = parts[0].zfill(2), parts[1].zfill(2), parts[2]
    else:
        return ts
    if "." in s:
        sec, ms = s.split(".", 1)
        return f"{h}:{m}:{sec.zfill(2)},{ms[:3].ljust(3, '0')}"
    return f"{h}:{m}:{s.zfill(2)},000"


def convert_vtt_to_srt(vtt_text: str) -> str:
    """Converts WebVTT subtitle text cleanly into standard SubRip (.srt) format."""
    blocks = re.split(r'\r?\n\r?\n+', vtt_text.strip())
    srt_cues: List[str] = []
    cue_index = 1
    timestamp_pat = re.compile(
        r'((?:\d+:)?\d{1,2}:\d{2}\.\d+)\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}\.\d+)'
    )

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        ts_line_idx, ts_match = -1, None
        for idx, line in enumerate(lines):
            m = timestamp_pat.search(line)
            if m:
                ts_line_idx, ts_match = idx, m
                break
        if ts_line_idx == -1 or not ts_match:
            continue

        start_ts = _format_srt_timestamp(ts_match.group(1))
        end_ts = _format_srt_timestamp(ts_match.group(2))
        srt_timing = f"{start_ts} --> {end_ts}"

        cue_lines = lines[ts_line_idx + 1:]
        cleaned = [html.unescape(re.sub(r'<[^>]+>', '', cl)).strip() for cl in cue_lines]
        valid_lines = [l for l in cleaned if l]
        if not valid_lines:
            continue

        srt_cues.append(f"{cue_index}\n{srt_timing}\n" + "\n".join(valid_lines))
        cue_index += 1

    return "\n\n".join(srt_cues) + ("\n" if srt_cues else "")


def download_subtitle_as_srt(sub_track: Dict[str, Any], video_filepath: str) -> Optional[str]:
    """
    Downloads subtitle, converts VTT to SRT, and saves alongside video in UTF-8-SIG.
    Writes both <video_stem>.<language>.srt and <video_stem>.srt so media players auto-detect.
    """
    if not sub_track or sub_track.get("sub_id") in (None, "none") or not sub_track.get("url"):
        return None
    url = sub_track["url"]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}
    raw_text = None
    if requests is not None:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                raw_text = resp.content.decode("utf-8", errors="replace")
        except Exception:
            raw_text = None
    if raw_text is None:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_text = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None

    ext = str(sub_track.get("ext") or "").lower()
    srt_content = convert_vtt_to_srt(raw_text) if (ext == "vtt" or "WEBVTT" in raw_text[:120]) else raw_text
    stem = os.path.splitext(video_filepath)[0]
    srt_path = f"{stem}.{sub_track.get('language') or 'sub'}.srt"
    default_srt_path = f"{stem}.srt"
    try:
        with open(srt_path, "w", encoding="utf-8-sig") as f:
            f.write(srt_content)
        try:
            with open(default_srt_path, "w", encoding="utf-8-sig") as f:
                f.write(srt_content)
        except Exception:
            pass
        return srt_path
    except Exception:
        return None


def embed_subtitle_into_mp4(
    video_path: str, srt_path: str, lang_code: str, ffmpeg_path: str,
    on_log: Optional[Callable[[str], None]] = None
) -> bool:
    """Muxes .srt into MP4 as soft subtitle stream via FFmpeg, atomically replacing video file."""
    if not ffmpeg_path or not video_path.lower().endswith(".mp4") or not os.path.isfile(srt_path):
        return False
    norm_lang = str(lang_code or "und").strip().lower()
    base_lang = norm_lang.split("-")[0].split("_")[0]
    iso3 = ISO_639_2.get(norm_lang) or ISO_639_2.get(base_lang) or (base_lang if len(base_lang) == 3 and base_lang.isalpha() else "und")
    temp_mp4 = f"{os.path.splitext(video_path)[0]}.submux.mp4"
    cmd = [
        ffmpeg_path, "-y", "-i", video_path, "-i", srt_path,
        "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
        "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
        "-metadata:s:s:0", f"language={iso3}",
        "-disposition:s:0", "default",
        "-f", "mp4", temp_mp4
    ]
    try:
        cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=cflags)
        if res.returncode == 0 and os.path.isfile(temp_mp4) and os.path.getsize(temp_mp4) > 0:
            os.replace(temp_mp4, video_path)
            if on_log: on_log(f"[SUBTITLES] Successfully embedded soft subtitle ({iso3}) into MP4 container.")
            return True
        if on_log and res.stderr:
            on_log(f"[SUBTITLES] Soft-mux error: {res.stderr[-200:].strip()}")
        if os.path.exists(temp_mp4):
            try: os.remove(temp_mp4)
            except Exception: pass
        return False
    except Exception as exc:
        if on_log: on_log(f"[SUBTITLES] FFmpeg soft-muxing skipped: {exc}")
        if os.path.exists(temp_mp4):
            try: os.remove(temp_mp4)
            except Exception: pass
        return False


def burn_subtitle_into_video(
    video_path: str, srt_path: str, ffmpeg_path: str,
    on_log: Optional[Callable[[str], None]] = None
) -> bool:
    """Burns subtitles directly onto video frames using FFmpeg's subtitles filter with veryfast H.264."""
    if not ffmpeg_path or not os.path.isfile(video_path) or not os.path.isfile(srt_path):
        return False
    temp_burn_mp4 = f"{os.path.splitext(video_path)[0]}.burn.mp4"
    srt_dir = os.path.dirname(os.path.abspath(srt_path))
    srt_base = os.path.basename(srt_path)
    escaped_base = srt_base.replace("\\", "/").replace("'", "'\\''")
    cmd = [
        ffmpeg_path, "-y",
        "-i", video_path,
        "-vf", f"subtitles='{escaped_base}'",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-c:a", "copy",
        "-f", "mp4",
        temp_burn_mp4
    ]
    try:
        cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=srt_dir,
            creationflags=cflags
        )
        if res.returncode == 0 and os.path.isfile(temp_burn_mp4) and os.path.getsize(temp_burn_mp4) > 0:
            os.replace(temp_burn_mp4, video_path)
            if on_log:
                on_log("[SUBTITLES] Successfully burned subtitles permanently into video frames.")
            return True
        if on_log and res.stderr:
            on_log(f"[SUBTITLES] FFmpeg burn error (code {res.returncode}): {res.stderr[-200:].strip()}")
        if os.path.exists(temp_burn_mp4):
            try: os.remove(temp_burn_mp4)
            except Exception: pass
        return False
    except Exception as exc:
        if on_log:
            on_log(f"[SUBTITLES] FFmpeg burn exception: {exc}")
        if os.path.exists(temp_burn_mp4):
            try: os.remove(temp_burn_mp4)
            except Exception: pass
        return False


def handle_subtitles_post_download(
    stream_info: Any, output_path: str, on_log: Optional[Callable[[str], None]] = None
) -> None:
    """Post-download pipeline: handles external SRT, soft-muxing, or hard burning based on selected mode."""
    sub = getattr(stream_info, "subtitle_track", None)
    if not sub or sub.get("sub_id") in (None, "none") or not sub.get("url"):
        return
    try:
        if on_log:
            on_log(f"[SUBTITLES] Downloading subtitle track: {sub.get('label', sub.get('language', 'sub'))}...")
        srt_path = download_subtitle_as_srt(sub, output_path)
        if not srt_path or not os.path.isfile(srt_path):
            if on_log:
                on_log("[SUBTITLES] Warning: Failed to download or convert subtitle track.")
            return

        if on_log:
            on_log(f"[SUBTITLES] Saved subtitle to {os.path.basename(srt_path)}")

        mode = getattr(stream_info, "subtitle_embed_mode", "soft_embed")
        if mode == "srt_only":
            if on_log:
                on_log("[SUBTITLES] External .srt saved (SRT-only mode selected; skipping video mux).")
            return

        ffmpeg_bin = find_ffmpeg_bin()
        if not ffmpeg_bin:
            if on_log:
                on_log("[SUBTITLES] FFmpeg not found; skipping video subtitle embedding/burning.")
            return

        if not output_path.lower().endswith(".mp4"):
            return

        if mode == "hard_burn":
            if on_log:
                on_log("[SUBTITLES] Burning subtitles permanently onto video frames...")
            ok = burn_subtitle_into_video(output_path, srt_path, ffmpeg_bin, on_log=on_log)
            if not ok:
                if on_log:
                    on_log("[SUBTITLES] Hard burn failed; falling back to soft subtitle embedding.")
                embed_subtitle_into_mp4(output_path, srt_path, sub.get("language", "und"), ffmpeg_bin, on_log=on_log)
        else:
            embed_subtitle_into_mp4(output_path, srt_path, sub.get("language", "und"), ffmpeg_bin, on_log=on_log)
    except Exception as exc:
        if on_log:
            on_log(f"[SUBTITLES] Warning: Subtitle handling encountered an issue: {exc}")
