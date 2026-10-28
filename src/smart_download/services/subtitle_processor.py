"""
Subtitle processing, VTT-to-SRT conversion, FFmpeg soft-muxing, and frame burn-in.
Dedicated service for flexible subtitle delivery modes (Stage 8.1 & Stage 9).
"""
import os
import re
import sys
import time
import subprocess
import shutil
from typing import Dict, List, Optional, Tuple, Callable, Any

from .subtitle_downloader import (
    _format_srt_timestamp,
    _format_seconds_to_srt,
    _parse_timestamp_or_seconds,
    _parse_xml_subtitles_to_srt,
    _parse_json_subtitles_to_srt,
    convert_vtt_to_srt,
    download_subtitle_as_srt,
    _translate_srt_cues_via_gtx,
)

try:
    from .youtube_models import find_ffmpeg_bin, detect_installed_cookie_browsers
except Exception:
    def find_ffmpeg_bin() -> Optional[str]: return shutil.which("ffmpeg")  # type: ignore
    def detect_installed_cookie_browsers() -> List[str]: return ["edge", "chrome", "firefox"]  # type: ignore

IS_WINDOWS = sys.platform.startswith("win")

ISO_639_2: Dict[str, str] = {
    "en": "eng", "ar": "ara", "es": "spa", "fr": "fra", "de": "deu", "it": "ita", "pt": "por",
    "ru": "rus", "ja": "jpn", "ko": "kor", "zh": "chi", "zh-hans": "chi", "zh-hant": "chi",
    "hi": "hin", "tr": "tur", "id": "ind", "nl": "nld", "pl": "pol", "vi": "vie", "th": "tha",
    "sv": "swe", "no": "nor", "da": "dan", "fi": "fin",
}


def strip_burn_tag_from_filename(filepath: str) -> str:
    """Strips [Sub-Burned] or [Sub] tag from file on disk if burning was not performed."""
    if not filepath or not os.path.exists(filepath):
        return filepath
    dir_name, file_name = os.path.split(filepath)
    new_name = re.sub(r'\s*\[(?:sub|sub-burned)\]', '', file_name, flags=re.IGNORECASE).strip()
    if new_name != file_name:
        new_path = os.path.join(dir_name, new_name)
        try:
            if not os.path.exists(new_path) or os.path.samefile(filepath, new_path):
                os.replace(filepath, new_path)
                return new_path
        except Exception:
            pass
    return filepath


def _is_ascii_writable_dir(path: str) -> bool:
    if not path or not os.path.isdir(path):
        return False
    abs_path = os.path.abspath(path)
    if not all(ord(c) < 128 for c in abs_path):
        return False
    test_file = os.path.join(abs_path, f"_sd_test_{os.getpid()}_{int(time.time()*1000)}.tmp")
    try:
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return True
    except Exception:
        return False


def _get_ascii_safe_temp_dir(fallback_dir: str) -> str:
    """Returns the first existing writable 100% ASCII directory for libass safe fopen on Windows."""
    if fallback_dir and _is_ascii_writable_dir(fallback_dir):
        return os.path.abspath(fallback_dir)
    import tempfile
    candidates = [
        tempfile.gettempdir(),
        r"C:\Users\Public",
        r"C:\Users\Public\Documents",
        r"C:\Users\Public\Downloads",
        r"C:\Temp",
        r"C:\Windows\Temp",
    ]
    for cand in candidates:
        try:
            if not os.path.isdir(cand) and cand == r"C:\Temp":
                try:
                    os.makedirs(cand, exist_ok=True)
                except Exception:
                    pass
            if _is_ascii_writable_dir(cand):
                return os.path.abspath(cand)
        except Exception:
            pass
    return os.path.abspath(fallback_dir) if fallback_dir else os.getcwd()


