"""
VidMate-Style In-App Video Preview Modal (Stage 10 / Stage 8.2).
Provides hardware-accelerated chromeless native preview with live WebVTT subtitles,
progressive MP4 direct stream playback, and seamless web/embed fallback.
"""
import os
import re
import sys
import html
import time
import base64
import tempfile
import shutil
import subprocess
import webbrowser
from typing import Dict, List, Optional, Any, Callable

from ...locales.i18n import tr
from ...services.subtitle_processor import download_subtitle_as_srt

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
        os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]
    for p in brave_paths:
        if p and os.path.isfile(p):
            return os.path.abspath(p)

    return None


def _find_progressive_mp4_url(
    stream_info: Optional[Any],
    info_dict: Optional[Dict[str, Any]],
    source_url: str = ""
) -> Optional[str]:
    """Finds direct playable progressive MP4 stream (e.g. format 18/22 or direct URL)."""
    # Check info_dict formats
    if isinstance(info_dict, dict):
        formats = info_dict.get("formats") or []
        prog_formats = [
            f for f in formats
            if f.get("url") and f.get("vcodec") != "none" and f.get("acodec") != "none"
            and str(f.get("ext") or "").lower() == "mp4"
        ]
        if prog_formats:
            # Sort by height ascending or pick 720p/360p
            prog_formats.sort(key=lambda f: int(f.get("height") or 0), reverse=True)
            # Prefer <= 720p for fast preview buffering
            fast_candidates = [f for f in prog_formats if int(f.get("height") or 0) <= 720]
            chosen = fast_candidates[0] if fast_candidates else prog_formats[0]
            return str(chosen.get("url") or "")

    # Check stream_info object
    if stream_info is not None:
        url_val = getattr(stream_info, "url", None)
        ext_val = getattr(stream_info, "ext", "mp4")
        if url_val and str(ext_val).lower() == "mp4" and "googlevideo.com" not in str(url_val):
            return str(url_val)

    # Check direct source_url
    clean_u = (source_url or "").split("?")[0].lower()
    if clean_u.endswith((".mp4", ".m4v", ".webm")):
        return source_url

    return None


def _convert_srt_to_vtt_data_uri(srt_content: str) -> Optional[str]:
    """Converts raw SRT text into a base64 data:text/vtt URI for HTML5 <track>."""
    if not srt_content or "-->" not in srt_content:
        return None
    # Change comma in timestamps to period
    vtt_body = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', srt_content.strip())
    # Ensure WEBVTT header
    if not vtt_body.startswith("WEBVTT"):
        vtt_body = "WEBVTT\n\n" + vtt_body
    b64 = base64.b64encode(vtt_body.encode("utf-8")).decode("ascii")
    return f"data:text/vtt;charset=utf-8;base64,{b64}"


