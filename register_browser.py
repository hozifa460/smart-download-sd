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
from typing import Dict, List, Optional, Any

HOST_NAME = "com.turbodownloader.host"
HOST_DESCRIPTION = "Turbo Download Manager Pro Native Messaging Host"

CHROME_REG_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"
EDGE_REG_KEY = rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}"

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


def get_default_extension_origins(extension_id: Optional[str] = None) -> List[str]:
    """
    Compiles list of allowed extension origins for Chrome and Edge.
    """
    origins = [
        "chrome-extension://turbo-downloader-integration/",
        "chrome-extension://com.turbodownloader.extension/",
        f"chrome-extension://{STATIC_EXTENSION_ID}/"
    ]

    # Compute ID for local unpacked extension folder if it exists
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        ext_dir = os.path.join(exe_dir, "extension")
        if not os.path.isdir(ext_dir) and hasattr(sys, "_MEIPASS"):
            ext_dir = os.path.join(sys._MEIPASS, "extension")
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ext_dir = os.path.join(base_dir, "extension")

    if os.path.isdir(ext_dir):
        computed_id = compute_unpacked_extension_id(ext_dir)
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
    Prefers ultra-fast Python execution (<50ms) to avoid PyInstaller unpack overhead,
    falling back seamlessly to TurboDownloader.exe --native-host when standalone.
    """
    bat_content = (
        "@echo off\r\n"
        "setlocal\r\n"
        "REM Launcher for Turbo Download Manager Native Messaging Host\r\n"
        "set SCRIPT_DIR=%~dp0\r\n"
        "\r\n"
        "REM 1. Fast path: If python is available on system, run script directly (<50ms)\r\n"
        "where python >nul 2>nul\r\n"
        "if %ERRORLEVEL% equ 0 (\r\n"
        "    if exist \"%SCRIPT_DIR%native_messaging_host.py\" (\r\n"
        "        python \"%SCRIPT_DIR%native_messaging_host.py\" %*\r\n"
        "        goto :EOF\r\n"
        "    )\r\n"
        "    if exist \"%SCRIPT_DIR%..\\native_messaging_host.py\" (\r\n"
        "        python \"%SCRIPT_DIR%..\\native_messaging_host.py\" %*\r\n"
        "        goto :EOF\r\n"
        "    )\r\n"
        ")\r\n"
        "\r\n"
        "REM 2. Check py launcher\r\n"
        "where py >nul 2>nul\r\n"
        "if %ERRORLEVEL% equ 0 (\r\n"
        "    if exist \"%SCRIPT_DIR%native_messaging_host.py\" (\r\n"
        "        py -3 \"%SCRIPT_DIR%native_messaging_host.py\" %*\r\n"
        "        goto :EOF\r\n"
        "    )\r\n"
        "    if exist \"%SCRIPT_DIR%..\\native_messaging_host.py\" (\r\n"
        "        py -3 \"%SCRIPT_DIR%..\\native_messaging_host.py\" %*\r\n"
        "        goto :EOF\r\n"
        "    )\r\n"
        ")\r\n"
        "\r\n"
        "REM 3. Standalone binary fallback\r\n"
        "if exist \"%SCRIPT_DIR%TurboDownloader.exe\" (\r\n"
        "    \"%SCRIPT_DIR%TurboDownloader.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ") else if exist \"%SCRIPT_DIR%dist\\TurboDownloader.exe\" (\r\n"
        "    \"%SCRIPT_DIR%dist\\TurboDownloader.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "\r\n"
        "REM 4. Final attempt\r\n"
        "python \"%SCRIPT_DIR%native_messaging_host.py\" %*\r\n"
    )

    with open(output_bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    return os.path.abspath(output_bat_path)


def register_native_host(
    extension_id: Optional[str] = None,
    target_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Registers the Native Messaging Host in Windows Registry for both Chrome and Edge:
    1. Creates launcher batch script.
    2. Writes host manifest JSON.
    3. Adds registry keys in HKCU.
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

    bat_path = os.path.join(target_dir, "turbo_host.bat")
    json_path = os.path.join(target_dir, f"{HOST_NAME}.json")

    # 1. Generate files
    generate_launcher_batch(bat_path)
    allowed_origins = get_default_extension_origins(extension_id)
    manifest_abs_path = generate_host_manifest(bat_path, json_path, allowed_origins)

    # 2. Write to Windows Registry
    registry_results = {}
    for browser_name, reg_key_path in [("Chrome", CHROME_REG_KEY), ("Edge", EDGE_REG_KEY)]:
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_key_path)
            winreg.SetValue(key, "", winreg.REG_SZ, manifest_abs_path)
            winreg.CloseKey(key)
            registry_results[browser_name] = True
        except Exception as e:
            registry_results[browser_name] = False

    all_success = all(registry_results.values())
    return {
        "success": all_success,
        "manifest_path": manifest_abs_path,
        "launcher_path": os.path.abspath(bat_path),
        "registry": registry_results,
        "allowed_origins": allowed_origins
    }


def unregister_native_host() -> Dict[str, Any]:
    """
    Removes native messaging registry entries for Chrome and Edge from HKCU.
    """
    if not HAS_WINREG or not sys.platform.startswith("win"):
        return {
            "success": False,
            "error": "Windows Registry operations are only supported on Windows OS."
        }

    results = {}
    for browser_name, reg_key_path in [("Chrome", CHROME_REG_KEY), ("Edge", EDGE_REG_KEY)]:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, reg_key_path)
            results[browser_name] = True
        except FileNotFoundError:
            results[browser_name] = True  # Already deleted
        except Exception as e:
            results[browser_name] = False

    return {
        "success": all(results.values()),
        "registry": results
    }


def is_registered(browser: str = "chrome") -> bool:
    """
    Checks if Native Messaging Host registry key exists and points to a valid manifest file.
    """
    if not HAS_WINREG or not sys.platform.startswith("win"):
        return False

    reg_key_path = CHROME_REG_KEY if browser.lower() == "chrome" else EDGE_REG_KEY
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_key_path, 0, winreg.KEY_READ)
        manifest_path, _ = winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)
        return bool(manifest_path and os.path.isfile(manifest_path))
    except Exception:
        return False


def get_status() -> Dict[str, Any]:
    """
    Returns registration status for Chrome and Edge along with manifest path.
    """
    chrome_ok = is_registered("chrome")
    edge_ok = is_registered("edge")

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
        "is_registered": chrome_ok or edge_ok,
        "manifest_path": manifest_path
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Turbo Download Manager Browser Registration Utility")
    parser.add_argument("--register", action="store_true", help="Register Native Messaging Host in Windows Registry")
    parser.add_argument("--unregister", action="store_true", help="Unregister Native Messaging Host")
    parser.add_argument("--status", action="store_true", help="Check current registration status")
    parser.add_argument("--extension-id", type=str, default="", help="Optional extension ID to allow in manifest")

    args = parser.parse_args()

    if args.unregister:
        res = unregister_native_host()
        print(json.dumps(res, indent=2))
    elif args.status:
        res = get_status()
        print(json.dumps(res, indent=2))
    else:
        # Default action: register
        res = register_native_host(extension_id=args.extension_id or None)
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
