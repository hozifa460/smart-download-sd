"""
Built-In In-Memory Preview & Control Bridge (preview_stream_bridge.py).
Provides a lightweight, zero-dependency, local loopback HTTP server (127.0.0.1)
for hardware-accelerated HTML5 video preview, header-forwarding media stream proxy,
live audio dubbing stream delivery, asynchronous WebVTT subtitle compilation,
and real-time bidirectional GUI control actions.
"""
import http.server, urllib.request, urllib.parse, urllib.error
import threading, json, os, re, tempfile, uuid
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

from ..locales.i18n import tr
from ..utils.file_ops import apply_media_filename_tags, generate_unique_destination_path
from .preview_stream_proxy import compile_and_serve_vtt, stream_upstream_media

_SERVER_LOCK = threading.Lock()
_BRIDGE_SERVER: Optional[http.server.ThreadingHTTPServer] = None
_BRIDGE_PORT: int = 0
_SESSIONS_LOCK = threading.Lock()
_SESSIONS: Dict[str, "PreviewSession"] = {}


@dataclass
class PreviewSession:
    """Stores all context and callbacks for an active media preview and configuration session."""
    sid: str
    url: str
    video_title: str
    info_dict: Dict[str, Any] = field(default_factory=dict)
    options: List[Any] = field(default_factory=list)
    audio_tracks: List[Dict[str, Any]] = field(default_factory=list)
    subtitle_tracks: List[Dict[str, Any]] = field(default_factory=list)
    default_dest_path: str = ""
    on_confirm: Optional[Callable[[Any, str], None]] = None
    on_open_in_main: Optional[Callable[[Any, str], None]] = None
    on_cancel: Optional[Callable[[], None]] = None
    parent_app: Optional[Any] = None
    modal_ref: Optional[Any] = None
    cached_subtitles: Dict[int, str] = field(default_factory=dict)
    selected_audio_track: Optional[Dict[str, Any]] = None
    selected_sub_track: Optional[Dict[str, Any]] = None
    subtitle_embed_mode: str = "soft_embed"
    selected_q_idx: int = 0
    subtitle_position: str = "bottom"


def start_preview_bridge(host: str = "127.0.0.1") -> int:
    """Starts the singleton background preview bridge HTTP server on an ephemeral loopback port."""
    global _BRIDGE_SERVER, _BRIDGE_PORT
    with _SERVER_LOCK:
        if _BRIDGE_SERVER is not None and _BRIDGE_PORT > 0:
            return _BRIDGE_PORT
        server = http.server.ThreadingHTTPServer((host, 0), PreviewBridgeRequestHandler)
        server.daemon_threads = True
        _BRIDGE_PORT = server.server_address[1]
        _BRIDGE_SERVER = server
        t = threading.Thread(target=server.serve_forever, daemon=True, name="SD-PreviewBridge")
        t.start()
        return _BRIDGE_PORT


def get_preview_bridge_port() -> int:
    """Returns the active preview bridge port, starting the server if necessary."""
    if _BRIDGE_PORT > 0:
        return _BRIDGE_PORT
    return start_preview_bridge()