def embed_subtitle_into_mp4(
    video_path: str, srt_path: str, lang_code: str, ffmpeg_path: str,
    on_log: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[Any] = None
) -> bool:
    """Muxes .srt into MP4 as soft subtitle stream via FFmpeg, atomically replacing video file."""
    if cancel_event and cancel_event.is_set():
        return False
    if not ffmpeg_path or not video_path.lower().endswith(".mp4") or not os.path.isfile(video_path) or not os.path.isfile(srt_path):
        return False
    norm_lang = str(lang_code or "und").strip().lower()
    base_lang = norm_lang.split("-")[0].split("_")[0]
    iso3 = ISO_639_2.get(norm_lang) or ISO_639_2.get(base_lang) or (base_lang if len(base_lang) == 3 and base_lang.isalpha() else "und")
    temp_mp4 = f"{os.path.splitext(video_path)[0]}.submux.mp4"
    video_dir = os.path.dirname(os.path.abspath(video_path))
    ascii_work_dir = _get_ascii_safe_temp_dir(video_dir)
    temp_srt = os.path.join(ascii_work_dir, f"_sd_mux_{os.getpid()}_{int(time.time() * 1000)}.srt")

    try:
        with open(os.path.abspath(srt_path), "r", encoding="utf-8-sig", errors="replace") as sf:
            srt_content = sf.read()
        with open(temp_srt, "w", encoding="utf-8") as df:
            df.write(srt_content)
    except Exception:
        temp_srt = srt_path

    cmd_copy = [
        ffmpeg_path, "-y", "-i", video_path, "-i", temp_srt,
        "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
        "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
        "-metadata:s:s:0", f"language={iso3}", "-disposition:s:0", "default", "-f", "mp4", temp_mp4
    ]
    cmd_transcode = [
        ffmpeg_path, "-y", "-i", video_path, "-i", temp_srt,
        "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-c:s", "mov_text",
        "-metadata:s:s:0", f"language={iso3}", "-disposition:s:0", "default", "-f", "mp4", temp_mp4
    ]

    p: Optional[subprocess.Popen] = None
    cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0

    def _exec(current_cmd: List[str]) -> Tuple[int, str]:
        nonlocal p
        p = None
        if cancel_event is None:
            res = subprocess.run(current_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=ascii_work_dir, creationflags=cflags)
            return res.returncode, res.stderr
        p = subprocess.Popen(current_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=ascii_work_dir, creationflags=cflags)
        while True:
            try:
                _, err = p.communicate(timeout=0.05)
                return p.returncode, err
            except subprocess.TimeoutExpired:
                if cancel_event and cancel_event.is_set():
                    try: p.kill()
                    except Exception: pass
                    try: p.communicate()
                    except Exception: pass
                    if os.path.exists(temp_mp4):
                        try: os.remove(temp_mp4)
                        except Exception: pass
                    return -999, "Cancelled"

    try:
        rc, err = _exec(cmd_copy)
        if rc != 0 and (not cancel_event or not cancel_event.is_set()):
            if on_log:
                on_log(f"[SUBTITLES] Soft-mux copy attempt failed, retrying with audio transcode AAC: {err[-160:].strip()}")
            if os.path.exists(temp_mp4):
                try: os.remove(temp_mp4)
                except Exception: pass
            rc, err = _exec(cmd_transcode)

        if rc == 0 and os.path.isfile(temp_mp4) and os.path.getsize(temp_mp4) > 0:
            os.replace(temp_mp4, video_path)
            if on_log: on_log(f"[SUBTITLES] Successfully embedded soft subtitle ({iso3}) into MP4 container.")
            return True
        if on_log and err:
            on_log(f"[SUBTITLES] Soft-mux error: {err[-200:].strip()}")
        if os.path.exists(temp_mp4):
            try: os.remove(temp_mp4)
            except Exception: pass
        return False
    except Exception as exc:
        if p and p.poll() is None:
            try: p.kill()
            except Exception: pass
        if on_log: on_log(f"[SUBTITLES] FFmpeg soft-muxing skipped: {exc}")
        if os.path.exists(temp_mp4):
            try: os.remove(temp_mp4)
            except Exception: pass
        return False
    finally:
        if p and p.poll() is None:
            try: p.kill()
            except Exception: pass
        if temp_srt != srt_path and os.path.exists(temp_srt):
            try: os.remove(temp_srt)
            except Exception: pass



