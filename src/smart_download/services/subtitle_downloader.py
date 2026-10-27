"""
Subtitle downloading, VTT/XML/JSON parsing, GTX translation, and SRT persistence.
Decomposed component of subtitle_processor (Stage 8.1 & Stage 9 SRP).
"""
import os
import re
import sys
import html
import json
import urllib.request
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any

try:
    import requests
except ImportError:
    requests = None

try:
    from .youtube_models import detect_installed_cookie_browsers
except Exception:
    def detect_installed_cookie_browsers() -> List[str]: return ["edge", "chrome", "firefox"]  # type: ignore


def _format_srt_timestamp(ts: str) -> str:
    """Converts MM:SS.mmm, MM:SS,mmm, HH:MM:SS.mmm, or HH:MM:SS,mmm into standard SRT HH:MM:SS,mmm."""
    parts = ts.strip().split(":")
    if len(parts) == 2: h, m, s = "00", parts[0].zfill(2), parts[1]
    elif len(parts) == 3: h, m, s = parts[0].zfill(2), parts[1].zfill(2), parts[2]
    else: return ts
    s = s.replace(",", ".")
    if "." in s:
        sec, ms = s.split(".", 1)
        return f"{h}:{m}:{sec.zfill(2)},{ms[:3].ljust(3, '0')}"
    return f"{h}:{m}:{s.zfill(2)},000"


def _format_seconds_to_srt(seconds: float) -> str:
    """Formats float seconds into SRT timestamp HH:MM:SS,mmm."""
    if seconds < 0: seconds = 0.0
    hrs, mins, secs = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000: secs += 1; ms = 0
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def _parse_timestamp_or_seconds(val: str) -> float:
    """Parses seconds string (e.g. '1.5s', '12.4', '1500ms') or HH:MM:SS.mmm into float seconds."""
    s = str(val or "").strip().replace(",", ".")
    if s.lower().endswith("ms"):
        try: return float(s[:-2].strip()) / 1000.0
        except Exception: return 0.0
    s = s.rstrip("sS")
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2: return int(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            if len(parts) == 4: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) + float(parts[3]) / 30.0
        except Exception: return 0.0
    try: return float(s)
    except Exception: return 0.0


def _parse_xml_subtitles_to_srt(text: str) -> str:
    """Parses YouTube timedtext XML (<transcript>, <tt>, <text>, <p>) into valid SRT."""
    cues = _parse_xml_to_cues(text)
    return _format_cues_to_srt(cues)


def _parse_json_subtitles_to_srt(text: str) -> str:
    """Parses YouTube json3 timedtext into valid SRT."""
    cues = _parse_json_to_cues(text)
    return _format_cues_to_srt(cues)


def _parse_xml_to_cues(text: str) -> List[Tuple[float, float, str]]:
    """Extracts raw (start_sec, end_sec, text) cues from XML timedtext."""
    cues: List[Tuple[float, float, str]] = []
    tag_pat = re.compile(r'<(?:[a-zA-Z0-9_-]+:)?(?:text|p)\b([^>]*?)>(.*?)</(?:[a-zA-Z0-9_-]+:)?(?:text|p)>', re.DOTALL | re.IGNORECASE)
    attr_pat = re.compile(r'([a-zA-Z0-9_:-]+)\s*=\s*(?:[\'"]([^\'"]*)[\'"]|([^\s>]+))')
    for m in tag_pat.finditer(text):
        attrs = {k: v1 if v1 != "" else v2 for k, v1, v2 in attr_pat.findall(m.group(1))}
        t_val, start_val = attrs.get("t"), attrs.get("start") or attrs.get("begin")
        if not start_val and not t_val: continue
        try:
            start = float(t_val) / 1000.0 if t_val else _parse_timestamp_or_seconds(start_val)
            d_val, dur_val, end_val = attrs.get("d"), attrs.get("dur"), attrs.get("end")
            if d_val: end = start + max(0.5, float(d_val) / 1000.0)
            elif dur_val: end = start + max(0.5, _parse_timestamp_or_seconds(dur_val))
            elif end_val: end = _parse_timestamp_or_seconds(end_val)
            else: end = start + 2.0
            body = html.unescape(re.sub(r'<[^>]+>', '', re.sub(r'</?s\b[^>]*>', '', re.sub(r'<br\s*/?>', '\n', m.group(2), flags=re.IGNORECASE), flags=re.IGNORECASE))).strip()
            if body:
                cues.append((start, end, body))
        except Exception: continue
    return cues


