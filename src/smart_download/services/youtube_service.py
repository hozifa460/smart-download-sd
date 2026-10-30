"""
YouTube & universal streaming resolver: yt-dlp metadata extraction,
fallback TikTok direct rehydration, progressive format detection, and FFmpeg stream merging.
"""
import os, re, sys, time, json, shutil, subprocess, http.cookiejar, urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable, Any

try:
    from .updater_service import APP_VERSION, YtDlpAutoUpdater, get_ytdlp_plugin_dir
except ImportError:
    try: from smart_download.services.updater_service import APP_VERSION, YtDlpAutoUpdater, get_ytdlp_plugin_dir
    except ImportError: from updater import APP_VERSION, YtDlpAutoUpdater, get_ytdlp_plugin_dir

from ..core.chunk import get_permissive_ssl_context

from .youtube_models import (
    YOUTUBE_URL_REGEX, SOCIAL_MEDIA_PATTERNS, INVALID_FILENAME_CHARS,
    SUPPORTED_COOKIE_BROWSERS, detect_installed_cookie_browsers,
    is_youtube_url, is_social_media_url, is_ytdlp_available,
    get_ytdlp_version, update_ytdlp_engine, is_ytdlp_extractor_supported,
    is_media_url, PLATFORM_DISPLAY_NAMES, extract_media_platform,
    extract_media_id, extract_youtube_id, find_ffmpeg_bin, has_ffmpeg,
    sanitize_filename, VideoFormatOption, format_filesize,
    YouTubeStreamInfo, MediaStreamInfo,
)
from .youtube_format_builder import YouTubeFormatBuilderMixin


