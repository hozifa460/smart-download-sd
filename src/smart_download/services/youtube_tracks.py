"""
YouTube audio dubbing and subtitle tracks extraction, WebVTT-to-SRT conversion,
subtitle soft-embedding via FFmpeg, and UI selector helpers.
"""
import os
import re
import sys
from typing import Dict, List, Optional, Tuple, Callable, Any

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None  # type: ignore
    ttk = None  # type: ignore

try:
    from ...locales.i18n import tr
except Exception:
    def tr(key: str, default: str = "") -> str:  # type: ignore
        return default

try:
    from ..config import get_setting, set_setting
except Exception:
    def get_setting(k: str, d: Any = None) -> Any: return d  # type: ignore
    def set_setting(k: str, v: Any) -> bool: return True  # type: ignore

from .youtube_models import find_ffmpeg_bin
from .subtitle_processor import (
    ISO_639_2,
    _format_srt_timestamp,
    convert_vtt_to_srt,
    download_subtitle_as_srt,
    embed_subtitle_into_mp4,
    burn_subtitle_into_video,
    handle_subtitles_post_download,
)

LANG_NAMES: Dict[str, Tuple[str, str]] = {
    "en": ("English", "الإنجليزية"), "ar": ("Arabic", "العربية"), "es": ("Spanish", "الإسبانية"),
    "fr": ("French", "الفرنسية"), "de": ("German", "الألمانية"), "it": ("Italian", "الإيطالية"),
    "pt": ("Portuguese", "البرتغالية"), "ru": ("Russian", "الروسية"), "ja": ("Japanese", "اليابانية"),
    "ko": ("Korean", "الكورية"), "zh": ("Chinese", "الصينية"), "zh-hans": ("Chinese (Simplified)", "الصينية المبسطة"),
    "zh-hant": ("Chinese (Traditional)", "الصينية التقليدية"), "hi": ("Hindi", "الهندية"),
    "tr": ("Turkish", "التركية"), "id": ("Indonesian", "الإندونيسية"), "nl": ("Dutch", "الهولندية"),
    "pl": ("Polish", "البولندية"), "vi": ("Vietnamese", "الفيتنامية"), "th": ("Thai", "التايلاندية"),
}

POPULAR_AUTO_LANGS = (
    "en", "ar", "es", "fr", "de", "tr", "ru", "hi", "ja", "ko", "zh-Hans", "zh-Hant", "zh"
)