def _parse_json_to_cues(text: str) -> List[Tuple[float, float, str]]:
    """Extracts raw (start_sec, end_sec, text) cues from json3 timedtext."""
    try: data = json.loads(text.lstrip("\ufeff"))
    except Exception: return []
    events = data.get("events")
    if not isinstance(events, list): return []
    cues: List[Tuple[float, float, str]] = []
    for ev in events:
        if not isinstance(ev, dict): continue
        start_ms, dur_ms = ev.get("tStartMs"), ev.get("dDurationMs", 2000)
        if start_ms is None: continue
        start = float(start_ms) / 1000.0
        end = start + max(0.5, float(dur_ms or 2000) / 1000.0)
        segs = ev.get("segs", [])
        body = "".join(str(s.get("utf8", "")) for s in segs if isinstance(s, dict)).strip() if isinstance(segs, list) and segs else str(ev.get("text", "")).strip()
        body = html.unescape(re.sub(r'<[^>]+>', '', body)).strip()
        if body:
            cues.append((start, end, body))
    return cues


def _parse_vtt_to_cues(raw: str) -> List[Tuple[float, float, str]]:
    """Extracts raw (start_sec, end_sec, text) cues from WebVTT or SRT text."""
    blocks = re.split(r'\r?\n\r?\n+', raw)
    cues: List[Tuple[float, float, str]] = []
    timestamp_pat = re.compile(r'((?:\d+:)?\d{1,2}:\d{2}[.,]\d+)\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}[.,]\d+)')
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines: continue
        ts_line_idx, ts_match = -1, None
        for idx, line in enumerate(lines):
            m = timestamp_pat.search(line)
            if m:
                ts_line_idx, ts_match = idx, m
                break
        if ts_line_idx == -1 or not ts_match: continue
        start = _parse_timestamp_or_seconds(ts_match.group(1))
        end = _parse_timestamp_or_seconds(ts_match.group(2))
        cue_lines = lines[ts_line_idx + 1:]
        cleaned = [html.unescape(re.sub(r'<[^>]+>', '', cl)).strip() for cl in cue_lines]
        body = "\n".join(l for l in cleaned if l)
        if body:
            cues.append((start, end, body))
    return cues


def _parse_timedtext_to_cues(raw_text: str) -> List[Tuple[float, float, str]]:
    """Parses any timedtext payload (JSON3, XML, WebVTT, SRT) into [(start_sec, end_sec, text), ...]."""
    raw = str(raw_text or "").lstrip("\ufeff").strip()
    if not raw:
        return []
    if ("\"events\"" in raw or "'events'" in raw) and raw.startswith("{"):
        cues = _parse_json_to_cues(raw)
        if cues: return cues
    if any(tag in raw for tag in ("<transcript", "<tt", "<text", "<p")):
        cues = _parse_xml_to_cues(raw)
        if cues: return cues
    return _parse_vtt_to_cues(raw)


def _format_cues_to_srt(cues: List[Tuple[float, float, str]]) -> str:
    """Formats cues into standard SubRip (.srt) text."""
    out: List[str] = []
    for idx, (start, end, body) in enumerate(cues, 1):
        s_str = _format_seconds_to_srt(start)
        e_str = _format_seconds_to_srt(end)
        out.append(f"{idx}\n{s_str} --> {e_str}\n{body}")
    return "\n\n".join(out) + ("\n" if out else "")


def convert_vtt_to_srt(vtt_text: str) -> str:
    """Converts WebVTT, YouTube XML (srv1/srv3/transcript/ttml), or JSON3 into standard SubRip (.srt)."""
    cues = _parse_timedtext_to_cues(vtt_text)
    return _format_cues_to_srt(cues)


