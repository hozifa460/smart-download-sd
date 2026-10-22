"""
========================================================================================
🔧 WINDOWS REGISTRY & BROWSER NATIVE MESSAGING REGISTRATION
========================================================================================
Enables 1-click seamless browser integration for Chrome & Microsoft Edge via Windows Registry:
1. Creates host manifest: com.turbodownloader.host.json
2. Creates runner launcher script: turbo_host.bat
3. Registers NativeMessagingHosts keys in Windows Registry:
   - HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts\\com.turbodownloader.host
   - HKCU\\Software\\Microsoft\\Edge\\NativeMessagingHosts\\com.turbodownloader.host
4. Computes deterministic extension IDs for unpacked WebExtension development.
5. Provides registration verification and clean unregistration functions.
========================================================================================
"""

import os
import sys
import json
import hashlib
import time
from typing import Dict, List, Optional, Any

HOST_NAME = "com.smartdownload.host"
HOST_DESCRIPTION = "Smart Download (SD) Native Messaging Host"

LEGACY_HOST_NAME = "com.turbodownloader.host"
LEGACY_CHROME_REG_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{LEGACY_HOST_NAME}"
LEGACY_EDGE_REG_KEY = rf"Software\Microsoft\Edge\NativeMessagingHosts\{LEGACY_HOST_NAME}"

CHROME_REG_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"
EDGE_REG_KEY = rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}"

CHROME_EXT_KEY_PREFIX = r"Software\Google\Chrome\Extensions"
EDGE_EXT_KEY_PREFIX = r"Software\Microsoft\Edge\Extensions"
CHROME_UPDATE_URL = "https://clients2.google.com/service/update2/crx"
EDGE_UPDATE_URL = "https://edge.microsoft.com/extensionwho10/service/update2/crx"

# Try importing winreg on Windows
try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False


def compute_unpacked_extension_id(extension_dir: str) -> str:
    """
    Computes Chromium extension ID for an unpacked extension folder path.
    Chromium algorithm: SHA-256 of absolute folder path, first 32 hex nibbles
    mapped to ASCII chars 'a' through 'p'.
    """
    try:
        norm_path = os.path.normpath(os.path.abspath(extension_dir))
        # On Windows, drive letter must be lowercase for Chromium compatibility
        if len(norm_path) > 1 and norm_path[1] == ':':
            norm_path = norm_path[0].lower() + norm_path[1:]

        digest = hashlib.sha256(norm_path.encode("utf-8")).hexdigest()[:32]
        # Map hex characters (0-f) to letters (a-p)
        ext_id = "".join(chr(ord('a') + int(c, 16)) for c in digest)
        return ext_id
    except Exception:
        return "turbodownloaderextensionid"


# Deterministic static extension ID corresponding to the extension's RSA public key in manifest.json
STATIC_EXTENSION_ID = "gokbjcmdmbjlngbdpanlccbfpmppjloa"


def get_default_extension_origins(
    extension_id: Optional[str] = None,
    extension_dir: Optional[str] = None,
    target_dir: Optional[str] = None
) -> List[str]:
    """
    Compiles list of allowed extension origins for Chrome and Edge.
    """
    origins = [
        "chrome-extension://turbo-downloader-integration/",
        "chrome-extension://com.turbodownloader.extension/",
        f"chrome-extension://{STATIC_EXTENSION_ID}/"
    ]

    candidate_ext_dirs = []
    if extension_dir:
        candidate_ext_dirs.append(extension_dir)
    if target_dir:
        candidate_ext_dirs.append(os.path.join(target_dir, "extension"))

    # Compute ID for local unpacked extension folder if it exists
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidate_ext_dirs.append(os.path.join(exe_dir, "extension"))
        if hasattr(sys, "_MEIPASS"):
            candidate_ext_dirs.append(os.path.join(sys._MEIPASS, "extension"))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_ext_dirs.append(os.path.join(base_dir, "extension"))

    for edir in candidate_ext_dirs:
        if edir and os.path.isdir(edir):
            computed_id = compute_unpacked_extension_id(edir)
            origins.append(f"chrome-extension://{computed_id}/")

    if extension_id:
        clean_id = extension_id.strip().rstrip("/")
        if clean_id.startswith("chrome-extension://"):
            origins.append(f"{clean_id}/")
        else:
            origins.append(f"chrome-extension://{clean_id}/")

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for orig in origins:
        if orig not in seen:
            seen.add(orig)
            deduped.append(orig)

    return deduped