def burn_subtitle_into_video(
    video_path: str, srt_path: str, ffmpeg_path: str,
    on_log: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[Any] = None,
    subtitle_position: str = "bottom"
) -> bool:
    """Burns subtitles directly onto video frames using a robust 3-candidate FFmpeg filter and transcode chain."""
    if cancel_event and cancel_event.is_set():
        return False
    if not ffmpeg_path or not os.path.isfile(video_path) or not os.path.isfile(srt_path):
        return False
    abs_video = os.path.abspath(video_path)
    abs_srt = os.path.abspath(srt_path)
    video_dir = os.path.dirname(abs_video)
    ascii_work_dir = _get_ascii_safe_temp_dir(video_dir)
    burn_srt_name = f"_sd_burn_{os.getpid()}_{int(time.time() * 1000)}.srt"
    burn_srt_path = os.path.join(ascii_work_dir, burn_srt_name)
    temp_burn_mp4 = f"{os.path.splitext(abs_video)[0]}.burn.mp4"

    try:
        with open(abs_srt, "r", encoding="utf-8-sig", errors="replace") as sf:
            srt_content = sf.read()
        with open(burn_srt_path, "w", encoding="utf-8") as bf:
            bf.write(srt_content)
    except Exception as exc:
        if on_log:
            on_log(f"[SUBTITLES] Warning: Failed to prepare UTF-8 SRT: {exc}")
        return False

    escaped_path = burn_srt_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    align_styles = {
        "top": "Alignment=8,MarginV=25,FontSize=20,Outline=1,Shadow=1",
        "middle": "Alignment=5,MarginV=0,FontSize=20,Outline=1,Shadow=1",
        "bottom": "Alignment=2,MarginV=25,FontSize=20,Outline=1,Shadow=1",
    }
    style_str = align_styles.get(str(subtitle_position or "bottom").strip().lower(), align_styles["bottom"])

    # Candidate 1: subtitles={burn_srt_name}:charenc=UTF-8 with force_style
    # Candidate 2: subtitles={burn_srt_name} with force_style (no libiconv dependency)
    # Candidate 3: subtitles='{escaped_path}' with force_style
    candidate_vfs = [
        f"subtitles={burn_srt_name}:charenc=UTF-8:force_style='{style_str}'",
        f"subtitles={burn_srt_name}:force_style='{style_str}'",
        f"subtitles='{escaped_path}':force_style='{style_str}'",
    ]

    p: Optional[subprocess.Popen] = None
    cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0

    def _run_burn_cmd(current_cmd: List[str]) -> Tuple[int, str]:
        nonlocal p
        p = None
        if cancel_event is None:
            res = subprocess.run(
                current_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=ascii_work_dir,
                creationflags=cflags
            )
            return res.returncode, res.stderr
        p = subprocess.Popen(
            current_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ascii_work_dir,
            creationflags=cflags
        )
        while True:
            try:
                _, err = p.communicate(timeout=0.05)
                return p.returncode, err
            except subprocess.TimeoutExpired:
                if cancel_event and cancel_event.is_set():
                    try: p.kill()
                    except Exception: pass
                    try: p.communicate()
                    except Exception: pass
                    return -999, "Cancelled"

    try:
        success = False
        last_err = ""
        for idx, vf in enumerate(candidate_vfs, 1):
            if cancel_event and cancel_event.is_set():
                break
            cmd = [
                ffmpeg_path, "-y", "-i", abs_video, "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                "-c:a", "aac", "-b:a", "192k", "-f", "mp4", temp_burn_mp4
            ]
            rc, err = _run_burn_cmd(cmd)
            if rc == 0:
                if os.path.isfile(temp_burn_mp4) and os.path.getsize(temp_burn_mp4) > 0:
                    for _ in range(3):
                        try:
                            os.replace(temp_burn_mp4, abs_video)
                            break
                        except Exception:
                            time.sleep(0.08)
                if on_log:
                    on_log(f"[SUBTITLES] Successfully burned subtitles permanently into video frames (Candidate {idx}).")
                success = True
                break
            else:
                last_err = err
                if on_log and err:
                    on_log(f"[SUBTITLES] Burn candidate {idx} failed (code {rc}): {err[-180:].strip()}")
                if os.path.exists(temp_burn_mp4):
                    try: os.remove(temp_burn_mp4)
                    except Exception: pass

        if success:
            return True

        if on_log and last_err:
            on_log(f"[SUBTITLES] All subtitle burn candidates failed: {last_err[-200:].strip()}")
        if os.path.exists(temp_burn_mp4):
            try: os.remove(temp_burn_mp4)
            except Exception: pass
        return False
    except Exception as exc:
        if p and p.poll() is None:
            try: p.kill()
            except Exception: pass
        if on_log:
            on_log(f"[SUBTITLES] FFmpeg burn exception: {exc}")
        if os.path.exists(temp_burn_mp4):
            try: os.remove(temp_burn_mp4)
            except Exception: pass
        return False
    finally:
        if p and p.poll() is None:
            try: p.kill()
            except Exception: pass
        if os.path.exists(burn_srt_path):
            try: os.remove(burn_srt_path)
            except Exception: pass