def register_preview_session(
    url: str,
    video_title: str,
    info_dict: Optional[Dict[str, Any]] = None,
    options: Optional[List[Any]] = None,
    audio_tracks: Optional[List[Dict[str, Any]]] = None,
    subtitle_tracks: Optional[List[Dict[str, Any]]] = None,
    default_dest_path: str = "",
    on_confirm: Optional[Callable[[Any, str], None]] = None,
    on_open_in_main: Optional[Callable[[Any, str], None]] = None,
    on_cancel: Optional[Callable[[], None]] = None,
    parent_app: Optional[Any] = None,
    modal_ref: Optional[Any] = None,
    sid: Optional[str] = None,
    selected_audio_track: Optional[Dict[str, Any]] = None,
    selected_sub_track: Optional[Dict[str, Any]] = None,
    subtitle_embed_mode: str = "hard_burn",
    selected_q_idx: int = 0,
    subtitle_position: str = "bottom",
) -> str:
    """Registers an active media preview session and returns its unique random session ID token."""
    start_preview_bridge()
    session_id = sid or uuid.uuid4().hex[:16]
    session = PreviewSession(
        sid=session_id, url=str(url or "").strip(), video_title=str(video_title or "Video Preview").strip(),
        info_dict=info_dict or {}, options=options or [], audio_tracks=audio_tracks or [],
        subtitle_tracks=subtitle_tracks or [], default_dest_path=str(default_dest_path or "").strip(),
        on_confirm=on_confirm, on_open_in_main=on_open_in_main, on_cancel=on_cancel, parent_app=parent_app,
        modal_ref=modal_ref, selected_audio_track=selected_audio_track, selected_sub_track=selected_sub_track,
        subtitle_embed_mode=subtitle_embed_mode or "hard_burn", selected_q_idx=selected_q_idx,
        subtitle_position=subtitle_position or "bottom",
    )
    with _SESSIONS_LOCK:
        _SESSIONS[session_id] = session
    return session_id


def get_preview_session(sid: str) -> Optional[PreviewSession]:
    """Retrieves an active preview session by session ID."""
    with _SESSIONS_LOCK:
        return _SESSIONS.get(sid)


def unregister_preview_session(sid: str) -> None:
    """Removes a finished preview session."""
    with _SESSIONS_LOCK:
        _SESSIONS.pop(sid, None)