def generate_preview_html(
    url: str,
    video_title: str,
    stream_url: Optional[str] = None,
    vtt_data_uri: Optional[str] = None,
    video_id: Optional[str] = None,
    sub_label: Optional[str] = None,
    quality_label: Optional[str] = None
) -> str:
    """Generates standalone modern dark-themed HTML5 preview player with live WebVTT subtitles."""
    safe_title = html.escape(video_title or "Video Preview")
    safe_stream = html.escape(stream_url or "")
    safe_sub_label = html.escape(sub_label or "Subtitles")
    safe_quality = html.escape(quality_label or ("MP4 Stream" if stream_url else "Web Player"))

    if video_id:
        embed_src = f"https://www.youtube.com/embed/{video_id}?autoplay=1&cc_load_policy=1&cc_lang_pref=ar&hl=ar"
    else:
        embed_src = url

    has_stream_js = "true" if stream_url else "false"
    track_html = ""
    if vtt_data_uri:
        track_html = f'<track label="{safe_sub_label}" kind="subtitles" srclang="ar" src="{vtt_data_uri}" default>'

    sub_badge_html = ""
    if vtt_data_uri:
        sub_badge_html = f'<span class="badge badge-sub">💬 {safe_sub_label}</span>'
    else:
        sub_badge_html = '<span class="badge badge-dim">💬 No Subtitles</span>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_title} — Smart Download Preview</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: #090d16;
            color: #f1f5f9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            user-select: none;
        }}
        .header {{
            background: #131a29;
            height: 52px;
            padding: 0 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #1e293b;
            flex-shrink: 0;
            gap: 12px;
        }}
        .title-group {{
            display: flex;
            align-items: center;
            gap: 10px;
            overflow: hidden;
            flex: 1;
        }}
        .title {{
            font-size: 14px;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            color: #f8fafc;
        }}
        .badge {{
            font-size: 11px;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 9999px;
            white-space: nowrap;
        }}
        .badge-res {{ background: #0284c7; color: #ffffff; }}
        .badge-sub {{ background: #059669; color: #ffffff; }}
        .badge-dim {{ background: #334155; color: #94a3b8; }}
        .actions {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .btn {{
            background: #1e293b;
            color: #38bdf8;
            border: 1px solid #334155;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
            white-space: nowrap;
        }}
        .btn:hover {{
            background: #0284c7;
            color: #ffffff;
            border-color: #0284c7;
        }}
        .player-container {{
            flex: 1;
            position: relative;
            background: #000000;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}
        video, iframe {{
            width: 100%;
            height: 100%;
            border: none;
            outline: none;
            background: #000000;
        }}
        ::cue {{
            background-color: rgba(0, 0, 0, 0.75);
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            font-size: 18px;
            font-weight: 600;
            text-shadow: 0 2px 4px rgba(0,0,0,0.9);
            line-height: 1.4;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title-group">
            <span class="badge badge-res">🎞️ {safe_quality}</span>
            {sub_badge_html}
            <span class="title" title="{safe_title}">🎬 {safe_title}</span>
        </div>
        <div class="actions">
            <button id="toggleBtn" class="btn" onclick="togglePlayer()">🌐 Switch to Web Player</button>
        </div>
    </div>
    <div class="player-container">
        <video id="videoEl" controls autoplay playsinline style="display: {'block' if stream_url else 'none'};">
            {f'<source src="{safe_stream}" type="video/mp4">' if stream_url else ''}
            {track_html}
        </video>
        <iframe id="iframeEl" src="{'about:blank' if stream_url else embed_src}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen style="display: {'none' if stream_url else 'block'};"></iframe>
    </div>
    <script>
        const hasStream = {has_stream_js};
        const embedUrl = "{embed_src}";
        const videoEl = document.getElementById("videoEl");
        const iframeEl = document.getElementById("iframeEl");
        const toggleBtn = document.getElementById("toggleBtn");
        let isUsingVideo = hasStream;

        function updateUI() {{
            if (isUsingVideo) {{
                videoEl.style.display = "block";
                iframeEl.style.display = "none";
                toggleBtn.textContent = "🌐 Switch to Web Player / المشغل المدمج";
                try {{ videoEl.play(); }} catch (e) {{}}
            }} else {{
                try {{ videoEl.pause(); }} catch (e) {{}}
                videoEl.style.display = "none";
                iframeEl.style.display = "block";
                if (!iframeEl.src || iframeEl.src === "about:blank") {{
                    iframeEl.src = embedUrl;
                }}
                toggleBtn.textContent = "🎞️ Switch to Direct Stream / المشغل المباشر";
            }}
        }}

        function togglePlayer() {{
            if (!hasStream && isUsingVideo) return;
            isUsingVideo = !isUsingVideo;
            updateUI();
        }}

        if (videoEl) {{
            videoEl.addEventListener("error", function() {{
                console.warn("[SD Preview] Direct stream failed to load; falling back to Web Embed player.");
                isUsingVideo = false;
                updateUI();
            }});
        }}
    </script>
</body>
</html>
"""


def open_video_preview(
    parent: Any,
    url: str,
    video_title: str,
    stream_info: Optional[Any] = None,
    info_dict: Optional[Dict[str, Any]] = None,
    selected_sub_track: Optional[Dict[str, Any]] = None,
    theme: Optional[Dict[str, str]] = None,
    on_log: Optional[Callable[[str], None]] = None
) -> str:
    """
    Builds and opens a real, VidMate-style video preview with live WebVTT subtitles
    in a dedicated chromeless native desktop window.
    """
    clean_url = str(url or "").strip()
    title = str(video_title or "Video Preview").strip()
    if on_log:
        on_log(f"[PREVIEW] Preparing video preview for: {title[:40]}...")

    # 1. Direct progressive MP4 stream
    stream_url = _find_progressive_mp4_url(stream_info, info_dict, source_url=clean_url)

    # 2. Extract video ID for YouTube embed
    yt_match = re.search(r'(?:v=|\/|youtu\.be\/|embed\/)([0-9A-Za-z_-]{11})', clean_url)
    video_id = yt_match.group(1) if yt_match else (info_dict.get("id") if isinstance(info_dict, dict) else None)

    # 3. Process subtitles if selected
    vtt_data_uri = None
    sub_label = None
    if selected_sub_track and selected_sub_track.get("sub_id") not in (None, "none"):
        sub_label = selected_sub_track.get("label") or selected_sub_track.get("language") or "Subtitles"
        try:
            temp_sub_stem = os.path.join(tempfile.gettempdir(), f"_sd_prev_{os.getpid()}_{int(time.time()*1000)}")
            srt_path = download_subtitle_as_srt(selected_sub_track, f"{temp_sub_stem}.mp4")
            if srt_path and os.path.isfile(srt_path):
                with open(srt_path, "r", encoding="utf-8-sig", errors="replace") as sf:
                    srt_text = sf.read()
                vtt_data_uri = _convert_srt_to_vtt_data_uri(srt_text)
                try: os.remove(srt_path)
                except Exception: pass
        except Exception as exc:
            if on_log:
                on_log(f"[PREVIEW] Note: Subtitle overlay conversion skipped: {exc}")

    # 4. Determine quality badge
    quality_label = getattr(stream_info, "resolution_label", None) if stream_info else None
    if not quality_label and stream_url:
        quality_label = "Direct MP4"
    elif not quality_label:
        quality_label = "Web Player"

    # 5. Generate self-contained HTML
    html_content = generate_preview_html(
        url=clean_url,
        video_title=title,
        stream_url=stream_url,
        vtt_data_uri=vtt_data_uri,
        video_id=video_id,
        sub_label=sub_label,
        quality_label=quality_label
    )

    temp_html = os.path.join(tempfile.gettempdir(), f"_sd_preview_{os.getpid()}_{int(time.time()*1000)}.html")
    with open(temp_html, "w", encoding="utf-8") as hf:
        hf.write(html_content)

    # 6. Launch Native Window (Zero Tkinter thread deadlocks)
    # Check pywebview first
    pywebview_available = False
    try:
        import webview  # type: ignore
        pywebview_available = True
    except Exception:
        pass

    if pywebview_available:
        try:
            cmd = [
                sys.executable, "-c",
                f"import webview; webview.create_window({repr(title)}, {repr(temp_html)}, width=860, height=560); webview.start()"
            ]
            cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0
            subprocess.Popen(cmd, creationflags=cflags)
            if on_log:
                on_log("[PREVIEW] Launched preview window via pywebview subprocess.")
            return temp_html
        except Exception:
            pass

    # Launch Chromeless native app window (Edge, Chrome, Brave)
    browser_exe = _find_chromeless_browser() if IS_WINDOWS else None
    if browser_exe:
        file_uri = f"file:///{temp_html.replace(os.sep, '/')}"
        app_arg = f"--app={file_uri}"
        cmd = [browser_exe, app_arg, "--window-size=860,560"]
        try:
            subprocess.Popen(cmd)
            if on_log:
                on_log(f"[PREVIEW] Launched native chromeless preview window via {os.path.basename(browser_exe)}.")
            return temp_html
        except Exception:
            pass

    # Fallback to system default browser
    try:
        webbrowser.open(f"file:///{temp_html.replace(os.sep, '/')}")
        if on_log:
            on_log("[PREVIEW] Opened preview in default web browser.")
    except Exception as exc:
        if on_log:
            on_log(f"[PREVIEW] Failed to open browser: {exc}")

    return temp_html