def _translate_srt_cues_via_gtx(
    cues: List[Tuple[float, float, str]],
    target_lang: str = "ar"
) -> List[Tuple[float, float, str]]:
    """
    Translates cue texts into target_lang using Google Translate GTX endpoint.
    Batches cues up to ~2500 characters joined by '\n ||| \n'.
    """
    if not cues:
        return []

    t_lang = str(target_lang or "ar").strip().lower().split("-")[0].split("_")[0] or "ar"
    sep = "\n ||| \n"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}

    batches: List[List[Tuple[float, float, str]]] = []
    cur_batch: List[Tuple[float, float, str]] = []
    cur_len = 0
    for cue in cues:
        cue_text = str(cue[2] if len(cue) >= 3 else "")
        added_len = len(cue_text) + len(sep)
        if cur_batch and (cur_len + added_len > 2500):
            batches.append(cur_batch)
            cur_batch = [cue]
            cur_len = added_len
        else:
            cur_batch.append(cue)
            cur_len += added_len
    if cur_batch:
        batches.append(cur_batch)

    translated_cues: List[Tuple[float, float, str]] = []

    def _query_gtx(text_chunk: str) -> str:
        q = urllib.parse.quote(text_chunk)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={t_lang}&dt=t&q={q}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if isinstance(data, list) and data and isinstance(data[0], list):
                return "".join(part[0] for part in data[0] if part and len(part) > 0 and part[0])
        return ""

    for batch in batches:
        chunk = sep.join(str(c[2]) for c in batch)
        try:
            full_trans = _query_gtx(chunk)
            parts = re.split(r'\s*\|\|\|\s*', full_trans) if full_trans else []
            if len(parts) == len(batch):
                for i, c in enumerate(batch):
                    translated_cues.append((c[0], c[1], parts[i].strip()))
                continue
        except Exception:
            pass

        for c in batch:
            try:
                single_trans = _query_gtx(str(c[2]))
                translated_cues.append((c[0], c[1], single_trans.strip() if single_trans else c[2]))
            except Exception:
                translated_cues.append((c[0], c[1], c[2]))

    return translated_cues


def _strip_tlang_param(url: str) -> str:
    """Removes &tlang=... or ?tlang=... query parameter from URL."""
    if not url:
        return ""
    u = re.sub(r'([?&])tlang=[^&]*(&|$)', r'\1', url)
    return u.replace("?&", "?").rstrip("?&")


