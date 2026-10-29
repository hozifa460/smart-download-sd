# Smart Download (SD) — Persistent AI Architecture & Dependency Map

> **Auto-generated and verified by `python scripts/update_arch_map.py`**.
> This document provides the complete, authoritative architectural layout, mixin hierarchy,
> data flow graph, and file-by-file inventory of Smart Download (SD). Read this file at the start
> of every session to immediately navigate the codebase without guessing.

---

## 1. ⚠️ Strict Agent Workflow Rules (CRITICAL)

1. **NEVER run `PyInstaller` or `build_installer.py` automatically after code edits!**
   - Compiling `.exe` binaries takes 3–5 minutes and is **strictly forbidden** during routine edits.
   - Only build the installer if the user explicitly types: `"build installer"` or `"ابنِ المثبت"`.

2. **Fast Unit Verification Only (<2 seconds)**:
   - After editing a module, ONLY run the single test file relevant to that module:
     - e.g., `python -m unittest tests/test_updater.py` (finishes in ~3s).
     - e.g., `python -m unittest tests/test_stage4_srp_decomposition.py` (finishes in 0.01s).
   - Do NOT run the full test suite after small edits unless requested.

3. **Strict Single Responsibility Principle (<550 lines per file)**:
   - Every file in `src/smart_download/` must remain under **550 physical lines**.
   - If adding logic causes a file to approach 550 lines, decompose it into a specialized mixin or helper module.

4. **Zero-Rebuild Core Hot-Patch Workflow**:
   - Core application edits do NOT require rebuilding `SmartDownload.exe`.
   - For local development: Set `SD_DEV_SRC` or run `SmartDownload.exe` adjacent to `src/` to load code directly.
   - For remote distribution: Run `python -c "from updater import build_core_patch_zip; build_core_patch_zip('dist/SmartDownload-CorePatch.zip')"` to produce a ~120 KB hot-patch in <0.5 seconds.

5. **Architecture Synchronization**:
   - Whenever a file, class, or method is added, deleted, or moved, execute:
     ```bash
     python scripts/update_arch_map.py
     ```
     to ensure `GEMINI.md` and `AGENTS.md` remain 100% synchronized.

---

## 2. 🏛️ Class Inheritance & Connection Graph

### A. ModernFramelessGUI Mixin Inheritance Hierarchy
`ModernFramelessGUI` in `src/smart_download/ui/main_window.py` is composed of 22 specialized mixins:

```text
ModernFramelessGUI (tk.Tk root)
├── BrowserSettingsModalMixin (ui/modals/browser_settings_modal.py)
│   └── BrowserControllerMixin (ui/controllers/browser_controller.py)
├── HistoryPanelMixin (ui/panels/history_panel.py)
├── ChunksPanelMixin (ui/panels/chunks_panel.py)
│   └── MetricsPanelMixin (ui/panels/metrics_panel.py)
├── InputsPanelMixin (ui/panels/inputs_panel.py)
│   └── ControlsPanelMixin (ui/panels/controls_panel.py)
├── ClipboardControllerMixin (ui/controllers/clipboard_controller.py)
├── UpdateControllerMixin (ui/controllers/update_controller.py)
│   └── ToastControllerMixin (ui/controllers/toast_controller.py)
├── DownloadControllerMixin (ui/controllers/download_controller.py)
│   └── MediaDownloadControllerMixin (ui/controllers/media_download_controller.py)
│       ├── YouTubeDownloadControllerMixin (ui/controllers/youtube_download_controller.py)
│       ├── BatchDownloadControllerMixin (ui/controllers/batch_download_controller.py)
│       └── LinkRefreshControllerMixin (ui/controllers/link_refresh_controller.py)
├── SettingsControllerMixin (ui/controllers/settings_controller.py)
│   ├── LocaleControllerMixin (ui/controllers/locale_controller.py)
│   └── SpeedLimiterControllerMixin (ui/controllers/speed_limiter_controller.py)
└── WindowChromeMixin (ui/controllers/window_controller.py)
    ├── ThemeControllerMixin (ui/controllers/theme_controller.py)
    ├── DispatchControllerMixin (ui/controllers/dispatch_controller.py)
    └── WindowLifecycleMixin (ui/controllers/lifecycle_controller.py)
        └── DialogControllerMixin (ui/controllers/dialog_controller.py)
```

### B. TurboDownloadEngine & YouTubeResolver Hierarchy

```text
EngineResumerMixin (core/engine_resumer.py)
└── EngineWorkersMixin (core/engine_workers.py)
    └── TurboDownloadEngine (core/engine.py) + EnginePersistenceMixin (core/engine_persistence.py)

YouTubeFormatBuilderMixin (services/youtube_format_builder.py)
└── YouTubeResolver (services/youtube_service.py) -> alias MediaResolver
```

