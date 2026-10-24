"""
========================================================================================
🌐 NATIVE MESSAGING HOST — Smart Download (SD)
========================================================================================
Implements Chromium & Microsoft Edge Native Messaging Host protocol (stdio):
1. Reads 32-bit length-prefixed JSON from standard input.
2. Dispatches commands ("ping", "download", "status") to Smart Download (SD).
3. Forwards download tasks to the desktop application's loopback bridge (127.0.0.1:9242).
4. Writes 32-bit length-prefixed JSON response to standard output.
5. Zero external dependencies — pure Python standard library.
========================================================================================
"""

import os
import sys
import io
import json
import struct
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

DEFAULT_BRIDGE_PORT = 9242
APP_VERSION = "2.0.0"
MAX_PAYLOAD_SIZE = 1024 * 1024  # 1 MB maximum message size for Chromium native messaging


def get_binary_stdin():
    """Returns a raw binary input stream for stdio reading across console and GUI subsystem."""
    if sys.stdin is not None and hasattr(sys.stdin, "buffer") and sys.stdin.buffer is not None:
        return sys.stdin.buffer
    if sys.platform.startswith("win"):
        try:
            import msvcrt, ctypes
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-10)  # STD_INPUT_HANDLE
            if h and h != -1 and k32.GetFileType(h) != 0:
                fd = msvcrt.open_osfhandle(h, os.O_RDONLY)
                return io.open(fd, "rb", closefd=False)
        except Exception:
            pass
    return sys.stdin


def get_binary_stdout():
    """Returns a raw binary output stream for stdio writing across console and GUI subsystem."""
    if sys.stdout is not None and hasattr(sys.stdout, "buffer") and sys.stdout.buffer is not None:
        return sys.stdout.buffer
    if sys.platform.startswith("win"):
        try:
            import msvcrt, ctypes
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            if h and h != -1 and k32.GetFileType(h) != 0:
                fd = msvcrt.open_osfhandle(h, os.O_WRONLY)
                return io.open(fd, "wb", closefd=False)
        except Exception:
            pass
    return sys.stdout


def read_message(stream=None) -> Optional[Dict[str, Any]]:
    """
    Reads a 32-bit unsigned length prefix followed by UTF-8 JSON message from binary stdin.
    Returns None on EOF or invalid stream.
    """
    if stream is None:
        stream = get_binary_stdin()

    if stream is None:
        return None

    try:
        raw_length = stream.read(4)
        if not raw_length or len(raw_length) < 4:
            return None

        # Chromium length prefix is 32-bit unsigned little-endian
        message_length = struct.unpack("<I", raw_length)[0]
        if message_length <= 0 or message_length > MAX_PAYLOAD_SIZE:
            return None

        raw_data = stream.read(message_length)
        if len(raw_data) < message_length:
            return None

        return json.loads(raw_data.decode("utf-8"))
    except Exception:
        return None


def send_message(message: Dict[str, Any], stream=None) -> bool:
    """
    Encodes JSON message and writes 32-bit length prefix followed by payload to binary stdout.
    Flushes stream immediately.
    """
    if stream is None:
        stream = get_binary_stdout()

    if stream is None:
        return False

    try:
        encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
        stream.write(struct.pack("<I", len(encoded)))
        stream.write(encoded)
        stream.flush()
        return True
    except Exception:
        return False


def handle_payload(payload: Dict[str, Any], port: int = DEFAULT_BRIDGE_PORT) -> Dict[str, Any]:
    """
    Processes incoming native messaging payload and routes to local Turbo Download Manager.
    """
    if not isinstance(payload, dict):
        return {"success": False, "error": "Payload must be a JSON dictionary"}

    action = payload.get("action", "download")

    if action in ("ping", "status"):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/ping")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "success": True,
                    "host": "Smart Download Native Host",
                    "app_online": True,
                    "app_info": data
                }
        except Exception:
            return {
                "success": True,
                "host": "Smart Download Native Host",
                "app_online": False,
                "message": "Native host is active, but Smart Download (SD) desktop app is offline."
            }

    elif action in ("download", "sendUrl", "intercept"):
        raw_url = payload.get("url", "").strip()
        if not raw_url:
            return {"success": False, "error": "Missing required 'url' parameter"}

        # Build download dispatch request for loopback bridge
        forward_data = {
            "url": raw_url,
            "filename": str(payload.get("filename", "")).strip(),
            "referrer": str(payload.get("referrer", "")).strip(),
            "headers": payload.get("headers", {}) if isinstance(payload.get("headers"), dict) else {},
            "start_immediately": bool(payload.get("start_immediately", True))
        }

        try:
            post_body = json.dumps(forward_data).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/download",
                data=post_body,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result
        except urllib.error.URLError as e:
            return {
                "success": False,
                "error": f"Smart Download (SD) desktop app is not running or unreachable on port {port}: {e}"
            }
        except Exception as e:
            return {"success": False, "error": f"Bridge request failed: {e}"}

    return {"success": False, "error": f"Unrecognized action '{action}'"}


def run_host(port: int = DEFAULT_BRIDGE_PORT):
    """
    Main loop for Native Messaging Host process. Reads messages until stdin closes.
    """
    # Configure binary I/O mode for Windows stdio
    if sys.platform.startswith("win"):
        try:
            import msvcrt
            if sys.stdin is not None and hasattr(sys.stdin, "fileno"):
                msvcrt.setmode(sys.stdin.fileno(), 0x8000)  # _O_BINARY
        except Exception:
            pass
        try:
            import msvcrt
            if sys.stdout is not None and hasattr(sys.stdout, "fileno"):
                msvcrt.setmode(sys.stdout.fileno(), 0x8000) # _O_BINARY
        except Exception:
            pass

    while True:
        try:
            message = read_message()
            if message is None:
                break
            response = handle_payload(message, port=port)
            send_message(response)
        except Exception as e:
            try:
                send_message({"success": False, "error": str(e)})
            except Exception:
                pass
            break


if __name__ == "__main__":
    run_host()
