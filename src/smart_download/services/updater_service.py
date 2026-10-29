"""
========================================================================================
↻ AUTO-UPDATE ENGINE — Smart Download (SD) & yt-dlp Dynamic Plugin Updater
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
APP_VERSION = "2.0.1"

GITHUB_REPO_OWNER = "hozifa460"
GITHUB_REPO_NAME = "smart-download-sd"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"

YTDLP_PYPI_JSON_API = "https://pypi.org/pypi/yt-dlp/json"
YTDLP_GITHUB_LATEST_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
YTDLP_GITHUB_RELEASES_API = YTDLP_GITHUB_LATEST_API


def get_app_data_dir() -> str:
    """Returns persistent application data directory (%APPDATA%\\SmartDownload on Windows)."""
    cfg_override = os.environ.get("SD_CONFIG_DIR")
    if cfg_override:
        try:
            os.makedirs(cfg_override, exist_ok=True)
        except Exception:
            pass
        return cfg_override
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



from .ytdlp_updater import _ExternalYtDlpFinder, YtDlpAutoUpdater

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
            core_patch_url = ""
            core_patch_size = 0

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
                    elif a_name.lower() == "smartdownload-corepatch.zip":
                        core_patch_url = a_url
                        core_patch_size = a_size

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
                "core_patch_url": core_patch_url,
                "core_patch_size": core_patch_size,
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


from .core_patch_updater import (
    build_core_patch_zip,
    CoreHotPatchUpdater,
    _ExternalCoreFinder,
    get_core_plugin_dir,
    init_core_loader,
    is_version_ge,
)

__all__ = [
    "APP_NAME",
    "APP_ID",
    "APP_VERSION",
    "GITHUB_REPO_OWNER",
    "GITHUB_REPO_NAME",
    "GITHUB_LATEST_RELEASE_API",
    "YTDLP_PYPI_JSON_API",
    "YTDLP_GITHUB_LATEST_API",
    "YTDLP_GITHUB_RELEASES_API",
    "get_app_data_dir",
    "get_ytdlp_plugin_dir",
    "_get_ssl_context",
    "_get_verified_ssl_context",
    "parse_version",
    "is_newer_version",
    "is_version_ge",
    "YtDlpAutoUpdater",
    "_ExternalYtDlpFinder",
    "AppAutoUpdater",
    "build_core_patch_zip",
    "CoreHotPatchUpdater",
    "_ExternalCoreFinder",
    "get_core_plugin_dir",
    "init_core_loader",
]