class YouTubeResolver(YouTubeFormatBuilderMixin):
    """
    High-level resolver that communicates with yt-dlp to extract high-speed direct
    stream URLs, extracts all available video qualities/formats, and orchestrates
    video + audio merging with FFmpeg for YouTube and social media platforms.
    """

    def __init__(
        self, on_log: Optional[Callable[[str], None]] = None, socket_timeout: int = 12,
        auto_update_on_failure: bool = True, cookies_from_browser: Optional[str] = "auto",
        cookies_file: Optional[str] = None
    ):
        self.on_log = on_log
        self.socket_timeout = max(1, int(socket_timeout))
        self.auto_update_on_failure = bool(auto_update_on_failure)
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file

    def _build_ydl_opts(self, browser: Optional[str] = None, cookiefile: Optional[str] = None) -> Dict[str, Any]:
        """Builds standard yt-dlp extraction options dictionary."""
        opts: Dict[str, Any] = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "nocheckcertificate": True, "noplaylist": True, "extract_flat": False,
            "socket_timeout": min(self.socket_timeout, 8),
            "youtube_include_dash_manifest": True, "youtube_include_hls_manifest": False,
            "check_formats": False,
        }
        if cookiefile and os.path.isfile(cookiefile): opts["cookiefile"] = cookiefile
        if browser and browser.lower() not in ("none", "auto", "off", ""):
            opts["cookiesfrombrowser"] = (browser.lower(),)
        return opts

    def log(self, message: str):
        if self.on_log:
            try: self.on_log(message)
            except Exception: pass

    def _extract_tiktok_via_tikwm(self, url: str) -> Optional[Dict[str, Any]]:
        """Queries TikWM API fallback when TikTok webpage requests fail or trigger WAF challenge."""
        try:
            import urllib.parse
            api_url = f"https://www.tikwm.com/api/?url={urllib.parse.quote(url)}&hd=1"
            self.log(f"[TIKTOK] Querying TikWM API fallback: {api_url}")
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=12, context=get_permissive_ssl_context()) as resp:
                res = json.loads(resp.read().decode("utf-8", errors="replace"))

            if not isinstance(res, dict) or res.get("code") != 0 or not isinstance(res.get("data"), dict):
                return None

            d = res["data"]
            media_id = str(d.get("id") or extract_media_id(url) or "tiktok_video")
            raw_title = re.sub(r"[\ufffd\s]+", " ", str(d.get("title") or "")).strip()
            title = (raw_title or f"TikTok_Video_{media_id}")[:180]
            music_info = d.get("music_info") if isinstance(d.get("music_info"), dict) else {}
            duration = int(d.get("duration") or 0) or int(music_info.get("duration") or 0)
            thumbnail = d.get("origin_cover") or d.get("cover") or ""
            formats: List[Dict[str, Any]] = []
            seen_urls = set()

            def _resolve_url(u: str) -> str:
                return f"https://www.tikwm.com{u}" if u.startswith("/") else u

            stream_headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.tiktok.com/"}

            if d.get("hdplay"):
                hd_url = _resolve_url(str(d["hdplay"]))
                seen_urls.add(hd_url)
                formats.append({
                    "format_id": "hd_no_watermark", "url": hd_url, "ext": "mp4",
                    "width": 1080, "height": 1920,
                    "filesize": int(d.get("hd_size") or d.get("size") or 0),
                    "tbr": 0.0, "vcodec": "h264", "acodec": "aac",
                    "http_headers": dict(stream_headers), "protocol": "https",
                    "format_note": "HD (No Watermark)"
                })

            if d.get("play"):
                play_url = _resolve_url(str(d["play"]))
                if play_url not in seen_urls:
                    seen_urls.add(play_url)
                    formats.append({
                        "format_id": "sd_no_watermark", "url": play_url, "ext": "mp4",
                        "width": 576, "height": 1024,
                        "filesize": int(d.get("size") or 0),
                        "tbr": 0.0, "vcodec": "h264", "acodec": "aac",
                        "http_headers": dict(stream_headers), "protocol": "https",
                        "format_note": "SD (No Watermark)"
                    })

            if d.get("wmplay"):
                wm_url = _resolve_url(str(d["wmplay"]))
                if wm_url not in seen_urls:
                    seen_urls.add(wm_url)
                    formats.append({
                        "format_id": "watermarked", "url": wm_url, "ext": "mp4",
                        "width": 480, "height": 854,
                        "filesize": int(d.get("wm_size") or d.get("size") or 0),
                        "tbr": 0.0, "vcodec": "h264", "acodec": "aac",
                        "http_headers": dict(stream_headers), "protocol": "https"
                    })

            if d.get("music"):
                music_url = _resolve_url(str(d["music"]))
                formats.append({
                    "format_id": "music_audio", "url": music_url, "ext": "mp3",
                    "vcodec": "none", "acodec": "mp3", "abr": 128, "filesize": 0,
                    "http_headers": dict(stream_headers), "protocol": "https"
                })

            if not formats:
                return None

            self.log(f"[TIKTOK] TikWM API extraction successful: {len(formats)} formats found.")
            return {
                "id": media_id, "title": title, "duration": duration, "thumbnail": thumbnail,
                "webpage_url": url, "http_headers": stream_headers, "_sd_cookie_header": "",
                "formats": formats, "subtitles": {}
            }
        except Exception as e:
            self.log(f"[TIKTOK ERROR] TikWM extraction failed: {e}")
            return None

    def _extract_tiktok_direct(self, url: str) -> Optional[Dict[str, Any]]:
        """Direct TikTok rehydration extractor parsing __UNIVERSAL_DATA_FOR_REHYDRATION__, falling back to TikWM API."""
        html_info = None
        try:
            self.log(f"[TIKTOK] Attempting direct HTML rehydration extraction for: {url}")
            cj = http.cookiejar.CookieJar()
            ctx = get_permissive_ssl_context()
            https_h = urllib.request.HTTPSHandler(context=ctx)
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), https_h)
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            req = urllib.request.Request(url, headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.tiktok.com/",
            })
            with opener.open(req, timeout=12) as resp:
                final_url = resp.geturl()
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if "gzip" in enc or raw[:2] == b"\x1f\x8b":
                    import gzip; raw = gzip.decompress(raw)
                elif "deflate" in enc:
                    import zlib; raw = zlib.decompress(raw)
                html = raw.decode("utf-8", errors="replace")

            data = None
            m = re.search(r'<script[^>]*\bid="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if m:
                try: data = json.loads(m.group(1).strip())
                except Exception: pass
            if not data:
                m2 = re.search(r'<script[^>]*\bid="(?:SIGI_STATE|sigi-persisted-data)"[^>]*>(.*?)</script>', html, re.DOTALL)
                if m2:
                    try: data = json.loads(m2.group(1).strip())
                    except Exception: pass

            if isinstance(data, dict):
                scope = data.get("__DEFAULT_SCOPE__", {})
                vdetail = scope.get("webapp.video-detail", {})
                item = vdetail.get("itemInfo", {}).get("itemStruct") or vdetail.get("itemStruct")
                if not item and "ItemModule" in data and isinstance(data["ItemModule"], dict):
                    item = next(iter(data["ItemModule"].values()), None)
                if not isinstance(item, dict):
                    def _find_item(obj, d=0):
                        if d > 8 or not isinstance(obj, dict): return None
                        if "itemStruct" in obj and isinstance(obj["itemStruct"], dict): return obj["itemStruct"]
                        if "video" in obj and "id" in obj and isinstance(obj.get("video"), dict): return obj
                        for v in obj.values():
                            if isinstance(v, dict):
                                r = _find_item(v, d + 1)
                                if r: return r
                        return None
                    item = _find_item(data)

                if isinstance(item, dict):
                    cookie_header = "; ".join(f"{c.name}={c.value}" for c in cj)
                    stream_headers = {"User-Agent": ua, "Referer": "https://www.tiktok.com/"}
                    if cookie_header: stream_headers["Cookie"] = cookie_header
                    video = item.get("video") or {}
                    media_id = str(item.get("id") or extract_media_id(final_url) or "tiktok_video")
                    title = str(item.get("desc") or f"TikTok_Video_{media_id}").strip()[:180]
                    duration = int(video.get("duration") or 0)
                    thumbnail = video.get("originCover") or video.get("cover") or ""
                    formats: List[Dict[str, Any]] = []
                    seen_urls = set()

                    for b in video.get("bitrateInfo") or []:
                        if not isinstance(b, dict): continue
                        pa = b.get("PlayAddr") or {}
                        url_list = pa.get("UrlList") or []
                        s_url = next((u for u in url_list if u and isinstance(u, str) and u.startswith("http")), None)
                        if not s_url or s_url in seen_urls: continue
                        seen_urls.add(s_url)
                        formats.append({
                            "format_id": str(b.get("GearName") or f"tt_{pa.get('Height') or 1024}p"),
                            "url": s_url, "ext": "mp4",
                            "width": int(pa.get("Width") or video.get("width") or 576),
                            "height": int(pa.get("Height") or video.get("height") or 1024),
                            "filesize": int(pa.get("DataSize") or 0),
                            "tbr": float(b.get("Bitrate") or 0) / 1000.0,
                            "vcodec": str(b.get("CodecType") or "h264").lower(),
                            "acodec": "aac", "http_headers": dict(stream_headers), "protocol": "https"
                        })

                    for k, pfx in (("downloadAddr", "download"), ("playAddr", "play")):
                        v = video.get(k)
                        cu = v if isinstance(v, str) and v.startswith("http") else None
                        if not cu and isinstance(v, dict):
                            cu = next((u for u in v.get("UrlList") or [] if isinstance(u, str) and u.startswith("http")), None)
                        if cu and cu not in seen_urls:
                            seen_urls.add(cu)
                            formats.append({
                                "format_id": f"{pfx}_addr", "url": cu, "ext": "mp4",
                                "width": int(video.get("width") or 576), "height": int(video.get("height") or 1024),
                                "filesize": int(video.get("dataSize") or 0), "tbr": 0.0,
                                "vcodec": "h264", "acodec": "aac", "http_headers": dict(stream_headers), "protocol": "https"
                            })

                    music = item.get("music") or {}
                    mu = music.get("playUrl")
                    if isinstance(mu, str) and mu.startswith("http") and mu not in seen_urls:
                        seen_urls.add(mu)
                        formats.append({
                            "format_id": "music_audio", "url": mu, "ext": "mp3",
                            "vcodec": "none", "acodec": "mp3", "abr": 128,
                            "http_headers": dict(stream_headers), "protocol": "https"
                        })

                    subtitles: Dict[str, List[Dict[str, Any]]] = {}
                    caps = (video.get("claInfo") or {}).get("captionInfos") or video.get("subtitleInfos") or (item.get("claInfo") or {}).get("captionInfos") or item.get("subtitleInfos") or []
                    for cap in caps:
                        if isinstance(cap, dict) and cap.get("Url"):
                            lang_raw = str(cap.get("LanguageCodeName") or cap.get("language") or "und").strip()
                            l_key = lang_raw.split("-")[0].lower() if "-" in lang_raw else lang_raw.lower()
                            fmt = str(cap.get("Format") or "vtt").lower()
                            subtitles.setdefault(l_key, []).append({
                                "url": str(cap["Url"]), "ext": fmt if fmt in ("vtt", "srt") else "vtt", "name": lang_raw
                            })

                    if formats:
                        self.log(f"[TIKTOK] Direct rehydration successful: {len(formats)} formats, {len(subtitles)} subtitle tracks.")
                        html_info = {
                            "id": media_id, "title": title, "duration": duration, "thumbnail": thumbnail,
                            "webpage_url": final_url, "http_headers": stream_headers, "_sd_cookie_header": cookie_header,
                            "formats": formats, "subtitles": subtitles
                        }
        except Exception as e:
            self.log(f"[TIKTOK ERROR] Direct extraction failed: {e}")

        if html_info and html_info.get("formats"):
            return html_info

        self.log(f"[TIKTOK] Direct HTML rehydration produced no formats. Falling back to TikWM API for: {url}")
        tikwm_info = self._extract_tiktok_via_tikwm(url)
        if tikwm_info and tikwm_info.get("formats"):
            return tikwm_info

        return None

    def extract_format_options(self, url: str) -> Tuple[Dict[str, Any], List[VideoFormatOption]]:
        """Extracts raw metadata and structured VideoFormatOption choices."""
        if not is_media_url(url, check_ytdlp_extractors=True):
            raise ValueError(f"URL is not a recognized media or streaming URL: {url}")
        if not is_ytdlp_available():
            raise RuntimeError("yt-dlp is not installed. To download media streams, install with 'pip install yt-dlp'.")

        platform = extract_media_platform(url)
        media_id = extract_media_id(url) or extract_youtube_id(url) or "media"
        tag = platform.upper().replace(" / X", "")
        self.log(f"[{tag}] Extracting formats and stream metadata for {platform} media (ID: {media_id})...")

        try:
            from .media_extractor import _get_yt_dlp
            yt_dlp = _get_yt_dlp()
            if yt_dlp is None:
                raise ImportError()
        except ImportError:
            raise RuntimeError("yt-dlp Python package is required. Install with 'pip install yt-dlp'.")

        if self.cookies_file and os.path.isfile(self.cookies_file):
            ydl_opts = self._build_ydl_opts(cookiefile=self.cookies_file)
        elif self.cookies_from_browser and self.cookies_from_browser.lower() not in ("none", "auto", "off", ""):
            ydl_opts = self._build_ydl_opts(browser=self.cookies_from_browser)
        else:
            ydl_opts = self._build_ydl_opts()

        info, ydl, tried_tiktok_direct = None, None, False

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as active_ydl:
                info = active_ydl.extract_info(url, download=False)
                ydl = active_ydl
        except Exception as e:
            err_str = str(e).lower()
            is_auth_error = any(kw in err_str for kw in (
                "sign in", "confirm your age", "private", "login", "log in", "account",
                "permission", "403", "401", "forbidden", "cookie", "restricted", "member",
                "bot", "authenticate", "unauthorized", "unavailable", "checkpoint", "not available",
                "unexpected response", "webpage request", "unable to extract", "status code",
                "10204", "challenge", "captcha", "slardar"
            ))

            if platform == "TikTok" and not tried_tiktok_direct:
                self.log(f"[{tag}] yt-dlp extraction failed ({e}). Attempting direct TikTok extraction...")
                info = self._extract_tiktok_direct(url)
                tried_tiktok_direct = True

            if not info and self.cookies_from_browser and self.cookies_from_browser.lower() not in ("none", "auto", "off", "") and not (self.cookies_file and os.path.isfile(self.cookies_file)):
                self.log(f"[{tag}] Cookie extraction from browser '{self.cookies_from_browser}' failed ({e}). Falling back without cookies...")
                try:
                    fallback_opts = self._build_ydl_opts()
                    with yt_dlp.YoutubeDL(fallback_opts) as fb_ydl:
                        info = fb_ydl.extract_info(url, download=False)
                        ydl = fb_ydl
                except Exception as fb_err:
                    self.log(f"[{tag}] Unauthenticated fallback also failed: {fb_err}")
                    info = None
                    if any(kw in str(fb_err).lower() for kw in ("sign in", "confirm your age", "private", "login", "log in", "account", "permission", "403", "401", "forbidden", "cookie", "restricted")):
                        is_auth_error = True

            if not info and is_auth_error:
                for b in detect_installed_cookie_browsers():
                    if self.cookies_from_browser and b.lower() == self.cookies_from_browser.lower():
                        continue
                    try:
                        self.log(f"[{tag}] Retrying extraction with cookies from '{b}'...")
                        cookie_opts = self._build_ydl_opts(browser=b)
                        with yt_dlp.YoutubeDL(cookie_opts) as cookie_ydl:
                            info = cookie_ydl.extract_info(url, download=False)
                            if info:
                                ydl = cookie_ydl
                                self.log(f"[{tag}] Successfully extracted stream info using '{b}' cookies.")
                                break
                    except Exception as cookie_err:
                        self.log(f"[{tag}] Cookies from '{b}' failed: {cookie_err}")

            if not info and platform != "TikTok":
                is_ydl_mocked = bool(getattr(yt_dlp.YoutubeDL, "_mock_name", None))
                is_updater_mocked = bool(getattr(YtDlpAutoUpdater, "_mock_name", None) or getattr(YtDlpAutoUpdater.update, "_mock_name", None))
                if self.auto_update_on_failure and (not is_ydl_mocked or is_updater_mocked):
                    self.log(f"[{tag}] Extraction failed ({e}). Checking for yt-dlp engine update...")
                    try:
                        up_res = YtDlpAutoUpdater(on_log=self.log).update()
                        if up_res.get("updated"):
                            import yt_dlp as refreshed_yt_dlp
                            self.log(f"[{tag}] Retrying extraction with updated yt-dlp v{up_res.get('version')}...")
                            with refreshed_yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                                info = ydl2.extract_info(url, download=False)
                                ydl = ydl2
                    except Exception:
                        pass
            if not info and platform == "TikTok" and not tried_tiktok_direct:
                info = self._extract_tiktok_direct(url)
                tried_tiktok_direct = True
            if not info:
                raise RuntimeError(f"Failed to extract {platform} media stream info: {e}")

        if not info:
            raise RuntimeError("yt-dlp returned empty metadata for the provided URL.")

        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        if not info:
            raise RuntimeError("yt-dlp returned empty metadata for the provided URL.")

        if platform == "TikTok" and not (info and info.get("formats")) and not tried_tiktok_direct:
            self.log(f"[{tag}] yt-dlp returned no formats for TikTok. Retrying direct extraction...")
            tt_direct = self._extract_tiktok_direct(url)
            tried_tiktok_direct = True
            if tt_direct and tt_direct.get("formats"):
                info = tt_direct

        cookiejar = getattr(ydl, "cookiejar", None) if ydl else None
        formats_to_patch = info.get("formats", []) or ([info] if info.get("url") else [])
        fallback_cookie_str = ""
        if isinstance(info.get("cookies"), str): fallback_cookie_str = info["cookies"]
        elif isinstance(info.get("cookies"), dict): fallback_cookie_str = "; ".join(f"{k}={v}" for k, v in info["cookies"].items())
        elif isinstance(info.get("http_headers"), dict): fallback_cookie_str = info["http_headers"].get("Cookie") or info["http_headers"].get("cookie") or ""

        if not fallback_cookie_str and cookiejar:
            try: fallback_cookie_str = (hasattr(cookiejar, "get_cookie_header") and cookiejar.get_cookie_header(url)) or "; ".join(f"{c.name}={c.value}" for c in cookiejar)
            except Exception: pass

        if cookiejar:
            try:
                yt_c = "; ".join(f"{c.name}={c.value}" for c in cookiejar if "youtube" in (getattr(c, "domain", "") or ""))
                if yt_c: info["_sd_cookie_header"] = yt_c
            except Exception: pass
        if not info.get("_sd_cookie_header") and fallback_cookie_str:
            info["_sd_cookie_header"] = fallback_cookie_str

        for f in formats_to_patch:
            headers = f.setdefault("http_headers", {})
            if platform == "TikTok": headers.setdefault("Referer", "https://www.tiktok.com/")
            if "Cookie" in headers or "cookie" in headers: continue
            fmt_url = f.get("url") or ""
            c_val = ""
            if cookiejar and fmt_url and hasattr(cookiejar, "get_cookie_header"):
                try: c_val = cookiejar.get_cookie_header(fmt_url) or ""
                except Exception: pass
            c_val = c_val or fallback_cookie_str
            if c_val: headers["Cookie"] = c_val

        options = self.build_format_options(info)
        if not options and platform == "TikTok":
            self.log(f"[{tag}] No downloadable format options produced by yt-dlp. Retrying direct extraction...")
            tt_direct = self._extract_tiktok_direct(url) or self._extract_tiktok_via_tikwm(url)
            if tt_direct and tt_direct.get("formats"):
                info = tt_direct
                options = self.build_format_options(info)
        return info, options

    def resolve(self, url: str, format_id: Optional[str] = None) -> YouTubeStreamInfo:
        """Extracts stream URLs and metadata from a YouTube or social media link using yt-dlp."""
        info, options = self.extract_format_options(url)
        if not options:
            raise RuntimeError("No downloadable media formats found for this media URL.")

        selected_option = next((opt for opt in options if opt.format_id == format_id), None) if format_id else None
        if not selected_option:
            selected_option = options[0]

        stream_info = self.build_stream_info(info, selected_option)
        plat = extract_media_platform(url)
        tag = plat.upper().replace(" / X", "")
        if stream_info.is_progressive:
            self.log(f"[{tag}] Selected stream: {stream_info.video_resolution} ({stream_info.video_ext}). Directly chunk-downloadable without merging.")
        else:
            self.log(f"[{tag}] Selected dual-stream: Video {stream_info.video_resolution} ({stream_info.video_ext}) + Audio ({stream_info.audio_ext}). Merging with FFmpeg.")
        return stream_info

    @staticmethod
    def merge_video_audio(video_path: str, audio_path: str, output_path: str, on_log: Optional[Callable[[str], None]] = None, cancel_event: Optional[Any] = None) -> bool:
        """Lossless FFmpeg stream multiplexing (-c copy) or transcode fallback."""
        ffmpeg_bin = find_ffmpeg_bin()
        if not ffmpeg_bin:
            raise RuntimeError("FFmpeg executable was not found on PATH or app directory. Cannot merge video and audio.")
        if cancel_event and cancel_event.is_set():
            if on_log: on_log("[FFMPEG] Merge cancelled before execution.")
            return False
        if not os.path.exists(video_path): raise FileNotFoundError(f"Video part file not found: {video_path}")
        if not os.path.exists(audio_path): raise FileNotFoundError(f"Audio part file not found: {audio_path}")
        dest_dir = os.path.dirname(output_path)
        if dest_dir: os.makedirs(dest_dir, exist_ok=True)
        if on_log: on_log(f"[FFMPEG] Merging streams into final file: {os.path.basename(output_path)}...")

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform.startswith("win") else 0
        def _run_proc(cmd_list):
            if cancel_event is None:
                res = subprocess.run(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", creationflags=flags)
                return res.returncode, res.stderr
            p = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", creationflags=flags)
            try:
                while True:
                    try:
                        _, err = p.communicate(timeout=0.05)
                        return p.returncode, err
                    except subprocess.TimeoutExpired:
                        if cancel_event and cancel_event.is_set():
                            try: p.kill(); p.communicate()
                            except Exception: pass
                            if os.path.exists(output_path):
                                try: os.remove(output_path)
                                except Exception: pass
                            return -999, "Cancelled"
            finally:
                if p and p.poll() is None:
                    try: p.kill()
                    except Exception: pass

        def _build_cmd(extra_args):
            c = [ffmpeg_bin, "-y", "-i", video_path, "-i", audio_path, "-map", "0:v:0", "-map", "1:a:0"] + extra_args
            if output_path.lower().endswith((".mp4", ".m4v", ".mov")): c.extend(["-movflags", "+faststart"])
            c.append(output_path)
            return c

        rc, primary_err = _run_proc(_build_cmd(["-c", "copy"]))
        if cancel_event and cancel_event.is_set(): return False

        if rc != 0:
            for enc_args, desc in [
                (["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"], "audio transcode to AAC"),
                (["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "192k"], "container transcode (libx264+aac)"),
            ]:
                if on_log: on_log(f"[FFMPEG] Direct stream copy failed ({rc}). Retrying with {desc}...")
                rc, primary_err = _run_proc(_build_cmd(enc_args))
                if (cancel_event and cancel_event.is_set()) or rc == 0: break
            if rc != 0:
                err_msg = primary_err.strip() or "Unknown FFmpeg error"
                if on_log: on_log(f"[FFMPEG ERROR] Merge failed (exit code {rc}): {err_msg}")
                raise RuntimeError(f"FFmpeg stream merge failed: {err_msg}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("FFmpeg merge completed but output file is missing or empty.")
        for p in (video_path, audio_path):
            try:
                if os.path.exists(p): os.remove(p)
            except Exception: pass
        if on_log:
            on_log(f"[FFMPEG SUCCESS] Merged file successfully created ({os.path.getsize(output_path):,} bytes).")
        return True

# Backward-compatible alias for universal media resolution
MediaResolver = YouTubeResolver