def handle_subtitles_post_download(
    stream_info: Any, output_path: str, on_log: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[Any] = None
) -> str:
    """Post-download pipeline: handles external SRT, soft-muxing, or hard burning based on selected mode. Returns final output path."""
    sub = getattr(stream_info, "subtitle_track", None) or getattr(stream_info, "selected_subtitle_track", None)
    if not sub or sub.get("sub_id") in (None, "none") or (not sub.get("url") and not sub.get("base_url")) or (cancel_event and cancel_event.is_set()):
        return output_path
    try:
        if on_log:
            on_log(f"[SUBTITLES] Downloading subtitle track: {sub.get('label', sub.get('language', 'sub'))}...")
        srt_path = download_subtitle_as_srt(sub, output_path)
        mode = getattr(stream_info, "subtitle_embed_mode", "hard_burn")

        if not srt_path or not os.path.isfile(srt_path) or (cancel_event and cancel_event.is_set()):
            if on_log and not (cancel_event and cancel_event.is_set()):
                on_log("[SUBTITLES] Warning: Failed to download or convert subtitle track.")
            if mode == "hard_burn":
                output_path = strip_burn_tag_from_filename(output_path)
            return output_path

        if on_log:
            on_log(f"[SUBTITLES] Saved subtitle to {os.path.basename(srt_path)}")

        if mode == "srt_only" or (cancel_event and cancel_event.is_set()):
            if on_log and mode == "srt_only":
                on_log("[SUBTITLES] External .srt saved (SRT-only mode selected; skipping video mux).")
            return output_path

        ffmpeg_bin = find_ffmpeg_bin()
        if not ffmpeg_bin:
            if on_log:
                on_log("[SUBTITLES] FFmpeg not found; skipping video subtitle embedding/burning.")
            if mode == "hard_burn":
                output_path = strip_burn_tag_from_filename(output_path)
            return output_path

        if not output_path.lower().endswith(".mp4"):
            return output_path

        sub_kwargs = {"cancel_event": cancel_event} if cancel_event is not None else {}
        orig_stem = os.path.splitext(output_path)[0]
        default_srt = f"{orig_stem}.srt"

        def _cleanup_srt():
            cur_stem = os.path.splitext(output_path)[0]
            for p_path in {srt_path, default_srt, f"{cur_stem}.srt"}:
                if p_path and os.path.isfile(p_path):
                    try:
                        os.remove(p_path)
                    except Exception:
                        pass

        sub_pos = getattr(stream_info, "subtitle_position", None)
        if not sub_pos:
            try:
                from ..config import get_setting
                sub_pos = get_setting("subtitle_position", "bottom")
            except Exception:
                sub_pos = "bottom"

        if mode == "hard_burn":
            if on_log:
                on_log("[SUBTITLES] Burning subtitles permanently onto video frames...")
            burn_kwargs = dict(sub_kwargs)
            if sub_pos and isinstance(sub_pos, str) and sub_pos != "bottom":
                burn_kwargs["subtitle_position"] = sub_pos
            ok = burn_subtitle_into_video(output_path, srt_path, ffmpeg_bin, on_log=on_log, **burn_kwargs)
            if ok:
                _cleanup_srt()
            elif not (cancel_event and cancel_event.is_set()):
                if on_log:
                    on_log("[SUBTITLES] Hard burn failed; falling back to soft subtitle embedding.")
                output_path = strip_burn_tag_from_filename(output_path)
                soft_ok = embed_subtitle_into_mp4(output_path, srt_path, sub.get("language", "und"), ffmpeg_bin, on_log=on_log, **sub_kwargs)
                if soft_ok:
                    _cleanup_srt()
        else:
            soft_ok = embed_subtitle_into_mp4(output_path, srt_path, sub.get("language", "und"), ffmpeg_bin, on_log=on_log, **sub_kwargs)
            if soft_ok:
                _cleanup_srt()
        return output_path
    except Exception as exc:
        if on_log:
            on_log(f"[SUBTITLES] Warning: Subtitle handling encountered an issue: {exc}")
        return output_path

