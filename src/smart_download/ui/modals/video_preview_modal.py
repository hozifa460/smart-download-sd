"""
VidMate-Style In-App Video Preview Modal (video_preview_modal.py).
Provides hardware-accelerated chromeless native preview with live WebVTT subtitles,
synchronized live audio dubbing, progressive MP4 direct stream playback,
and seamless web/embed fallback.
"""
import os
import re
import sys
import time
import base64
import tempfile
import shutil
import subprocess
import webbrowser
from typing import Dict, List, Optional, Any, Callable

from ...locales.i18n import tr
from .preview_html_builder import generate_preview_html

IS_WINDOWS = sys.platform.startswith("win")


def _find_chromeless_browser() -> Optional[str]:
    """Finds installed Microsoft Edge, Google Chrome, or Brave executable on Windows."""
    # 1. Edge
    edge_paths = [
        shutil.which("msedge"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for p in edge_paths:
        if p and os.path.isfile(p):
            return os.path.abspath(p)

    # 2. Chrome
    chrome_paths = [
        shutil.which("chrome"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in chrome_paths:
        if p and os.path.isfile(p):
            return os.path.abspath(p)

    # 3. Brave
    brave_paths = [
        shutil.which("brave"),
        shutil.which("brave-browser"),
        os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]
    for p in brave_paths:
        if p and os.path.isfile(p):
            return os.path.abspath(p)

    # 4. Chromium / Google Chrome on Linux/Mac
    for name in ("google-chrome", "chromium", "chromium-browser"):
        w = shutil.which(name)
        if w and os.path.isfile(w):
            return os.path.abspath(w)

    return None


def _find_progressive_mp4_url(
    stream_info: Optional[Any],
    info_dict: Optional[Dict[str, Any]],
    source_url: str = ""
) -> Optional[str]:
    """Finds direct playable progressive MP4 stream (e.g. format 18/22 or direct URL)."""
    if stream_info is not None:
        url_val = getattr(stream_info, "video_url", None) or getattr(stream_info, "url", None)
        is_prog = getattr(stream_info, "is_progressive", False)
        ext_val = getattr(stream_info, "ext", getattr(stream_info, "video_ext", "mp4"))
        if url_val and is_prog and str(ext_val).lower() == "mp4":
            return str(url_val)

    if isinstance(info_dict, dict):
        formats = info_dict.get("formats") or []
        prog_formats = [
            f for f in formats
            if f.get("url") and f.get("vcodec") != "none" and f.get("acodec") != "none"
            and str(f.get("ext") or "").lower() == "mp4"
        ]
        if prog_formats:
            prog_formats.sort(key=lambda f: int(f.get("height") or 0), reverse=True)
            fast_candidates = [f for f in prog_formats if int(f.get("height") or 0) <= 720]
            chosen = fast_candidates[0] if fast_candidates else prog_formats[0]
            return str(chosen.get("url") or "")

    clean_u = (source_url or "").split("?")[0].lower()
    if clean_u.endswith((".mp4", ".m4v", ".webm")):
        return source_url

    return None


def _convert_srt_to_vtt_data_uri(srt_content: str) -> Optional[str]:
    """Converts raw SRT text into a base64 data:text/vtt URI for HTML5 <track>."""
    if not srt_content or "-->" not in srt_content:
        return None
    vtt_body = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', srt_content.strip())
    if not vtt_body.startswith("WEBVTT"):
        vtt_body = "WEBVTT\n\n" + vtt_body
    b64 = base64.b64encode(vtt_body.encode("utf-8")).decode("ascii")
    return f"data:text/vtt;charset=utf-8;base64,{b64}"


def open_video_preview(
    parent: Any,
    url: str,
    video_title: str,
    stream_info: Optional[Any] = None,
    info_dict: Optional[Dict[str, Any]] = None,
    selected_sub_track: Optional[Dict[str, Any]] = None,
    theme: Optional[Dict[str, str]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    selected_audio_track: Optional[Dict[str, Any]] = None,
    options: Optional[List[Any]] = None,
    audio_tracks: Optional[List[Dict[str, Any]]] = None,
    subtitle_tracks: Optional[List[Dict[str, Any]]] = None,
    default_dest_path: str = "",
    on_confirm: Optional[Callable[[Any, str], None]] = None,
    on_open_in_main: Optional[Callable[[Any, str], None]] = None,
    on_cancel: Optional[Callable[[], None]] = None,
    parent_app: Optional[Any] = None,
    modal_ref: Optional[Any] = None,
    use_bridge: bool = True,
    subtitle_embed_mode: str = "hard_burn"
) -> str:
    """
    Builds and opens a real, VidMate-style video preview with synchronized live audio dubbing,
    asynchronous subtitles, and interactive format picker in a chromeless native window.
    """
    clean_url = str(url or "").strip()
    title = str(video_title or "Video Preview").strip()
    if on_log:
        on_log(f"[PREVIEW] Preparing video preview for: {title[:40]}...")

    stream_url = _find_progressive_mp4_url(stream_info, info_dict, source_url=clean_url)

    yt_match = re.search(r'(?:v=|\/|youtu\.be\/|embed\/)([0-9A-Za-z_-]{11})', clean_url)
    video_id = yt_match.group(1) if yt_match else (info_dict.get("id") if isinstance(info_dict, dict) else None)

    # Subtitle metadata
    vtt_data_uri = None
    sub_label = None
    sub_lang = "ar"
    if selected_sub_track and selected_sub_track.get("sub_id") not in (None, "none"):
        sub_label = selected_sub_track.get("label") or selected_sub_track.get("language") or "Subtitles"
        sub_lang = (selected_sub_track.get("language") or "ar").split("-")[0].split("_")[0] or "ar"

    # Audio dubbing metadata
    dub_audio_url = None
    audio_label = None
    if selected_audio_track and selected_audio_track.get("track_id") != "original":
        dub_audio_url = selected_audio_track.get("url")
        audio_label = selected_audio_track.get("label") or selected_audio_track.get("language")

    # Determine quality badge
    quality_label = getattr(stream_info, "resolution_label", None) if stream_info else None
    if not quality_label and stream_url:
        quality_label = "Direct MP4"
    elif not quality_label:
        quality_label = "Web Player"

    # Set up preview bridge session
    sid = None
    port = None
    target_launch_url = None
    if use_bridge:
        try:
            from ...services.preview_stream_bridge import register_preview_session, get_preview_bridge_port
            port = get_preview_bridge_port()
            sid = register_preview_session(
                url=clean_url,
                video_title=title,
                info_dict=info_dict,
                options=options or ([stream_info] if stream_info else []),
                audio_tracks=audio_tracks or ([selected_audio_track] if selected_audio_track else []),
                subtitle_tracks=subtitle_tracks or ([selected_sub_track] if selected_sub_track else []),
                default_dest_path=default_dest_path,
                on_confirm=on_confirm,
                on_open_in_main=on_open_in_main,
                on_cancel=on_cancel,
                parent_app=parent_app,
                modal_ref=modal_ref,
                selected_audio_track=selected_audio_track,
                selected_sub_track=selected_sub_track,
                subtitle_embed_mode=subtitle_embed_mode,
            )
            target_launch_url = f"http://127.0.0.1:{port}/player?sid={sid}"
            if not stream_url:
                stream_url = f"http://127.0.0.1:{port}/stream_video?sid={sid}&q_idx=0"
            if dub_audio_url and not dub_audio_url.startswith("http://127.0.0.1"):
                sel_a_idx = 0
                all_auds = audio_tracks or ([selected_audio_track] if selected_audio_track else [])
                if selected_audio_track and all_auds:
                    for idx, trk in enumerate(all_auds):
                        if trk == selected_audio_track or (trk.get("track_id") and trk.get("track_id") == selected_audio_track.get("track_id")):
                            sel_a_idx = idx
                            break
                dub_audio_url = f"http://127.0.0.1:{port}/stream_audio?sid={sid}&a_idx={sel_a_idx if sel_a_idx > 0 else 1}"
        except Exception as exc:
            if on_log:
                on_log(f"[PREVIEW] Note: Local bridge setup skipped: {exc}")

    # Fallback to synchronous subtitle conversion ONLY when not using bridge
    if not sid and selected_sub_track and selected_sub_track.get("sub_id") not in (None, "none"):
        try:
            from ...services.subtitle_downloader import download_subtitle_as_srt
            temp_sub_stem = os.path.join(tempfile.gettempdir(), f"_sd_prev_{os.getpid()}_{int(time.time()*1000)}")
            srt_path = download_subtitle_as_srt(selected_sub_track, f"{temp_sub_stem}.mp4")
            if srt_path and os.path.isfile(srt_path):
                with open(srt_path, "r", encoding="utf-8-sig", errors="replace") as sf:
                    srt_text = sf.read()
                vtt_data_uri = _convert_srt_to_vtt_data_uri(srt_text)
                try: os.remove(srt_path)
                except Exception: pass
        except Exception:
            pass

    # Generate self-contained HTML
    html_content = generate_preview_html(
        url=clean_url,
        video_title=title,
        stream_url=stream_url,
        vtt_data_uri=vtt_data_uri,
        video_id=video_id,
        sub_label=sub_label,
        quality_label=quality_label,
        sub_lang=sub_lang,
        dub_audio_url=dub_audio_url,
        audio_label=audio_label,
        selected_audio_track=selected_audio_track,
        audio_tracks=audio_tracks,
        options=options,
        subtitle_tracks=subtitle_tracks,
        default_dest_path=default_dest_path,
        sid=sid,
        bridge_port=port,
        selected_sub_track=selected_sub_track,
        subtitle_embed_mode=subtitle_embed_mode,
    )

    temp_html = os.path.join(tempfile.gettempdir(), f"_sd_preview_{os.getpid()}_{int(time.time()*1000)}.html")
    with open(temp_html, "w", encoding="utf-8") as hf:
        hf.write(html_content)

    launch_uri = target_launch_url if target_launch_url else f"file:///{temp_html.replace(os.sep, '/')}"
    win_size = "920,720" if options else "860,560"

    # 1. Check pywebview
    pywebview_available = False
    try:
        import webview  # type: ignore
        pywebview_available = True
    except Exception:
        pass

    if pywebview_available:
        try:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--preview-html", launch_uri]
            else:
                w, h = map(int, win_size.split(","))
                cmd = [
                    sys.executable, "-c",
                    f"import webview; webview.create_window({repr(title)}, {repr(launch_uri)}, width={w}, height={h}); webview.start()"
                ]
            cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0
            subprocess.Popen(cmd, creationflags=cflags)
            if on_log:
                on_log("[PREVIEW] Launched preview window via pywebview subprocess.")
            return temp_html
        except Exception:
            pass

    # 2. Chromeless native app window (Edge, Chrome, Brave)
    browser_exe = _find_chromeless_browser()
    if browser_exe:
        app_arg = f"--app={launch_uri}"
        cmd = [browser_exe, app_arg, f"--window-size={win_size}"]
        try:
            subprocess.Popen(cmd)
            if on_log:
                on_log(f"[PREVIEW] Launched native chromeless preview window via {os.path.basename(browser_exe)}.")
            return temp_html
        except Exception:
            pass

    # 3. Fallback to system default browser
    try:
        webbrowser.open(launch_uri)
        if on_log:
            on_log("[PREVIEW] Opened preview in default web browser.")
    except Exception as exc:
        if on_log:
            on_log(f"[PREVIEW] Failed to open browser: {exc}")

    return temp_html
