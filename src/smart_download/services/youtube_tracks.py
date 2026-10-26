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
        if "original" in fn or "default" in fn or f.get("language_preference", -1) >= 0:
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

        is_orig = (
            "original" in fn or "default" in fn
            or f.get("language_preference", -1) >= 0
            or (orig_lang and lang == orig_lang) or (not lang and not orig_lang)
        )
        key = "original" if is_orig else (lang or next((c for c in LANG_NAMES if c in fn), "und"))
        groups.setdefault(key, []).append((f, disp_name))

    if "original" not in groups and groups:
        groups["original"] = groups.pop(next(iter(groups.keys())))

    result: List[Dict[str, Any]] = []
    for key, f_tuples in groups.items():
        best_f, best_disp = max(
            f_tuples,
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
    tracks: List[Dict[str, Any]] = [{
        "sub_id": "none", "language": "none", "label": "None / بدون ترجمة",
        "url": "", "ext": "", "is_auto": False,
    }]
    manual_subs = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}

    for is_auto, sub_dict in ((False, manual_subs), (True, auto_subs)):
        for lang, flist in sub_dict.items():
            lang_norm = lang.lower()
            if is_auto and lang_norm not in POPULAR_AUTO_LANGS and lang not in manual_subs:
                continue
            res = _pick_best_sub_url(flist)
            if not res:
                continue
            url, ext = res
            if is_auto:
                suffix = "ترجمة تلقائية" if lang_norm == "ar" else "Auto-Translated"
            else:
                suffix = "Official"
            name = "العربية" if lang_norm == "ar" else ("English" if lang_norm == "en" else LANG_NAMES.get(lang_norm, (lang.upper(), ""))[0])
            label = f"{name} ({suffix})" if lang_norm != "ar" or not is_auto else f"العربية ({suffix})"
            tracks.append({
                "sub_id": f"{lang}-auto" if is_auto else lang,
                "language": lang, "label": label, "url": url, "ext": ext, "is_auto": is_auto,
            })

    def _sub_sort_key(t: Dict[str, Any]) -> Tuple[int, int, str]:
        if t["sub_id"] == "none": return (0, 0, "")
        lang = t["language"].lower()
        sub_order = 0 if lang == "en" else (1 if lang == "ar" else 2)
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
        tk.Label(
            row1,
            text=tr("lbl_audio_track", "🎙️ لغة الصوت (الدبلجة):"),
            font=("Segoe UI", 9, "bold"),
            bg=c_panel,
            fg=c_text_bright
        ).pack(side=tk.LEFT, padx=(0, 6))
        cb_audio = ttk.Combobox(
            row1,
            values=[t.get("label", "") for t in audio_tracks],
            state="readonly",
            font=("Segoe UI", 8),
            width=25
        )
        cb_audio.current(0)
        cb_audio.pack(side=tk.LEFT, padx=(0, 16))

    if subtitle_tracks:
        tk.Label(
            row1,
            text=tr("lbl_subtitle_track", "💬 الترجمة (Subtitles):"),
            font=("Segoe UI", 9, "bold"),
            bg=c_panel,
            fg=c_text_bright
        ).pack(side=tk.LEFT, padx=(0, 6))
        cb_sub = ttk.Combobox(
            row1,
            values=[s.get("label", "") for s in subtitle_tracks],
            state="readonly",
            font=("Segoe UI", 8),
            width=25
        )
        cb_sub.current(0)
        cb_sub.pack(side=tk.LEFT, padx=(0, 8))

        # Row 2: Interactive 3-Mode Selector (ALWAYS ENABLED & CLICKABLE)
        mode_options = [
            ("soft_embed", tr("sub_mode_soft", "ملف منفصل + دمج سريع (MP4)")),
            ("srt_only", tr("sub_mode_srt_only", "ملف ترجمة منفصل فقط (.srt)")),
            ("hard_burn", tr("sub_mode_burn", "ملف منفصل + طباعة بالفيديو (Burn-in)")),
        ]
        mode_codes = [m[0] for m in mode_options]
        mode_labels = [m[1] for m in mode_options]

        try:
            from ..config import get_setting, set_setting
        except Exception:
            try:
                from ...config import get_setting, set_setting
            except Exception:
                def get_setting(k: str, d: Any = None) -> Any: return d  # type: ignore
                def set_setting(k: str, v: Any) -> bool: return True  # type: ignore

        saved_mode = get_setting("subtitle_embed_mode", "soft_embed")
        initial_idx = mode_codes.index(saved_mode) if saved_mode in mode_codes else 0
        current_mode = mode_codes[initial_idx]

        # Backing combobox for unified test compatibility
        cb_sub_mode = ttk.Combobox(card, values=mode_labels, state="disabled", font=("Segoe UI", 8), width=24)
        cb_sub_mode.current(initial_idx)

        row2 = tk.Frame(card, bg=c_panel)
        row2.pack(fill=tk.X, pady=(2, 0))

        tk.Label(
            row2,
            text=tr("lbl_subtitle_mode", "⚙️ وضع الترجمة:"),
            font=("Segoe UI", 9, "bold"),
            bg=c_panel,
            fg=c_text_bright
        ).pack(side=tk.LEFT, padx=(0, 8))

        mode_var = tk.StringVar(master=card, value=current_mode)

        def _on_sub_changed(event=None):
            idx = cb_sub.current()
            if idx > 0:
                cb_sub_mode.configure(state="readonly")
            else:
                cb_sub_mode.configure(state="disabled")
                cb_sub._user_touched_mode = False

        def _on_radio_click():
            chosen = mode_var.get()
            cb_sub._selected_mode = chosen
            cb_sub._user_touched_mode = True
            if chosen in mode_codes:
                cb_sub_mode.current(mode_codes.index(chosen))
            try:
                set_setting("subtitle_embed_mode", chosen)
            except Exception:
                pass
            # Smart Auto-Select UX: If subtitles were 'None' and tracks exist, advance to first track
            if cb_sub.current() <= 0 and len(subtitle_tracks) > 1:
                cb_sub.current(1)
                _on_sub_changed()

        radio_widgets = []
        for code, label_txt in mode_options:
            rb = tk.Radiobutton(
                row2,
                text=label_txt,
                value=code,
                variable=mode_var,
                command=_on_radio_click,
                bg=c_panel,
                fg=c_text_bright,
                selectcolor=c_input_bg,
                activebackground=c_panel,
                activeforeground=c_accent,
                cursor="hand2",
                font=("Segoe UI", 8, "bold")
            )
            rb.pack(side=tk.LEFT, padx=(0, 8))
            radio_widgets.append(rb)

        def _on_mode_var_changed(*_):
            val = mode_var.get()
            if val in mode_codes:
                cb_sub._selected_mode = val
                idx = mode_codes.index(val)
                if cb_sub_mode.current() != idx:
                    cb_sub_mode.current(idx)

        try:
            mode_var.trace_add("write", _on_mode_var_changed)
        except Exception:
            try:
                mode_var.trace("w", _on_mode_var_changed)
            except Exception:
                pass

        def _get_active_mode() -> str:
            cur_idx = cb_sub_mode.current()
            if 0 <= cur_idx < len(mode_codes):
                cb_code = mode_codes[cur_idx]
                if cb_code != getattr(cb_sub, "_selected_mode", None):
                    cb_sub._selected_mode = cb_code
                    if mode_var.get() != cb_code:
                        mode_var.set(cb_code)
                    return cb_code
            if mode_var and mode_var.get() in mode_codes:
                return mode_var.get()
            return getattr(cb_sub, "_selected_mode", "soft_embed")

        def _on_mode_cb_changed(event=None):
            cur_idx = cb_sub_mode.current()
            if 0 <= cur_idx < len(mode_codes):
                code = mode_codes[cur_idx]
                cb_sub._selected_mode = code
                cb_sub._user_touched_mode = True
                mode_var.set(code)
                try:
                    set_setting("subtitle_embed_mode", code)
                except Exception:
                    pass
                if cb_sub.current() <= 0 and len(subtitle_tracks) > 1:
                    cb_sub.current(1)
                    _on_sub_changed()

        cb_sub._mode_combobox = cb_sub_mode
        cb_sub._mode_radios = radio_widgets
        cb_sub._mode_var = mode_var
        cb_sub._selected_mode = current_mode
        cb_sub._mode_codes = mode_codes
        cb_sub.get_selected_mode = _get_active_mode
        cb_sub._update_mode_state = _on_sub_changed

        cb_sub.bind("<<ComboboxSelected>>", _on_sub_changed)
        cb_sub_mode.bind("<<ComboboxSelected>>", _on_mode_cb_changed)

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
    "build_audio_subtitle_row",
]
