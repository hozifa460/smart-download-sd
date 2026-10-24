"""
Backward compatibility entry-point for browser_bridge.
Logic has moved to smart_download.services.browser.bridge_server.
"""
import sys
import os

_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_src_dir) and _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from smart_download.services.browser.bridge_server import *
from smart_download.services.browser.bridge_server import (
    BrowserBridgeServer,
    BrowserBridgeHandler,
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    APP_VERSION,
)

if __name__ == "__main__":
    import smart_download.services.browser.bridge_server as _bb
    if hasattr(_bb, "main"):
        _bb.main()
