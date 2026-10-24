"""
========================================================================================
🔄 AUTO-UPDATE ENGINE — Smart Download (SD) & yt-dlp Dynamic Plugin Updater
========================================================================================
Provides:
1. Unified application version constant (APP_VERSION = "2.0.0").
2. Semantic & date-based version parsing and comparison (parse_version, is_newer_version).
3. YtDlpAutoUpdater:
   - Allows frozen PyInstaller executables (SmartDownload.exe) to dynamically load and
     self-update yt-dlp in %APPDATA%\\SmartDownload\\yt_dlp_plugin without rebuilding.
   - Uses a custom sys.meta_path finder + sys.path[0] injection so updated extractors
     take precedence over the static bundled PyInstaller PYZ archive in-process.
   - Downloads official pure-Python wheel/zip archives from PyPI or GitHub Releases,
     performs safe atomic extraction with backup rollback, and falls back to the
     bundled yt_dlp if offline or if an update fails.
4. AppAutoUpdater:
   - Queries GitHub Releases API (https://api.github.com/repos/hozifa460/smart-download-sd/releases/latest).
   - Compares remote tag_name against APP_VERSION.
   - Downloads SmartDownload-Setup.exe with live byte progress and cancellation support.
   - Launches seamless silent or interactive upgrade.
========================================================================================
"""

import os
import re
import sys
import json
import time
import shutil
import ssl
import zipfile
import tempfile
import threading
import subprocess
import importlib
import importlib.abc
import importlib.machinery
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple, Callable, Any

APP_NAME = "Smart Download (SD)"
APP_ID = "SmartDownload"
APP_VERSION = "2.0.0"

GITHUB_REPO_OWNER = "hozifa460"
GITHUB_REPO_NAME = "smart-download-sd"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"

YTDLP_PYPI_JSON_API = "https://pypi.org/pypi/yt-dlp/json"
YTDLP_GITHUB_LATEST_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
YTDLP_GITHUB_RELEASES_API = YTDLP_GITHUB_LATEST_API


def get_app_data_dir() -> str:
    """Returns persistent application data directory (%APPDATA%\\SmartDownload on Windows)."""
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            cfg = os.path.join(appdata, APP_ID)
        else:
            cfg = os.path.join(os.path.expanduser("~"), ".smartdownload")
    else:
        cfg = os.path.join(os.path.expanduser("~"), ".smartdownload")
    try:
        os.makedirs(cfg, exist_ok=True)
    except Exception:
        pass
    return cfg


def get_ytdlp_plugin_dir(base_dir: Optional[str] = None) -> str:
    """Returns directory where external updated yt_dlp package is extracted."""
    root = base_dir if base_dir else get_app_data_dir()
    return os.path.join(root, "yt_dlp_plugin")


def _get_ssl_context() -> ssl.SSLContext:
    """Creates an SSL context for HTTPS update checks with fallback if certs are missing."""
    try:
        ctx = ssl.create_default_context()
        return ctx
    except Exception:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


