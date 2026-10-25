"""
Core Hot-Patch Packager & OTA Updater: Zero-Rebuild Workflow for Smart Download.
Allows frozen SmartDownload.exe to load updated core modules or local dev sources
without recompiling PyInstaller binaries.
"""
import os
import sys
import json
import time
import shutil
import zipfile
import tempfile
import threading
import importlib
import importlib.abc
import importlib.machinery
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple, Callable, Any

from .updater_service import (
    APP_NAME,
    APP_ID,
    APP_VERSION,
    GITHUB_REPO_OWNER,
    GITHUB_REPO_NAME,
    get_app_data_dir,
    _get_verified_ssl_context,
    parse_version,
    is_newer_version,
)


def get_core_plugin_dir(base_dir: Optional[str] = None) -> str:
    """Returns directory where external core patch package is installed."""
    root = base_dir if base_dir else get_app_data_dir()
    return os.path.join(root, "core_plugin")


def is_version_ge(v1: str, v2: str) -> bool:
    """Returns True if version v1 >= v2."""
    if not v1:
        return False
    if not v2:
        return True
    if is_newer_version(v1, v2):
        return True
    if is_newer_version(v2, v1):
        return False
    # If neither is strictly newer, verify equality including pre-release and zero-padding
    p1 = parse_version(v1)
    p2 = parse_version(v2)
    if p1 and p2:
        max_len = max(len(p1), len(p2))
        p1_pad = p1 + (0,) * (max_len - len(p1))
        p2_pad = p2 + (0,) * (max_len - len(p2))
        if p1_pad == p2_pad:
            c1 = str(v1).strip().lstrip("vV").strip().split("+", 1)[0]
            c2 = str(v2).strip().lstrip("vV").strip().split("+", 1)[0]
            pre1 = c1.split("-", 1)[1].strip() if "-" in c1 else ""
            pre2 = c2.split("-", 1)[1].strip() if "-" in c2 else ""
            return pre1 == pre2
    return str(v1).strip().lstrip("vV") == str(v2).strip().lstrip("vV")


def build_core_patch_zip(
    output_path: str,
    src_dir: Optional[str] = None,
    version: Optional[str] = None
) -> str:
    """
    Packages src/smart_download/ (all .py and locales/*.json files + core_version.json)
    into a lightweight SmartDownload-CorePatch.zip (<150 KB) in <0.5 seconds.
    """
    out_abs = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)

    if not src_dir:
        cur_file = os.path.abspath(__file__)
        candidate = os.path.dirname(os.path.dirname(cur_file))
        if os.path.basename(candidate) == "smart_download":
            src_pkg = candidate
        else:
            src_pkg = os.path.join(os.getcwd(), "src", "smart_download")
    else:
        src_dir_abs = os.path.abspath(src_dir)
        if os.path.basename(src_dir_abs) == "smart_download":
            src_pkg = src_dir_abs
        else:
            src_pkg = os.path.join(src_dir_abs, "smart_download")

    if not os.path.isdir(src_pkg):
        raise FileNotFoundError(f"smart_download package directory not found at: {src_pkg}")

    ver_raw = str(version or APP_VERSION).strip()
    ver_clean = ver_raw.lstrip("vV").strip() or APP_VERSION
    manifest_data = {
        "version": ver_clean,
        "app_name": APP_NAME,
        "app_id": APP_ID,
        "created_at": int(time.time()),
        "release_tag": f"v{ver_clean}"
    }
    manifest_json = json.dumps(manifest_data, indent=2).encode("utf-8")

    part_out = f"{out_abs}.part_{os.getpid()}_{threading.get_ident()}_{time.time_ns()}"
    with zipfile.ZipFile(part_out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("core_version.json", manifest_json)
        zf.writestr("smart_download/core_version.json", manifest_json)

        for root, dirs, files in os.walk(src_pkg):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".pytest_cache")]
            for f in sorted(files):
                if f.endswith((".py", ".json")):
                    full_p = os.path.join(root, f)
                    rel_to_pkg = os.path.relpath(full_p, src_pkg)
                    arcname = os.path.join("smart_download", rel_to_pkg).replace("\\", "/")
                    zf.write(full_p, arcname)

    os.replace(part_out, out_abs)
    return out_abs


