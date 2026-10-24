"""
Backward compatibility entry-point for native_messaging_host.
Logic has moved to smart_download.services.browser.native_host.
"""
import sys
import os

_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_src_dir) and _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from smart_download.services.browser.native_host import *
from smart_download.services.browser.native_host import (
    get_binary_stdin,
    get_binary_stdout,
    read_message,
    send_message,
    handle_payload,
    run_host,
    DEFAULT_BRIDGE_PORT,
    APP_VERSION,
    MAX_PAYLOAD_SIZE,
)

handle_native_message = handle_payload
run_native_messaging_host = run_host

if __name__ == "__main__":
    run_host()