def extract_audio_tracks(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Groups audio-only formats by language/dub: Original first, then en, ar, others. Always >=1 item."""
    formats = info.get("formats", []) or []
    audio_formats = [
        f for f in formats
        if str(f.get("vcodec") or "none").lower() in ("none", "")
        and str(f.get("acodec") or "none").lower() not in ("none", "")
        and (f.get("url") or "").startswith("http")
    ]
    if not audio_formats:
        top_lang = str(info.get("language") or "und").strip().lower()
        return [{
            "track_id": "original", "language": top_lang, "label": tr("audio_original_default", "Original (Default)"),
            "format_id": "", "url": "", "ext": "m4a", "acodec": "aac", "abr": 0.0,
            "filesize": None, "is_original": True, "http_headers": {},
        }]

    orig_lang = None
    for f in audio_formats:
        fn = str(f.get("format_note") or "").lower()
        lang = str(f.get("language") or "").strip().lower()
        if not lang and isinstance(f.get("audio_track"), dict):
            at = f["audio_track"]
            lang = str(at.get("language") or "").strip().lower()
            if not lang and at.get("id"):
                lang = str(at.get("id")).split(".")[0].strip().lower()
        pref = f.get("language_preference")
        has_lang_pref = (pref if pref is not None else -1) >= 0
        if "original" in fn or "default" in fn or has_lang_pref:
            if lang:
                orig_lang = lang
                break
    if not orig_lang:
        top_lang = str(info.get("language") or "").strip().lower()
        first_lang = ""
        if audio_formats:
            first_f = audio_formats[0]
            first_lang = str(first_f.get("language") or "").strip().lower()
            if not first_lang and isinstance(first_f.get("audio_track"), dict):
                first_lang = str(first_f["audio_track"].get("language") or "").strip().lower()
        orig_lang = top_lang or first_lang

    def _is_manifest_f(f_dict: Dict[str, Any]) -> bool:
        proto = str(f_dict.get("protocol") or "").lower()
        u = str(f_dict.get("url") or "").lower()
        return "m3u8" in proto or "dash" in proto or ".m3u8" in u or ".mpd" in u or "/manifest/" in u

    groups: Dict[str, List[Tuple[Dict[str, Any], str]]] = {}
    for f in audio_formats:
        lang = str(f.get("language") or "").strip().lower()
        fn = str(f.get("format_note") or "").strip().lower()
        disp_name = ""
        if isinstance(f.get("audio_track"), dict):
            at = f["audio_track"]
            if not lang:
                lang = str(at.get("language") or "").strip().lower()
                if not lang and at.get("id"):
                    lang = str(at.get("id")).split(".")[0].strip().lower()
            disp_name = str(at.get("display_name") or at.get("name") or "").strip()

        pref = f.get("language_preference")
        has_lang_pref = (pref if pref is not None else -1) >= 0
        is_orig = (
            "original" in fn or "default" in fn
            or has_lang_pref
            or (orig_lang and lang == orig_lang) or (not lang and not orig_lang)
        )
        key = "original" if is_orig else (lang or next((c for c in LANG_NAMES if c in fn), "und"))
        groups.setdefault(key, []).append((f, disp_name))

    if "original" not in groups and groups:
        groups["original"] = groups.pop(next(iter(groups.keys())))

    result: List[Dict[str, Any]] = []
    for key, f_tuples in groups.items():
        direct_cand = [t for t in f_tuples if not _is_manifest_f(t[0])]
        active_tuples = direct_cand if direct_cand else f_tuples
        best_f, best_disp = max(
            active_tuples,
            key=lambda t: (1 if str(t[0].get("ext") or "").lower() == "m4a" else 0, float(t[0].get("abr") or t[0].get("tbr") or 0.0))
        )
        abr = float(best_f.get("abr") or best_f.get("tbr") or 0.0)
        is_orig = (key == "original")
        lang_code = str(best_f.get("language") or (orig_lang if is_orig and orig_lang else key)).lower()

        if is_orig:
            label = tr("audio_original_default", "Original (Default)")
        elif best_disp:
            label = f"{best_disp} ({lang_code}) - {int(abr)}kbps" if abr > 0 else f"{best_disp} ({lang_code})"
        elif lang_code == "ar":
            label = f"العربية (ar) - {int(abr)}kbps" if abr > 0 else "العربية (ar)"
        elif lang_code == "en":
            label = f"English (en) - {int(abr)}kbps" if abr > 0 else "English (en)"
        elif lang_code in LANG_NAMES:
            name_en = LANG_NAMES[lang_code][0]
            label = f"{name_en} ({lang_code}) - {int(abr)}kbps" if abr > 0 else f"{name_en} ({lang_code})"
        else:
            label = f"{lang_code.upper()} - {int(abr)}kbps" if abr > 0 else lang_code.upper()

        result.append({
            "track_id": key, "language": lang_code, "label": label,
            "format_id": str(best_f.get("format_id") or ""), "url": str(best_f.get("url") or ""),
            "ext": str(best_f.get("ext") or "m4a"), "acodec": str(best_f.get("acodec") or ""),
            "abr": abr, "filesize": best_f.get("filesize") or best_f.get("filesize_approx"),
            "is_original": is_orig, "http_headers": dict(best_f.get("http_headers") or {}),
        })

    def _sort_key(t: Dict[str, Any]) -> Tuple[int, str]:
        if t["is_original"] or t["track_id"] == "original": return (0, "")
        if t["language"] == "en": return (1, "")
        if t["language"] == "ar": return (2, "")
        return (3, t["language"])

    res = sorted(result, key=_sort_key)
    if not res:
        res = [{
            "track_id": "original", "language": str(info.get("language") or "und").strip().lower(),
            "label": tr("audio_original_default", "Original (Default)"),
            "format_id": "", "url": "", "ext": "m4a", "acodec": "aac", "abr": 0.0,
            "filesize": None, "is_original": True, "http_headers": {},
        }]
    return res


def _normalize_sub_url_and_ext(url: str, ext: str) -> Tuple[str, str]:
    """Rewrites timedtext URLs with srv3/ttml/json3/srv1 to fmt=vtt for standard WebVTT delivery."""
    if not url:
        return url, ext
    if "fmt=" in url:
        url = re.sub(r'([?&]fmt=)(?:srv3|ttml|json3|srv1)\b', r'\g<1>vtt', url)
        if "fmt=vtt" in url:
            ext = "vtt"
    elif "timedtext" in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}fmt=vtt"
        ext = "vtt"
    return url, ext


def _pick_best_sub_url(sub_formats: List[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    """Selects the best subtitle URL and extension preferring srt > vtt > ttml > srv3."""
    order = {"srt": 5, "vtt": 4, "ttml": 3, "srv3": 2, "srv1": 1, "json3": 0}
    candidates = [f for f in sub_formats if f.get("url")]
    if not candidates:
        return None
    best = max(candidates, key=lambda f: order.get(str(f.get("ext") or "").lower(), 0))
    url = best["url"]
    ext = str(best.get("ext") or "vtt").lower()
    return _normalize_sub_url_and_ext(url, ext)


def extract_subtitle_tracks(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extracts manual and auto-translated subtitle tracks: None first, en, ar, manual, auto."""
    webpage_url = str(info.get("webpage_url") or info.get("original_url") or "").strip()
    tracks: List[Dict[str, Any]] = [{
        "sub_id": "none", "language": "none", "label": "None / بدون ترجمة",
        "url": "", "ext": "", "is_auto": False, "fallback_urls": [], "http_headers": {},
        "webpage_url": webpage_url, "base_url": "",
    }]
    manual_subs = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}
    popular_lower = [x.lower() for x in POPULAR_AUTO_LANGS]
    base_headers = dict(info.get("http_headers") or {})
    if "Cookie" not in base_headers and "cookie" not in base_headers:
        cookie_val = info.get("_sd_cookie_header") or info.get("cookies")
        if isinstance(cookie_val, dict):
            base_headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookie_val.items())
        elif isinstance(cookie_val, str) and cookie_val.strip():
            base_headers["Cookie"] = cookie_val.strip()

    for is_auto, sub_dict in ((False, manual_subs), (True, auto_subs)):
        for lang, flist in sub_dict.items():
            lang_norm = lang.lower()
            base_lang = lang_norm.split("-")[0].split("_")[0]
            if is_auto and lang_norm not in popular_lower and base_lang not in popular_lower and lang not in manual_subs:
                continue
            res = _pick_best_sub_url(flist)
            if not res:
                continue
            url, ext = res

            base_url = ""
            if "tlang=" in url:
                base_url = re.sub(r'([?&])tlang=[^&]*(&|$)', r'\1', url).replace("?&", "?").rstrip("?&")
            elif not is_auto:
                base_url = url
            if not base_url and is_auto:
                for orig_cand in (str(info.get("language") or "en").lower(), "en"):
                    if orig_cand in manual_subs:
                        m_res = _pick_best_sub_url(manual_subs[orig_cand])
                        if m_res and m_res[0]:
                            base_url = m_res[0]
                            break
                    if not base_url and orig_cand in auto_subs:
                        a_res = _pick_best_sub_url(auto_subs[orig_cand])
                        if a_res and a_res[0]:
                            base_url = a_res[0]
                            break

            fallback_urls: List[str] = []
            sub_headers = dict(base_headers)
            for f in flist:
                f_url = f.get("url")
                if f_url and f_url not in fallback_urls:
                    fallback_urls.append(f_url)
                if isinstance(f.get("http_headers"), dict):
                    sub_headers.update(f["http_headers"])

            if is_auto:
                suffix = "ترجمة تلقائية" if base_lang == "ar" else "Auto-Translated"
            else:
                suffix = "Official"
            name = "العربية" if base_lang == "ar" else ("English" if base_lang == "en" else LANG_NAMES.get(lang_norm, LANG_NAMES.get(base_lang, (lang.upper(), "")))[0])
            label = f"{name} ({suffix})" if base_lang != "ar" or not is_auto else f"العربية ({suffix})"
            tracks.append({
                "sub_id": f"{lang}-auto" if is_auto else lang,
                "language": lang, "label": label, "url": url, "ext": ext, "is_auto": is_auto,
                "fallback_urls": fallback_urls,
                "http_headers": sub_headers,
                "webpage_url": webpage_url,
                "base_url": base_url,
            })

    if not any(t.get("language", "").lower().startswith("ar") for t in tracks):
        base_track = next((t for t in tracks if t.get("sub_id") != "none" and (t.get("base_url") or t.get("url"))), None)
        if base_track:
            b_url = base_track.get("base_url") or base_track.get("url") or ""
            if b_url:
                sep = "&" if "?" in b_url else "?"
                ar_url = f"{b_url}{sep}tlang=ar"
                tracks.append({
                    "sub_id": "ar_auto",
                    "language": "ar",
                    "label": "العربية (ترجمة تلقائية)",
                    "url": ar_url,
                    "ext": base_track.get("ext", "vtt"),
                    "is_auto": True,
                    "fallback_urls": [ar_url],
                    "http_headers": dict(base_track.get("http_headers") or {}),
                    "webpage_url": webpage_url,
                    "base_url": b_url,
                })

    def _sub_sort_key(t: Dict[str, Any]) -> Tuple[int, int, str]:
        if t["sub_id"] == "none": return (0, 0, "")
        lang = t["language"].lower()
        sub_order = 0 if lang.startswith("ar") else (1 if lang.startswith("en") else 2)
        return (2 if t["is_auto"] else 1, sub_order, lang)

    return sorted(tracks, key=_sub_sort_key)