def _fetch_url_direct(url: str, headers: Dict[str, str], timeout: int = 15) -> Optional[str]:
    """Performs direct HTTP GET via requests or urllib."""
    if requests is not None:
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r.content.decode("utf-8", errors="replace")
        except Exception:
            pass
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def download_subtitle_as_srt(sub_track: Dict[str, Any], video_filepath: str) -> Optional[str]:
    """
    Downloads subtitle, converts VTT/XML/JSON to SRT, and saves alongside video in pure UTF-8.
    Tries fallback_urls, browser cookies, and deterministic base timedtext URL with GTX translation.
    Never writes .srt if srt_content is empty or lacks '-->' timing.
    """
    if not sub_track or sub_track.get("sub_id") in (None, "none"):
        return None

    primary_url = sub_track.get("url") or ""
    fallbacks = sub_track.get("fallback_urls") or []
    cand_urls = [u for u in [primary_url] + fallbacks if u]
    if not cand_urls and not sub_track.get("base_url"):
        return None

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}
    if isinstance(sub_track.get("http_headers"), dict):
        headers.update(sub_track["http_headers"])

    def _convert(txt: Optional[str]) -> str:
        if not txt or not txt.strip(): return ""
        c = convert_vtt_to_srt(txt)
        return c if c and "-->" in c else (txt if "-->" in txt else "")

    # Phase 1: Try candidate URLs directly
    srt_content = ""
    for u in cand_urls:
        srt_content = _convert(_fetch_url_direct(u, headers))
        if srt_content: break

    # Phase 2: Try browser cookies if available
    if not srt_content:
        try:
            import yt_dlp.cookies
            for b in detect_installed_cookie_browsers():
                try: cj = yt_dlp.cookies.extract_cookies_from_browser(b)
                except Exception: cj = None
                if not cj: continue
                try:
                    cstr = "; ".join(f"{c.name}={c.value}" for c in cj)
                    if cstr: headers["Cookie"] = cstr
                except Exception: pass
                for u in cand_urls:
                    if requests is not None:
                        try:
                            r = requests.get(u, headers=headers, cookies=cj, timeout=15)
                            if r.status_code == 200:
                                srt_content = _convert(r.content.decode("utf-8", errors="replace"))
                        except Exception: pass
                    if not srt_content:
                        try:
                            req = urllib.request.Request(u, headers=headers)
                            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
                            with opener.open(req, timeout=15) as resp:
                                srt_content = _convert(resp.read().decode("utf-8", errors="replace"))
                        except Exception: pass
                    if srt_content: break
                if srt_content: break
        except Exception: pass

    # Phase 3: Try yt_dlp subprocess/temporary directory if webpage_url exists
    if not srt_content and sub_track.get("webpage_url"):
        try:
            import tempfile, yt_dlp
            lang = sub_track.get("language") or "en"
            with tempfile.TemporaryDirectory() as tmp_dir:
                ydl_opts: Dict[str, Any] = {
                    "writesubtitles": True, "writeautomaticsub": True,
                    "subtitleslangs": [lang], "subtitlesformat": "srt/vtt/ttml/srv3/json3/best",
                    "skip_download": True, "quiet": True, "no_warnings": True,
                    "outtmpl": os.path.join(tmp_dir, "%(id)s.%(ext)s"),
                }
                if isinstance(sub_track.get("http_headers"), dict) and sub_track["http_headers"]:
                    ydl_opts["http_headers"] = sub_track["http_headers"]

                def _scan_tmp() -> str:
                    for fn in os.listdir(tmp_dir):
                        fp = os.path.join(tmp_dir, fn)
                        if os.path.isfile(fp) and any(fp.endswith(e) for e in (".srt", ".vtt", ".ttml", ".srv3", ".xml", ".json3")):
                            try:
                                with open(fp, "r", encoding="utf-8-sig", errors="replace") as sf:
                                    sc = _convert(sf.read())
                                    if sc: return sc
                            except Exception: pass
                    return ""

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try: ydl.download([sub_track["webpage_url"]])
                    except Exception: pass
                srt_content = _scan_tmp()
        except Exception: pass

    # Phase 4: Deterministic fallback for YouTube &tlang= HTTP 429 rate-limiting
    # Fetch untranslated base timedtext track directly and translate via GTX
    if not srt_content:
        base_cand_url = sub_track.get("base_url") or ""
        if not base_cand_url:
            for u in cand_urls:
                if "tlang=" in u:
                    base_cand_url = _strip_tlang_param(u)
                    break

        if base_cand_url:
            base_content = None
            clean_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}
            # Try formats vtt, json3, srv3, ttml
            for fmt in ("vtt", "json3", "srv3", "ttml"):
                if "fmt=" in base_cand_url:
                    test_url = re.sub(r'([?&]fmt=)[^&]+', rf'\g<1>{fmt}', base_cand_url)
                else:
                    sep = "&" if "?" in base_cand_url else "?"
                    test_url = f"{base_cand_url}{sep}fmt={fmt}"
                fetched = _fetch_url_direct(test_url, clean_headers, timeout=10)
                if fetched and len(fetched.strip()) > 30:
                    base_content = fetched
                    break

            if base_content:
                cues = _parse_timedtext_to_cues(base_content)
                if cues:
                    target_lang = str(sub_track.get("language") or "ar").split("-")[0].split("_")[0] or "ar"
                    translated_cues = _translate_srt_cues_via_gtx(cues, target_lang=target_lang)
                    if translated_cues:
                        srt_content = _format_cues_to_srt(translated_cues)

    if not srt_content or "-->" not in srt_content:
        return None

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
