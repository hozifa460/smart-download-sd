"""
Live Preview Service for Smart Download (SD).
Coordinates media preview playback, seek management, and real-time subtitle cue tracking.
"""
import os
import re
import time
import shutil
import logging
import threading
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Callable, Dict, Any

logger = logging.getLogger("smart_download.preview")


@dataclass
class SubtitleCue:
    start_sec: float
    end_sec: float
    text: str


def _parse_timestamp(ts: str) -> float:
    """Converts HH:MM:SS,mmm or HH:MM:SS.mmm to seconds."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60.0 + float(parts[1])
    return float(parts[0]) if parts else 0.0


def parse_srt_cues(content_or_path: str) -> List[SubtitleCue]:
    """Parses SRT or VTT content / file path into ordered SubtitleCue list."""
    if not content_or_path:
        return []
    text = content_or_path
    if os.path.exists(content_or_path) and os.path.isfile(content_or_path):
        try:
            with open(content_or_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception:
            return []
    cues: List[SubtitleCue] = []
    pattern = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3}|\d{1,2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3}|\d{1,2}:\d{2}[,\.]\d{1,3})"
    )
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        time_idx, m = -1, None
        for idx, line in enumerate(lines):
            m = pattern.search(line)
            if m:
                time_idx = idx
                break
        if not m or time_idx == -1:
            continue
        try:
            start_s = _parse_timestamp(m.group(1))
            end_s = _parse_timestamp(m.group(2))
            clean_text = re.sub(r"<[^>]+>", "", " ".join(lines[time_idx + 1:])).strip()
            if clean_text:
                cues.append(SubtitleCue(start_sec=start_s, end_sec=end_s, text=clean_text))
        except Exception:
            continue
    cues.sort(key=lambda c: c.start_sec)
    return cues


def fetch_cues_for_track(sub_track: Optional[Dict[str, Any]]) -> List[SubtitleCue]:
    """Extracts or downloads subtitle cues from subtitle track dict."""
    if not sub_track or not isinstance(sub_track, dict):
        return []
    fp = sub_track.get("filepath")
    if fp and os.path.exists(fp):
        return parse_srt_cues(fp)
    content = sub_track.get("content")
    if content:
        return parse_srt_cues(content)
    sub_url = sub_track.get("url")
    if sub_url and (sub_url.startswith("http://") or sub_url.startswith("https://")):
        try:
            import urllib.request
            req = urllib.request.Request(sub_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return parse_srt_cues(resp.read().decode("utf-8", errors="replace"))
        except Exception as e:
            logger.debug("Failed to fetch subtitle cues from URL: %s", e)
    return []


def _find_ffplay_bin() -> Optional[str]:
    """Resolves ffplay executable from PATH or next to bundled FFmpeg."""
    p = shutil.which("ffplay")
    if p:
        return p
    try:
        from .youtube_models import find_ffmpeg_bin
        ff = find_ffmpeg_bin()
        if ff:
            d = os.path.dirname(ff)
            cand = os.path.join(d, "ffplay.exe" if os.name == "nt" else "ffplay")
            if os.path.isfile(cand):
                return cand
    except Exception:
        pass
    return None


class PreviewSession:
    """Manages live playback clock, seeking, subtitle synchronization, and ffplay video/audio execution."""

    def __init__(
        self,
        media_url: str = "",
        duration: float = 0.0,
        cues: Optional[List[SubtitleCue]] = None,
        on_time_update: Optional[Callable[[float, str], None]] = None,
        on_state_change: Optional[Callable[[bool], None]] = None,
        use_ffplay: bool = True
    ):
        self.media_url = media_url
        self.duration = max(0.0, float(duration))
        self.cues: List[SubtitleCue] = list(cues or [])
        self.on_time_update = on_time_update
        self.on_state_change = on_state_change
        self.use_ffplay = use_ffplay and bool(_find_ffplay_bin())
        self.current_time: float = 0.0
        self.is_playing: bool = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._clock_thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None

    def start(self):
        self.play()

    def play(self):
        with self._lock:
            if self.is_playing:
                return
            self.is_playing = True
            self._stop_event.clear()
            if self.use_ffplay and self.media_url:
                self._launch_ffplay(self.current_time)
            if not self._clock_thread or not self._clock_thread.is_alive():
                self._clock_thread = threading.Thread(target=self._clock_loop, daemon=True)
                self._clock_thread.start()
        if self.on_state_change:
            try: self.on_state_change(True)
            except Exception: pass

    def pause(self):
        with self._lock:
            if not self.is_playing:
                return
            self.is_playing = False
            self._stop_event.set()
            self._kill_proc()
        if self.on_state_change:
            try: self.on_state_change(False)
            except Exception: pass

    def stop(self):
        with self._lock:
            self.is_playing = False
            self._stop_event.set()
            self._kill_proc()
            self.current_time = 0.0
        if self.on_state_change:
            try: self.on_state_change(False)
            except Exception: pass
        if self.on_time_update:
            try: self.on_time_update(0.0, self.get_active_subtitle(0.0))
            except Exception: pass

    def seek(self, delta_sec: float):
        self.seek_to(self.current_time + delta_sec)

    def seek_to(self, target_time: float):
        with self._lock:
            max_d = self.duration if self.duration > 0 else 86400.0
            self.current_time = max(0.0, min(float(target_time), max_d))
            was_playing = self.is_playing
            self._kill_proc()
            if was_playing and self.use_ffplay and self.media_url:
                self._launch_ffplay(self.current_time)
        cue = self.get_active_subtitle(self.current_time)
        if self.on_time_update:
            try: self.on_time_update(self.current_time, cue)
            except Exception: pass

    def get_active_subtitle(self, timestamp: Optional[float] = None) -> str:
        t = self.current_time if timestamp is None else timestamp
        for cue in self.cues:
            if cue.start_sec <= t <= cue.end_sec:
                return cue.text
        return ""

    def _clock_loop(self):
        last_tick = time.time()
        while not self._stop_event.is_set():
            time.sleep(0.08)
            with self._lock:
                if not self.is_playing:
                    break
                now = time.time()
                elapsed = now - last_tick
                last_tick = now
                self.current_time += elapsed
                if self.duration > 0 and self.current_time >= self.duration:
                    self.current_time = self.duration
                    self.is_playing = False
                    self._kill_proc()
                    reached_end = True
                else:
                    reached_end = False
                t = self.current_time
            cue = self.get_active_subtitle(t)
            if self.on_time_update:
                try: self.on_time_update(t, cue)
                except Exception: pass
            if reached_end:
                if self.on_state_change:
                    try: self.on_state_change(False)
                    except Exception: pass
                break

    def _launch_ffplay(self, start_pos: float):
        self._kill_proc()
        ffplay_exe = _find_ffplay_bin()
        if not ffplay_exe:
            return
        cmd = [
            ffplay_exe, "-ss", f"{start_pos:.2f}", "-autoexit",
            "-window_title", "Smart Download - Live Preview", "-loglevel", "quiet"
        ]
        if self.media_url.startswith(("http://", "https://")):
            cmd.extend(["-headers", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\n"])
        cmd.append(self.media_url)
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.debug("Failed to spawn ffplay: %s", e)
            self._proc = None

    def _kill_proc(self):
        if self._proc:
            try: self._proc.kill()
            except Exception: pass
            self._proc = None


__all__ = ["SubtitleCue", "parse_srt_cues", "fetch_cues_for_track", "PreviewSession"]