def generate_host_manifest(
    launcher_path: str,
    output_json_path: str,
    allowed_origins: Optional[List[str]] = None
) -> str:
    """
    Writes the Native Messaging Host JSON manifest file.
    """
    if allowed_origins is None:
        allowed_origins = get_default_extension_origins()

    manifest_data = {
        "name": HOST_NAME,
        "description": HOST_DESCRIPTION,
        "path": os.path.abspath(launcher_path),
        "type": "stdio",
        "allowed_origins": allowed_origins
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    return os.path.abspath(output_json_path)


def generate_launcher_batch(output_bat_path: str) -> str:
    """
    Creates a robust Windows .bat launcher that works for both frozen .exe and Python source.
    Prioritizes direct SmartDownload.exe --native-host execution (<5ms) when present in the directory,
    falling back seamlessly to Python script execution in development environments.
    """
    bat_content = (
        "@echo off\r\n"
        "setlocal\r\n"
        "REM Launcher for Smart Download (SD) Native Messaging Host\r\n"
        "set SCRIPT_DIR=%~dp0\r\n"
        "\r\n"
        "REM 1. Fast Standalone path: If SmartDownload.exe exists in directory, launch immediately (<5ms)\r\n"
        "if exist \"%SCRIPT_DIR%SmartDownload.exe\" (\r\n"
        "    \"%SCRIPT_DIR%SmartDownload.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "if exist \"%SCRIPT_DIR%TurboDownloader.exe\" (\r\n"
        "    \"%SCRIPT_DIR%TurboDownloader.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "\r\n"
        "REM 2. Development source mode: Execute native_messaging_host.py directly via python (<50ms)\r\n"
        "if exist \"%SCRIPT_DIR%native_messaging_host.py\" (\r\n"
        "    python \"%SCRIPT_DIR%native_messaging_host.py\" %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "if exist \"%SCRIPT_DIR%..\\native_messaging_host.py\" (\r\n"
        "    python \"%SCRIPT_DIR%..\\native_messaging_host.py\" %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "\r\n"
        "REM 3. Dist folder fallback\r\n"
        "if exist \"%SCRIPT_DIR%dist\\SmartDownload.exe\" (\r\n"
        "    \"%SCRIPT_DIR%dist\\SmartDownload.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "if exist \"%SCRIPT_DIR%dist\\TurboDownloader.exe\" (\r\n"
        "    \"%SCRIPT_DIR%dist\\TurboDownloader.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "\r\n"
        "REM 4. Py launcher fallback\r\n"
        "where py >nul 2>nul\r\n"
        "if %ERRORLEVEL% equ 0 (\r\n"
        "    if exist \"%SCRIPT_DIR%native_messaging_host.py\" (\r\n"
        "        py -3 \"%SCRIPT_DIR%native_messaging_host.py\" %*\r\n"
        "        goto :EOF\r\n"
        "    )\r\n"
        ")\r\n"
        "\r\n"
        "REM 5. Final fallback\r\n"
        "python \"%SCRIPT_DIR%native_messaging_host.py\" %*\r\n"
    )

    with open(output_bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    return os.path.abspath(output_bat_path)


def register_browser_extensions(
    extension_id: Optional[str] = None,
    extension_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Registers the browser extension in Windows Registry for Chrome and Edge:
    - HKCU\\Software\\Google\\Chrome\\Extensions\\<extension_id>
    - HKCU\\Software\\Microsoft\\Edge\\Extensions\\<extension_id>
    Sets 'path', 'version', and 'update_url' where appropriate.
    """
    if not HAS_WINREG or not sys.platform.startswith("win"):
        return {
            "success": False,
            "error": "Windows Registry operations are only supported on Windows OS."
        }

    if not extension_dir:
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(os.path.abspath(sys.executable))
            ext_candidate = os.path.join(base_dir, "extension")
            if not os.path.isdir(ext_candidate) and hasattr(sys, "_MEIPASS"):
                ext_candidate = os.path.join(sys._MEIPASS, "extension")
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            ext_candidate = os.path.join(base_dir, "extension")
        if os.path.isdir(ext_candidate):
            extension_dir = ext_candidate

    ids_to_register = [STATIC_EXTENSION_ID]
    if extension_dir and os.path.isdir(extension_dir):
        unpacked_id = compute_unpacked_extension_id(extension_dir)
        if unpacked_id not in ids_to_register:
            ids_to_register.append(unpacked_id)
    if extension_id and extension_id not in ids_to_register:
        clean_ext_id = extension_id.strip().rstrip("/").replace("chrome-extension://", "")
        if clean_ext_id not in ids_to_register:
            ids_to_register.append(clean_ext_id)

    ext_version = "1.0.0"
    if extension_dir and os.path.isfile(os.path.join(extension_dir, "manifest.json")):
        try:
            with open(os.path.join(extension_dir, "manifest.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
                ext_version = data.get("version", "1.0.0")
        except Exception:
            pass

    results = {}
    for ext_id in ids_to_register:
        # Chrome
        try:
            c_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{CHROME_EXT_KEY_PREFIX}\{ext_id}")
            if extension_dir and os.path.isdir(extension_dir):
                winreg.SetValueEx(c_key, "path", 0, winreg.REG_SZ, os.path.abspath(extension_dir))
            winreg.SetValueEx(c_key, "version", 0, winreg.REG_SZ, ext_version)
            winreg.SetValueEx(c_key, "update_url", 0, winreg.REG_SZ, CHROME_UPDATE_URL)
            winreg.CloseKey(c_key)
            results[f"Chrome_{ext_id}"] = True
        except Exception:
            results[f"Chrome_{ext_id}"] = False

        # Edge
        try:
            e_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{EDGE_EXT_KEY_PREFIX}\{ext_id}")
            if extension_dir and os.path.isdir(extension_dir):
                winreg.SetValueEx(e_key, "path", 0, winreg.REG_SZ, os.path.abspath(extension_dir))
            winreg.SetValueEx(e_key, "version", 0, winreg.REG_SZ, ext_version)
            winreg.SetValueEx(e_key, "update_url", 0, winreg.REG_SZ, EDGE_UPDATE_URL)
            winreg.CloseKey(e_key)
            results[f"Edge_{ext_id}"] = True
        except Exception:
            results[f"Edge_{ext_id}"] = False

    return {
        "success": any(results.values()) if results else False,
        "registered_ids": ids_to_register,
        "details": results
    }


def unregister_browser_extensions(extension_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Removes extension registry keys for Chrome and Edge from HKCU.
    """
    if not HAS_WINREG or not sys.platform.startswith("win"):
        return {
            "success": False,
            "error": "Windows Registry operations are only supported on Windows OS."
        }

    if extension_ids is None:
        extension_ids = [STATIC_EXTENSION_ID]
        if getattr(sys, "frozen", False):
            ext_dir = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "extension")
        else:
            ext_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extension")
        if os.path.isdir(ext_dir):
            unpacked_id = compute_unpacked_extension_id(ext_dir)
            if unpacked_id not in extension_ids:
                extension_ids.append(unpacked_id)

    results = {}
    for ext_id in extension_ids:
        clean_ext_id = ext_id.strip().rstrip("/").replace("chrome-extension://", "")
        for browser_name, prefix in [("Chrome", CHROME_EXT_KEY_PREFIX), ("Edge", EDGE_EXT_KEY_PREFIX)]:
            full_key = rf"{prefix}\{clean_ext_id}"
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, full_key)
                results[f"{browser_name}_{clean_ext_id}"] = True
            except FileNotFoundError:
                results[f"{browser_name}_{clean_ext_id}"] = True
            except Exception:
                results[f"{browser_name}_{clean_ext_id}"] = False

    return {
        "success": all(results.values()) if results else True,
        "registry": results
    }


def is_extension_registered(browser: str = "chrome", extension_id: Optional[str] = None) -> bool:
    """Checks if browser extension registry key exists in HKCU."""
    if not HAS_WINREG or not sys.platform.startswith("win"):
        return False
    ext_id = extension_id or STATIC_EXTENSION_ID
    clean_ext_id = ext_id.strip().rstrip("/").replace("chrome-extension://", "")
    prefix = CHROME_EXT_KEY_PREFIX if browser.lower() == "chrome" else EDGE_EXT_KEY_PREFIX
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{prefix}\{clean_ext_id}", 0, winreg.KEY_READ)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def register_native_host(
    extension_id: Optional[str] = None,
    target_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Registers the Native Messaging Host in Windows Registry for both Chrome and Edge:
    1. Creates launcher batch script.
    2. Writes host manifest JSON.
    3. Adds registry keys in HKCU for NativeMessagingHosts and Extensions.
    """
    if not HAS_WINREG or not sys.platform.startswith("win"):
        return {
            "success": False,
            "error": "Windows Registry operations are only supported on Windows OS."
        }

    if not target_dir:
        if getattr(sys, "frozen", False):
            target_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            target_dir = os.path.dirname(os.path.abspath(__file__))

    os.makedirs(target_dir, exist_ok=True)

    bat_path = os.path.join(target_dir, "sd_host.bat")
    json_path = os.path.join(target_dir, f"{HOST_NAME}.json")

    # 1. Generate files (generate both sd_host.bat and turbo_host.bat for backward compatibility)
    generate_launcher_batch(bat_path)
    try:
        generate_launcher_batch(os.path.join(target_dir, "turbo_host.bat"))
    except Exception:
        pass
    allowed_origins = get_default_extension_origins(extension_id=extension_id, target_dir=target_dir)
    manifest_abs_path = generate_host_manifest(bat_path, json_path, allowed_origins)

    # 2. Write Native Messaging Host to Windows Registry
    registry_results = {}
    for browser_name, reg_key_path in [("Chrome", CHROME_REG_KEY), ("Edge", EDGE_REG_KEY)]:
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_key_path)
            winreg.SetValue(key, "", winreg.REG_SZ, manifest_abs_path)
            winreg.CloseKey(key)
            registry_results[browser_name] = True
        except Exception:
            registry_results[browser_name] = False

    # 3. Write Extension keys to Windows Registry
    ext_dir = os.path.join(target_dir, "extension")
    ext_results = register_browser_extensions(
        extension_id=extension_id,
        extension_dir=ext_dir if os.path.isdir(ext_dir) else None
    )

    all_success = all(registry_results.values())
    return {
        "success": all_success,
        "manifest_path": manifest_abs_path,
        "launcher_path": os.path.abspath(bat_path),
        "registry": registry_results,
        "allowed_origins": allowed_origins,
        "extensions": ext_results
    }


def unregister_native_host(unregister_extensions: bool = True) -> Dict[str, Any]:
    """
    Removes native messaging registry entries for Chrome and Edge from HKCU.
    Also cleans up legacy TurboDownloader host keys.
    Optionally unregisters extension keys.
    """
    if not HAS_WINREG or not sys.platform.startswith("win"):
        return {
            "success": False,
            "error": "Windows Registry operations are only supported on Windows OS."
        }

    results = {}
    for browser_name, reg_key_path, legacy_key_path in [
        ("Chrome", CHROME_REG_KEY, LEGACY_CHROME_REG_KEY),
        ("Edge", EDGE_REG_KEY, LEGACY_EDGE_REG_KEY)
    ]:
        # Delete primary key
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, reg_key_path)
            results[browser_name] = True
        except FileNotFoundError:
            results[browser_name] = True
        except Exception:
            results[browser_name] = False

        # Delete legacy key if present
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, legacy_key_path)
        except Exception:
            pass

    ext_results = None
    if unregister_extensions:
        ext_results = unregister_browser_extensions()

    return {
        "success": all(results.values()),
        "registry": results,
        "extensions": ext_results
    }


def is_registered(browser: str = "chrome") -> bool:
    """
    Checks if Native Messaging Host registry key exists and points to a valid manifest file.
    Checks primary com.smartdownload.host first, then falls back to legacy com.turbodownloader.host.
    """
    if not HAS_WINREG or not sys.platform.startswith("win"):
        return False

    is_chrome = browser.lower() == "chrome"
    primary_key = CHROME_REG_KEY if is_chrome else EDGE_REG_KEY
    legacy_key = LEGACY_CHROME_REG_KEY if is_chrome else LEGACY_EDGE_REG_KEY

    for reg_key_path in [primary_key, legacy_key]:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_key_path, 0, winreg.KEY_READ)
            manifest_path, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            if manifest_path and os.path.isfile(manifest_path):
                return True
        except Exception:
            continue
    return False


def get_status() -> Dict[str, Any]:
    """
    Returns registration status for Chrome and Edge along with manifest path.
    """
    chrome_ok = is_registered("chrome")
    edge_ok = is_registered("edge")
    chrome_ext_ok = is_extension_registered("chrome")
    edge_ext_ok = is_extension_registered("edge")

    manifest_path = ""
    if HAS_WINREG:
        for reg_key_path in [CHROME_REG_KEY, EDGE_REG_KEY]:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_key_path, 0, winreg.KEY_READ)
                val, _ = winreg.QueryValueEx(key, "")
                winreg.CloseKey(key)
                if val:
                    manifest_path = val
                    break
            except Exception:
                pass

    return {
        "chrome_registered": chrome_ok,
        "edge_registered": edge_ok,
        "chrome_extension_registered": chrome_ext_ok,
        "edge_extension_registered": edge_ext_ok,
        "is_registered": chrome_ok or edge_ok,
        "manifest_path": manifest_path
    }


def check_and_register_browser(
    force: bool = False,
    target_dir: Optional[str] = None,
    extension_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Idempotent and self-healing browser integration registration:
    1. Idempotent check (< 5ms): checks if NativeMessagingHosts registry keys for Chrome & Edge
       exist, point to the current manifest path, and the manifest file exists on disk.
    2. Also checks if extension registry keys exist.
    3. If already registered with the correct path, skips silently in < 5ms without overhead.
    4. If keys are missing or path changed, self-heals by cleanly updating the manifest
       and registry keys.
    """
    if not HAS_WINREG or not sys.platform.startswith("win"):
        return {"success": False, "skipped": True, "reason": "Not Windows OS"}

    t_start = time.perf_counter()

    if not target_dir:
        if getattr(sys, "frozen", False):
            target_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            target_dir = os.path.dirname(os.path.abspath(__file__))

    expected_manifest_path = os.path.normcase(os.path.abspath(os.path.join(target_dir, f"{HOST_NAME}.json")))
    ext_dir = os.path.join(target_dir, "extension")
    ext_id = extension_id or STATIC_EXTENSION_ID

    needs_registration = force

    if not needs_registration:
        # 1. Check manifest file existence and validate launcher target
        if not os.path.isfile(expected_manifest_path):
            needs_registration = True
        else:
            try:
                with open(expected_manifest_path, "r", encoding="utf-8") as mf:
                    mf_data = json.load(mf)
                mf_launcher = mf_data.get("path", "")
                if not mf_launcher or not os.path.isfile(mf_launcher):
                    needs_registration = True
                elif os.path.normcase(os.path.dirname(os.path.abspath(mf_launcher))) != os.path.normcase(os.path.abspath(target_dir)):
                    needs_registration = True
            except Exception:
                needs_registration = True

        if not needs_registration:
            # 2. Check Chrome NativeMessagingHost
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHROME_REG_KEY, 0, winreg.KEY_READ)
                val, _ = winreg.QueryValueEx(k, "")
                winreg.CloseKey(k)
                if not val or os.path.normcase(os.path.abspath(val)) != expected_manifest_path:
                    needs_registration = True
            except Exception:
                needs_registration = True

        if not needs_registration:
            # 3. Check Edge NativeMessagingHost
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, EDGE_REG_KEY, 0, winreg.KEY_READ)
                val, _ = winreg.QueryValueEx(k, "")
                winreg.CloseKey(k)
                if not val or os.path.normcase(os.path.abspath(val)) != expected_manifest_path:
                    needs_registration = True
            except Exception:
                needs_registration = True

        if not needs_registration:
            # 4. Check Chrome Extension key
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{CHROME_EXT_KEY_PREFIX}\{ext_id}", 0, winreg.KEY_READ)
                if os.path.isdir(ext_dir):
                    p_val, _ = winreg.QueryValueEx(k, "path")
                    if os.path.normcase(os.path.abspath(p_val)) != os.path.normcase(os.path.abspath(ext_dir)):
                        needs_registration = True
                winreg.CloseKey(k)
            except Exception:
                needs_registration = True

        if not needs_registration:
            # 5. Check Edge Extension key
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{EDGE_EXT_KEY_PREFIX}\{ext_id}", 0, winreg.KEY_READ)
                if os.path.isdir(ext_dir):
                    p_val, _ = winreg.QueryValueEx(k, "path")
                    if os.path.normcase(os.path.abspath(p_val)) != os.path.normcase(os.path.abspath(ext_dir)):
                        needs_registration = True
                winreg.CloseKey(k)
            except Exception:
                needs_registration = True

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    if not needs_registration:
        return {
            "success": True,
            "idempotent": True,
            "healed": False,
            "manifest_path": expected_manifest_path,
            "duration_ms": elapsed_ms,
            "message": "Already correctly registered (<5ms check)."
        }

    # Perform self-healing registration
    native_res = register_native_host(extension_id=ext_id, target_dir=target_dir)
    ext_res = register_browser_extensions(extension_id=ext_id, extension_dir=ext_dir if os.path.isdir(ext_dir) else None)

    total_ms = (time.perf_counter() - t_start) * 1000.0
    return {
        "success": native_res.get("success", False),
        "idempotent": False,
        "healed": True,
        "manifest_path": native_res.get("manifest_path", expected_manifest_path),
        "native_host": native_res,
        "extensions": ext_res,
        "duration_ms": total_ms
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Turbo Download Manager Browser Registration Utility")
    parser.add_argument("--register", action="store_true", help="Register Native Messaging Host in Windows Registry")
    parser.add_argument("--unregister", action="store_true", help="Unregister Native Messaging Host and Extensions")
    parser.add_argument("--status", action="store_true", help="Check current registration status")
    parser.add_argument("--check-and-register", action="store_true", help="Idempotent and self-healing registration check")
    parser.add_argument("--extension-id", type=str, default="", help="Optional extension ID to allow in manifest")

    args = parser.parse_args()

    if args.unregister:
        res = unregister_native_host()
        print(json.dumps(res, indent=2))
    elif args.status:
        res = get_status()
        print(json.dumps(res, indent=2))
    elif args.check_and_register:
        res = check_and_register_browser(extension_id=args.extension_id or None)
        print(json.dumps(res, indent=2))
    else:
        # Default action: register
        res = register_native_host(extension_id=args.extension_id or None)
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
