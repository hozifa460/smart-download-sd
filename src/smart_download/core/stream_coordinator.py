"""
StreamDownloadCoordinator: Orchestrates separate video/audio stream downloads and container multiplexing.
"""
import os
import sys
import time
import threading
import subprocess
import shutil
import ssl
import dataclasses
from typing import Optional, Callable, Dict, Any, List

from .engine import TurboDownloadEngine
from .chunk import DownloadChunk
from ..config import IS_WINDOWS
from ..services.youtube_service import (
    YouTubeStreamInfo,
    MediaStreamInfo,
    YouTubeResolver,
    MediaResolver,
    has_ffmpeg,
    find_ffmpeg_bin,
    is_youtube_url,
)

class StreamDownloadCoordinator:
    """
    Coordinates multi-part YouTube & media stream downloads:
    - If stream is progressive: delegates directly to TurboDownloadEngine for full dynamic chunking.
    - If stream is split (separate video and audio): downloads video stream with TurboDownloadEngine,
      then downloads audio stream with TurboDownloadEngine, and losslessly merges them via FFmpeg (-c copy).
    - Fully compatible interface with ModernFramelessGUI (is_running, is_paused, chunks, total_size,
      rate limiter, pause, resume, cancel).
    - Provides unified multi-stream progress reporting (no jumping backwards on stream change).
    """
    def __init__(
        self,
        stream_info: YouTubeStreamInfo,
        destination_path: str,
        max_connections: int = 8,
        rate_limit_bytes_per_sec: float = 0.0,
        ssl_context: Optional[ssl.SSLContext] = None,
        on_progress: Optional[Callable] = None,
        on_chunk_update: Optional[Callable] = None,
        on_log: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        self.stream_info = stream_info
        self.destination_path = destination_path
        self.max_connections = max(1, min(max_connections, 32))
        self._requested_max_connections = self.max_connections
        self.rate_limit = rate_limit_bytes_per_sec
        self.ssl_context = ssl_context
        self.on_progress = on_progress
        self.on_chunk_update = on_chunk_update
        self.on_log = on_log
        self.on_complete = on_complete
        self.on_error = on_error

        # YouTube googlevideo CDN detection and concurrency safety
        self.is_youtube_stream = (
            TurboDownloadEngine.is_googlevideo_url(self.stream_info.video_url)
            or (bool(self.stream_info.audio_url) and TurboDownloadEngine.is_googlevideo_url(self.stream_info.audio_url))
            or is_youtube_url(getattr(self.stream_info, "video_id", ""))
            or "googlevideo.com" in (self.stream_info.video_url or "")
            or getattr(self.stream_info, "platform", "").lower() == "youtube"
        )
        if self.is_youtube_stream:
            self.max_connections = min(self.max_connections, 1)

        self.current_engine: Optional[TurboDownloadEngine] = None
        self._lock = threading.RLock()
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._supervisor_thread: Optional[threading.Thread] = None
        self._is_running = False
        self._is_paused = False
        self.start_time = 0.0
        self._last_active_speed = 0.0
        self._active_engines: List[TurboDownloadEngine] = []

        # Aggregated stream metrics for smooth progress visualization
        self._v_total_size = max(0, self.stream_info.video_size)
        self._a_total_size = max(0, self.stream_info.audio_size) if not self.stream_info.is_progressive else 0
        self._v_downloaded = 0
        self._a_downloaded = 0
        self._active_phase = 1

    def log(self, msg: str):
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                pass

    @property
    def chunks(self) -> List[DownloadChunk]:
        return self.get_chunks_snapshot()

    def get_chunks_snapshot(self) -> List[DownloadChunk]:
        """Returns snapshot combining chunks from all active engines with distinct IDs."""
        with self._lock:
            res: List[DownloadChunk] = []
            targets = list(self._active_engines) if self._active_engines else ([self.current_engine] if self.current_engine else [])
            offset = 0
            for eng in targets:
                try:
                    with eng._lock:
                        max_id = -1
                        for c in eng.chunks:
                            res.append(dataclasses.replace(c, chunk_id=c.chunk_id + offset) if offset > 0 else c)
                            if c.chunk_id > max_id:
                                max_id = c.chunk_id
                        offset += max(0, max_id + 1)
                except Exception:
                    pass
            return res

    @property
    def total_size(self) -> int:
        with self._lock:
            if self.stream_info.is_progressive or not self.stream_info.audio_url:
                if self.current_engine and self.current_engine.total_size > 0:
                    return self.current_engine.total_size
                return self.stream_info.video_size
            return max(1, self._v_total_size + self._a_total_size)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._is_paused

    def set_speed_limit(self, bytes_per_sec: float):
        with self._lock:
            self.rate_limit = bytes_per_sec
            targets = list(self._active_engines) if self._active_engines else ([self.current_engine] if self.current_engine else [])
            for eng in targets:
                try: eng.set_speed_limit(bytes_per_sec)
                except Exception: pass

    def start(self):
        self._is_running = True
        self._is_paused = False
        self._cancel_event.clear()
        self._pause_event.clear()
        self.start_time = time.time()
        self._supervisor_thread = threading.Thread(target=self._run_coordinator, daemon=True)
        self._supervisor_thread.start()

    def pause(self):
        with self._lock:
            self._is_paused = True
            targets = list(self._active_engines) if self._active_engines else ([self.current_engine] if self.current_engine else [])
            for eng in targets:
                try: eng.pause()
                except Exception: pass

    def resume(self):
        with self._lock:
            self._is_paused = False
            targets = list(self._active_engines) if self._active_engines else ([self.current_engine] if self.current_engine else [])
            for eng in targets:
                try: eng.resume()
                except Exception: pass

    def cancel(self):
        with self._lock:
            self._is_running = False
            self._cancel_event.set()
            targets = list(self._active_engines) if self._active_engines else ([self.current_engine] if self.current_engine else [])
            for eng in targets:
                try: eng.cancel()
                except Exception: pass

    def safe_shutdown(self):
        with self._lock:
            self._is_running = False
            self._cancel_event.set()
            targets = list(self._active_engines) if self._active_engines else ([self.current_engine] if self.current_engine else [])
            for eng in targets:
                try:
                    if hasattr(eng, "safe_shutdown"): eng.safe_shutdown()
                    else: eng.cancel()
                except Exception: pass

    def update_url(self, new_url: str, headers: Optional[Dict[str, str]] = None):
        with self._lock:
            if self.current_engine:
                self.current_engine.update_url(new_url, headers)

    def refresh_link(self, new_url: str, headers: Optional[Dict[str, str]] = None, auto_resume: bool = True) -> bool:
        with self._lock:
            if self.current_engine:
                return self.current_engine.refresh_link(new_url, headers, auto_resume)
            return False

    @property
    def url(self) -> str:
        with self._lock:
            if self.current_engine and getattr(self.current_engine, "url", None):
                return self.current_engine.url
            return getattr(self.stream_info, "video_url", "")

    @property
    def supports_ranges(self) -> bool:
        with self._lock:
            if self.current_engine:
                return getattr(self.current_engine, "supports_ranges", True)
            return True

    @property
    def has_expired_link(self) -> bool:
        with self._lock:
            if self.current_engine:
                return getattr(self.current_engine, "has_expired_link", False)
            return False

    @property
    def last_http_status(self) -> int:
        with self._lock:
            if self.current_engine:
                return getattr(self.current_engine, "last_http_status", 0)
            return 0

    def _run_coordinator(self):
        video_tmp = ""
        audio_tmp = ""
        actual_dest = ""
        is_mp3_request = False
        v_error: List[str] = []
        a_error: List[str] = []
        has_error = False
        try:
            if self.stream_info.is_progressive or not self.stream_info.audio_url:
                # Progressive single-stream download with dynamic chunking
                # Check if this is an audio-only stream requesting MP3 conversion via FFmpeg
                src_audio_ext = (getattr(self.stream_info, "audio_ext", "") or "").lower()
                is_mp3_request = (
                    self.stream_info.is_audio_only
                    and (self.destination_path.lower().endswith(".mp3") or self.stream_info.video_ext.lower() == "mp3")
                    and src_audio_ext != "mp3"
                    and has_ffmpeg()
                )
                if is_mp3_request and not self.destination_path.lower().endswith(".mp3"):
                    base, _ = os.path.splitext(self.destination_path)
                    self.destination_path = base + ".mp3"
                actual_dest = self.destination_path + ".audio.tmp" if is_mp3_request else self.destination_path
                plat = getattr(self.stream_info, "platform", "Media")
                tag = plat.upper().replace(" / X", "")
                self.log(f"[{tag}] Initializing dynamic multi-chunk download for: {os.path.basename(self.destination_path)}")

                def _on_single_complete(path, size, elapsed):
                    if is_mp3_request:
                        self.log("[FFMPEG] Transcoding downloaded audio stream to universal MP3...")
                        if self.on_progress:
                            rep_spd = self._last_active_speed if self._last_active_speed > 0 else (size / max(0.05, elapsed))
                            self.on_progress(size, size, rep_spd, "Transcoding...", 0)
                        try:
                            ffmpeg_bin = find_ffmpeg_bin()
                            if not ffmpeg_bin:
                                raise RuntimeError("FFmpeg executable not found.")
                            cmd = [ffmpeg_bin, "-y", "-i", actual_dest, "-vn", "-c:a", "libmp3lame", "-q:a", "2", self.destination_path]
                            cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0
                            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=cflags)
                            if res.returncode != 0:
                                raise RuntimeError(f"FFmpeg MP3 transcoding failed: {res.stderr.strip()}")
                            if os.path.exists(actual_dest):
                                try:
                                    os.remove(actual_dest)
                                except Exception:
                                    pass
                            final_sz = os.path.getsize(self.destination_path)
                            self.log(f"[SUCCESS] Audio converted to MP3 successfully ({final_sz:,} bytes)!")
                            if self.on_complete:
                                self.on_complete(self.destination_path, final_sz, elapsed)
                        except Exception as ex:
                            if os.path.exists(actual_dest):
                                try:
                                    os.remove(actual_dest)
                                except Exception:
                                    pass
                            if os.path.exists(self.destination_path):
                                try:
                                    os.remove(self.destination_path)
                                except Exception:
                                    pass
                            if self.on_error:
                                self.on_error(f"MP3 transcoding error: {ex}")
                    else:
                        self._process_subtitles(path)
                        if self.on_complete:
                            self.on_complete(path, size, elapsed)

                req_conn = getattr(self, "_requested_max_connections", self.max_connections)
                safe_conn = min(max(1, req_conn), 8)
                allow_split = True

                def _on_single_prog(downloaded, total, speed, eta, active):
                    if speed > 0:
                        self._last_active_speed = speed
                    elif downloaded > 0 and self._last_active_speed <= 0.0:
                        st = self.start_time; el = (time.time() - st) if (isinstance(st, (int, float)) and st > 0) else 0.1
                        self._last_active_speed = downloaded / max(0.05, el)
                    if self.on_progress:
                        self.on_progress(downloaded, total, speed, eta, active)

                engine = TurboDownloadEngine(
                    url=self.stream_info.video_url,
                    destination_path=actual_dest,
                    max_connections=safe_conn,
                    allow_dynamic_split=allow_split,
                    rate_limit_bytes_per_sec=self.rate_limit,
                    ssl_context=self.ssl_context,
                    headers=self.stream_info.video_headers,
                    on_progress=_on_single_prog,
                    on_chunk_update=self.on_chunk_update,
                    on_log=self.on_log,
                    on_complete=_on_single_complete,
                    on_error=self.on_error
                )
                with self._lock:
                    self.current_engine = engine
                    self._active_engines = [engine]
                    if self._is_paused:
                        engine.pause()
                engine.start()

                while engine.is_running and not self._cancel_event.is_set():
                    time.sleep(0.1)
                return

            # Dual-stream: Video + Audio + FFmpeg merge
            video_tmp = self.destination_path + ".video.tmp"
            audio_tmp = self.destination_path + ".audio.tmp"

            self._active_phase = 1
            plat = getattr(self.stream_info, "platform", "Media")
            tag = plat.upper().replace(" / X", "")
            self.log(f"[{tag}] Phase 1/2: Downloading Video & Audio streams in parallel ({self.stream_info.video_resolution})...")
            v_completed = threading.Event()
            a_completed = threading.Event()
            v_error: List[str] = []
            a_error: List[str] = []

            self._v_speed = 0.0
            self._a_speed = 0.0
            self._v_active = 0
            self._a_active = 0

            def _report_combined():
                with self._lock:
                    combined_total = max(1, self._v_total_size + self._a_total_size)
                    combined_dl = min(combined_total, self._v_downloaded + self._a_downloaded)
                    combined_speed = self._v_speed + self._a_speed
                    combined_active = self._v_active + self._a_active
                    if combined_speed > 0:
                        self._last_active_speed = combined_speed
                    elif combined_dl > 0 and self._last_active_speed <= 0.0:
                        st = self.start_time; el = (time.time() - st) if (isinstance(st, (int, float)) and st > 0) else 0.1
                        self._last_active_speed = combined_dl / max(0.05, el)
                    if combined_speed <= 0.0 and self._last_active_speed > 0 and (v_completed.is_set() or a_completed.is_set()):
                        combined_speed = self._last_active_speed
                rem_bytes = max(0, combined_total - combined_dl)
                if combined_speed > 1024 and rem_bytes > 0:
                    eta_sec = int(rem_bytes / combined_speed)
                    eta_str = f"{eta_sec // 3600:02d}:{(eta_sec % 3600) // 60:02d}:{eta_sec % 60:02d}"
                else:
                    eta_str = "--:--:--"
                if self.on_progress:
                    self.on_progress(combined_dl, combined_total, combined_speed, eta_str, combined_active)

            def _on_v_complete(path, size, elapsed):
                with self._lock:
                    if size > 0: self._v_total_size = size
                    self._v_downloaded = self._v_total_size
                    self._v_speed = 0.0
                    self._v_active = 0
                    if not a_completed.is_set():
                        self.current_engine = a_engine
                v_completed.set()
                _report_combined()

            def _on_v_error(err):
                v_error.append(err)
                v_completed.set()
                a_completed.set()
                try: a_engine.cancel()
                except Exception: pass

            def _on_v_progress(downloaded, total, speed, eta, active):
                with self._lock:
                    self._v_downloaded = downloaded
                    if total > 0: self._v_total_size = total
                    self._v_speed = speed
                    self._v_active = active
                _report_combined()

            def _on_a_complete(path, size, elapsed):
                with self._lock:
                    if size > 0: self._a_total_size = size
                    self._a_downloaded = self._a_total_size
                    self._a_speed = 0.0
                    self._a_active = 0
                a_completed.set()
                _report_combined()

            def _on_a_error(err):
                a_error.append(err)
                a_completed.set()
                v_completed.set()
                try: v_engine.cancel()
                except Exception: pass

            def _on_a_progress(downloaded, total, speed, eta, active):
                with self._lock:
                    self._a_downloaded = downloaded
                    if total > 0: self._a_total_size = total
                    self._a_speed = speed
                    self._a_active = active
                _report_combined()

            req_conn = getattr(self, "_requested_max_connections", self.max_connections)
            v_conn = min(max(1, req_conn), 8)
            v_engine = TurboDownloadEngine(
                url=self.stream_info.video_url,
                destination_path=video_tmp,
                max_connections=v_conn,
                allow_dynamic_split=True,
                rate_limit_bytes_per_sec=self.rate_limit,
                ssl_context=self.ssl_context,
                headers=self.stream_info.video_headers,
                on_progress=_on_v_progress,
                on_chunk_update=self.on_chunk_update,
                on_log=self.on_log,
                on_complete=_on_v_complete,
                on_error=_on_v_error
            )

            a_conn = min(max(1, req_conn // 2), 4)
            a_engine = TurboDownloadEngine(
                url=self.stream_info.audio_url,
                destination_path=audio_tmp,
                max_connections=a_conn,
                allow_dynamic_split=True,
                rate_limit_bytes_per_sec=self.rate_limit,
                ssl_context=self.ssl_context,
                headers=self.stream_info.audio_headers,
                on_progress=_on_a_progress,
                on_chunk_update=self.on_chunk_update,
                on_log=self.on_log,
                on_complete=_on_a_complete,
                on_error=_on_a_error
            )

            with self._lock:
                self.current_engine = v_engine
                self._active_engines = [v_engine, a_engine]
                if self._is_paused:
                    v_engine.pause()
                    a_engine.pause()
            v_engine.start()
            a_engine.start()

            while not (v_completed.is_set() and a_completed.is_set()) and not self._cancel_event.is_set():
                if v_error or a_error:
                    break
                time.sleep(0.05)

            def _drain_workers():
                for eng in (v_engine, a_engine):
                    for w in list(getattr(eng, "active_workers", [])):
                        if w.is_alive() and w != threading.current_thread():
                            w.join(timeout=0.15)

            if self._cancel_event.is_set():
                v_engine.cancel(); a_engine.cancel(); _drain_workers()
                return
            if v_error:
                a_engine.cancel(); _drain_workers()
                raise RuntimeError(f"Video stream download error: {v_error[0]}")
            if a_error:
                v_engine.cancel(); _drain_workers()
                raise RuntimeError(f"Audio stream download error: {a_error[0]}")

            # 3. Merge Phase via FFmpeg
            self._active_phase = 3
            with self._lock:
                self._active_engines.clear()
            combined_total = max(1, self._v_total_size + self._a_total_size)
            st = self.start_time; el = (time.time() - st) if (isinstance(st, (int, float)) and st > 0) else 0.1
            rep_spd = self._last_active_speed if self._last_active_speed > 0 else (combined_total / max(0.05, el))
            if self.on_progress:
                self.on_progress(combined_total, combined_total, rep_spd, "Merging...", 0)

            self.log(f"[{tag}] Phase 2/2: Merging video and audio streams into final container...")
            YouTubeResolver.merge_video_audio(video_tmp, audio_tmp, self.destination_path, on_log=self.log)
            self._process_subtitles(self.destination_path)

            elapsed = max(0.01, time.time() - self.start_time)
            final_size = os.path.getsize(self.destination_path)
            self.log(f"[SUCCESS] {plat} media assembled & merged successfully ({final_size:,} bytes in {elapsed:.1f}s)!")

            if self.on_complete:
                self.on_complete(self.destination_path, final_size, elapsed)

        except Exception as e:
            has_error = True
            plat = getattr(self.stream_info, "platform", "Media")
            tag = plat.upper().replace(" / X", "")
            self.log(f"[{tag} ERROR] {e}")
            if self.on_error:
                self.on_error(str(e))
        finally:
            with self._lock:
                self._is_running = False
            # Cleanly remove temporary part files on cancel or error
            if self._cancel_event.is_set() or has_error or v_error or a_error:
                clean_targets = [p for p in (video_tmp, audio_tmp, actual_dest if is_mp3_request else "") if p]
                for p in clean_targets:
                    if os.path.exists(p):
                        try: os.remove(p)
                        except Exception: pass
                    for ext in (".sd_parts", ".tdm_parts"):
                        parts_dir = p + ext
                        if os.path.isdir(parts_dir):
                            try: shutil.rmtree(parts_dir, ignore_errors=True)
                            except Exception: pass

    def _process_subtitles(self, target_path: str):
        sub = getattr(self.stream_info, "subtitle_track", None)
        if sub and sub.get("sub_id") not in (None, "none") and sub.get("url"):
            try:
                from ..services.youtube_tracks import handle_subtitles_post_download
                handle_subtitles_post_download(self.stream_info, target_path, on_log=self.log)
            except Exception as e:
                self.log(f"[SUBTITLES] Warning: {e}")

