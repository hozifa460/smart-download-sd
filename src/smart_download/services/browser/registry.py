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

try:
    from .host_manifest import (
        HOST_NAME,
        HOST_DESCRIPTION,
        APP_VERSION,
        LEGACY_HOST_NAME,
        LEGACY_CHROME_REG_KEY,
        LEGACY_EDGE_REG_KEY,
        CHROME_REG_KEY,
        EDGE_REG_KEY,
        CHROME_EXT_KEY_PREFIX,
        EDGE_EXT_KEY_PREFIX,
        CHROME_UPDATE_URL,
        EDGE_UPDATE_URL,
        STATIC_EXTENSION_ID,
        compute_unpacked_extension_id,
        get_project_root,
        get_default_extension_origins,
        generate_host_manifest,
        generate_launcher_batch,
    )
except (ImportError, ValueError):
    from host_manifest import (
        HOST_NAME,
        HOST_DESCRIPTION,
        APP_VERSION,
        LEGACY_HOST_NAME,
        LEGACY_CHROME_REG_KEY,
        LEGACY_EDGE_REG_KEY,
        CHROME_REG_KEY,
        EDGE_REG_KEY,
        CHROME_EXT_KEY_PREFIX,
        EDGE_EXT_KEY_PREFIX,
        CHROME_UPDATE_URL,
        EDGE_UPDATE_URL,
        STATIC_EXTENSION_ID,
        compute_unpacked_extension_id,
        get_project_root,
        get_default_extension_origins,
        generate_host_manifest,
        generate_launcher_batch,
    )

# Try importing winreg on Windows
try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False


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
            ext_candidate = os.path.join(get_project_root(), "extension")
            if not os.path.isdir(ext_candidate):
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

    ext_version = APP_VERSION
    if extension_dir and os.path.isfile(os.path.join(extension_dir, "manifest.json")):
        try:
            with open(os.path.join(extension_dir, "manifest.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
                ext_version = data.get("version", APP_VERSION)
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
            target_dir = get_project_root()

    os.makedirs(target_dir, exist_ok=True)

    bat_path = os.path.join(target_dir, "sd_host.bat")
    json_path = os.path.join(target_dir, f"{HOST_NAME}.json")

    # 1. Generate launcher batch and host manifest
    generate_launcher_batch(bat_path)
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
            target_dir = get_project_root()

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
    parser = argparse.ArgumentParser(description="Smart Download (SD) Browser Registration Utility")
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
