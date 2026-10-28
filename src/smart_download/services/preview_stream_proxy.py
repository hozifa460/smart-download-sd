"""
Smart Download — Preview Stream Proxy & VTT Subtitle Compiler
Handles upstream media byte-range proxying and WebVTT subtitle delivery.
"""

from __future__ import annotations

import http.server
import os
import re
import tempfile
import urllib.error
import urllib.request
from typing import Any, Dict

from ..core.chunk import get_permissive_ssl_context
from .subtitle_downloader import download_subtitle_as_srt


def stream_upstream_media(
    handler: http.server.BaseHTTPRequestHandler,
    target_url: str,
    custom_headers: Dict[str, str],
    is_head: bool = False,
) -> None:
    """
    Forwards Range requests and essential HTTP headers upstream,
    proxying chunks back to the browser with 206 Partial Content / 200 OK.
    """
    if not target_url or not target_url.startswith("http"):
        handler.send_response(404)
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        return

    req = urllib.request.Request(target_url)
    ua = (
        custom_headers.get("User-Agent")
        or custom_headers.get("user-agent")
        or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    req.add_header("User-Agent", ua)
    for k, v in custom_headers.items():
        if k.lower() not in ("host", "user-agent", "range"):
            req.add_header(k, str(v))

    client_range = handler.headers.get("Range")
    if client_range:
        req.add_header("Range", client_range)

    ctx = get_permissive_ssl_context()
    try:
        upstream = urllib.request.urlopen(req, timeout=18, context=ctx)
        code = upstream.getcode() or 200
    except urllib.error.HTTPError as err:
        handler.send_response(err.code)
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        return
    except Exception:
        handler.send_response(502)
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        return

    try:
        handler.send_response(code)
        headers = [
            ("Content-Type", upstream.headers.get("Content-Type", "video/mp4")),
            ("Content-Length", upstream.headers.get("Content-Length")),
            ("Content-Range", upstream.headers.get("Content-Range")),
            ("Accept-Ranges", "bytes"),
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Headers", "*"),
            ("Cache-Control", "no-cache"),
        ]
        for h, v in headers:
            if v:
                handler.send_header(h, v)
        handler.end_headers()
        if is_head:
            return

        chunk_size = 64 * 1024
        while True:
            chunk = upstream.read(chunk_size)
            if not chunk:
                break
            handler.wfile.write(chunk)
    except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
        pass
    finally:
        try:
            upstream.close()
        except Exception:
            pass


def compile_and_serve_vtt(handler: http.server.BaseHTTPRequestHandler, session: Any, s_idx: int) -> None:
    """Asynchronously compiles and serves WebVTT subtitles on the background HTTP worker thread."""
    if s_idx in session.cached_subtitles:
        vtt_content = session.cached_subtitles[s_idx]
    else:
        track = session.subtitle_tracks[s_idx] if 0 <= s_idx < len(session.subtitle_tracks) else None
        if not track or track.get("sub_id") in (None, "none"):
            vtt_content = "WEBVTT\n\n"
        else:
            temp_stem = os.path.join(tempfile.gettempdir(), f"_sd_prev_{session.sid}_{s_idx}_{os.getpid()}")
            import sys
            bridge_mod = sys.modules.get("smart_download.services.preview_stream_bridge")
            dl_fn = getattr(bridge_mod, "download_subtitle_as_srt", download_subtitle_as_srt) if bridge_mod else download_subtitle_as_srt
            srt_path = dl_fn(track, f"{temp_stem}.mp4")
            if srt_path and os.path.isfile(srt_path):
                with open(srt_path, "r", encoding="utf-8-sig", errors="replace") as sf:
                    srt_text = sf.read()
                for f_p in (srt_path, f"{temp_stem}.srt"):
                    try:
                        if os.path.exists(f_p):
                            os.remove(f_p)
                    except Exception:
                        pass
                vtt_body = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', srt_text.strip())
                if not vtt_body.startswith("WEBVTT"):
                    vtt_body = "WEBVTT\n\n" + vtt_body
                vtt_content = vtt_body
            else:
                vtt_content = "WEBVTT\n\n"
        session.cached_subtitles[s_idx] = vtt_content

    data = vtt_content.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/vtt; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(data)
