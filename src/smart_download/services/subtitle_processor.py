"""
Subtitle processing, VTT-to-SRT conversion, FFmpeg soft-muxing, and frame burn-in.
Dedicated service for flexible subtitle delivery modes (Stage 8.1).
"""
import os
import re
import sys
import html
import subprocess
import shutil
import urllib.request
from typing import Dict, List, Optional, Tuple, Callable, Any

try:
    import requests
except ImportError:
    requests = None

try:
    from .youtube_models import find_ffmpeg_bin
except Exception:
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
    """Converts MM:SS.mmm, MM:SS,mmm, HH:MM:SS.mmm, or HH:MM:SS,mmm into standard SRT HH:MM:SS,mmm."""
    parts = ts.strip().split(":")
    if len(parts) == 2:
        h, m, s = "00", parts[0].zfill(2), parts[1]
    elif len(parts) == 3:
        h, m, s = parts[0].zfill(2), parts[1].zfill(2), parts[2]
    else:
        return ts
    s = s.replace(",", ".")
    if "." in s:
        sec, ms = s.split(".", 1)
        return f"{h}:{m}:{sec.zfill(2)},{ms[:3].ljust(3, '0')}"
    return f"{h}:{m}:{s.zfill(2)},000"


def _format_seconds_to_srt(seconds: float) -> str:
    """Formats float seconds into SRT timestamp HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        secs += 1
        ms = 0
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def _parse_timestamp_or_seconds(val: str) -> float:
    """Parses seconds string (e.g. '1.5s', '12.4', '1500ms') or HH:MM:SS.mmm into float seconds."""
    s = str(val or "").strip().replace(",", ".")
    if s.lower().endswith("ms"):
        try:
            return float(s[:-2].strip()) / 1000.0
        except Exception:
            return 0.0
    s = s.rstrip("sS")
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            if len(parts) == 4:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) + float(parts[3]) / 30.0
        except Exception:
            return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def _parse_xml_subtitles_to_srt(text: str) -> str:
    """Parses YouTube timedtext XML (<transcript>, <tt>, <text>, <p>) into valid SRT."""
    cues: List[str] = []
    cue_idx = 1
    tag_pat = re.compile(
        r'<(?:[a-zA-Z0-9_-]+:)?(?:text|p)\b([^>]*?)>(.*?)</(?:[a-zA-Z0-9_-]+:)?(?:text|p)>',
        re.DOTALL | re.IGNORECASE
    )
    attr_pat = re.compile(r'([a-zA-Z0-9_:-]+)\s*=\s*(?:[\'"]([^\'"]*)[\'"]|([^\s>]+))')

    for m in tag_pat.finditer(text):
        attrs_str = m.group(1)
        raw_body = m.group(2)
        attrs = {k: v1 if v1 != "" else v2 for k, v1, v2 in attr_pat.findall(attrs_str)}
        start_val = attrs.get("start") or attrs.get("begin")
        if not start_val:
            continue
        try:
            start = _parse_timestamp_or_seconds(start_val)
            dur_val = attrs.get("dur")
            end_val = attrs.get("end")
            if dur_val:
                dur = _parse_timestamp_or_seconds(dur_val)
                end = start + max(0.5, dur)
            elif end_val:
                end = _parse_timestamp_or_seconds(end_val)
            else:
                end = start + 2.0
            body = re.sub(r'<br\s*/?>', '\n', raw_body, flags=re.IGNORECASE)
            body = html.unescape(re.sub(r'<[^>]+>', '', body)).strip()
            if body:
                timing = f"{_format_seconds_to_srt(start)} --> {_format_seconds_to_srt(end)}"
                cues.append(f"{cue_idx}\n{timing}\n{body}")
                cue_idx += 1
        except Exception:
            continue
    return "\n\n".join(cues) + ("\n" if cues else "")


def _parse_json_subtitles_to_srt(text: str) -> str:
    """Parses YouTube json3 timedtext into valid SRT."""
    import json
    try:
        data = json.loads(text.lstrip("\ufeff"))
    except Exception:
        return ""
    events = data.get("events")
    if not isinstance(events, list):
        return ""
    cues: List[str] = []
    cue_idx = 1
    for ev in events:
        if not isinstance(ev, dict):
            continue
        start_ms = ev.get("tStartMs")
        dur_ms = ev.get("dDurationMs", 2000)
        if start_ms is None:
            continue
        start = float(start_ms) / 1000.0
        end = start + max(0.5, float(dur_ms or 2000) / 1000.0)
        segs = ev.get("segs", [])
        if isinstance(segs, list) and segs:
            body = "".join(str(s.get("utf8", "")) for s in segs if isinstance(s, dict)).strip()
        else:
            body = str(ev.get("text", "")).strip()
        body = html.unescape(re.sub(r'<[^>]+>', '', body)).strip()
        if body:
            timing = f"{_format_seconds_to_srt(start)} --> {_format_seconds_to_srt(end)}"
            cues.append(f"{cue_idx}\n{timing}\n{body}")
            cue_idx += 1
    return "\n\n".join(cues) + ("\n" if cues else "")


def convert_vtt_to_srt(vtt_text: str) -> str:
    """Converts WebVTT, YouTube XML (srv1/srv3/transcript/ttml), or JSON3 into standard SubRip (.srt)."""
    raw = str(vtt_text or "").lstrip("\ufeff").strip()
    if not raw:
        return ""

    # 1. JSON3 format
    if ("\"events\"" in raw or "'events'" in raw) and raw.startswith("{"):
        parsed_json = _parse_json_subtitles_to_srt(raw)
        if parsed_json:
            return parsed_json

    # 2. XML format (<transcript>, <tt>, <text>, <p>)
    if any(tag in raw for tag in ("<transcript", "<tt", "<text", "<p")):
        parsed_xml = _parse_xml_subtitles_to_srt(raw)
        if parsed_xml:
            return parsed_xml

    # 3. WebVTT format
    blocks = re.split(r'\r?\n\r?\n+', raw)
    srt_cues: List[str] = []
    cue_index = 1
    timestamp_pat = re.compile(
        r'((?:\d+:)?\d{1,2}:\d{2}[.,]\d+)\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}[.,]\d+)'
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
    Downloads subtitle, converts VTT/XML/JSON to SRT, and saves alongside video in pure UTF-8.
    Writes both <video_stem>.<language>.srt and <video_stem>.srt so media players auto-detect.
    """
    if not sub_track or sub_track.get("sub_id") in (None, "none") or not sub_track.get("url"):
        return None
    url = sub_track["url"]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}
    if isinstance(sub_track.get("http_headers"), dict):
        headers.update(sub_track["http_headers"])
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

    srt_content = convert_vtt_to_srt(raw_text)
    if not srt_content:
        srt_content = raw_text
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
        if cancel_event is None:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=cflags)
            rc, err = res.returncode, res.stderr
        else:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=cflags)
            while p.poll() is None:
                if cancel_event and cancel_event.is_set():
                    try: p.kill()
                    except Exception: pass
                    try: p.communicate()
                    except Exception: pass
                    if os.path.exists(temp_mp4):
                        try: os.remove(temp_mp4)
                        except Exception: pass
                    return False
                time.sleep(0.05)
            _, err = p.communicate()
            rc = p.returncode
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
        if on_log: on_log(f"[SUBTITLES] FFmpeg soft-muxing skipped: {exc}")
        if os.path.exists(temp_mp4):
            try: os.remove(temp_mp4)
            except Exception: pass
        return False