class PreviewBridgeRequestHandler(http.server.BaseHTTPRequestHandler):
    """Handles HTTP requests for player UI, media streaming proxy, subtitles, and control APIs."""

    def log_message(self, format, *args):
        """Silences standard HTTP server console logging to avoid test and UI noise."""
        pass

    def do_OPTIONS(self):
        """Responds to CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_HEAD(self):
        """Handles HEAD probe requests for media stream duration and byte range headers."""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        sid = params.get("sid", [""])[0]
        session = get_preview_session(sid)
        if not session:
            self.send_response(404)
            self.end_headers()
            return

        if parsed.path == "/stream_video":
            q_idx = int(params.get("q_idx", ["0"])[0]) if params.get("q_idx") else 0
            target_url, target_headers = self._resolve_video_target(session, q_idx)
            stream_upstream_media(self, target_url, target_headers, is_head=True)
        elif parsed.path == "/stream_audio":
            a_idx = int(params.get("a_idx", ["0"])[0]) if params.get("a_idx") else 0
            target_url, target_headers = self._resolve_audio_target(session, a_idx)
            stream_upstream_media(self, target_url, target_headers, is_head=True)
        else:
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

    def do_GET(self):
        """Dispatches GET requests for player HTML, video stream, audio stream, or subtitles."""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        sid = params.get("sid", [""])[0]
        session = get_preview_session(sid)

        if not session:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"404 Session Not Found or Expired")
            return

        if parsed.path == "/player":
            self._handle_player(session)
        elif parsed.path == "/stream_video":
            q_idx = int(params.get("q_idx", ["0"])[0]) if params.get("q_idx") else 0
            target_url, target_headers = self._resolve_video_target(session, q_idx)
            stream_upstream_media(self, target_url, target_headers, is_head=False)
        elif parsed.path == "/stream_audio":
            a_idx = int(params.get("a_idx", ["0"])[0]) if params.get("a_idx") else 0
            target_url, target_headers = self._resolve_audio_target(session, a_idx)
            stream_upstream_media(self, target_url, target_headers, is_head=False)
        elif parsed.path == "/subtitle.vtt":
            s_idx = int(params.get("s_idx", ["0"])[0]) if params.get("s_idx") else 0
            self._handle_subtitle(session, s_idx)
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data: Dict[str, Any], code: int = 200) -> None:
        """Sends JSON HTTP response with CORS headers."""
        payload = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        """Dispatches JSON POST API calls for dynamic filename tagging or confirmed action."""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        sid = params.get("sid", [""])[0]
        session = get_preview_session(sid)
        if not session:
            self.send_response(404)
            self.end_headers()
            return

        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            body = json.loads(raw_body)
        except Exception:
            body = {}

        if parsed.path == "/api/update_filename":
            self._handle_api_update_filename(session, body)
        elif parsed.path == "/api/action":
            self._handle_api_action(session, body)
        elif parsed.path == "/api/sync_state":
            self._handle_api_sync_state(session, body)
        elif parsed.path == "/api/browse":
            self._handle_api_browse(session, body, params)
        else:
            self.send_response(404)
            self.end_headers()

    def _resolve_video_target(self, session: PreviewSession, q_idx: int) -> tuple[str, Dict[str, str]]:
        """Finds the best progressive playable stream URL and forwarding HTTP headers."""
        opt = session.options[q_idx] if 0 <= q_idx < len(session.options) else (session.options[0] if session.options else None)
        if opt and getattr(opt, "is_progressive", False) and not getattr(opt, "is_audio_only", False) and getattr(opt, "video_url", None):
            return str(opt.video_url), dict(getattr(opt, "video_headers", {}) or {})

        # Check info_dict formats for fast progressive MP4
        formats = session.info_dict.get("formats") or []
        prog_formats = [
            f for f in formats
            if f.get("url") and f.get("vcodec") != "none" and f.get("acodec") != "none"
            and str(f.get("ext") or "").lower() == "mp4"
        ]
        if prog_formats:
            prog_formats.sort(key=lambda f: int(f.get("height") or 0), reverse=True)
            fast = [f for f in prog_formats if int(f.get("height") or 0) <= 720]
            chosen = fast[0] if fast else prog_formats[0]
            headers = dict(chosen.get("http_headers") or {})
            if "Referer" not in headers and session.url:
                headers["Referer"] = session.url
            return str(chosen.get("url") or ""), headers

        if opt and getattr(opt, "video_url", None):
            return str(opt.video_url), dict(getattr(opt, "video_headers", {}) or {})

        headers = dict(session.info_dict.get("http_headers") or {})
        if "Referer" not in headers and session.url:
            headers["Referer"] = session.url
        return session.url, headers

    def _resolve_audio_target(self, session: PreviewSession, a_idx: int) -> tuple[str, Dict[str, str]]:
        """Finds the dedicated audio stream URL and headers for dubbed audio playback."""
        track = session.audio_tracks[a_idx] if 0 <= a_idx < len(session.audio_tracks) else None
        if not track or not track.get("url") or track.get("track_id") == "original":
            return "", {}
        headers = dict(track.get("http_headers") or {})
        if not headers:
            headers = dict(session.info_dict.get("http_headers") or {})
        if "Referer" not in headers and session.url:
            headers["Referer"] = session.url
        return str(track.get("url") or ""), headers

    def _handle_player(self, session: PreviewSession) -> None:
        """Renders and serves the complete unified VidMate-style preview and settings HTML page."""
        from ..ui.modals.preview_html_builder import generate_preview_html
        idx = session.selected_q_idx if 0 <= session.selected_q_idx < len(session.options) else 0
        opt = session.options[idx] if session.options else None
        q_label = getattr(opt, "resolution_label", "MP4 Stream") if opt else "MP4 Stream"
        stream_proxy_url = f"/stream_video?sid={session.sid}&q_idx={idx}"
        html_code = generate_preview_html(
            url=session.url,
            video_title=session.video_title,
            stream_url=stream_proxy_url,
            quality_label=q_label,
            options=session.options,
            audio_tracks=session.audio_tracks,
            subtitle_tracks=session.subtitle_tracks,
            default_dest_path=session.default_dest_path,
            sid=session.sid,
            bridge_port=_BRIDGE_PORT,
            selected_audio_track=session.selected_audio_track,
            selected_sub_track=session.selected_sub_track,
            subtitle_embed_mode=session.subtitle_embed_mode,
            selected_q_idx=idx,
            subtitle_position=session.subtitle_position,
        )
        data = html_code.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _handle_subtitle(self, session: PreviewSession, s_idx: int) -> None:
        """Asynchronously compiles and serves WebVTT subtitles on the background HTTP worker thread."""
        compile_and_serve_vtt(self, session, s_idx)

    def _handle_api_update_filename(self, session: PreviewSession, body: Dict[str, Any]) -> None:
        """Updates the destination filename with quality and burn-in tags live."""
        q_idx = int(body.get("q_idx", 0))
        sub_mode = str(body.get("sub_mode", "soft_embed"))
        cur_dest = str(body.get("current_dest", "")).strip() or session.default_dest_path

        opt = session.options[q_idx] if 0 <= q_idx < len(session.options) else (session.options[0] if session.options else None)
        if opt:
            is_burned = (sub_mode == "hard_burn")
            updated = apply_media_filename_tags(
                cur_dest,
                quality_label=getattr(opt, "resolution_label", ""),
                is_sub_burned=is_burned,
                ext=getattr(opt, "ext", "mp4")
            )
        else:
            updated = cur_dest

        hm = getattr(session.parent_app, "history_manager", None)
        reserved = hm.get_active_or_queued_paths() if hm else None
        final_dest = generate_unique_destination_path(updated, reserved_paths=reserved)

        self._send_json({"dest_path": final_dest})

    def _handle_api_browse(self, session: PreviewSession, body: Dict[str, Any], params: Dict[str, List[str]]) -> None:
        """Opens native file picker on Tkinter thread to choose download destination file."""
        current_dest = str(body.get("current_dest") or params.get("current_dest", [""])[0] or session.default_dest_path).strip()
        chosen_holder: List[Optional[str]] = [None]
        browse_evt = threading.Event()

        def _ask():
            try:
                from tkinter import filedialog
                parent_w = session.modal_ref if (session.modal_ref and hasattr(session.modal_ref, "winfo_exists") and session.modal_ref.winfo_exists()) else (session.parent_app.root if (session.parent_app and hasattr(session.parent_app, "root")) else None)
                cur_d = current_dest or session.default_dest_path
                init_dir = os.path.dirname(os.path.abspath(cur_d)) if cur_d else os.path.expanduser("~")
                init_file = os.path.basename(cur_d) if cur_d else "video.mp4"
                res = filedialog.asksaveasfilename(parent=parent_w, title="Save Video As", initialdir=init_dir, initialfile=init_file)
                if res: chosen_holder[0] = str(res)
            except Exception: pass
            finally: browse_evt.set()

        parent = session.parent_app or (session.modal_ref.master if session.modal_ref else None)
        target = session.modal_ref if (session.modal_ref and hasattr(session.modal_ref, "after")) else parent
        if target and hasattr(target, "after"):
            target.after(0, _ask)
            browse_evt.wait(timeout=60.0)
        else:
            _ask()

        chosen = chosen_holder[0]
        if chosen:
            session.default_dest_path = chosen
            try:
                from ..config import set_setting
                set_setting("last_download_dir", os.path.dirname(os.path.abspath(chosen)))
            except Exception: pass
            self._send_json({"ok": True, "dest": chosen})
        else:
            self._send_json({"ok": False, "dest": ""})

    def _handle_api_action(self, session: PreviewSession, body: Dict[str, Any]) -> None:
        """Processes download, open in main window, or cancel actions and dispatches safely to Tkinter."""
        action = str(body.get("action", "download"))
        q_idx, a_idx, s_idx = int(body.get("q_idx", 0)), int(body.get("a_idx", 0)), int(body.get("s_idx", 0))
        sub_mode = str(body.get("sub_mode", "hard_burn"))
        sub_pos = str(body.get("sub_pos", "bottom"))
        dest_path = str(body.get("dest_path", "")).strip()

        session.selected_q_idx = q_idx
        session.subtitle_position = sub_pos
        session.subtitle_embed_mode = sub_mode

        selected_opt = session.options[q_idx] if 0 <= q_idx < len(session.options) else (session.options[0] if session.options else None)
        if selected_opt:
            if session.audio_tracks and 0 <= a_idx < len(session.audio_tracks):
                selected_opt.selected_audio_track = session.audio_tracks[a_idx]
            selected_opt.subtitle_embed_mode = sub_mode or "hard_burn"
            selected_opt.subtitle_position = sub_pos or "bottom"
            if session.subtitle_tracks:
                if 0 < s_idx < len(session.subtitle_tracks):
                    selected_opt.selected_subtitle_track = session.subtitle_tracks[s_idx]
                else:
                    selected_opt.selected_subtitle_track = None

        final_dest = dest_path or session.default_dest_path
        if selected_opt:
            is_burned = (getattr(selected_opt, "subtitle_embed_mode", "") == "hard_burn")
            final_dest = apply_media_filename_tags(final_dest, quality_label=getattr(selected_opt, "resolution_label", ""), is_sub_burned=is_burned, ext=getattr(selected_opt, "ext", "mp4"))
        hm = getattr(session.parent_app, "history_manager", None)
        reserved = hm.get_active_or_queued_paths() if hm else None
        final_dest = generate_unique_destination_path(final_dest, reserved_paths=reserved)

        try:
            from ..config import set_setting
            set_setting("subtitle_embed_mode", sub_mode)
            set_setting("subtitle_position", sub_pos)
            if selected_opt:
                set_setting("preferred_video_height", -1 if getattr(selected_opt, "is_audio_only", False) else getattr(selected_opt, "height", 0))
                if getattr(selected_opt, "selected_audio_track", None):
                    set_setting("preferred_audio_lang", selected_opt.selected_audio_track.get("language") or "original")
                if getattr(selected_opt, "selected_subtitle_track", None):
                    set_setting("preferred_subtitle_lang", selected_opt.selected_subtitle_track.get("language") or "none")
        except Exception: pass

        def _dispatch():
            if session.modal_ref:
                try:
                    session.modal_ref._confirmed = True
                    session.modal_ref.destroy()
                except Exception: pass
            if action == "download" and session.on_confirm:
                session.on_confirm(selected_opt, final_dest)
            elif action == "open_in_main":
                if session.on_open_in_main: session.on_open_in_main(selected_opt, final_dest)
            elif action == "cancel" and session.on_cancel:
                session.on_cancel()
            def _cleanup(): unregister_preview_session(session.sid)
            if parent and hasattr(parent, "after"): parent.after(2000, _cleanup)
            else: threading.Timer(2.0, _cleanup).start()

        parent = session.parent_app or (session.modal_ref.master if session.modal_ref else None)
        target = parent if (parent and hasattr(parent, "after")) else (session.modal_ref if (session.modal_ref and hasattr(session.modal_ref, "after")) else None)
        if target: target.after(0, _dispatch)
        else: _dispatch()

        self._send_json({"status": "ok", "action": action, "dest_path": final_dest})

    def _handle_api_sync_state(self, session: PreviewSession, body: Dict[str, Any]) -> None:
        """Synchronizes format, dubbed audio, subtitle, and mode selections live to Tkinter modal."""
        q_idx, a_idx, s_idx = int(body.get("q_idx", 0)), int(body.get("a_idx", 0)), int(body.get("s_idx", 0))
        sub_mode = str(body.get("sub_mode", "hard_burn"))
        sub_pos = str(body.get("sub_pos", "bottom"))
        dest_path = str(body.get("dest_path", "")).strip()

        session.selected_q_idx = q_idx
        session.subtitle_position = sub_pos
        session.subtitle_embed_mode = sub_mode
        if dest_path:
            session.default_dest_path = dest_path

        if session.audio_tracks and 0 <= a_idx < len(session.audio_tracks):
            session.selected_audio_track = session.audio_tracks[a_idx]
        if session.subtitle_tracks and 0 < s_idx < len(session.subtitle_tracks):
            session.selected_sub_track = session.subtitle_tracks[s_idx]
        else:
            session.selected_sub_track = None

        if session.options and 0 <= q_idx < len(session.options):
            opt = session.options[q_idx]
            opt.selected_audio_track = session.selected_audio_track
            opt.selected_subtitle_track = session.selected_sub_track
            opt.subtitle_embed_mode = session.subtitle_embed_mode
            opt.subtitle_position = session.subtitle_position

        try:
            from ..config import set_setting
            set_setting("subtitle_embed_mode", sub_mode)
            set_setting("subtitle_position", sub_pos)
            if session.options and 0 <= q_idx < len(session.options):
                opt = session.options[q_idx]
                set_setting("preferred_video_height", -1 if getattr(opt, "is_audio_only", False) else getattr(opt, "height", 0))
            if session.selected_audio_track:
                set_setting("preferred_audio_lang", session.selected_audio_track.get("language") or "original")
            if session.selected_sub_track:
                set_setting("preferred_subtitle_lang", session.selected_sub_track.get("language") or "none")
        except Exception: pass

        def _sync_tk():
            m = session.modal_ref
            if not m or (hasattr(m, "winfo_exists") and not m.winfo_exists()):
                return
            try:
                iid = f"opt_{q_idx}"
                if hasattr(m, "tree") and m.tree:
                    m.tree.selection_set(iid)
                    m.tree.focus(iid)
                if hasattr(m, "options") and 0 <= q_idx < len(m.options):
                    m.selected_option = m.options[q_idx]
                    m.selected_option.selected_audio_track = session.selected_audio_track
                    m.selected_option.selected_subtitle_track = session.selected_sub_track
                    m.selected_option.subtitle_embed_mode = session.subtitle_embed_mode
                    m.selected_option.subtitle_position = session.subtitle_position
                if hasattr(m, "cb_audio") and m.cb_audio:
                    m.cb_audio.current(a_idx)
                if hasattr(m, "cb_sub") and m.cb_sub:
                    m.cb_sub.current(s_idx)
                    m.cb_sub._selected_mode = sub_mode
                    m.cb_sub._user_touched_mode = True
                    m.cb_sub._selected_pos = sub_pos
                    if hasattr(m.cb_sub, "_mode_var"): m.cb_sub._mode_var.set(sub_mode)
                    mode_cb = getattr(m.cb_sub, "_mode_combobox", None)
                    if mode_cb and hasattr(mode_cb, "current"):
                        codes = getattr(m.cb_sub, "_mode_codes", ["soft_embed", "hard_burn", "srt_only"])
                        if sub_mode in codes: mode_cb.current(codes.index(sub_mode))
                        if hasattr(mode_cb, "configure"): mode_cb.configure(state="readonly" if s_idx > 0 else "disabled")
                    pos_cb = getattr(m.cb_sub, "_pos_combobox", None)
                    if pos_cb and hasattr(pos_cb, "current"):
                        pos_codes = ["bottom", "middle", "top"]
                        if sub_pos in pos_codes: pos_cb.current(pos_codes.index(sub_pos))
                if dest_path and hasattr(m, "entry_dest") and m.entry_dest:
                    import tkinter as tk
                    m.entry_dest.delete(0, tk.END); m.entry_dest.insert(0, dest_path)
                    if hasattr(m, "dest_path"): m.dest_path = dest_path
            except Exception:
                pass

        parent = session.parent_app or (session.modal_ref.master if session.modal_ref else None)
        target = session.modal_ref if (session.modal_ref and hasattr(session.modal_ref, "after")) else parent
        if target and hasattr(target, "after"):
            target.after(0, _sync_tk)

        self._send_json({"status": "ok"})
