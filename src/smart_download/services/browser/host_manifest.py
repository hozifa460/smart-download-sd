"""
Host manifest and launcher batch generation for browser native messaging.
"""
import os
import sys
import json
import hashlib
from typing import Dict, List, Optional, Any

HOST_NAME = "com.smartdownload.host"
HOST_DESCRIPTION = "Smart Download (SD) Native Messaging Host"
APP_VERSION = "2.0.0"

LEGACY_HOST_NAME = "com.turbodownloader.host"
LEGACY_CHROME_REG_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{LEGACY_HOST_NAME}"
LEGACY_EDGE_REG_KEY = rf"Software\Microsoft\Edge\NativeMessagingHosts\{LEGACY_HOST_NAME}"

CHROME_REG_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"
EDGE_REG_KEY = rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}"

CHROME_EXT_KEY_PREFIX = r"Software\Google\Chrome\Extensions"
EDGE_EXT_KEY_PREFIX = r"Software\Microsoft\Edge\Extensions"
CHROME_UPDATE_URL = "https://clients2.google.com/service/update2/crx"
EDGE_UPDATE_URL = "https://edge.microsoft.com/extensionwho10/service/update2/crx"

# Deterministic static extension ID corresponding to the extension's RSA public key in manifest.json
STATIC_EXTENSION_ID = "gokbjcmdmbjlngbdpanlccbfpmppjloa"


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
        return "smartdownloadextensionid"


def get_project_root() -> str:
    """Returns the application/repository root directory in both source and frozen environments."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    curr = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if (
            os.path.isdir(os.path.join(curr, "extension"))
            or os.path.isdir(os.path.join(curr, "assets"))
            or os.path.isdir(os.path.join(curr, "scripts"))
        ):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))


def get_default_extension_origins(
    extension_id: Optional[str] = None,
    extension_dir: Optional[str] = None,
    target_dir: Optional[str] = None
) -> List[str]:
    """
    Compiles list of allowed extension origins for Chrome and Edge.
    """
    origins = [
        "chrome-extension://smart-download-integration/",
        "chrome-extension://com.smartdownload.extension/",
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
        root_dir = get_project_root()
        candidate_ext_dirs.append(os.path.join(root_dir, "extension"))
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_ext_dirs.append(os.path.join(base_dir, "extension"))
        candidate_ext_dirs.append(os.path.join(os.getcwd(), "extension"))

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
        "if exist \"%SCRIPT_DIR%..\\SmartDownload.exe\" (\r\n"
        "    \"%SCRIPT_DIR%..\\SmartDownload.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "if exist \"%SCRIPT_DIR%TurboDownloader.exe\" (\r\n"
        "    \"%SCRIPT_DIR%TurboDownloader.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "if exist \"%SCRIPT_DIR%..\\TurboDownloader.exe\" (\r\n"
        "    \"%SCRIPT_DIR%..\\TurboDownloader.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "\r\n"
        "REM 2. Dist folder fallback\r\n"
        "if exist \"%SCRIPT_DIR%dist\\SmartDownload.exe\" (\r\n"
        "    \"%SCRIPT_DIR%dist\\SmartDownload.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "if exist \"%SCRIPT_DIR%..\\dist\\SmartDownload.exe\" (\r\n"
        "    \"%SCRIPT_DIR%..\\dist\\SmartDownload.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "if exist \"%SCRIPT_DIR%dist\\TurboDownloader.exe\" (\r\n"
        "    \"%SCRIPT_DIR%dist\\TurboDownloader.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "if exist \"%SCRIPT_DIR%..\\dist\\TurboDownloader.exe\" (\r\n"
        "    \"%SCRIPT_DIR%..\\dist\\TurboDownloader.exe\" --native-host %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "\r\n"
        "REM 3. Development source mode: Execute native_messaging_host.py directly via python (<50ms)\r\n"
        "if exist \"%SCRIPT_DIR%native_messaging_host.py\" (\r\n"
        "    python \"%SCRIPT_DIR%native_messaging_host.py\" %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "if exist \"%SCRIPT_DIR%..\\native_messaging_host.py\" (\r\n"
        "    python \"%SCRIPT_DIR%..\\native_messaging_host.py\" %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "if exist \"%SCRIPT_DIR%..\\src\\smart_download\\services\\browser\\native_host.py\" (\r\n"
        "    python \"%SCRIPT_DIR%..\\src\\smart_download\\services\\browser\\native_host.py\" %*\r\n"
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
        "    if exist \"%SCRIPT_DIR%..\\native_messaging_host.py\" (\r\n"
        "        py -3 \"%SCRIPT_DIR%..\\native_messaging_host.py\" %*\r\n"
        "        goto :EOF\r\n"
        "    )\r\n"
        "    if exist \"%SCRIPT_DIR%..\\src\\smart_download\\services\\browser\\native_host.py\" (\r\n"
        "        py -3 \"%SCRIPT_DIR%..\\src\\smart_download\\services\\browser\\native_host.py\" %*\r\n"
        "        goto :EOF\r\n"
        "    )\r\n"
        ")\r\n"
        "\r\n"
        "REM 5. Final fallback\r\n"
        "if exist \"%SCRIPT_DIR%..\\native_messaging_host.py\" (\r\n"
        "    python \"%SCRIPT_DIR%..\\native_messaging_host.py\" %*\r\n"
        "    goto :EOF\r\n"
        ")\r\n"
        "python \"%SCRIPT_DIR%native_messaging_host.py\" %*\r\n"
    )

    with open(output_bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    return os.path.abspath(output_bat_path)