def burn_subtitle_into_video(
    video_path: str, srt_path: str, ffmpeg_path: str,
    on_log: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[Any] = None
) -> bool:
    """Burns subtitles directly onto video frames using FFmpeg's subtitles filter with veryfast H.264."""
    if cancel_event and cancel_event.is_set():
        return False
    if not ffmpeg_path or not os.path.isfile(video_path) or not os.path.isfile(srt_path):
        return False
    abs_video = os.path.abspath(video_path)
    abs_srt = os.path.abspath(srt_path)
    srt_dir = os.path.dirname(abs_video)
    burn_srt_path = os.path.join(srt_dir, "_sd_burn_sub.srt")
    temp_burn_mp4 = f"{os.path.splitext(abs_video)[0]}.burn.mp4"

    try:
        with open(abs_srt, "r", encoding="utf-8-sig", errors="replace") as sf:
            srt_content = sf.read()
        with open(burn_srt_path, "w", encoding="utf-8") as bf:
            bf.write(srt_content)
    except Exception as exc:
        if on_log:
            on_log(f"[SUBTITLES] Warning: Failed to prepare BOM-free SRT: {exc}")
        return False

    cmd = [
        ffmpeg_path, "-y",
        "-i", abs_video,
        "-vf", "subtitles=_sd_burn_sub.srt:charenc=UTF-8",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-c:a", "copy",
        "-f", "mp4",
        temp_burn_mp4
    ]
    try:
        cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0
        if cancel_event is None:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=srt_dir, creationflags=cflags)
            rc, err = res.returncode, res.stderr
        else:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=srt_dir, creationflags=cflags)
            while p.poll() is None:
                if cancel_event and cancel_event.is_set():
                    try: p.kill()
                    except Exception: pass
                    try: p.communicate()
                    except Exception: pass
                    if os.path.exists(temp_burn_mp4):
                        try: os.remove(temp_burn_mp4)
                        except Exception: pass
                    return False
                time.sleep(0.05)
            _, err = p.communicate()
            rc = p.returncode
        if rc == 0 and os.path.isfile(temp_burn_mp4) and os.path.getsize(temp_burn_mp4) > 0:
            os.replace(temp_burn_mp4, abs_video)
            if on_log:
                on_log("[SUBTITLES] Successfully burned subtitles permanently into video frames.")
            return True
        if on_log and err:
            on_log(f"[SUBTITLES] FFmpeg burn error (code {rc}): {err[-200:].strip()}")
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
    finally:
        if os.path.exists(burn_srt_path):
            try:
                os.remove(burn_srt_path)
            except Exception:
                pass