class _ExternalCoreFinder(importlib.abc.MetaPathFinder):
    """
    MetaPathFinder placed at sys.meta_path[0] to ensure an updated external smart_download
    package in %APPDATA%\\SmartDownload\\core_plugin or local dev src takes precedence
    over PyInstaller's PyiFrozenImporter when frozen as a standalone .exe.
    """
    def __init__(self, core_root: str):
        self.core_root = os.path.abspath(core_root)

    def find_spec(self, fullname: str, path=None, target=None):
        if fullname != "smart_download" and not fullname.startswith("smart_download."):
            return None
        pkg_root = os.path.join(self.core_root, "smart_download")
        if not os.path.isfile(os.path.join(pkg_root, "__init__.py")):
            return None
        try:
            parts = fullname.split(".")
            parent_dir = os.path.join(self.core_root, *parts[:-1])
            if os.path.isdir(parent_dir):
                spec = importlib.machinery.PathFinder.find_spec(fullname, [parent_dir], target)
                if spec is not None:
                    return spec
            if path is not None:
                return importlib.machinery.PathFinder.find_spec(fullname, path, target)
        except Exception:
            return None
        return None


def _purge_and_reimport_core(core_root: str) -> bool:
    """
    Installs _ExternalCoreFinder and sys.path[0], purges cached smart_download modules
    from sys.modules, and re-imports smart_download to verify successful dynamic loading.
    """
    norm_root = os.path.normcase(os.path.abspath(core_root))
    sys.path[:] = [
        p for p in sys.path
        if not (p and os.path.normcase(os.path.abspath(p)) == norm_root)
    ]
    sys.path.insert(0, core_root)

    sys.meta_path[:] = [
        f for f in sys.meta_path
        if not isinstance(f, _ExternalCoreFinder)
    ]
    sys.meta_path.insert(0, _ExternalCoreFinder(core_root))

    to_delete = [
        k for k in list(sys.modules.keys())
        if k == "smart_download" or k.startswith("smart_download.")
    ]
    saved_modules = {k: sys.modules.pop(k) for k in to_delete}

    try:
        mod = importlib.import_module("smart_download")
        importlib.import_module("smart_download.config")
        loaded_file = os.path.normcase(os.path.abspath(getattr(mod, "__file__", "") or ""))
        norm_pkg = os.path.normcase(os.path.abspath(os.path.join(core_root, "smart_download")))
        if not loaded_file.startswith(norm_pkg):
            raise RuntimeError(f"Loaded smart_download from {loaded_file} instead of {norm_pkg}")
        return True
    except Exception:
        sys.path[:] = [
            p for p in sys.path
            if not (p and os.path.normcase(os.path.abspath(p)) == norm_root)
        ]
        sys.meta_path[:] = [
            f for f in sys.meta_path
            if not isinstance(f, _ExternalCoreFinder)
        ]
        for k in [m for m in list(sys.modules.keys()) if m == "smart_download" or m.startswith("smart_download.")]:
            sys.modules.pop(k, None)
        sys.modules.update(saved_modules)
        return False


