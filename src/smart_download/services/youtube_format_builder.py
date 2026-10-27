"""
YouTubeFormatBuilderMixin: Stream info and format options construction for yt-dlp extracted media.
"""
import os
import sys
import re
import math
import copy
from typing import List, Dict, Any, Optional

from .youtube_models import (
    VideoFormatOption,
    YouTubeStreamInfo,
    has_ffmpeg,
    extract_media_platform,
    extract_youtube_id,
    extract_media_id,
    sanitize_filename,
)


class YouTubeFormatBuilderMixin:
    """Mixin providing format options building and stream info resolution logic."""

    def build_format_options(self, info: Dict[str, Any]) -> List[VideoFormatOption]:
        """
        Processes formats dictionary from yt-dlp info and constructs sorted VideoFormatOption list.
        Accurately estimates sizes from bitrate and duration when raw filesize is omitted.
        Handles YouTube, TikTok, Instagram, Twitter/X, Facebook, Reddit, Vimeo, and generic media streams.
        """
        raw_formats = info.get("formats", [])
        duration = int(info.get("duration") or 0)

        # If formats is empty but top-level url exists (e.g. some direct Instagram/TikTok/Pinterest posts)
        if not raw_formats and info.get("url"):
            raw_formats = [{
                "format_id": info.get("format_id") or "direct",
                "url": info.get("url"),
                "ext": info.get("ext") or "mp4",
                "height": info.get("height") or 720,
                "width": info.get("width") or 1280,
                "filesize": info.get("filesize") or info.get("filesize_approx") or 0,
                "vcodec": info.get("vcodec") or "h264",
                "acodec": info.get("acodec") or "aac",
                "http_headers": info.get("http_headers") or {},
                "protocol": info.get("protocol") or "https",
            }]

        if not raw_formats:
            return []

        def _is_direct_stream(f: Dict[str, Any]) -> bool:
            url = f.get("url") or ""
            if not url or not url.startswith("http"):
                return False
            proto = str(f.get("protocol") or "").lower()
            if "m3u8" in proto or "dash" in proto:
                return False
            return True

        def _has_audio(f: Dict[str, Any]) -> bool:
            acodec = str(f.get("acodec") or "").lower()
            return bool(acodec and acodec != "none")

        def _has_video(f: Dict[str, Any]) -> bool:
            vcodec = str(f.get("vcodec") or "").lower()
            return bool(vcodec and vcodec != "none")

        def _estimate_size(f: Dict[str, Any]) -> int:
            if not f:
                return 0
            raw_sz = f.get("filesize") or f.get("filesize_approx")
            if raw_sz:
                try:
                    val = int(raw_sz)
                    if val > 0:
                        return val
                except (ValueError, TypeError):
                    pass
            tbr = float(f.get("tbr") or 0.0)
            vbr = float(f.get("vbr") or 0.0)
            abr = float(f.get("abr") or 0.0)
            bitrate_kbps = tbr or (vbr + abr) or vbr or abr
            if bitrate_kbps > 0 and duration > 0:
                return int((bitrate_kbps * 1000.0 / 8.0) * duration)
            return 0

        # Filter direct streams; fallback to any HTTP stream if strict filter removes all
        formats = [f for f in raw_formats if _is_direct_stream(f)]
        if not formats:
            formats = [f for f in raw_formats if f.get("url") and str(f.get("url")).startswith("http")]
        if not formats:
            return []

        # Fix missing / zero heights by inferring from width or resolution string
        for f in formats:
            h = int(f.get("height") or 0)
            w = int(f.get("width") or 0)
            if h <= 0 and w > 0:
                f["height"] = int(w * 9 / 16) if w > 1000 else int(w * 16 / 9)
            elif h <= 0:
                res_str = str(f.get("resolution") or f.get("format_note") or f.get("format_id") or "")
                m = re.search(r'(\d{3,4})p', res_str)
                if m:
                    f["height"] = int(m.group(1))
                else:
                    m2 = re.search(r'\d+x(\d+)', res_str)
                    if m2:
                        f["height"] = int(m2.group(1))
            if int(f.get("height") or 0) <= 0:
                f["height"] = 720

        # 1. Identify valid audio-only formats
        audio_only_formats = [
            f for f in formats
            if _has_audio(f) and not _has_video(f)
        ]

        def _audio_rank(f):
            # Prioritize original / default language audio tracks over dubs
            lang_pref = float(f.get("language_preference") or 0.0)
            abr = float(f.get("abr") or f.get("tbr") or 0.0)
            is_m4a = 1 if (f.get("ext") or "").lower() in ("m4a", "mp4") else 0
            return (lang_pref, is_m4a, abr)

        sorted_audios = sorted(audio_only_formats, key=_audio_rank, reverse=True)
        best_audio = sorted_audios[0] if sorted_audios else None
        best_audio_size = _estimate_size(best_audio) if best_audio else 0
        best_audio_ext = (best_audio.get("ext") or "m4a").lower() if best_audio else "m4a"
        best_audio_abr = int(best_audio.get("abr") or best_audio.get("tbr") or 128) if best_audio else 128

        # 2. Identify video-only formats
        video_only_formats = [
            f for f in formats
            if _has_video(f) and not _has_audio(f)
        ]

        # 3. Identify progressive (combined audio+video) formats
        progressive_formats = [
            f for f in formats
            if _has_video(f) and _has_audio(f)
        ]

        # Critical adaptation for social media (TikTok, Instagram, Twitter, etc.):
        # If there are no separate audio streams available, treat all video streams as progressive
        if not audio_only_formats:
            for vf in video_only_formats:
                if vf not in progressive_formats:
                    progressive_formats.append(vf)
            video_only_formats = []

        options: List[VideoFormatOption] = []
        ffmpeg_available = has_ffmpeg()

        # Collect distinct video heights
        all_heights = set()
        for f in video_only_formats:
            h = int(f.get("height") or 0)
            if h > 0:
                all_heights.add(h)
        for f in progressive_formats:
            h = int(f.get("height") or 0)
            if h > 0:
                all_heights.add(h)

        def _label_for_height(h: int, fps: int = 30, w: int = 0) -> str:
            if w > 0 and h > w:
                # Vertical format video (TikTok, Instagram Reels, Shorts)
                if w >= 1080 or h >= 1920:
                    base = f"1080p Vertical ({w}x{h})"
                elif w >= 720 or h >= 1280:
                    base = f"720p Vertical ({w}x{h})"
                elif w >= 480 or h >= 854:
                    base = f"480p Vertical ({w}x{h})"
                else:
                    base = f"{w}p Vertical ({w}x{h})"
            elif h >= 2000:
                base = "4K (2160p)"
            elif h >= 1350:
                base = "2K (1440p QHD)"
            elif h >= 1000:
                base = "1080p (Full HD)"
            elif h >= 700:
                base = "720p (HD)"
            elif h >= 450:
                base = "480p (SD)"
            elif h >= 340:
                base = "360p (SD)"
            elif h >= 220:
                base = "240p (SD)"
            elif h >= 140:
                base = "144p (SD)"
            elif h > 0:
                base = f"{h}p"
            else:
                base = "Original Quality"
            if fps >= 50:
                base += f" {fps}fps"
            return base

        # Helper to rank video-only streams for a given height
        def _video_rank(f):
            is_mp4 = 1 if (f.get("ext") or "").lower() == "mp4" else 0
            fps = int(f.get("fps") or 30)
            size = _estimate_size(f)
            return (is_mp4, fps, size)

        # Build options for each resolution height descending
        for h in sorted(all_heights, reverse=True):
            v_matches = [f for f in video_only_formats if int(f.get("height") or 0) == h]
            p_matches = [f for f in progressive_formats if int(f.get("height") or 0) == h]

            # Dual-stream option (FFmpeg required for merge)
            if ffmpeg_available and best_audio and v_matches:
                best_v = sorted(v_matches, key=_video_rank, reverse=True)[0]
                fps = int(best_v.get("fps") or 30)
                w = int(best_v.get("width") or 0)
                v_size = _estimate_size(best_v)
                approx_total = v_size + best_audio_size if (v_size and best_audio_size) else (v_size or best_audio_size)
                v_ext = (best_v.get("ext") or "mp4").lower()
                target_ext = "mp4" if (v_ext in ("mp4", "m4v") or ffmpeg_available) else v_ext

                options.append(VideoFormatOption(
                    format_id=f"{best_v.get('format_id')}+{best_audio.get('format_id')}",
                    resolution_label=_label_for_height(h, fps, w),
                    height=h,
                    ext=target_ext,
                    filesize_approx=approx_total,
                    fps=fps,
                    vcodec=best_v.get("vcodec", ""),
                    acodec=best_audio.get("acodec", ""),
                    is_progressive=False,
                    is_audio_only=False,
                    video_url=best_v["url"],
                    video_headers=best_v.get("http_headers", {}),
                    audio_url=best_audio["url"],
                    audio_headers=best_audio.get("http_headers", {}),
                    audio_ext=best_audio_ext,
                    audio_size=best_audio_size,
                    note=f"{fps} FPS • Lossless Merge (FFmpeg)"
                ))

            # Progressive option (if available and either no dual-stream or lower/equal 720p)
            if p_matches:
                def _prog_rank(f):
                    is_mp4 = 1 if (f.get("ext") or "").lower() == "mp4" else 0
                    return (is_mp4, _estimate_size(f))

                best_p = sorted(p_matches, key=_prog_rank, reverse=True)[0]
                p_size = _estimate_size(best_p)
                p_ext = (best_p.get("ext") or "mp4").lower()
                fps = int(best_p.get("fps") or 30)
                w = int(best_p.get("width") or 0)

                # Avoid duplicate if dual-stream with same height exists unless progressive is distinct
                has_dual = any(opt.height == h and not opt.is_progressive for opt in options)
                if not has_dual or not ffmpeg_available or h <= 720:
                    prog_label = _label_for_height(h, fps, w)
                    if has_dual:
                        prog_label += " (Progressive)"
                    options.append(VideoFormatOption(
                        format_id=str(best_p.get("format_id", "prog")),
                        resolution_label=prog_label,
                        height=h,
                        ext=p_ext,
                        filesize_approx=p_size,
                        fps=fps,
                        vcodec=best_p.get("vcodec", ""),
                        acodec=best_p.get("acodec", ""),
                        is_progressive=True,
                        is_audio_only=False,
                        video_url=best_p["url"],
                        video_headers=best_p.get("http_headers", {}),
                        note="Direct Stream (No merge needed)"
                    ))

        # 4. Add Audio-Only options (both M4A and universal MP3 if FFmpeg available)
        if best_audio:
            # Primary direct audio (M4A)
            options.append(VideoFormatOption(
                format_id=str(best_audio.get("format_id", "audio_m4a")),
                resolution_label=f"Audio Only ({best_audio_ext.upper()})",
                height=0,
                ext=best_audio_ext,
                filesize_approx=best_audio_size,
                fps=0,
                vcodec="none",
                acodec=best_audio.get("acodec", ""),
                is_progressive=True,
                is_audio_only=True,
                video_url=best_audio["url"],
                video_headers=best_audio.get("http_headers", {}),
                audio_ext=best_audio_ext,
                note=f"High Quality Audio (~{best_audio_abr} kbps)"
            ))

            # MP3 Universal Audio option (transcoded via FFmpeg if requested)
            if ffmpeg_available and best_audio_ext != "mp3":
                options.append(VideoFormatOption(
                    format_id=f"{best_audio.get('format_id', 'audio')}+mp3",
                    resolution_label="Audio Only (MP3)",
                    height=0,
                    ext="mp3",
                    filesize_approx=best_audio_size,
                    fps=0,
                    vcodec="none",
                    acodec="mp3",
                    is_progressive=True,
                    is_audio_only=True,
                    video_url=best_audio["url"],
                    video_headers=best_audio.get("http_headers", {}),
                    audio_ext=best_audio_ext,
                    note=f"Universal MP3 Audio (~{best_audio_abr} kbps • FFmpeg)"
                ))
        elif ffmpeg_available and (progressive_formats or formats):
            candidates = progressive_formats or formats
            audio_capable = [f for f in candidates if _has_audio(f)]
            best_pool = audio_capable if audio_capable else candidates

            def _prog_audio_rank(f):
                abr = float(f.get("abr") or 0.0)
                tbr = float(f.get("tbr") or 0.0)
                is_mp4 = 1 if (f.get("ext") or "").lower() == "mp4" else 0
                return (abr, tbr, is_mp4, _estimate_size(f))

            best_prog_for_audio = sorted(best_pool, key=_prog_audio_rank, reverse=True)[0]
            prog_size = _estimate_size(best_prog_for_audio)
            est_mp3_size = max(1, int(prog_size * 0.25)) if prog_size > 0 else 0
            options.append(VideoFormatOption(
                format_id=f"{best_prog_for_audio.get('format_id', 'prog')}+mp3",
                resolution_label="Audio Only (MP3)",
                height=0,
                ext="mp3",
                filesize_approx=est_mp3_size,
                fps=0,
                vcodec="none",
                acodec="mp3",
                is_progressive=True,
                is_audio_only=True,
                video_url=best_prog_for_audio["url"],
                video_headers=best_prog_for_audio.get("http_headers", {}),
                audio_ext=(best_prog_for_audio.get("ext") or "mp4").lower(),
                note="Universal MP3 Audio (Extracted via FFmpeg)"
            ))

        # 5. Safety fallback if options is still empty but formats exist
        if not options and formats:
            f0 = formats[0]
            options.append(VideoFormatOption(
                format_id=str(f0.get("format_id", "default")),
                resolution_label="Original Quality",
                height=int(f0.get("height") or 720),
                ext=(f0.get("ext") or "mp4").lower(),
                filesize_approx=_estimate_size(f0),
                fps=int(f0.get("fps") or 30),
                vcodec=str(f0.get("vcodec") or ""),
                acodec=str(f0.get("acodec") or ""),
                is_progressive=True,
                is_audio_only=False,
                video_url=f0["url"],
                video_headers=f0.get("http_headers", {}),
                note="Direct Stream"
            ))

        # Sort options: Video height descending, then filesize descending, audio-only (height 0) at end
        def _sort_key(opt: VideoFormatOption):
            return (opt.height > 0, opt.height, opt.filesize_approx)

        return sorted(options, key=_sort_key, reverse=True)

    def build_stream_info(self, info: Dict[str, Any], option: VideoFormatOption) -> YouTubeStreamInfo:
        """
        Constructs a YouTubeStreamInfo instance ready for StreamDownloadCoordinator
        based on the selected VideoFormatOption.
        """
        opt = copy.copy(option)
        web_url = info.get("webpage_url") or ""
        platform = extract_media_platform(web_url)
        video_id = str(info.get("id") or extract_youtube_id(web_url) or extract_media_id(web_url) or "video")
        raw_title = info.get("title") or f"{platform}_Video_{video_id}"
        clean_title = sanitize_filename(raw_title)
        duration = int(info.get("duration") or 0)
        thumbnail = info.get("thumbnail", "")

        res_str = opt.resolution_label if (opt.resolution_label and "Vertical" in opt.resolution_label) else (f"{opt.height}p" if opt.height > 0 else "Audio Only")

        sel_audio = getattr(opt, "selected_audio_track", None) or getattr(opt, "audio_track", None)
        sub_track = getattr(opt, "selected_subtitle_track", None) or getattr(opt, "subtitle_track", None)
        if sub_track and sub_track.get("sub_id") in (None, "none"):
            sub_track = None
        sub_mode = getattr(opt, "subtitle_embed_mode", None)
        if not sub_mode:
            try:
                from ..config import get_setting
                sub_mode = get_setting("subtitle_embed_mode", "hard_burn")
            except Exception:
                sub_mode = "hard_burn"
        audio_lang = sel_audio.get("language") if sel_audio else None

        is_dubbed_selection = bool(
            sel_audio and sel_audio.get("url") and (
                sel_audio.get("track_id") != "original" or not sel_audio.get("is_original", True)
            )
        )

        if opt.is_audio_only:
            if sel_audio and sel_audio.get("url"):
                opt.video_url = sel_audio["url"]
                opt.video_headers = sel_audio.get("http_headers") or info.get("http_headers") or {}
                if sel_audio.get("ext"):
                    opt.ext = sel_audio["ext"]
                if sel_audio.get("filesize"):
                    opt.filesize_approx = int(sel_audio["filesize"])
        elif is_dubbed_selection and (not opt.is_progressive or has_ffmpeg()):
            opt.is_progressive = False
            opt.audio_url = sel_audio["url"]
            opt.audio_ext = sel_audio.get("ext", "m4a")
            opt.audio_headers = sel_audio.get("http_headers") or info.get("http_headers") or {}
            if hasattr(opt, "audio_format_id"):
                setattr(opt, "audio_format_id", sel_audio.get("format_id", ""))
            if sel_audio.get("filesize"):
                opt.audio_size = int(sel_audio["filesize"])
        elif sel_audio and sel_audio.get("url") and not opt.is_progressive:
            opt.audio_url = sel_audio["url"]
            opt.audio_ext = sel_audio.get("ext", "m4a")
            opt.audio_headers = sel_audio.get("http_headers") or info.get("http_headers") or {}
            if hasattr(opt, "audio_format_id"):
                setattr(opt, "audio_format_id", sel_audio.get("format_id", ""))
            if sel_audio.get("filesize"):
                opt.audio_size = int(sel_audio["filesize"])

        webpage_url = str(info.get("webpage_url") or info.get("original_url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else ""))
        out_fn = f"{clean_title}.{opt.ext}"

        if opt.is_audio_only:
            return YouTubeStreamInfo(
                video_id=video_id,
                title=raw_title,
                clean_filename=out_fn,
                is_progressive=True,
                video_url=opt.video_url,
                video_headers=opt.video_headers,
                video_ext=opt.ext,
                video_resolution="Audio Only",
                video_size=opt.filesize_approx,
                audio_url=None,
                audio_headers={},
                audio_ext=opt.audio_ext or opt.ext,
                audio_size=0,
                duration=duration,
                thumbnail_url=thumbnail,
                is_audio_only=True,
                platform=platform,
                subtitle_track=sub_track,
                audio_language=audio_lang,
                subtitle_embed_mode=sub_mode,
                webpage_url=webpage_url,
            )
        elif opt.is_progressive or not opt.audio_url:
            return YouTubeStreamInfo(
                video_id=video_id,
                title=raw_title,
                clean_filename=out_fn,
                is_progressive=True,
                video_url=opt.video_url,
                video_headers=opt.video_headers,
                video_ext=opt.ext,
                video_resolution=res_str,
                video_size=opt.filesize_approx,
                audio_url=None,
                audio_headers={},
                audio_ext="",
                audio_size=0,
                duration=duration,
                thumbnail_url=thumbnail,
                is_audio_only=False,
                platform=platform,
                subtitle_track=sub_track,
                audio_language=audio_lang,
                subtitle_embed_mode=sub_mode,
                webpage_url=webpage_url,
            )
        else:
            v_size = max(0, opt.filesize_approx - opt.audio_size) if opt.audio_size else opt.filesize_approx
            return YouTubeStreamInfo(
                video_id=video_id,
                title=raw_title,
                clean_filename=out_fn,
                is_progressive=False,
                video_url=opt.video_url,
                video_headers=opt.video_headers,
                video_ext=opt.ext,
                video_resolution=res_str,
                video_size=v_size,
                audio_url=opt.audio_url,
                audio_headers=opt.audio_headers,
                audio_ext=opt.audio_ext,
                audio_size=opt.audio_size,
                duration=duration,
                thumbnail_url=thumbnail,
                is_audio_only=False,
                platform=platform,
                subtitle_track=sub_track,
                audio_language=audio_lang,
                subtitle_embed_mode=sub_mode,
                webpage_url=webpage_url,
            )