def handle_subtitles_post_download(
    stream_info: Any, output_path: str, on_log: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[Any] = None
) -> None:
    """Post-download pipeline: handles external SRT, soft-muxing, or hard burning based on selected mode."""
    sub = getattr(stream_info, "subtitle_track", None)
    if not sub or sub.get("sub_id") in (None, "none") or not sub.get("url") or (cancel_event and cancel_event.is_set()):
        return
    try:
        if on_log:
            on_log(f"[SUBTITLES] Downloading subtitle track: {sub.get('label', sub.get('language', 'sub'))}...")
        srt_path = download_subtitle_as_srt(sub, output_path)
        if not srt_path or not os.path.isfile(srt_path) or (cancel_event and cancel_event.is_set()):
            if on_log and not (cancel_event and cancel_event.is_set()):
                on_log("[SUBTITLES] Warning: Failed to download or convert subtitle track.")
            return

        if on_log:
            on_log(f"[SUBTITLES] Saved subtitle to {os.path.basename(srt_path)}")

        mode = getattr(stream_info, "subtitle_embed_mode", "soft_embed")
        if mode == "srt_only" or (cancel_event and cancel_event.is_set()):
            if on_log and mode == "srt_only":
                on_log("[SUBTITLES] External .srt saved (SRT-only mode selected; skipping video mux).")
            return

        ffmpeg_bin = find_ffmpeg_bin()
        if not ffmpeg_bin:
            if on_log:
                on_log("[SUBTITLES] FFmpeg not found; skipping video subtitle embedding/burning.")
            return

        if not output_path.lower().endswith(".mp4"):
            return

        sub_kwargs = {"cancel_event": cancel_event} if cancel_event is not None else {}
        if mode == "hard_burn":
            if on_log:
                on_log("[SUBTITLES] Burning subtitles permanently onto video frames...")
            ok = burn_subtitle_into_video(output_path, srt_path, ffmpeg_bin, on_log=on_log, **sub_kwargs)
            if not ok and not (cancel_event and cancel_event.is_set()):
                if on_log:
                    on_log("[SUBTITLES] Hard burn failed; falling back to soft subtitle embedding.")
                embed_subtitle_into_mp4(output_path, srt_path, sub.get("language", "und"), ffmpeg_bin, on_log=on_log, **sub_kwargs)
        else:
            embed_subtitle_into_mp4(output_path, srt_path, sub.get("language", "und"), ffmpeg_bin, on_log=on_log, **sub_kwargs)
    except Exception as exc:
        if on_log:
            on_log(f"[SUBTITLES] Warning: Subtitle handling encountered an issue: {exc}")
