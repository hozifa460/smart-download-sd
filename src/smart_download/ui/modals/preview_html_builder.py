"""
Unified VidMate-Style HTML5 Preview & Download Settings Builder (preview_html_builder.py).
Generates modern dark-themed HTML5 preview player with synchronized live audio dubbing,
WebVTT subtitle tracks, and interactive format/quality/dubbing/subtitle controls.
"""
import html
import json
from typing import Dict, List, Optional, Any
from ...services.youtube_models import extract_media_platform, format_filesize

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #090d16; color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; height: 100vh; display: flex; flex-direction: column; overflow: hidden; user-select: none; }
.header { background: #131a29; height: 50px; padding: 0 16px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #1e293b; flex-shrink: 0; gap: 10px; }
.title-group { display: flex; align-items: center; gap: 8px; overflow: hidden; flex: 1; }
.title { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #f8fafc; }
.badge { font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 9999px; white-space: nowrap; }
.badge-res { background: #0284c7; color: #fff; }
.badge-sub { background: #059669; color: #fff; }
.badge-audio { background: #8b5cf6; color: #fff; }
.badge-dim { background: #334155; color: #94a3b8; }
.plat-yt { background: #ef4444; color: #fff; }
.plat-tt { background: #ec4899; color: #fff; }
.plat-ig { background: #a855f7; color: #fff; }
.plat-tw { background: #38bdf8; color: #0f172a; font-weight: bold; }
.plat-fb { background: #2563eb; color: #fff; }
.plat-generic { background: #475569; color: #fff; }
.actions { display: flex; align-items: center; gap: 8px; }
.btn { background: #1e293b; color: #38bdf8; border: 1px solid #334155; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s ease; white-space: nowrap; }
.btn:hover { background: #0284c7; color: #fff; border-color: #0284c7; }
.player-container { flex: 52 1 0; min-height: 200px; position: relative; background: #000; display: flex; align-items: center; justify-content: center; overflow: hidden; }
video, iframe { width: 100%; height: 100%; border: none; outline: none; background: #000; }
::cue { background-color: rgba(0, 0, 0, 0.75); color: #ffffff; font-family: "Segoe UI", sans-serif; font-size: 18px; font-weight: 600; text-shadow: 0 2px 4px rgba(0,0,0,0.9); line-height: 1.4; }
.settings-panel { flex: 48 1 0; min-height: 200px; background: #0f172a; border-top: 1px solid #1e293b; padding: 8px 16px; display: flex; flex-direction: column; overflow-y: auto; gap: 6px; }
.settings-header { display: flex; justify-content: space-between; align-items: center; }
.settings-title { font-size: 11px; font-weight: 700; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.5px; }
.settings-count { font-size: 11px; color: #94a3b8; }
.table-container { max-height: 105px; overflow-y: auto; background: #131d31; border: 1px solid #1e293b; border-radius: 6px; }
.format-table { width: 100%; border-collapse: collapse; font-size: 12px; text-align: left; }
.format-table th { background: #17233c; color: #94a3b8; padding: 5px 10px; font-weight: 600; position: sticky; top: 0; border-bottom: 1px solid #1e293b; }
.format-table td { padding: 4px 10px; border-bottom: 1px solid #1e293b; color: #cbd5e1; }
.opt-row { cursor: pointer; transition: background 0.1s ease; }
.opt-row:hover { background: #1e293b; }
.opt-row.selected { background: #0284c7; color: #fff; }
.opt-row.selected td { color: #fff; }
.col-center { text-align: center; }
.col-right { text-align: right; }
.col-note { color: #94a3b8; font-size: 11px; }
.opt-row.selected .col-note { color: #e0f2fe; }
.controls-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.ctrl-group { display: flex; flex-direction: column; gap: 2px; }
.ctrl-group label { font-size: 11px; font-weight: 600; color: #94a3b8; }
.ctrl-group select { background: #17233c; color: #f8fafc; border: 1px solid #334155; padding: 4px 8px; border-radius: 6px; font-size: 12px; outline: none; cursor: pointer; }
.dest-card { display: flex; align-items: center; background: #17233c; border: 1px solid #334155; padding: 4px 10px; border-radius: 6px; gap: 8px; }
.dest-card label { font-size: 11px; font-weight: 600; color: #94a3b8; white-space: nowrap; }
.dest-card input { background: transparent; color: #f8fafc; border: none; outline: none; font-size: 12px; flex: 1; }
.action-bar { display: flex; align-items: center; gap: 10px; margin-top: 2px; }
.btn-download { background: #059669; color: #fff; border: none; padding: 7px 15px; font-size: 12px; font-weight: 700; border-radius: 6px; cursor: pointer; }
.btn-download:hover { background: #047857; }
.btn-secondary { background: #1e293b; color: #cbd5e1; border: 1px solid #334155; padding: 7px 13px; font-size: 12px; font-weight: 600; border-radius: 6px; cursor: pointer; }
.btn-secondary:hover { background: #334155; }
.btn-cancel { background: transparent; color: #94a3b8; border: 1px solid #334155; padding: 7px 13px; font-size: 12px; font-weight: 600; border-radius: 6px; cursor: pointer; margin-left: auto; }
.btn-cancel:hover { background: #334155; color: #fff; }
""".strip()

_JS_TEMPLATE = """
const hasStream = __HAS_STREAM__, embedUrl = __EMBED_SRC__, initialDubAudioUrl = __DUB_URL__;
const sid = __SID__, audioTracks = __AUDIO_TRACKS__, subtitleTracks = __SUBTITLE_TRACKS__;
const bridgeBase = __BRIDGE_BASE__;
const videoEl = document.getElementById("videoEl"), dubAudioEl = document.getElementById("dubAudioEl");
const iframeEl = document.getElementById("iframeEl"), toggleBtn = document.getElementById("toggleBtn");
const audioBadge = document.getElementById("badgeAudio"), subBadge = document.getElementById("badgeSub"), resBadge = document.getElementById("badgeRes");
const audioSelect = document.getElementById("audioSelect"), subSelect = document.getElementById("subSelect"), modeSelect = document.getElementById("modeSelect"), destInput = document.getElementById("destInput");
const muteBtn = document.getElementById("muteBtn"), volSlider = document.getElementById("volSlider");
let isUsingVideo = hasStream, selected_q_idx = 0, hasDubAudio = Boolean(initialDubAudioUrl);
let actionSubmitted = false;
window._userTouchedMode = false;

function updateUI() {
    if (isUsingVideo) {
        videoEl.style.display = "block"; iframeEl.style.display = "none";
        toggleBtn.textContent = "🌐 Switch to Web Player / المشغل المدمج";
        try { videoEl.play(); } catch (e) {}
    } else {
        try { videoEl.pause(); } catch (e) {}
        videoEl.style.display = "none"; iframeEl.style.display = "block";
        if (!iframeEl.src || iframeEl.src === "about:blank") iframeEl.src = embedUrl;
        toggleBtn.textContent = "🎞️ Switch to Direct Stream / المشغل المباشر";
    }
}
function togglePlayer() { if (!hasStream && isUsingVideo) return; isUsingVideo = !isUsingVideo; updateUI(); }
function handleVideoError() { console.warn("[SD Preview] Direct stream fallback to Web Embed"); isUsingVideo = false; updateUI(); }
if (videoEl) { videoEl.addEventListener("error", handleVideoError); }

function setDubAudioTrack(url, label) {
    if (!dubAudioEl) return;
    if (url) {
        hasDubAudio = true; dubAudioEl.src = url;
        const syncTime = () => {
            if (videoEl && !isNaN(videoEl.currentTime)) {
                try { dubAudioEl.currentTime = videoEl.currentTime; } catch (e) {}
            }
            if (videoEl && !videoEl.paused) dubAudioEl.play().catch(e => {});
        };
        if (dubAudioEl.readyState >= 1) syncTime();
        else dubAudioEl.addEventListener("loadedmetadata", syncTime, { once: true });
        videoEl.muted = true;
        if (audioBadge) { audioBadge.textContent = "🔊 " + (label || "Dubbed Audio"); audioBadge.className = "badge badge-audio"; }
    } else {
        hasDubAudio = false; dubAudioEl.pause(); dubAudioEl.removeAttribute("src"); videoEl.muted = false;
        if (audioBadge) { audioBadge.textContent = "🔊 Original Audio"; audioBadge.className = "badge badge-dim"; }
    }
}
if (initialDubAudioUrl) setDubAudioTrack(initialDubAudioUrl, __EFFECTIVE_AUDIO_LABEL__);

if (videoEl && dubAudioEl) {
    videoEl.addEventListener("volumechange", () => {
        if (hasDubAudio) { dubAudioEl.volume = videoEl.volume; if (!videoEl.muted) videoEl.muted = true; }
        if (volSlider) volSlider.value = videoEl.volume;
    });
    videoEl.addEventListener("play", () => { if (hasDubAudio) { dubAudioEl.currentTime = videoEl.currentTime; dubAudioEl.play().catch(e => {}); } });
    videoEl.addEventListener("pause", () => { if (hasDubAudio) dubAudioEl.pause(); });
    videoEl.addEventListener("seeking", () => { if (hasDubAudio) dubAudioEl.currentTime = videoEl.currentTime; });
    videoEl.addEventListener("seeked", () => { if (hasDubAudio) dubAudioEl.currentTime = videoEl.currentTime; });
    videoEl.addEventListener("waiting", () => { if (hasDubAudio) dubAudioEl.pause(); });
    videoEl.addEventListener("playing", () => { if (hasDubAudio) { if (Math.abs(dubAudioEl.currentTime - videoEl.currentTime) > 0.28) dubAudioEl.currentTime = videoEl.currentTime; dubAudioEl.play().catch(e => {}); } });
    videoEl.addEventListener("ratechange", () => { if (hasDubAudio) dubAudioEl.playbackRate = videoEl.playbackRate; });
    videoEl.addEventListener("timeupdate", () => { if (hasDubAudio && !videoEl.paused) { if (Math.abs(dubAudioEl.currentTime - videoEl.currentTime) > 0.28) dubAudioEl.currentTime = videoEl.currentTime; } });
    dubAudioEl.addEventListener("error", (e) => { hasDubAudio = false; videoEl.muted = false; if (audioBadge) { audioBadge.textContent = "🔊 Original Audio"; audioBadge.className = "badge badge-dim"; } });
}

if (muteBtn && volSlider) {
    muteBtn.addEventListener("click", () => {
        const isM = hasDubAudio ? dubAudioEl.muted : videoEl.muted;
        const nextM = !isM;
        if (hasDubAudio) { dubAudioEl.muted = nextM; }
        else { videoEl.muted = nextM; }
        muteBtn.textContent = nextM ? "🔇" : "🔊";
    });
    volSlider.addEventListener("input", (e) => {
        const v = parseFloat(e.target.value);
        if (hasDubAudio) { dubAudioEl.volume = v; dubAudioEl.muted = (v === 0); }
        videoEl.volume = v;
        if (!hasDubAudio) { videoEl.muted = (v === 0); }
        muteBtn.textContent = (v === 0) ? "🔇" : "🔊";
    });
}

function selectQualityRow(idx) {
    selected_q_idx = idx; document.querySelectorAll(".opt-row").forEach(r => r.classList.remove("selected"));
    const row = document.querySelector(`.opt-row[data-idx="${idx}"]`);
    if (row) row.classList.add("selected");
    const resCell = row ? row.querySelector(".col-res strong") : null;
    if (resCell && resBadge) resBadge.textContent = "🎞️ " + resCell.textContent;
    if (sid) {
        const savedTime = videoEl ? videoEl.currentTime : 0;
        videoEl.src = `${bridgeBase}/stream_video?sid=${encodeURIComponent(sid)}&q_idx=${idx}`;
        if (savedTime > 0) {
            videoEl.addEventListener("loadedmetadata", () => {
                try { videoEl.currentTime = savedTime; } catch (e) {}
                videoEl.play().catch(e => {});
            }, { once: true });
        } else {
            videoEl.play().catch(e => {});
        }
        requestUpdatedFilename();
        syncStateToBridge();
    }
}
function onAudioChange() {
    if (!audioSelect) return;
    const a = parseInt(audioSelect.value);
    if (a <= 0 || a >= audioTracks.length) setDubAudioTrack(null, "Original Audio");
    else { const t = audioTracks[a]; setDubAudioTrack(sid ? `${bridgeBase}/stream_audio?sid=${encodeURIComponent(sid)}&a_idx=${a}` : (t.url || ""), t.label || t.language); }
    syncStateToBridge();
}
function onSubChange() {
    if (!subSelect) return;
    const s = parseInt(subSelect.value);
    if (s > 0 && !window._userTouchedMode && modeSelect) {
        modeSelect.value = "hard_burn";
    }
    let trk = document.getElementById("vttTrack");
    if (s <= 0 || s >= subtitleTracks.length) {
        if (trk) { trk.src = ""; try { trk.track.mode = "disabled"; } catch (e) {} }
        if (subBadge) { subBadge.textContent = "💬 No Subtitles"; subBadge.className = "badge badge-dim"; }
    } else {
        const t = subtitleTracks[s], lbl = t.label || t.language || "Subtitles", vUrl = sid ? `${bridgeBase}/subtitle.vtt?sid=${encodeURIComponent(sid)}&s_idx=${s}` : (t.url || "");
        if (subBadge) { subBadge.textContent = "💬 " + lbl; subBadge.className = "badge badge-sub"; }
        if (!trk) { trk = document.createElement("track"); trk.id = "vttTrack"; trk.kind = "subtitles"; trk.default = true; videoEl.appendChild(trk); }
        trk.label = lbl; trk.srclang = (t.language || "ar").split("-")[0].split("_")[0]; trk.src = vUrl;
        try { trk.track.mode = "showing"; } catch (e) {}
    }
    requestUpdatedFilename();
    syncStateToBridge();
}
function onModeChange() {
    if (!modeSelect) return;
    window._userTouchedMode = true;
    if (modeSelect.value === "hard_burn" && subSelect && parseInt(subSelect.value) <= 0 && subtitleTracks.length > 1) {
        let ar = 1; for (let i = 1; i < subtitleTracks.length; i++) { if (String(subtitleTracks[i].language || "").toLowerCase().startsWith("ar")) { ar = i; break; } }
        subSelect.value = String(ar); onSubChange(); return;
    }
    requestUpdatedFilename();
    syncStateToBridge();
}
function syncStateToBridge() {
    if (!sid) return;
    fetch(`${bridgeBase}/api/sync_state?sid=${encodeURIComponent(sid)}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            q_idx: selected_q_idx,
            a_idx: audioSelect ? parseInt(audioSelect.value) : 0,
            s_idx: subSelect ? parseInt(subSelect.value) : 0,
            sub_mode: modeSelect ? modeSelect.value : "hard_burn",
            dest_path: destInput ? destInput.value.trim() : ""
        })
    }).catch(e => {});
}
function requestUpdatedFilename() {
    if (!sid || !destInput) return;
    fetch(`${bridgeBase}/api/update_filename?sid=${encodeURIComponent(sid)}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q_idx: selected_q_idx, sub_mode: modeSelect ? modeSelect.value : "hard_burn", current_dest: destInput.value })
    }).then(r => r.json()).then(d => { if (d && d.dest_path) destInput.value = d.dest_path; }).catch(e => {});
}
function doAction(actionType) {
    actionSubmitted = true;
    document.querySelectorAll(".action-bar button").forEach(b => { b.disabled = true; b.style.opacity = "0.6"; });
    try { if (videoEl) videoEl.pause(); if (dubAudioEl) dubAudioEl.pause(); } catch (e) {}
    if (!sid) { window.close(); return; }
    fetch(`${bridgeBase}/api/action?sid=${encodeURIComponent(sid)}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            action: actionType, q_idx: selected_q_idx,
            a_idx: audioSelect ? parseInt(audioSelect.value) : 0,
            s_idx: subSelect ? parseInt(subSelect.value) : 0,
            sub_mode: modeSelect ? modeSelect.value : "hard_burn",
            dest_path: destInput ? destInput.value.trim() : ""
        })
    }).then(r => r.json()).then(() => { setTimeout(() => { window.close(); }, 120); }).catch(() => { window.close(); });
}
window.addEventListener("pagehide", () => {
    if (sid && !actionSubmitted) { try { navigator.sendBeacon(`${bridgeBase}/api/action?sid=${encodeURIComponent(sid)}`, JSON.stringify({ action: "cancel" })); } catch (e) {} }
});
""".strip()



def generate_preview_html(
    url: str,
    video_title: str,
    stream_url: Optional[str] = None,
    vtt_data_uri: Optional[str] = None,
    video_id: Optional[str] = None,
    sub_label: Optional[str] = None,
    quality_label: Optional[str] = None,
    sub_lang: str = "ar",
    dub_audio_url: Optional[str] = None,
    audio_label: Optional[str] = None,
    selected_audio_track: Optional[Dict[str, Any]] = None,
    audio_tracks: Optional[List[Dict[str, Any]]] = None,
    options: Optional[List[Any]] = None,
    subtitle_tracks: Optional[List[Dict[str, Any]]] = None,
    default_dest_path: Optional[str] = None,
    sid: Optional[str] = None,
    bridge_port: Optional[int] = None,
    platform_name: Optional[str] = None,
    selected_sub_track: Optional[Dict[str, Any]] = None,
    subtitle_embed_mode: str = "hard_burn"
) -> str:
    """Generates modern dark-themed HTML5 preview player with synchronized dubbing and controls."""
    safe_title = html.escape(video_title or "Video Preview")
    safe_stream = html.escape(stream_url or "")
    safe_quality = html.escape(quality_label or ("MP4 Stream" if stream_url else "Web Player"))

    platform = platform_name or extract_media_platform(url)
    safe_platform = html.escape(platform)

    # Determine selected audio track index and effective dubbing URL
    sel_a_idx = 0
    if selected_audio_track and audio_tracks:
        for idx, trk in enumerate(audio_tracks):
            if trk == selected_audio_track or (trk.get("track_id") and trk.get("track_id") == selected_audio_track.get("track_id")):
                sel_a_idx = idx
                break

    eff_dub = dub_audio_url
    eff_audio_lbl = audio_label
    if not eff_dub and selected_audio_track and selected_audio_track.get("track_id") != "original":
        eff_dub = selected_audio_track.get("url")
        eff_audio_lbl = selected_audio_track.get("label") or selected_audio_track.get("language")
    if not eff_audio_lbl:
        eff_audio_lbl = "Original Audio"
    safe_audio_label = html.escape(eff_audio_lbl)

    # Determine selected subtitle index
    sel_s_idx = 0
    if selected_sub_track and subtitle_tracks:
        for idx, trk in enumerate(subtitle_tracks):
            if trk == selected_sub_track or (trk.get("sub_id") and trk.get("sub_id") == selected_sub_track.get("sub_id")):
                sel_s_idx = idx
                break
    if subtitle_embed_mode == "hard_burn" and sel_s_idx <= 0 and subtitle_tracks and len(subtitle_tracks) > 1:
        ar_idx = next((i for i, s in enumerate(subtitle_tracks) if i > 0 and str(s.get("language", "")).lower().startswith("ar")), None)
        sel_s_idx = ar_idx if ar_idx is not None else 1

    safe_sub_label = html.escape(sub_label or "Subtitles")
    safe_sub_lang = html.escape((sub_lang or "ar").split("-")[0].split("_")[0])

    embed_src = f"https://www.youtube.com/embed/{video_id}?autoplay=1&cc_load_policy=1&cc_lang_pref={safe_sub_lang}&hl={safe_sub_lang}" if video_id else url

    bridge_base = f"http://127.0.0.1:{bridge_port}" if bridge_port else ""

    track_html = ""
    if vtt_data_uri:
        track_html = f'<track label="{safe_sub_label}" kind="subtitles" srclang="{safe_sub_lang}" src="{vtt_data_uri}" default id="vttTrack">'
        sub_badge = f'<span id="badgeSub" class="badge badge-sub">💬 {safe_sub_label}</span>'
    elif sid and subtitle_tracks and 0 < sel_s_idx < len(subtitle_tracks):
        st = subtitle_tracks[sel_s_idx]
        lbl = html.escape(st.get("label") or st.get("language") or "Subtitles")
        sc = html.escape((st.get("language") or "ar").split("-")[0].split("_")[0])
        track_html = f'<track label="{lbl}" kind="subtitles" srclang="{sc}" src="{bridge_base}/subtitle.vtt?sid={sid}&s_idx={sel_s_idx}" default id="vttTrack">'
        sub_badge = f'<span id="badgeSub" class="badge badge-sub">💬 {lbl}</span>'
    elif subtitle_tracks and len(subtitle_tracks) > 1 and sel_s_idx > 0:
        sub_badge = f'<span id="badgeSub" class="badge badge-sub">💬 {safe_sub_label}</span>'
    else:
        sub_badge = '<span id="badgeSub" class="badge badge-dim">💬 No Subtitles</span>'

    audio_badge = f'<span id="badgeAudio" class="badge badge-audio">🔊 {safe_audio_label}</span>' if eff_dub else f'<span id="badgeAudio" class="badge badge-dim">🔊 {safe_audio_label}</span>'

    plat_low = platform.lower()
    plat_cls = "plat-generic"
    if "youtube" in plat_low: plat_cls = "plat-yt"
    elif "tiktok" in plat_low: plat_cls = "plat-tt"
    elif "instagram" in plat_low: plat_cls = "plat-ig"
    elif "twitter" in plat_low or "x" in plat_low: plat_cls = "plat-tw"
    elif "facebook" in plat_low: plat_cls = "plat-fb"

    settings_html = ""
    if options:
        rows = []
        for idx, opt in enumerate(options):
            r_l = html.escape(getattr(opt, "resolution_label", "Unknown"))
            r_e = html.escape(str(getattr(opt, "ext", "mp4")).upper())
            fps_val = getattr(opt, "fps", 0)
            r_f = str(fps_val) if isinstance(fps_val, (int, float)) and fps_val > 0 else "—"
            r_s = html.escape(format_filesize(getattr(opt, "filesize_approx", 0)))
            r_n = html.escape(getattr(opt, "note", ""))
            s_cls = "opt-row selected" if idx == 0 else "opt-row"
            rows.append(f'<tr class="{s_cls}" data-idx="{idx}" onclick="selectQualityRow({idx})"><td class="col-res"><strong>{r_l}</strong></td><td class="col-center">{r_e}</td><td class="col-right">{r_s}</td><td class="col-center">{r_f}</td><td class="col-note">{r_n}</td></tr>')
        a_opts = [f'<option value="{i}"{" selected" if i == sel_a_idx else ""}>{html.escape(t.get("label") or t.get("language") or f"Audio #{i}")}</option>' for i, t in enumerate(audio_tracks or [])] or ['<option value="0">Original Audio (Default)</option>']
        s_opts = [f'<option value="{i}"{" selected" if i == sel_s_idx else ""}>{html.escape(t.get("label") or t.get("language") or f"Subtitle #{i}")}</option>' for i, t in enumerate(subtitle_tracks or [])] or ['<option value="0">No Subtitles</option>']
        m_opts = [
            f'<option value="soft_embed"{" selected" if subtitle_embed_mode == "soft_embed" else ""}>Soft Embed (دمج ناعم داخل الفيديو)</option>',
            f'<option value="hard_burn"{" selected" if subtitle_embed_mode == "hard_burn" else ""}>Burn into Video (حرق دائم داخل الصورة)</option>',
            f'<option value="srt_only"{" selected" if subtitle_embed_mode == "srt_only" else ""}>Save External .srt (ملف ترجمة خارجي)</option>',
        ]
        safe_dst = html.escape(default_dest_path or "")
        settings_html = f"""<div class="settings-panel"><div class="settings-header"><span class="settings-title">⚡ Download Quality &amp; Controls</span><span class="settings-count">{len(options)} Formats Detected</span></div><div class="table-container"><table class="format-table"><thead><tr><th>Resolution / Quality</th><th class="col-center">Format</th><th class="col-right">Est. Size</th><th class="col-center">FPS</th><th>Stream Details</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div><div class="controls-row"><div class="ctrl-group"><label>🔊 Audio Dubbing / الدبلجة</label><select id="audioSelect" onchange="onAudioChange()">{"".join(a_opts)}</select></div><div class="ctrl-group"><label>💬 Subtitles / الترجمة</label><select id="subSelect" onchange="onSubChange()">{"".join(s_opts)}</select></div><div class="ctrl-group"><label>⚙️ Mode / طريقة الحفظ</label><select id="modeSelect" onchange="onModeChange()">{"".join(m_opts)}</select></div></div><div class="dest-card"><label>📁 Save As / مسار الحفظ:</label><input type="text" id="destInput" value="{safe_dst}" /></div><div class="action-bar"><button class="btn btn-download" onclick="doAction('download')">⚡ Download Selected Quality</button><button class="btn btn-secondary" onclick="doAction('open_in_main')">🖥️ Open in Main Window</button><button class="btn btn-cancel" onclick="doAction('cancel')">✕ Cancel</button></div></div>"""

    js_code = (
        _JS_TEMPLATE
        .replace("__HAS_STREAM__", "true" if stream_url else "false")
        .replace("__EMBED_SRC__", json.dumps(embed_src))
        .replace("__DUB_URL__", json.dumps(eff_dub or ""))
        .replace("__SID__", json.dumps(sid or ""))
        .replace("__AUDIO_TRACKS__", json.dumps(audio_tracks or []))
        .replace("__SUBTITLE_TRACKS__", json.dumps(subtitle_tracks or []))
        .replace("__EFFECTIVE_AUDIO_LABEL__", json.dumps(eff_audio_lbl))
        .replace("__BRIDGE_BASE__", json.dumps(bridge_base))
    )

    player_flex = "52 1 0" if options else "1"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_title} — Smart Download Preview</title>
    <style>
{_CSS}
    .player-container {{ flex: {player_flex}; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title-group">
            <span class="badge {plat_cls}">📺 {safe_platform}</span>
            <span id="badgeRes" class="badge badge-res">🎞️ {safe_quality}</span>
            {audio_badge}
            {sub_badge}
            <span class="title" title="{safe_title}">🎬 {safe_title}</span>
        </div>
        <div class="actions">
            <div style="display:flex;align-items:center;gap:6px;">
                <button id="muteBtn" class="btn" style="padding:4px 8px;" title="Mute / Unmute">🔊</button>
                <input type="range" id="volSlider" min="0" max="1" step="0.05" value="1" style="width:65px;accent-color:#38bdf8;cursor:pointer;" title="Volume">
            </div>
            <button id="toggleBtn" class="btn" onclick="togglePlayer()">🌐 Switch to Web Player</button>
        </div>
    </div>
    <div class="player-container">
        <video id="videoEl" src="{safe_stream}" controls autoplay playsinline style="display: {'block' if stream_url else 'none'};">
            {track_html}
        </video>
        <audio id="dubAudioEl" preload="auto" style="display: none;"></audio>
        <iframe id="iframeEl" src="{'about:blank' if stream_url else embed_src}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen style="display: {'none' if stream_url else 'block'};"></iframe>
    </div>
    {settings_html}
    <script>
{js_code}
    </script>
</body>
</html>
"""