def build_audio_subtitle_row(
    parent_frame: Any, theme: Dict[str, str],
    audio_tracks: List[Dict[str, Any]], subtitle_tracks: List[Dict[str, Any]]
) -> Tuple[Optional[Any], Optional[Any]]:
    """Renders spacious themed 2-row Audio Track, Subtitles, and Delivery Mode card for QualitySelectionModal."""
    if tk is None or ttk is None or (not audio_tracks and not subtitle_tracks):
        return None, None
    c_panel = theme.get("c_panel", "#1e293b")
    c_border = theme.get("c_border", "#475569")
    c_text_bright = theme.get("c_text_bright", "#f8fafc")
    c_input_bg = theme.get("c_input_bg", "#0f172a")
    c_accent = theme.get("c_accent", "#38bdf8")

    card = tk.Frame(parent_frame, bg=c_panel, padx=12, pady=8, highlightbackground=c_border, highlightthickness=1)
    card.pack(fill=tk.X, pady=(0, 10))

    cb_audio, cb_sub = None, None

    # Row 1: Audio Track & Subtitles dropdowns
    row1 = tk.Frame(card, bg=c_panel)
    row1.pack(fill=tk.X, pady=(0, 6 if subtitle_tracks else 0))

    if audio_tracks:
        tk.Label(row1, text=tr("lbl_audio_track", "🎙️ لغة الصوت:"), font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_bright).pack(side=tk.LEFT, padx=(0, 6))
        cb_audio = ttk.Combobox(row1, values=[t.get("label", "") for t in audio_tracks], state="readonly", font=("Segoe UI", 8), width=23)
        pref_a = str(get_setting("preferred_audio_lang", "original") or "").lower()
        a_idx = next((i for i, t in enumerate(audio_tracks) if pref_a in (str(t.get("language") or "").lower(), str(t.get("track_id") or "").lower())), 0)
        cb_audio.current(a_idx)
        def _on_audio_changed(event=None):
            c_a = cb_audio.current()
            if 0 <= c_a < len(audio_tracks):
                t = audio_tracks[c_a]
                set_setting("preferred_audio_lang", t.get("language") or t.get("track_id") or "original")
        cb_audio.bind("<<ComboboxSelected>>", _on_audio_changed)
        cb_audio.pack(side=tk.LEFT, padx=(0, 14))

    if subtitle_tracks:
        tk.Label(row1, text=tr("lbl_subtitle_track", "💬 الترجمة:"), font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_bright).pack(side=tk.LEFT, padx=(0, 6))
        cb_sub = ttk.Combobox(row1, values=[s.get("label", "") for s in subtitle_tracks], state="readonly", font=("Segoe UI", 8), width=23)
        pref_s = str(get_setting("preferred_subtitle_lang", "none") or "").lower()
        s_idx = next((i for i, s in enumerate(subtitle_tracks) if pref_s != "none" and pref_s in (str(s.get("language") or "").lower(), str(s.get("sub_id") or "").lower())), 0)
        cb_sub.current(s_idx)
        cb_sub.pack(side=tk.LEFT, padx=(0, 8))

        mode_options = [
            ("soft_embed", tr("sub_mode_soft", "دمج ناعم")),
            ("srt_only", tr("sub_mode_srt_only", "ملف منفصل")),
            ("hard_burn", tr("sub_mode_burn", "حرق دائم")),
        ]
        mode_codes = [m[0] for m in mode_options]
        mode_labels = [m[1] for m in mode_options]
        saved_mode = get_setting("subtitle_embed_mode", "hard_burn")
        initial_idx = mode_codes.index(saved_mode) if saved_mode in mode_codes else 0
        current_mode = mode_codes[initial_idx]

        cb_sub_mode = ttk.Combobox(card, values=mode_labels, state="disabled", font=("Segoe UI", 8), width=20)
        cb_sub_mode.current(initial_idx)

        row2 = tk.Frame(card, bg=c_panel)
        row2.pack(fill=tk.X, pady=(2, 0))
        tk.Label(row2, text=tr("lbl_subtitle_mode", "⚙️ الوضع:"), font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_bright).pack(side=tk.LEFT, padx=(0, 6))
        mode_var = tk.StringVar(master=card, value=current_mode)

        def _on_sub_changed(event=None):
            idx = cb_sub.current()
            if event is not None and 0 <= idx < len(subtitle_tracks):
                set_setting("preferred_subtitle_lang", subtitle_tracks[idx].get("language") or "none")
            if idx > 0:
                cb_sub_mode.configure(state="readonly")
                if not getattr(cb_sub, "_user_touched_mode", False):
                    cb_sub._selected_mode = "hard_burn"
                    mode_var.set("hard_burn")
                    if "hard_burn" in mode_codes: cb_sub_mode.current(mode_codes.index("hard_burn"))
            else:
                cb_sub_mode.configure(state="disabled")
                cb_sub._user_touched_mode = False

        def _on_radio_click():
            chosen = mode_var.get()
            cb_sub._selected_mode = chosen
            cb_sub._user_touched_mode = True
            if chosen in mode_codes: cb_sub_mode.current(mode_codes.index(chosen))
            set_setting("subtitle_embed_mode", chosen)
            if cb_sub.current() <= 0 and len(subtitle_tracks) > 1:
                ar_idx = next((i for i, s in enumerate(subtitle_tracks) if i > 0 and str(s.get("language", "")).lower().startswith("ar")), 1)
                cb_sub.current(ar_idx); _on_sub_changed()

        radio_widgets = []
        for code, label_txt in mode_options:
            rb = tk.Radiobutton(row2, text=label_txt, value=code, variable=mode_var, command=_on_radio_click, bg=c_panel, fg=c_text_bright, selectcolor=c_input_bg, activebackground=c_panel, activeforeground=c_accent, cursor="hand2", font=("Segoe UI", 8, "bold"))
            rb.pack(side=tk.LEFT, padx=(0, 6))
            radio_widgets.append(rb)

        # Subtitle Position Combobox
        tk.Label(row2, text=tr("lbl_subtitle_pos", "📍 الموضع:"), font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_bright).pack(side=tk.LEFT, padx=(10, 4))
        pos_codes = ["bottom", "middle", "top"]
        pos_labels = [tr("sub_pos_bottom", "أسفل (Bottom)"), tr("sub_pos_middle", "وسط (Middle)"), tr("sub_pos_top", "أعلى (Top)")]
        cb_sub_pos = ttk.Combobox(row2, values=pos_labels, state="readonly", font=("Segoe UI", 8), width=14)
        saved_pos = get_setting("subtitle_position", "bottom")
        p_idx = pos_codes.index(saved_pos) if saved_pos in pos_codes else 0
        cb_sub_pos.current(p_idx)
        cb_sub_pos.pack(side=tk.LEFT, padx=(0, 6))

        def _on_pos_changed(event=None):
            c_p = cb_sub_pos.current()
            if 0 <= c_p < len(pos_codes):
                chosen_p = pos_codes[c_p]
                cb_sub._selected_pos = chosen_p
                if event is not None:
                    set_setting("subtitle_position", chosen_p)

        cb_sub_pos.bind("<<ComboboxSelected>>", _on_pos_changed)
        cb_sub._pos_combobox = cb_sub_pos
        cb_sub._selected_pos = pos_codes[p_idx]
        cb_sub.get_selected_pos = lambda: getattr(cb_sub, "_selected_pos", "bottom")

        def _on_mode_cb_changed(event=None):
            cur_idx = cb_sub_mode.current()
            if 0 <= cur_idx < len(mode_codes):
                code = mode_codes[cur_idx]
                cb_sub._selected_mode = code
                cb_sub._user_touched_mode = True
                mode_var.set(code)
                set_setting("subtitle_embed_mode", code)
                if cb_sub.current() <= 0 and len(subtitle_tracks) > 1:
                    ar_idx = next((i for i, s in enumerate(subtitle_tracks) if i > 0 and str(s.get("language", "")).lower().startswith("ar")), 1)
                    cb_sub.current(ar_idx); _on_sub_changed()

        def _get_active_mode() -> str:
            cur_idx = cb_sub_mode.current()
            if 0 <= cur_idx < len(mode_codes):
                code = mode_codes[cur_idx]
                cb_sub._selected_mode = code
                if mode_var.get() != code: mode_var.set(code)
                return code
            if mode_var and mode_var.get() in mode_codes: return mode_var.get()
            return getattr(cb_sub, "_selected_mode", "soft_embed")

        cb_sub._mode_combobox = cb_sub_mode
        cb_sub._mode_radios = radio_widgets
        cb_sub._mode_var = mode_var
        cb_sub._selected_mode = current_mode
        cb_sub._mode_codes = mode_codes
        cb_sub.get_selected_mode = _get_active_mode
        cb_sub._update_mode_state = _on_sub_changed

        cb_sub.bind("<<ComboboxSelected>>", _on_sub_changed)
        cb_sub_mode.bind("<<ComboboxSelected>>", _on_mode_cb_changed)
        if s_idx > 0:
            cb_sub_mode.configure(state="readonly")

    return cb_audio, cb_sub


__all__ = [
    "LANG_NAMES",
    "POPULAR_AUTO_LANGS",
    "ISO_639_2",
    "extract_audio_tracks",
    "extract_subtitle_tracks",
    "convert_vtt_to_srt",
    "download_subtitle_as_srt",
    "embed_subtitle_into_mp4",
    "burn_subtitle_into_video",
    "handle_subtitles_post_download",
    "find_ffmpeg_bin",
    "build_audio_subtitle_row",
]