class CoreHotPatchUpdater:
    """
    Manages checking, downloading, atomically extracting, and dynamically activating
    the latest smart_download core package in %APPDATA%\\SmartDownload\\core_plugin.
    """
    _lock = threading.RLock()

    def __init__(
        self,
        plugin_dir: Optional[str] = None,
        repo_owner: str = GITHUB_REPO_OWNER,
        repo_name: str = GITHUB_REPO_NAME,
        current_version: Optional[str] = None,
        on_log: Optional[Callable[[str], None]] = None,
        timeout: int = 15
    ):
        self.plugin_dir = os.path.abspath(plugin_dir or get_core_plugin_dir())
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version = str(current_version or APP_VERSION).strip()
        self.on_log = on_log
        self.timeout = max(3, int(timeout))

    def log(self, message: str):
        if self.on_log:
            try:
                self.on_log(message)
            except Exception:
                pass

    def is_plugin_valid(self, directory: Optional[str] = None) -> bool:
        target = os.path.abspath(directory or self.plugin_dir)
        init_py = os.path.join(target, "smart_download", "__init__.py")
        config_py = os.path.join(target, "smart_download", "config.py")
        ver_json1 = os.path.join(target, "core_version.json")
        ver_json2 = os.path.join(target, "smart_download", "core_version.json")
        return os.path.isfile(init_py) and os.path.isfile(config_py) and (os.path.isfile(ver_json1) or os.path.isfile(ver_json2))

    def get_plugin_version(self, directory: Optional[str] = None) -> Optional[str]:
        target = os.path.abspath(directory or self.plugin_dir)
        for ver_file in (os.path.join(target, "core_version.json"), os.path.join(target, "smart_download", "core_version.json")):
            if os.path.isfile(ver_file):
                try:
                    with open(ver_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    v = data.get("version")
                    if v and isinstance(v, str):
                        return v.strip().lstrip("vV")
                except Exception:
                    pass
        return None

    def check_for_core_patch(self) -> Dict[str, Any]:
        """Queries GitHub Releases API for SmartDownload-CorePatch.zip asset."""
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"SmartDownload-CorePatchUpdater/{self.current_version}"
        }
        ctx = _get_verified_ssl_context()
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if not isinstance(data, dict):
                raise RuntimeError("Invalid JSON payload from GitHub Releases API.")

            tag_name = str(data.get("tag_name") or "").strip()
            latest_clean = tag_name.lstrip("vV").strip() or self.current_version
            release_notes = str(data.get("body") or "").strip()

            assets = data.get("assets", [])
            patch_url = ""
            patch_size = 0
            if isinstance(assets, list):
                for asset in assets:
                    if isinstance(asset, dict):
                        a_name = str(asset.get("name") or "")
                        if a_name.lower() == "smartdownload-corepatch.zip":
                            patch_url = str(asset.get("browser_download_url") or "")
                            patch_size = int(asset.get("size") or 0)
                            break

            newer = is_newer_version(latest_clean, self.current_version) if latest_clean else False
            return {
                "success": True,
                "patch_available": bool(newer and patch_url),
                "current_version": self.current_version,
                "latest_version": latest_clean,
                "tag_name": tag_name,
                "patch_url": patch_url,
                "patch_size": patch_size,
                "release_notes": release_notes,
                "error": None,
            }
        except Exception as e:
            self.log(f"[CORE PATCH] Check failed: {e}")
            return {
                "success": False,
                "patch_available": False,
                "current_version": self.current_version,
                "latest_version": self.current_version,
                "error": str(e)
            }

    def download_core_patch(
        self,
        download_url: str,
        dest_path: Optional[str] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event: Optional[threading.Event] = None
    ) -> str:
        if not download_url or not isinstance(download_url, str):
            raise ValueError("A valid download_url is required.")

        if not dest_path:
            dest_path = os.path.join(tempfile.gettempdir(), f"SmartDownload-CorePatch_{os.getpid()}_{threading.get_ident()}.zip")
        dest_path = os.path.abspath(dest_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        part_path = f"{dest_path}.part_{os.getpid()}_{threading.get_ident()}_{time.time_ns()}"

        headers = {"User-Agent": f"SmartDownload-CorePatchUpdater/{self.current_version}"}
        ctx = _get_verified_ssl_context()
        try:
            req = urllib.request.Request(download_url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                total_size = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                with open(part_path, "wb") as out_f:
                    while True:
                        if cancel_event and cancel_event.is_set():
                            raise RuntimeError("Core patch download cancelled by user.")
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
                raise RuntimeError("Downloaded core patch file is missing or empty.")

            os.replace(part_path, dest_path)
            self.log(f"[CORE PATCH] Downloaded patch to {dest_path} ({os.path.getsize(dest_path):,} bytes).")
            return dest_path
        except Exception:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except Exception:
                    pass
            raise

    @staticmethod
    def _safe_replace_dir(src: str, dst: str, retries: int = 5, delay: float = 0.06) -> None:
        """
        Replaces directory dst with src, retrying transient Windows PermissionError/OSError
        and falling back to copytree+rmtree if needed.
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
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
            shutil.rmtree(src, ignore_errors=True)
            return
        if last_err:
            raise last_err

    def apply_core_patch(
        self,
        zip_path: str,
        target_dir: Optional[str] = None,
        backup: bool = True
    ) -> bool:
        """
        Atomically extracts and validates SmartDownload-CorePatch.zip into target_dir
        with Zip Slip validation and automatic backup rollback if any step fails.
        """
        with self._lock:
            target = os.path.abspath(target_dir or self.plugin_dir)
            if not os.path.isfile(zip_path) or not zipfile.is_zipfile(zip_path):
                raise ValueError(f"Invalid or missing zip archive: {zip_path}")

            parent_dir = os.path.dirname(target)
            os.makedirs(parent_dir, exist_ok=True)
            stage_dir = tempfile.mkdtemp(prefix="sd_core_stage_", dir=parent_dir)
            backup_dir = f"{target}.bak_{os.getpid()}_{threading.get_ident()}_{time.time_ns()}"

            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    stage_abs = os.path.abspath(stage_dir)
                    for member in zf.infolist():
                        dest_file = os.path.abspath(os.path.join(stage_abs, member.filename))
                        if not (dest_file == stage_abs or dest_file.startswith(stage_abs + os.sep)):
                            raise ValueError(f"Zip Slip path traversal attempt: {member.filename}")
                    zf.extractall(stage_dir)

                if not self.is_plugin_valid(stage_dir):
                    raise ValueError("Core patch archive is missing essential smart_download modules or core_version.json.")

                if os.path.exists(target):
                    self._safe_replace_dir(target, backup_dir)

                try:
                    self._safe_replace_dir(stage_dir, target)
                except Exception:
                    if os.path.exists(backup_dir) and not os.path.exists(target):
                        self._safe_replace_dir(backup_dir, target)
                    raise

                if backup and os.path.exists(backup_dir):
                    shutil.rmtree(backup_dir, ignore_errors=True)

                self.log(f"[CORE PATCH] Successfully applied core patch to {target}.")
                return True
            except Exception as e:
                self.log(f"[CORE PATCH] Failed to apply core patch: {e}")
                if os.path.exists(stage_dir):
                    shutil.rmtree(stage_dir, ignore_errors=True)
                if os.path.exists(backup_dir) and not os.path.exists(target):
                    try:
                        self._safe_replace_dir(backup_dir, target)
                    except Exception:
                        pass
                raise

    def activate_plugin(self, force: bool = False) -> bool:
        with self._lock:
            if not self.is_plugin_valid():
                return False

            plugin_ver = self.get_plugin_version()
            if not force and plugin_ver:
                if is_newer_version(self.current_version, plugin_ver):
                    self.log(f"[CORE PATCH] Bundled core ({self.current_version}) is newer than plugin ({plugin_ver}); keeping bundled.")
                    return False

            return _purge_and_reimport_core(self.plugin_dir)

    def deactivate_plugin(self) -> None:
        with self._lock:
            norm_plugin = os.path.normcase(self.plugin_dir)
            sys.path[:] = [
                p for p in sys.path
                if not (p and os.path.normcase(os.path.abspath(p)) == norm_plugin)
            ]
            sys.meta_path[:] = [
                f for f in sys.meta_path
                if not isinstance(f, _ExternalCoreFinder)
            ]


def init_core_loader(force: bool = False) -> Optional[str]:
    """
    Checks external core override locations before falling back to bundled PYZ:
    1) Local Dev / Source Mode Override (SD_DEV_SRC env or adjacent dev folder)
    2) OTA Hot-Patch Plugin Directory (%APPDATA%\\SmartDownload\\core_plugin)
    Returns 'dev', 'plugin', or None.
    """
    # 1. Local Dev / Source Mode Override
    dev_src = os.environ.get("SD_DEV_SRC")
    candidate_dev_roots: List[str] = []
    if dev_src and os.path.isdir(dev_src):
        candidate_dev_roots.append(dev_src)
        candidate_dev_roots.append(os.path.dirname(dev_src))

    if getattr(sys, "frozen", False) or force:
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidate_dev_roots.extend([
            os.path.join(exe_dir, "src"),
            exe_dir,
            os.path.abspath(os.path.join(exe_dir, "..", "src")),
            os.path.abspath(os.path.join(exe_dir, "..", "..", "src")),
        ])

    for root_cand in candidate_dev_roots:
        if not root_cand or not os.path.isdir(root_cand):
            continue
        pkg_cand = os.path.join(root_cand, "smart_download")
        if os.path.isfile(os.path.join(pkg_cand, "__init__.py")):
            if _purge_and_reimport_core(root_cand):
                return "dev"

    # 2. OTA Hot-Patch Plugin Directory (only for frozen executable or forced runs)
    if getattr(sys, "frozen", False) or force:
        plugin_dir = get_core_plugin_dir()
        updater = CoreHotPatchUpdater(plugin_dir=plugin_dir)
        if updater.is_plugin_valid():
            patch_ver = updater.get_plugin_version()
            if patch_ver and is_version_ge(patch_ver, APP_VERSION):
                if updater.activate_plugin(force=True):
                    return "plugin"

    return None


__all__ = [
    "get_core_plugin_dir",
    "is_version_ge",
    "build_core_patch_zip",
    "_ExternalCoreFinder",
    "CoreHotPatchUpdater",
    "init_core_loader",
]