### C. Data & Event Flow Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│ Browser Extension (Chrome / Edge / Brave / Opera)           │
└──────────────┬──────────────────────────────┬───────────────┘
               │ (stdio length-prefixed)      │ (HTTP POST port 9654)
               ▼                              ▼
  services/browser/native_host.py   services/browser/bridge_server.py
               │                              │
               └──────────────┬───────────────┘
                              ▼
              ui/controllers/browser_controller.py
                              │ (dispatch_to_main_thread)
                              ▼
              ui/controllers/download_controller.py
                     │                     │
         [Media / YouTube URL]        [Direct File URL]
                     ▼                     ▼
          services/youtube_service.py     core/engine.py
          (MediaResolver / yt-dlp)       (TurboDownloadEngine)
                     │                     │
                     ▼                     │
          core/stream_coordinator.py       │
          (FFmpeg Audio+Video Merge)       │
                     │                     │
                     └──────────┬──────────┘
                                ▼
               Real-time UI Event Dispatchers:
               - ui/panels/metrics_panel.py (Speed, Size, ETA, Threads)
               - ui/panels/chunks_panel.py (Visual Segment Map)
               - ui/panels/history_panel.py (Persistent Record)
               - ui/system_tray.py (Status tooltip & toasts)
```

---

## 3. 📂 Complete File-by-File Inventory & Responsibility Table

| File Path | Lines | Responsibility | Key Classes / Functions | When to Edit |
|:---|:---:|:---|:---|:---|
| `src/smart_download/__init__.py` | 57 | Package initialization and unified namespace re-exports for the core application. | — | Edit when exposing new subpackages or top-level public APIs. |
| `src/smart_download/config.py` | 238 | Configuration constants, path resolvers, and settings file I/O with caching. | `get_resource_path()`, `is_test_environment()`, `get_config_dir()` | Edit when modifying app constants, version, default settings, or storage directories. |
| `src/smart_download/i18n.py` | 18 | Backward-compatible i18n import shim redirecting to locales.i18n. | — | Edit if re-exporting additional translation functions. |
| `src/smart_download/main.py` | 25 | Main runtime GUI entry point initializing Tkinter and launching ModernFramelessGUI. | — | Edit when altering CLI argument parsing at launch or main window instantiation. |
| `src/smart_download/core/__init__.py` | 32 | Re-exports core download engine, chunking, and candidate resolution components. | — | Edit when adding new core download engine modules. |
| `src/smart_download/core/candidate_extractor.py` | 386 | HTML link extraction using regex patterns and HTML link candidate parsers. | `_HtmlCandidateExtractor`, `resolve_all_download_candidates()` | Edit when updating candidate download link parsing patterns from HTML documents. |
| `src/smart_download/core/chunk.py` | 69 | DownloadChunk data class, per-chunk thread state, and permissive SSL context helper. | `DownloadChunk`, `get_permissive_ssl_context()` | Edit when changing per-chunk data structures or SSL verification policies. |
| `src/smart_download/core/engine.py` | 540 | TurboDownloadEngine coordinating multi-threaded chunked downloads and rate limiting. | `TurboDownloadEngine` | Edit when altering download orchestration, speed monitoring, or thread lifecycle. |
| `src/smart_download/core/engine_persistence.py` | 285 | State persistence mixin saving and resuming partial download progress via .sd_parts. | `EnginePersistenceMixin` | Edit when changing chunk serialization or resume manifest structure. |
| `src/smart_download/core/engine_resumer.py` | 122 | Engine resumer mixin validating server HTTP range support and multi-chunk compatibility. | `EngineResumerMixin` | Edit when modifying HTTP range probe logic or server capability checks. |
| `src/smart_download/core/engine_workers.py` | 392 | Engine worker pool mixin managing download streams and dynamic midpoint splitting. | `EngineWorkersMixin` | Edit when modifying parallel worker thread loops or dynamic chunk splitting rules. |
| `src/smart_download/core/history.py` | 308 | Persistent download history manager tracking completed and active download records. | `DownloadHistoryManager` | Edit when modifying history record schemas or history storage format. |
| `src/smart_download/core/html_resolver.py` | 519 | Resolves real download candidates from web pages and validates link refreshes. | `_HtmlLinkCandidateParser`, `clear_probe_cache()`, `resolve_real_download_url()`, `validate_refresh_url()` | Edit when improving download candidate probing or link refresh validation. |
| `src/smart_download/core/rate_limiter.py` | 78 | High-precision TokenBucketRateLimiter enforcing download bandwidth throttling. | `TokenBucketRateLimiter` | Edit when tuning speed limiter algorithms or bucket token replenishment. |
| `src/smart_download/core/stream_coordinator.py` | 546 | StreamDownloadCoordinator managing streaming media downloads and FFmpeg audio/video merges. | `StreamDownloadCoordinator` | Edit when altering streaming downloads or post-processing merging steps. |
| `src/smart_download/installer/__init__.py` | 85 | Installer package re-exports for setup wizard and ops. | — | Edit when changing public installer API interfaces. |
| `src/smart_download/installer/installer_gui.py` | 363 | Modern themed Tkinter wizard UI for installing Smart Download. | `InstallerGUI` | Edit when altering installer wizard steps, styling, or setup progress display. |
| `src/smart_download/installer/installer_ops.py` | 529 | File deployment, shortcut creation, and payload extraction for Windows installation. | `get_default_install_dir()`, `get_desktop_dir()`, `get_start_menu_programs_dir()` | Edit when modifying installation payload extraction or uninstaller creation. |
| `src/smart_download/installer/installer_registry.py` | 315 | Windows Registry manipulation for Add/Remove Programs and startup entries. | `get_startup_dir()`, `enable_high_dpi_awareness()`, `create_windows_shortcut()` | Edit when changing registry keys for uninstallers or file associations. |
| `src/smart_download/locales/__init__.py` | 15 | Locales package re-exports. | — | Edit when modifying locales package exports. |
| `src/smart_download/locales/ar.json` | 302 | Complete Arabic application translations and right-to-left localized string dictionary. | — | Edit when adding or updating Arabic translation strings. |
| `src/smart_download/locales/en.json` | 302 | Complete English application translations and UI text string dictionary. | — | Edit when adding or updating English translation strings. |
| `src/smart_download/locales/i18n.py` | 142 | Thread-safe LocalizationManager singleton enabling dynamic language toggles. | `LocalizationManager`, `_load_locale()`, `tr()`, `get_current_language()` | Edit when modifying translation loading or language notification callbacks. |
| `src/smart_download/services/__init__.py` | 193 | Services package namespace re-exports. | — | Edit when exposing new background or platform service modules. |
| `src/smart_download/services/core_patch_updater.py` | 513 | OTA hot-patch packager, atomic updater, and dynamic core loader (zero-rebuild workflow). | `_ExternalCoreFinder`, `CoreHotPatchUpdater`, `get_core_plugin_dir()`, `is_version_ge()`, `build_core_patch_zip()` | Edit when modifying core patch packaging, plugin extraction, or dev source overriding. |
| `src/smart_download/services/preview_stream_bridge.py` | 531 | Built-In In-Memory Preview & Control Bridge HTTP server and web API routing. | `PreviewSession`, `PreviewBridgeRequestHandler`, `start_preview_bridge()`, `get_preview_bridge_port()`, `register_preview_session()` | Edit when modifying in-app preview HTTP bridge or web player controls. |
| `src/smart_download/services/preview_stream_proxy.py` | 137 | Streaming media proxy and VTT subtitle compiler for real-time video previewing. | `stream_upstream_media()`, `compile_and_serve_vtt()` | Edit when changing upstream byte-range streaming proxy or VTT subtitle generation. |
| `src/smart_download/services/single_instance.py` | 52 | Single application instance enforcement using Windows named mutex or loopback socket. | `notify_running_instance()` | Edit when altering inter-instance signaling or command line forwarding. |
| `src/smart_download/services/startup_service.py` | 432 | Zero-elevation Windows auto-start via Run key, Task Scheduler, and Startup folder. | `get_installed_exe_path()`, `get_startup_folder()`, `get_startup_command()` | Edit when altering Windows background startup mechanisms or startup entry checks. |
| `src/smart_download/services/subtitle_downloader.py` | 412 | Subtitle downloading, VTT/XML/JSON parsing, GTX translation, and SRT persistence. | `convert_vtt_to_srt()`, `download_subtitle_as_srt()` | Edit when modifying subtitle fetching, timedtext parsing, or auto-translation fallbacks. |
| `src/smart_download/services/subtitle_processor.py` | 437 | Subtitle processing, VTT-to-SRT conversion, FFmpeg soft-muxing, and frame burn-in delivery modes. | `strip_burn_tag_from_filename()`, `embed_subtitle_into_mp4()`, `burn_subtitle_into_video()` | Edit when modifying subtitle delivery modes (srt_only, soft_embed, hard_burn) or FFmpeg subtitle embedding. |
| `src/smart_download/services/updater_service.py` | 497 | Application auto-update manager querying GitHub Releases and launching upgrade installers. | `AppAutoUpdater`, `get_app_data_dir()`, `get_ytdlp_plugin_dir()`, `parse_version()` | Edit when modifying GitHub release querying or update downloading mechanisms. |
| `src/smart_download/services/youtube_format_builder.py` | 518 | Formats video resolution options, audio bitrates, and file size estimates from metadata. | `YouTubeFormatBuilderMixin` | Edit when modifying YouTube/social media format extraction or presentation. |
| `src/smart_download/services/youtube_models.py` | 494 | Data classes and URL regex patterns for YouTube and social media platforms. | `VideoFormatOption`, `YouTubeStreamInfo`, `detect_installed_cookie_browsers()`, `is_youtube_url()`, `is_social_media_url()` | Edit when updating social media domain patterns or stream metadata models. |
| `src/smart_download/services/youtube_resolver.py` | 30 | Backward-compatibility alias re-exporting YouTube and media resolver interfaces. | — | Edit if re-exporting new streaming resolver functions. |
| `src/smart_download/services/youtube_service.py` | 547 | High-level YouTubeResolver and MediaResolver coordinating yt-dlp and FFmpeg. | `YouTubeResolver` | Edit when changing media stream extraction, cookie passing, or FFmpeg merging. |
| `src/smart_download/services/youtube_tracks.py` | 506 | YouTube audio dubbing and subtitle tracks extraction, language mapping, and UI track selectors. | `extract_audio_tracks()`, `extract_subtitle_tracks()`, `build_audio_subtitle_row()` | Edit when modifying audio dubbing languages, subtitle tracks parsing, or quality modal track selectors. |
| `src/smart_download/services/ytdlp_updater.py` | 523 | YtDlpAutoUpdater managing dynamic in-process yt-dlp package updates in %APPDATA%. | `_ExternalYtDlpFinder`, `YtDlpAutoUpdater` | Edit when changing yt-dlp PyPI/GitHub download logic or sys.meta_path finder hooks. |
| `src/smart_download/services/browser/__init__.py` | 62 | Browser integration package exports. | — | Edit when modifying browser service exports. |
| `src/smart_download/services/browser/bridge_server.py` | 363 | Local HTTP bridge server receiving intercepted links from browser extensions. | `ThreadedHTTPServer`, `BrowserBridgeHandler`, `BrowserBridgeServer` | Edit when altering HTTP endpoints or ports for extension communication. |
| `src/smart_download/services/browser/host_manifest.py` | 243 | Generates native messaging host manifest JSON files for Chrome and Edge. | `compute_unpacked_extension_id()`, `get_project_root()`, `get_default_extension_origins()` | Edit when updating extension IDs or native messaging manifest schemas. |
| `src/smart_download/services/browser/native_host.py` | 211 | Native messaging host stdio protocol handler reading 32-bit length-prefixed messages. | `get_binary_stdin()`, `get_binary_stdout()`, `read_message()` | Edit when modifying browser extension stdio communication. |
| `src/smart_download/services/browser/registry.py` | 519 | Windows Registry manager configuring native messaging host entries for Chrome/Edge. | `register_browser_extensions()`, `unregister_browser_extensions()`, `is_extension_registered()` | Edit when changing registry paths or browser integration verification logic. |
| `src/smart_download/ui/__init__.py` | 45 | UI package exports. | — | Edit when exposing new UI components or windows. |
| `src/smart_download/ui/main_window.py` | 526 | ModernFramelessGUI main application window aggregating all panel and controller mixins. | `ModernFramelessGUI`, `main()` | Edit when adding or removing window-level mixins or altering root layout. |
| `src/smart_download/ui/system_tray.py` | 253 | Windows system tray integration (pystray) with minimize/restore and context menus. | `SystemTrayManager` | Edit when modifying system tray icon behavior or menu options. |
| `src/smart_download/ui/components/__init__.py` | 4 | Reusable UI components package exports. | — | Edit when exposing new UI components. |
| `src/smart_download/ui/components/base_modal.py` | 331 | SafeModalDialog: non-blocking frameless themed modal dialog base class. | `SafeModalDialog` | Edit when modifying modal dialog styling, backdrop, or grab behavior. |
| `src/smart_download/ui/components/tooltip.py` | 104 | Hover tooltip widget providing contextual explanations for buttons and controls. | `ToolTip` | Edit when changing tooltip styling, delay timings, or positioning. |
| `src/smart_download/ui/controllers/__init__.py` | 41 | Controllers package exports. | — | Edit when adding new controller mixins. |
| `src/smart_download/ui/controllers/batch_download_controller.py` | 83 | BatchDownloadControllerMixin managing multiple download candidates selection and queueing. | `BatchDownloadControllerMixin` | Edit when modifying batch link selection or sequential download triggers. |
| `src/smart_download/ui/controllers/browser_controller.py` | 143 | BrowserControllerMixin handling background extension registration and intercepted downloads. | `BrowserControllerMixin` | Edit when modifying intercepted browser link handling in the GUI. |
| `src/smart_download/ui/controllers/clipboard_controller.py` | 542 | ClipboardControllerMixin sniffing clipboard for valid download and media URLs. | `ClipboardControllerMixin`, `get_url_sniffer_platform_key()` | Edit when modifying clipboard polling intervals, URL regexes, or sniffing logic. |
| `src/smart_download/ui/controllers/dialog_controller.py` | 171 | DialogControllerMixin providing thread-safe non-blocking modal dialogs. | `DialogControllerMixin` | Edit when modifying safe error, warning, or confirmation dialog dispatching. |
| `src/smart_download/ui/controllers/dispatch_controller.py` | 71 | DispatchControllerMixin dispatching background thread tasks safely to Tkinter event loop. | `DispatchControllerMixin` | Edit when changing thread synchronization or GUI queue processing. |
| `src/smart_download/ui/controllers/download_controller.py` | 542 | DownloadControllerMixin coordinating download start, engine creation, and queue execution. | `DownloadControllerMixin` | Edit when modifying download trigger flow or engine callback wiring. |
| `src/smart_download/ui/controllers/lifecycle_controller.py` | 284 | WindowLifecycleMixin managing resource cleanup, tray minimization, and clean exit. | `WindowLifecycleMixin` | Edit when modifying window close actions, thread cleanup, or tray exit. |
| `src/smart_download/ui/controllers/link_refresh_controller.py` | 97 | LinkRefreshControllerMixin handling expired download link resumption and URL substitution. | `LinkRefreshControllerMixin` | Edit when altering expired link substitution or refresh dialog triggers. |
| `src/smart_download/ui/controllers/locale_controller.py` | 219 | LocaleControllerMixin coordinating dynamic UI text re-translation upon language switch. | `LocaleControllerMixin` | Edit when adding dynamic language switch observers or RTL layout adjustments. |
| `src/smart_download/ui/controllers/media_download_controller.py` | 23 | MediaDownloadControllerMixin composite mixin aggregating YouTube, batch, and refresh. | `MediaDownloadControllerMixin` | Edit when altering composite media controller inheritance. |
| `src/smart_download/ui/controllers/settings_controller.py` | 335 | SettingsControllerMixin managing user preferences, cookies, and auto-categorization. | `SettingsControllerMixin` | Edit when adding new user preference toggles or cookies browser selection. |
| `src/smart_download/ui/controllers/speed_limiter_controller.py` | 179 | SpeedLimiterControllerMixin managing speed presets, slider events, and rate limits. | `SpeedLimiterControllerMixin` | Edit when modifying speed limiter presets or live slider adjustment handlers. |
| `src/smart_download/ui/controllers/theme_controller.py` | 218 | ThemeControllerMixin configuring dark theme color tokens and UI styling. | `ThemeControllerMixin` | Edit when changing application colors, fonts, or styling variables. |
| `src/smart_download/ui/controllers/toast_controller.py` | 173 | ToastControllerMixin presenting non-blocking corner toast notifications. | `ToastControllerMixin` | Edit when modifying startup welcome toast or notification toast animations. |
| `src/smart_download/ui/controllers/update_controller.py` | 170 | UpdateControllerMixin running background checks for app and yt-dlp updates. | `UpdateControllerMixin` | Edit when changing background update check frequency or update notification dialogs. |
| `src/smart_download/ui/controllers/window_controller.py` | 543 | WindowChromeMixin managing custom frameless title bar dragging and window controls. | `WindowChromeMixin` | Edit when modifying custom title bar widgets, drag handling, or window geometry. |
| `src/smart_download/ui/controllers/youtube_download_controller.py` | 420 | YouTubeDownloadControllerMixin analyzing streaming media formats and quality selection. | `YouTubeDownloadControllerMixin` | Edit when modifying YouTube/social media format inspection and dialog invocation. |
| `src/smart_download/ui/modals/__init__.py` | 32 | Modals package exports. | — | Edit when adding new modal dialog exports. |
| `src/smart_download/ui/modals/browser_settings_modal.py` | 544 | BrowserSettingsModalMixin displaying browser extension setup and diagnostic dialog. | `BrowserSettingsModalMixin` | Edit when modifying browser extension configuration instructions or diagnostic steps. |
| `src/smart_download/ui/modals/candidates_modal.py` | 482 | MultipleCandidatesModal displaying detected web download candidates with filter badges. | `MultipleCandidatesModal` | Edit when modifying candidate dialog multi-selection, search, or filtering controls. |
| `src/smart_download/ui/modals/confirm_modal.py` | 549 | DownloadConfirmationModal showing probed file details before starting download. | `DownloadConfirmationModal` | Edit when changing pre-download confirmation dialog layout or field editing. |
| `src/smart_download/ui/modals/confirm_modal_logic.py` | 546 | Logic helper probing download candidate metadata for the confirmation modal. | `ConfirmModalLogicMixin` | Edit when modifying candidate probing threads or URL validation. |
| `src/smart_download/ui/modals/fetching_toast.py` | 387 | FetchingLinkToast displaying a loading spinner toast during link inspection. | `FetchingLinkToast` | Edit when modifying link resolving loading animation or cancel triggers. |
| `src/smart_download/ui/modals/preview_html_builder.py` | 540 | Unified VidMate-Style HTML5 Preview & Download Settings Builder (preview_html_builder.py). | `generate_preview_html()` | Edit when modifying this module's features. |
| `src/smart_download/ui/modals/quality_modal.py` | 545 | QualitySelectionModal presenting video resolutions and audio bitrates for media. | `QualitySelectionModal` | Edit when modifying media format selection dialog, badges, or treeview. |
| `src/smart_download/ui/modals/quality_modal_helpers.py` | 276 | Helper functions and banner builder for QualitySelectionModal (quality_modal_helpers.py). | `attach_selected_tracks_to_option()`, `resolve_final_dest()`, `build_preview_header_banner()` | Edit when modifying this module's features. |
| `src/smart_download/ui/modals/refresh_modal.py` | 490 | RefreshLinkModal prompting for updated download link when a session expires. | `RefreshLinkModal` | Edit when changing expired link substitution dialog styling or URL validation. |
| `src/smart_download/ui/modals/settings_modal.py` | 546 | SettingsModal: Frameless dark application settings dialog with per-platform sniffer filtering. | `SettingsModal` | Edit when modifying this module's features. |
| `src/smart_download/ui/modals/toasts.py` | 10 | Re-exports toast notification classes for convenient imports. | — | Edit when exposing additional toast classes. |
| `src/smart_download/ui/modals/update_modal.py` | 365 | AppUpdateModal displaying new release notes and one-click update actions. | `AppUpdateModal` | Edit when modifying application update presentation or release notes formatting. |
| `src/smart_download/ui/modals/video_preview_modal.py` | 316 | VidMate-style in-app video preview modal with live WebVTT subtitles and chromeless player. | `open_video_preview()` | Edit when modifying video preview playback, WebVTT subtitle overlay, or player window launcher. |
| `src/smart_download/ui/modals/welcome_toast.py` | 287 | StartupWelcomeToast displaying Windows startup greeting when running minimized. | `StartupWelcomeToast` | Edit when modifying startup toast layout or click-to-restore action. |
| `src/smart_download/ui/panels/__init__.py` | 18 | Panels package exports. | — | Edit when adding new panel mixin exports. |
| `src/smart_download/ui/panels/chunks_panel.py` | 520 | ChunksPanelMixin rendering segmented dynamic chunk visualizer and status table. | `ChunksPanelMixin` | Edit when modifying segmented chunk canvas graphics or chunk details treeview. |
| `src/smart_download/ui/panels/controls_panel.py` | 426 | ControlsPanelMixin rendering thread selector, speed limiter controls, and action buttons. | `_StateButton`, `ControlsPanelMixin` | Edit when changing start/pause/cancel action buttons or limiter controls. |
| `src/smart_download/ui/panels/history_panel.py` | 287 | HistoryPanelMixin managing download history table and right-click context menu. | `HistoryPanelMixin` | Edit when modifying history treeview columns or context menu actions. |
| `src/smart_download/ui/panels/inputs_panel.py` | 186 | InputsPanelMixin rendering URL and destination inputs with auto-categorization button. | `InputsPanelMixin` | Edit when modifying URL entry, destination browse button, or auto-cat toggle. |
| `src/smart_download/ui/panels/media_options_bar.py` | 545 | MediaOptionsBarMixin: Main-window media format, dubbing audio, and subtitle options bar. | `MediaOptionsBarMixin` | Edit when modifying this module's features. |
| `src/smart_download/ui/panels/metrics_panel.py` | 99 | MetricsPanelMixin rendering overall progress bar and real-time metric cards. | `MetricsPanelMixin` | Edit when modifying speed, size, ETA, or thread count metric cards. |
| `src/smart_download/utils/__init__.py` | 74 | Utils package exports. | — | Edit when exporting new utility helpers. |
| `src/smart_download/utils/archive_utils.py` | 139 | Archive auto-extraction and SHA-256 file integrity verification. | `calculate_file_integrity()`, `auto_unpack_archive()` | Edit when supporting new archive formats or hash algorithms. |
| `src/smart_download/utils/clipboard.py` | 75 | Cross-platform and Win32 direct clipboard text retrieval. | `get_clipboard_text()` | Edit when improving clipboard access reliability on Windows. |
| `src/smart_download/utils/dpi.py` | 83 | Windows High-DPI awareness initialization and screen work area geometry. | `enable_high_dpi_awareness()`, `get_windows_work_area()` | Edit when tuning DPI scaling factors or multi-monitor geometry detection. |
| `src/smart_download/utils/file_ops.py` | 254 | File categorization into subfolders (Videos, Music, etc.) and file/folder launching. | `get_file_category_and_icon()`, `resolve_categorized_path()`, `open_downloaded_file()` | Edit when modifying category subfolder mappings or OS shell execute actions. |
| `src/smart_download/utils/magic_detector.py` | 88 | Binary magic bytes detector determining actual file types independent of URL extensions. | `MagicBytesDetector` | Edit when adding new file signature definitions. |
| `src/smart_download/utils/speed_utils.py` | 91 | Speed string parsing (e.g. '1.5 MB/s') and human-readable formatting. | `parse_speed_limit()`, `format_speed()` | Edit when updating speed parsing regexes or unit formats. |
| `src/smart_download/utils/tk_helpers.py` | 397 | Tkinter resource cleanup preventing photo reference and callback memory leaks. | `animate_window_open()`, `animate_window_close()` | Edit when adding memory leak mitigations for Tkinter widgets. |
| `src/smart_download/utils/url_utils.py` | 393 | URL parsing, filename derivation, and Content-Disposition header extraction. | `is_downloadable_url()`, `clean_download_filename()`, `derive_download_filename()` | Edit when improving filename derivation from complex redirect URLs. |
| `turbo_downloader.py` | 315 | Backward-compatibility root entry point and complete symbol re-exporter. | `_TurboDownloaderShim` | Edit when updating backward-compatible top-level exports or entry hooks. |
| `browser_bridge.py` | 24 | Backward-compatibility root shim re-exporting BrowserBridgeServer. | — | Edit when changing browser bridge root exports. |
| `native_messaging_host.py` | 29 | Backward-compatibility root shim re-exporting native messaging host functions. | — | Edit when updating native messaging entry point. |
| `register_browser.py` | 37 | Backward-compatibility root shim for browser extension registration commands. | — | Edit when updating browser registration CLI entry point. |
| `updater.py` | 48 | Backward-compatibility root shim re-exporting AppAutoUpdater and CoreHotPatchUpdater. | — | Edit when adding top-level updater exports. |
| `youtube_resolver.py` | 65 | Backward-compatibility root shim re-exporting YouTube and media resolver interfaces. | `_YouTubeResolverShim` | Edit when updating YouTube resolver root exports. |
| `release_publisher.py` | 272 | Automated GitHub Releases publisher supporting fast zero-rebuild core patch publishing. | `log()`, `get_git_credentials()`, `api_request()` | Edit when modifying release publishing workflow or asset upload logic. |
| `build_installer.py` | 358 | Automated build script compiling PyInstaller bundles and Windows setup installer. | `clean_stale_shadow_modules()`, `verify_exe_startup()`, `clean_stale_dist_artifacts()` | Edit ONLY when user explicitly commands 'build installer' or 'ابنِ المثبت'. |
| `installer.py` | 118 | Standalone installer runner executing SmartDownload setup wizard. | `_InstallerShim`, `main()` | Edit when modifying standalone installer CLI options. |
| `tests/__init__.py` | 11 | Tests package initialization. | — | Edit when configuring test discovery fixtures. |
| `tests/test_browser.py` | 631 | Unit tests for browser extension bridge, native host stdio, and Windows registry. | `TestBrowserBridgeServer`, `TestBrowserBridgeConcurrency`, `TestExtensionManifestAndAssets`, `TestNativeMessagingHostProtocol`, `TestBrowserRegistryIntegration`, `setUpModule()`, `tearDownModule()` | Edit when adding tests for browser integration features. |
| `tests/test_bugfixes.py` | 3004 | Automated unit and integration tests for Part 1 (Subtitle Hard-Burn fixes & GTX translation fallback) | `TestSubtitleProcessorAndGTXFallback`, `TestVideoPreviewModal`, `TestHardenedFFmpeg`, `TestPreviewStreamBridgeAndUnifiedVidMatePlayer`, `TestPart1To4CriticalBugfixes`, `TestWindowMaximizeAndTikTokDirectFixes`, `TestGeometryAndSanitizationAndTikTokDeduplication`, `TestClipboardPlatformFilteringAndSettings`, `TestMainToolbarCleanup` | Edit when modifying this module's features. |
| `tests/test_concurrent_redownload_and_tags.py` | 501 | Unit tests verifying concurrent re-download path uniqueness, | `TestConcurrentRedownloadAndTags` | Edit when modifying this module's features. |
| `tests/test_core_patch_updater.py` | 420 | Unit tests for CoreHotPatchUpdater, packaging, rollback, and dynamic loading. | `_MockStreamResp`, `TestCoreHotPatchAndZeroRebuildWorkflow` | Edit when testing OTA core hot-patching or zero-rebuild workflow. |
| `tests/test_dpi_and_assets.py` | 335 | Unit tests for Windows High-DPI scaling, icons, and asset resolution. | `TestDPIAndAssets`, `setUpModule()`, `tearDownModule()` | Edit when adding tests for display scaling or asset bundling. |
| `tests/test_engine_core.py` | 794 | Unit tests for TurboDownloadEngine, chunking, rate limiting, and worker pooling. | `MockServerHandler`, `TestTurboDownloader`, `TestSmartDownloadBrandingAndParts`, `setUpModule()`, `tearDownModule()` | Edit when testing download core algorithms and throttling. |
| `tests/test_engine_resume.py` | 485 | Unit tests for download pause, resume, and .sd_parts persistence. | `MockHeaderInspectHandler`, `TestEngineCustomHeaders`, `TestStreamCoordinatorIntegration`, `TestSmartDownloadPartsDirectory`, `TestHeadlessDecoupling`, `setUpModule()`, `tearDownModule()` | Edit when testing download resumption and manifest serialization. |
| `tests/test_html_candidates.py` | 825 | Unit tests for web page candidate link extraction and filtering. | `MockHtmlResolverHandler`, `TestHtmlLinkResolverAndStartupToast`, `MockMultiCandidateServer`, `TestMultipleDownloadCandidates`, `setUpModule()`, `tearDownModule()` | Edit when testing HTML candidate link discovery. |
| `tests/test_i18n.py` | 467 | Unit tests for Arabic and English translations and runtime language toggling. | `TestBilingualLocalization`, `setUpModule()`, `tearDownModule()` | Edit when adding i18n and localization test cases. |
| `tests/test_installer.py` | 681 | Unit tests for installer file extraction, registry keys, and shortcuts. | `TestWindowsInstallerLogic`, `TestStandaloneExeBuild`, `setUpModule()`, `tearDownModule()` | Edit when testing Windows installer operations. |
| `tests/test_main_window_actions.py` | 787 | Unit tests for main window user actions, queueing, and callbacks. | `TestClipboardNonBlockingInterception`, `TestClipboardSnifferAndUrlValidation`, `setUpModule()`, `tearDownModule()` | Edit when testing GUI button actions and download queueing. |
| `tests/test_main_window_ui.py` | 794 | Unit tests for main window UI structure, widget creation, and layout. | `TestBackgroundAndMinimizedLaunch`, `TestSystemTrayAndBackgroundMinimization`, `TestClipboardSequenceRecopying`, `TestBackgroundStartupNotificationAndTray`, `setUpModule()`, `tearDownModule()` | Edit when testing window geometry, cards, and widget hierarchies. |
| `tests/test_modals_confirm.py` | 783 | Unit tests for DownloadConfirmationModal and candidate size probing. | `TestTDMDownloadConfirmationDialog`, `TestTDMConfirmationAndStandaloneProgress`, `setUpModule()`, `tearDownModule()` | Edit when testing confirmation modal logic. |
| `tests/test_modals_other.py` | 744 | Unit tests for quality, refresh, browser settings, and toast modals. | `TestQualitySelectionModalGUI`, `TestInstantFetchingLinkToast`, `setUpModule()`, `tearDownModule()` | Edit when testing secondary modal dialogs and toasts. |
| `tests/test_settings_history.py` | 818 | Unit tests for settings persistence, auto-categorization, and history manager. | `TestWindowsStartupRegistryIntegration`, `TestDownloadHistoryAndCategorization`, `setUpModule()`, `tearDownModule()` | Edit when testing preferences and download history operations. |
| `tests/test_stage4_srp_decomposition.py` | 345 | Unit tests verifying strict SRP decomposition (<550 lines per file). | `TestUIControllersSRP`, `TestUIPanelsSRP`, `TestCoreAndUtilsSRP` | Edit when adding new decomposed modules to verify strict line limits. |
| `tests/test_stage6_performance.py` | 263 | Unit test suite verifying Stage 6: Ultra-Performance, Low-Latency & High-Throughput Optimization. | `TestStage6PerformanceOptimizations` | Edit when modifying this module's features. |
| `tests/test_stage7_security_stress.py` | 468 | Unit and stress test suite verifying Stage 7: Enterprise Security Hardening & Heavy Stress Resilience. | `TestZipTarSlipSecurity`, `TestBridgeServerOriginCSRFSecurity`, `TestFilenameSanitizationAndWindowsReserved`, `TestFileRedirectSchemeSecurity`, `TestStressAndHeavyLoadResilience` | Edit when modifying this module's features. |
| `tests/test_stage8_2_live_ux.py` | 402 | Live Tkinter GUI Verification for Stage 8.2 UX & Window Lifecycle Overhaul. | `TestStage82LiveUX` | Edit when modifying this module's features. |
| `tests/test_stage8_dubbing_subtitles.py` | 732 | Unit tests for Stage 8: YouTube Multi-Language Audio Dubbing & Subtitle Selection/Embedding. | `DummyBuilder`, `TestYouTubeTracks` | Edit when modifying this module's features. |
| `tests/test_stage9_1_and_10_e2e.py` | 260 | Comprehensive Unit & E2E Verification for Smart Download Stages 9.1 & 10. | `TestStage9_1_And_10_Verification` | Edit when modifying this module's features. |
| `tests/test_stage9_2_stabilization.py` | 326 | Comprehensive verification test suite for Stage 9.2: | `TestStage9_2Stabilization` | Edit when modifying this module's features. |
| `tests/test_stage9_runtime_fixes.py` | 597 | Unit and integration tests for Stage 9: Comprehensive Runtime & UX Overhaul. | `TestSubtitleConversionStage9`, `TestBurnSubtitleEncodingAndPaths`, `TestStreamCoordinatorMultiThreading`, `DummyMockApp`, `TestOpenInMainAppAndMediaOptionsBar`, `TestFetchingToastSafety`, `TestSubtitleAutoSelection`, `TestHistoryRedownloadQuality` | Edit when modifying this module's features. |
| `tests/test_updater.py` | 540 | Unit tests for AppAutoUpdater, YtDlpAutoUpdater, and version unification. | `_MockHttpResp`, `TestVersionComparisonAndUnification`, `TestYtDlpAutoUpdater`, `TestAppAutoUpdaterAndModal` | Edit when testing app/yt-dlp auto-updates or version comparison. |
| `tests/test_url_resolver.py` | 725 | Unit tests for URL utilities, filename sanitization, and speed formatting. | `MockRefreshLinkServerHandler`, `TestRefreshExpiredLinks`, `TestSpeedFormatting`, `setUpModule()`, `tearDownModule()` | Edit when testing URL manipulation and parsing utilities. |
| `tests/test_visual_defects_fix.py` | 289 | Unit tests for visual defects fix: | `TestVisualDefectsFix` | Edit when modifying this module's features. |
| `tests/test_youtube_extract.py` | 730 | Unit tests for YouTube and social media link extraction with yt-dlp. | `TestYouTubeDetectionAndSanitization`, `TestYouTubeResolver`, `TestSocialMediaDetectionAndSanitization`, `TestSocialMediaResolverAndExtraction`, `TestVideoQualityFormatExtraction`, `setUpModule()`, `tearDownModule()` | Edit when testing social media stream resolution. |
| `tests/test_youtube_merge.py` | 831 | Unit tests for FFmpeg video + audio stream merging and format building. | `TestYouTubeSafeConcurrencyAndErrorHandling`, `TestBrowserCookiesAndMP3Extraction`, `setUpModule()`, `tearDownModule()` | Edit when testing FFmpeg post-processing operations. |

---

## 4. ⚡ Verification Commands Cheat Sheet

| Task | Command | Typical Time |
|:---|:---|:---:|
| Verify OTA Core Hot-Patch | `python -m unittest tests/test_core_patch_updater.py` | ~0.5s |
| Verify App & Yt-Dlp Updater | `python -m unittest tests/test_updater.py` | ~3.5s |
| Verify Strict SRP Line Limits (<550) | `python -m unittest tests/test_stage4_srp_decomposition.py` | ~0.01s |
| Verify Architecture Map Sync | `python scripts/update_arch_map.py --check` | ~0.15s |
| Verify YouTube Extraction | `python -m unittest tests/test_youtube_extract.py` | ~1.5s |
| Verify Engine Resume & Persistence | `python -m unittest tests/test_engine_resume.py` | ~1.2s |
| Build Core Hot-Patch (~120 KB) | `python -c "from updater import build_core_patch_zip; build_core_patch_zip('dist/SmartDownload-CorePatch.zip')"` | <0.5s |

*(Reminder: NEVER run PyInstaller or `build_installer.py` unless user explicitly commands: `build installer`)*