def _get_verified_ssl_context() -> ssl.SSLContext:
    """Creates a strictly verified SSL context for secure application updates."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx
    except Exception:
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            return ctx
        except Exception:
            return ssl.create_default_context()


def parse_version(version_str: str) -> Tuple[int, ...]:
    """
    Parses a semantic or date-based version string (e.g. 'v2.1.0', '2.0.0', '2026.03.17')
    into a tuple of integers (e.g. (2, 1, 0), (2026, 3, 17)).
    Returns an empty tuple () if version_str is empty or invalid.
    """
    if not version_str or not isinstance(version_str, str):
        return ()
    cleaned = version_str.strip().lstrip("vV").strip()
    if not cleaned or cleaned.endswith("-") or cleaned.endswith("+"):
        return ()
    if "+" in cleaned:
        base_and_pre, build_meta = cleaned.split("+", 1)
        if not build_meta.strip():
            return ()
    else:
        base_and_pre = cleaned
    if "-" in base_and_pre:
        main_part, pre_part = base_and_pre.split("-", 1)
        if not pre_part.strip():
            return ()
    else:
        main_part = base_and_pre
    main_part = main_part.strip()
    if not main_part:
        return ()
    parts: List[int] = []
    for token in main_part.split("."):
        token_s = token.strip()
        m = re.match(r"^(\d+)$", token_s)
        if not m:
            return ()
        parts.append(int(m.group(1)))
    return tuple(parts)


def _compare_prerelease(pre_a: str, pre_b: str) -> int:
    """
    Compares two SemVer pre-release strings (e.g. 'alpha.10' vs 'alpha.2', 'rc10' vs 'rc2').
    Returns 1 if pre_a > pre_b, -1 if pre_a < pre_b, 0 if equal.
    """
    if pre_a == pre_b:
        return 0
    ids_a = [p.strip() for p in pre_a.split(".")]
    ids_b = [p.strip() for p in pre_b.split(".")]
    for tok_a, tok_b in zip(ids_a, ids_b):
        if tok_a == tok_b:
            continue
        a_is_num = tok_a.isdigit()
        b_is_num = tok_b.isdigit()
        if a_is_num and b_is_num:
            na, nb = int(tok_a), int(tok_b)
            if na != nb:
                return 1 if na > nb else -1
        elif a_is_num != b_is_num:
            # Per SemVer 2.0.0 section 11: numeric identifiers have lower precedence than non-numeric
            return -1 if a_is_num else 1
        else:
            # Natural comparison for combined alphanumeric tokens like 'rc10' vs 'rc2'
            chunks_a = [int(x) if x.isdigit() else x for x in re.findall(r"\d+|\D+", tok_a)]
            chunks_b = [int(x) if x.isdigit() else x for x in re.findall(r"\d+|\D+", tok_b)]
            for ca, cb in zip(chunks_a, chunks_b):
                if ca == cb:
                    continue
                if isinstance(ca, int) and isinstance(cb, int):
                    return 1 if ca > cb else -1
                sa, sb = str(ca), str(cb)
                if sa != sb:
                    return 1 if sa > sb else -1
            if len(chunks_a) != len(chunks_b):
                return 1 if len(chunks_a) > len(chunks_b) else -1
    if len(ids_a) != len(ids_b):
        return 1 if len(ids_a) > len(ids_b) else -1
    return 0


def is_newer_version(remote_ver: str, current_ver: str) -> bool:
    """
    Compares remote_ver against current_ver and returns True if remote_ver is strictly newer.
    Supports:
    - Semantic versions: 'v2.1.0' > '2.0.0', '2.0.1' > '2.0', '2.0.0' == 'v2.0.0'
    - Pre-release tags: '2.0.0' > '2.0.0-beta.1', '2.0.0-alpha.10' > '2.0.0-alpha.2'
    - Date-based versions (yt-dlp): '2026.03.17' > '2025.11.12'
    Returns False on empty, malformed, or equal versions.
    """
    if not remote_ver or not current_ver or not isinstance(remote_ver, str) or not isinstance(current_ver, str):
        return False
    r_tuple = parse_version(remote_ver)
    c_tuple = parse_version(current_ver)
    if not r_tuple or not c_tuple:
        return False

    max_len = max(len(r_tuple), len(c_tuple))
    r_padded = r_tuple + (0,) * (max_len - len(r_tuple))
    c_padded = c_tuple + (0,) * (max_len - len(c_tuple))
    if r_padded != c_padded:
        return r_padded > c_padded

    # Numeric components are equal; compare pre-release suffix (e.g. '2.0.0' vs '2.0.0-beta.1')
    r_clean = remote_ver.strip().lstrip("vV").strip().split("+", 1)[0]
    c_clean = current_ver.strip().lstrip("vV").strip().split("+", 1)[0]
    r_pre = r_clean.split("-", 1)[1].strip() if "-" in r_clean else ""
    c_pre = c_clean.split("-", 1)[1].strip() if "-" in c_clean else ""
    r_has_pre = bool(r_pre)
    c_has_pre = bool(c_pre)
    if c_has_pre and not r_has_pre:
        # Stable release is newer than pre-release of the same number
        return True
    if r_has_pre and not c_has_pre:
        # Pre-release is older than stable release of the same number
        return False
    if r_has_pre and c_has_pre:
        return _compare_prerelease(r_pre, c_pre) > 0
    return False


class _ExternalYtDlpFinder(importlib.abc.MetaPathFinder):
    """
    MetaPathFinder placed at sys.meta_path[0] to ensure an updated external yt_dlp
    package in %APPDATA%\\SmartDownload\\yt_dlp_plugin takes precedence over
    PyInstaller's PyiFrozenImporter when frozen as a standalone .exe.
    """

    def __init__(self, plugin_dir: str):
        self.plugin_dir = os.path.abspath(plugin_dir)

    def find_spec(self, fullname: str, path=None, target=None):
        if fullname != "yt_dlp" and not fullname.startswith("yt_dlp."):
            return None
        pkg_root = os.path.join(self.plugin_dir, "yt_dlp")
        if not os.path.isfile(os.path.join(pkg_root, "__init__.py")):
            return None
        try:
            if fullname == "yt_dlp":
                return importlib.machinery.PathFinder.find_spec(fullname, [self.plugin_dir], target)
            parts = fullname.split(".")
            parent_dir = os.path.join(self.plugin_dir, *parts[:-1])
            if os.path.isdir(parent_dir):
                return importlib.machinery.PathFinder.find_spec(fullname, [parent_dir], target)
        except Exception:
            return None
        return None


class YtDlpAutoUpdater:
    """
    Manages checking, downloading, atomically extracting, and dynamically activating
    the latest yt-dlp Python package inside %APPDATA%\\SmartDownload\\yt_dlp_plugin.
    """

    _lock = threading.RLock()

    def __init__(
        self,
        plugin_dir: Optional[str] = None,
        on_log: Optional[Callable[[str], None]] = None,
        timeout: int = 15
    ):
        self.plugin_dir = os.path.abspath(plugin_dir or get_ytdlp_plugin_dir())
        self.on_log = on_log
        self.timeout = max(3, int(timeout))

    def log(self, message: str):
        if self.on_log:
            try:
                self.on_log(message)
            except Exception:
                pass

    def is_plugin_valid(self, directory: Optional[str] = None) -> bool:
        """Checks whether the given directory contains a valid yt_dlp Python package."""
        target = os.path.abspath(directory or self.plugin_dir)
        pkg_dir = os.path.join(target, "yt_dlp")
        init_py = os.path.join(pkg_dir, "__init__.py")
        ver_py = os.path.join(pkg_dir, "version.py")
        extractor_py = os.path.join(pkg_dir, "extractor", "__init__.py")
        return os.path.isfile(init_py) and os.path.isfile(ver_py) and os.path.isfile(extractor_py)

    def get_plugin_version(self, directory: Optional[str] = None) -> Optional[str]:
        """Reads the yt-dlp version string from the external plugin directory without importing it."""
        target = os.path.abspath(directory or self.plugin_dir)
        ver_py = os.path.join(target, "yt_dlp", "version.py")
        if os.path.isfile(ver_py):
            try:
                with open(ver_py, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", content)
                if m:
                    return m.group(1).strip()
            except Exception:
                pass
        meta_file = os.path.join(target, "plugin_meta.json")
        if os.path.isfile(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                v = data.get("version")
                if v and isinstance(v, str):
                    return v.strip()
            except Exception:
                pass
        return None

    def get_current_version(self) -> str:
        """Returns the currently active yt-dlp version (from external plugin or bundled package)."""
        if self.is_plugin_valid():
            norm_plugin = os.path.normcase(self.plugin_dir)
            if any(os.path.normcase(os.path.abspath(p)) == norm_plugin for p in sys.path if p):
                p_ver = self.get_plugin_version()
                if p_ver:
                    return p_ver
        try:
            import yt_dlp
            return str(getattr(yt_dlp.version, "__version__", "0.0.0"))
        except Exception:
            p_ver = self.get_plugin_version()
            return p_ver if p_ver else "0.0.0"

    def activate_plugin(self, force: bool = False) -> bool:
        """
        Prepends self.plugin_dir to sys.path[0] and registers _ExternalYtDlpFinder on sys.meta_path[0],
        then reloads yt_dlp in-process. If loading fails, cleanly rolls back to bundled yt_dlp.
        """
        with self._lock:
            if not self.is_plugin_valid():
                return False

            plugin_ver = self.get_plugin_version()
            if not force and plugin_ver:
                # Check if currently loaded/bundled yt_dlp is strictly newer than the plugin on disk
                try:
                    import yt_dlp
                    cur_ver = str(getattr(yt_dlp.version, "__version__", ""))
                    if cur_ver and is_newer_version(cur_ver, plugin_ver):
                        self.log(f"[YTDLP] Bundled yt-dlp ({cur_ver}) is newer than plugin ({plugin_ver}); keeping bundled.")
                        return False
                except Exception:
                    pass

            norm_plugin = os.path.normcase(self.plugin_dir)
            # Clean existing occurrences in sys.path and insert at index 0
            sys.path[:] = [
                p for p in sys.path
                if not (p and os.path.normcase(os.path.abspath(p)) == norm_plugin)
            ]
            sys.path.insert(0, self.plugin_dir)

            # Register or update _ExternalYtDlpFinder at sys.meta_path[0]
            sys.meta_path[:] = [
                finder for finder in sys.meta_path
                if not isinstance(finder, _ExternalYtDlpFinder)
            ]
            sys.meta_path.insert(0, _ExternalYtDlpFinder(self.plugin_dir))

            # Evict cached yt_dlp modules so Python imports the updated package
            to_delete = [k for k in list(sys.modules.keys()) if k == "yt_dlp" or k.startswith("yt_dlp.")]
            saved_modules = {k: sys.modules.pop(k) for k in to_delete}

            # Reset extractor cache in youtube_resolver if loaded
            if "youtube_resolver" in sys.modules:
                try:
                    setattr(sys.modules["youtube_resolver"], "_YTDLP_EXTRACTORS_CACHE", None)
                except Exception:
                    pass

            try:
                mod = importlib.import_module("yt_dlp")
                importlib.import_module("yt_dlp.version")
                importlib.import_module("yt_dlp.extractor")
                loaded_file = os.path.normcase(os.path.abspath(getattr(mod, "__file__", "") or ""))
                if not loaded_file.startswith(norm_plugin):
                    raise RuntimeError(f"Loaded yt_dlp from {loaded_file} instead of plugin {self.plugin_dir}")
                return True
            except Exception as e:
                self.log(f"[YTDLP] Failed to activate external yt-dlp plugin ({e}); falling back to bundled yt-dlp.")
                # Remove broken plugin from sys.path and sys.meta_path
                sys.path[:] = [
                    p for p in sys.path
                    if not (p and os.path.normcase(os.path.abspath(p)) == norm_plugin)
                ]
                sys.meta_path[:] = [
                    finder for finder in sys.meta_path
                    if not isinstance(finder, _ExternalYtDlpFinder)
                ]
                for k in [m for m in list(sys.modules.keys()) if m == "yt_dlp" or m.startswith("yt_dlp.")]:
                    sys.modules.pop(k, None)
                sys.modules.update(saved_modules)
                return False

    def deactivate_plugin(self) -> None:
        """Removes external plugin hooks and restores bundled yt_dlp."""
        with self._lock:
            norm_plugin = os.path.normcase(self.plugin_dir)
            sys.path[:] = [
                p for p in sys.path
                if not (p and os.path.normcase(os.path.abspath(p)) == norm_plugin)
            ]
            sys.meta_path[:] = [
                finder for finder in sys.meta_path
                if not isinstance(finder, _ExternalYtDlpFinder)
            ]
            for k in [m for m in list(sys.modules.keys()) if m == "yt_dlp" or m.startswith("yt_dlp.")]:
                sys.modules.pop(k, None)
            if "youtube_resolver" in sys.modules:
                try:
                    setattr(sys.modules["youtube_resolver"], "_YTDLP_EXTRACTORS_CACHE", None)
                except Exception:
                    pass

    def check_for_update(self) -> Dict[str, Any]:
        """
        Queries PyPI JSON API (with fallback to GitHub Releases API) for the latest yt-dlp version.
        Never raises on network errors; returns a structured dict with 'success' and 'update_available'.
        """
        current_ver = self.get_current_version()
        headers = {
            "Accept": "application/json",
            "User-Agent": f"SmartDownload-Updater/{APP_VERSION}"
        }
        ctx = _get_ssl_context()

        # 1. Primary source: PyPI JSON API
        try:
            req = urllib.request.Request(YTDLP_PYPI_JSON_API, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            info = data.get("info", {})
            remote_ver = str(info.get("version") or "").strip()
            urls = data.get("urls", [])
            wheel_url = ""
            for u in urls:
                if isinstance(u, dict):
                    u_url = str(u.get("url") or "")
                    pkg_type = str(u.get("packagetype") or "")
                    if pkg_type == "bdist_wheel" or u_url.endswith(".whl"):
                        wheel_url = u_url
                        break
            if remote_ver and wheel_url:
                newer = is_newer_version(remote_ver, current_ver)
                return {
                    "success": True,
                    "update_available": newer,
                    "current_version": current_ver,
                    "latest_version": remote_ver,
                    "download_url": wheel_url,
                    "source": "pypi"
                }
        except Exception as pypi_err:
            self.log(f"[YTDLP] PyPI check failed ({pypi_err}); trying GitHub Releases fallback...")

        # 2. Fallback source: GitHub Releases API
        try:
            req = urllib.request.Request(YTDLP_GITHUB_LATEST_API, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            remote_ver = str(data.get("tag_name") or "").strip().lstrip("vV")
            assets = data.get("assets", [])
            zip_url = ""
            for asset in assets:
                if isinstance(asset, dict) and asset.get("name") == "yt-dlp":
                    zip_url = str(asset.get("browser_download_url") or "")
                    break
            if remote_ver and zip_url:
                newer = is_newer_version(remote_ver, current_ver)
                return {
                    "success": True,
                    "update_available": newer,
                    "current_version": current_ver,
                    "latest_version": remote_ver,
                    "download_url": zip_url,
                    "source": "github"
                }
            raise RuntimeError("Could not locate yt-dlp package asset in release metadata.")
        except Exception as gh_err:
            return {
                "success": False,
                "update_available": False,
                "current_version": current_ver,
                "latest_version": current_ver,
                "error": str(gh_err)
            }

    @staticmethod
    def _safe_replace_dir(src: str, dst: str, retries: int = 5, delay: float = 0.06) -> None:
        """
        Replaces directory dst with src, retrying transient Windows PermissionError/OSError
        (e.g., antivirus/indexer read handles) and falling back to copytree+rmtree if needed.
        """
        last_err: Optional[Exception] = None
        for attempt in range(max(1, retries)):
            try:
                if os.path.exists(dst):
                    shutil.rmtree(dst, ignore_errors=True)
                os.replace(src, dst)
                return
            except OSError as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(delay * (attempt + 1))
        # Fallback if os.replace failed due to a transient open handle on Windows
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
            shutil.rmtree(src, ignore_errors=True)
            return
        if last_err:
            raise last_err

    def download_and_extract_archive(
        self,
        download_url: str,
        target_version: str = "",
        progress_cb: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Downloads a yt-dlp wheel or zipimport archive, extracts the yt_dlp package into a staging
        directory, validates its structure, atomically swaps it into self.plugin_dir, and activates it.
        """
        parent_dir = os.path.dirname(self.plugin_dir)
        os.makedirs(parent_dir, exist_ok=True)
        uid = f"{os.getpid()}_{threading.get_ident()}_{int(time.time() * 1000)}"
        staging_dir = os.path.join(parent_dir, f"yt_dlp_staging_{uid}")
        backup_dir = f"{self.plugin_dir}_backup_{uid}"
        archive_path = os.path.join(parent_dir, f"yt_dlp_download_{uid}.zip")

        try:
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)
            os.makedirs(staging_dir, exist_ok=True)

            headers = {"User-Agent": f"SmartDownload-Updater/{APP_VERSION}"}
            req = urllib.request.Request(download_url, headers=headers)
            ctx = _get_ssl_context()

            self.log(f"[YTDLP] Downloading yt-dlp package update from {download_url}...")
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                total_size = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                with open(archive_path, "wb") as out_f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            try:
                                progress_cb(downloaded, total_size)
                            except Exception:
                                pass

            if not os.path.isfile(archive_path) or os.path.getsize(archive_path) == 0:
                raise RuntimeError("Downloaded yt-dlp archive is missing or empty.")

            if not zipfile.is_zipfile(archive_path):
                raise RuntimeError("Downloaded file is not a valid ZIP/Wheel archive.")

            # Extract only yt_dlp/ package files safely (preventing path traversal)
            abs_staging = os.path.abspath(staging_dir)
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.infolist():
                    norm_name = member.filename.replace("\\", "/").lstrip("/")
                    if not (norm_name == "yt_dlp" or norm_name.startswith("yt_dlp/")):
                        continue
                    if ".." in norm_name.split("/"):
                        continue
                    dest_path = os.path.abspath(os.path.join(abs_staging, *norm_name.split("/")))
                    if not dest_path.startswith(abs_staging):
                        continue
                    if member.is_dir() or norm_name.endswith("/"):
                        os.makedirs(dest_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        with zf.open(member, "r") as src_f, open(dest_path, "wb") as dst_f:
                            shutil.copyfileobj(src_f, dst_f)

            if not self.is_plugin_valid(staging_dir):
                raise RuntimeError("Extracted archive does not contain a valid yt_dlp Python package.")

            detected_ver = self.get_plugin_version(staging_dir) or target_version or "unknown"
            meta_path = os.path.join(staging_dir, "plugin_meta.json")
            with open(meta_path, "w", encoding="utf-8") as mf:
                json.dump({
                    "version": detected_ver,
                    "updated_at": time.time(),
                    "download_url": download_url
                }, mf, indent=2)

            # Thread-safe atomic swap with backup recovery
            with self._lock:
                if os.path.exists(backup_dir):
                    shutil.rmtree(backup_dir, ignore_errors=True)
                moved_to_backup = False
                if os.path.exists(self.plugin_dir):
                    self._safe_replace_dir(self.plugin_dir, backup_dir)
                    moved_to_backup = True

                try:
                    self._safe_replace_dir(staging_dir, self.plugin_dir)
                except Exception:
                    if moved_to_backup and os.path.exists(backup_dir):
                        try:
                            self._safe_replace_dir(backup_dir, self.plugin_dir)
                        except Exception:
                            pass
                    raise

                if not self.activate_plugin(force=True):
                    # Rollback to backup if activation failed
                    if os.path.exists(self.plugin_dir):
                        shutil.rmtree(self.plugin_dir, ignore_errors=True)
                    if os.path.exists(backup_dir):
                        self._safe_replace_dir(backup_dir, self.plugin_dir)
                        self.activate_plugin(force=True)
                    raise RuntimeError("Failed to activate newly extracted yt-dlp plugin.")

                if os.path.exists(backup_dir):
                    shutil.rmtree(backup_dir, ignore_errors=True)

                active_ver = self.get_current_version()
                self.log(f"[YTDLP] Successfully updated and activated yt-dlp v{active_ver}!")
                return {
                    "success": True,
                    "updated": True,
                    "version": active_ver,
                    "plugin_dir": self.plugin_dir
                }

        except Exception as e:
            with self._lock:
                if not self.is_plugin_valid(self.plugin_dir) and os.path.exists(backup_dir):
                    try:
                        self._safe_replace_dir(backup_dir, self.plugin_dir)
                        self.activate_plugin(force=True)
                    except Exception:
                        pass
            self.log(f"[YTDLP ERROR] Update failed: {e}")
            return {
                "success": False,
                "updated": False,
                "version": self.get_current_version(),
                "error": str(e)
            }
        finally:
            if os.path.exists(archive_path):
                try:
                    os.remove(archive_path)
                except Exception:
                    pass
            if os.path.exists(staging_dir):
                try:
                    shutil.rmtree(staging_dir, ignore_errors=True)
                except Exception:
                    pass
            if os.path.exists(backup_dir):
                try:
                    shutil.rmtree(backup_dir, ignore_errors=True)
                except Exception:
                    pass

    def update(
        self,
        force: bool = False,
        progress_cb: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """Checks for a newer yt-dlp release and updates the external plugin if available."""
        check_res = self.check_for_update()
        if not check_res.get("success"):
            return {
                "success": False,
                "updated": False,
                "version": check_res.get("current_version", self.get_current_version()),
                "error": check_res.get("error", "Failed to check for yt-dlp updates")
            }

        if not check_res.get("update_available") and not force:
            cur = check_res.get("current_version", self.get_current_version())
            self.log(f"[YTDLP] yt-dlp is already up to date (v{cur}).")
            return {
                "success": True,
                "updated": False,
                "version": cur,
                "latest_version": check_res.get("latest_version", cur),
                "message": f"yt-dlp is up to date ({cur})"
            }

        download_url = check_res.get("download_url", "")
        if not download_url:
            return {
                "success": False,
                "updated": False,
                "version": check_res.get("current_version", self.get_current_version()),
                "error": "No download URL found for yt-dlp update"
            }

        return self.download_and_extract_archive(
            download_url=download_url,
            target_version=check_res.get("latest_version", ""),
            progress_cb=progress_cb
        )


class AppAutoUpdater:
    """
    Manages checking GitHub Releases for new Smart Download (SD) versions,
    downloading SmartDownload-Setup.exe with progress reporting, and launching upgrades.
    """

    def __init__(
        self,
        current_version: str = APP_VERSION,
        repo_owner: str = GITHUB_REPO_OWNER,
        repo_name: str = GITHUB_REPO_NAME,
        on_log: Optional[Callable[[str], None]] = None,
        timeout: int = 12,
        ssl_context: Optional[ssl.SSLContext] = None
    ):
        self.current_version = str(current_version or APP_VERSION).strip()
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        self.on_log = on_log
        self.timeout = max(3, int(timeout))
        if ssl_context is not None:
            self.ssl_context = ssl_context
        else:
            self.ssl_context = _get_verified_ssl_context()

    def log(self, message: str):
        if self.on_log:
            try:
                self.on_log(message)
            except Exception:
                pass

    def check_for_update(self) -> Dict[str, Any]:
        """
        Queries GitHub Releases /releases/latest and compares tag_name against self.current_version.
        Returns a structured dictionary with release metadata and asset URLs.
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"SmartDownload-AutoUpdater/{self.current_version}"
        }
        ctx = self.ssl_context if hasattr(self, 'ssl_context') and self.ssl_context is not None else _get_verified_ssl_context()
        try:
            req = urllib.request.Request(self.api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if not isinstance(data, dict):
                raise RuntimeError("Invalid JSON payload from GitHub Releases API.")

            tag_name = str(data.get("tag_name") or "").strip()
            latest_clean = tag_name.lstrip("vV").strip() or self.current_version
            release_name = str(data.get("name") or f"{APP_NAME} {tag_name}").strip()
            release_notes = str(data.get("body") or "").strip()
            html_url = str(data.get("html_url") or f"https://github.com/{self.repo_owner}/{self.repo_name}/releases").strip()

            assets = data.get("assets", [])
            installer_url = ""
            installer_name = "SmartDownload-Setup.exe"
            installer_size = 0
            portable_url = ""

            if isinstance(assets, list):
                for asset in assets:
                    if not isinstance(asset, dict):
                        continue
                    a_name = str(asset.get("name") or "")
                    a_url = str(asset.get("browser_download_url") or "")
                    a_size = int(asset.get("size") or 0)
                    if a_name.lower() == "smartdownload-setup.exe":
                        installer_url = a_url
                        installer_name = a_name
                        installer_size = a_size
                    elif a_name.lower() == "smartdownload.exe":
                        portable_url = a_url

                # Fallback if Setup.exe wasn't found but another .exe asset exists
                if not installer_url:
                    for asset in assets:
                        if isinstance(asset, dict):
                            a_name = str(asset.get("name") or "")
                            a_url = str(asset.get("browser_download_url") or "")
                            if a_name.lower().endswith(".exe") and a_url:
                                installer_url = a_url
                                installer_name = a_name
                                installer_size = int(asset.get("size") or 0)
                                break

            newer = is_newer_version(tag_name, self.current_version)
            return {
                "success": True,
                "update_available": newer,
                "current_version": self.current_version,
                "latest_version": latest_clean,
                "tag_name": tag_name,
                "release_name": release_name,
                "release_notes": release_notes,
                "html_url": html_url,
                "release_url": html_url,
                "installer_url": installer_url,
                "download_url": installer_url or portable_url,
                "installer_name": installer_name,
                "asset_name": installer_name,
                "installer_size": installer_size,
                "asset_size": installer_size,
                "portable_url": portable_url,
                "error": None,
            }
        except Exception as e:
            self.log(f"[APP UPDATER] Check failed: {e}")
            return {
                "success": False,
                "update_available": False,
                "current_version": self.current_version,
                "latest_version": self.current_version,
                "error": str(e)
            }

    def download_update(
        self,
        download_url: str,
        dest_path: Optional[str] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event: Optional[threading.Event] = None
    ) -> str:
        """
        Streams the installer executable from download_url into a temporary .part file
        and atomically renames it to dest_path upon completion.
        Returns the absolute path to the downloaded installer.
        """
        if not download_url or not isinstance(download_url, str):
            raise ValueError("A valid download_url is required to download update.")

        auto_dest = dest_path is None
        if not dest_path:
            dest_path = os.path.join(tempfile.gettempdir(), "SmartDownload-Setup.exe")
        dest_path = os.path.abspath(dest_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        part_path = f"{dest_path}.part_{os.getpid()}_{threading.get_ident()}"

        headers = {"User-Agent": f"SmartDownload-AutoUpdater/{self.current_version}"}
        ctx = self.ssl_context if hasattr(self, 'ssl_context') and self.ssl_context is not None else _get_verified_ssl_context()
        try:
            req = urllib.request.Request(download_url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                total_size = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                with open(part_path, "wb") as out_f:
                    while True:
                        if cancel_event and cancel_event.is_set():
                            raise RuntimeError("Update download cancelled by user.")
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            try:
                                progress_cb(downloaded, total_size)
                            except Exception:
                                pass

            if not os.path.isfile(part_path) or os.path.getsize(part_path) == 0:
                raise RuntimeError("Downloaded update file is missing or empty.")

            try:
                os.replace(part_path, dest_path)
            except PermissionError:
                if auto_dest:
                    alt_dest = os.path.join(
                        tempfile.gettempdir(),
                        f"SmartDownload-Setup-{os.getpid()}-{int(time.time())}.exe"
                    )
                    os.replace(part_path, alt_dest)
                    dest_path = os.path.abspath(alt_dest)
                else:
                    raise
            self.log(f"[APP UPDATER] Downloaded update installer to {dest_path} ({os.path.getsize(dest_path):,} bytes).")
            return dest_path
        except Exception:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except Exception:
                    pass
            raise

    def apply_update(
        self,
        installer_path: str,
        silent: bool = True,
        launch_after: bool = True,
        exit_callback: Optional[Callable[[], None]] = None
    ) -> bool:
        """
        Launches the downloaded SmartDownload-Setup.exe installer to upgrade the application,
        and invokes exit_callback so the running instance closes cleanly.
        """
        if not installer_path or not os.path.isfile(installer_path):
            raise FileNotFoundError(f"Update installer not found: {installer_path}")

        abs_installer = os.path.abspath(installer_path)
        cmd = [abs_installer]
        if silent:
            cmd.append("--silent")
            if launch_after:
                cmd.append("--launch")

        self.log(f"[APP UPDATER] Launching update installer: {' '.join(cmd)}")
        subprocess.Popen(cmd, cwd=os.path.dirname(abs_installer))

        if exit_callback:
            try:
                exit_callback()
            except Exception:
                pass
        return True
