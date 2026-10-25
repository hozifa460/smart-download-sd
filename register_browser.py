"""
Backward compatibility entry-point for register_browser.
Logic has moved to smart_download.services.browser.registry.
"""
import sys
import os

_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_src_dir) and _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from smart_download.services.browser.registry import *
from smart_download.services.browser.registry import (
    register_native_host,
    unregister_native_host,
    check_and_register_browser,
    register_browser_extensions,
    unregister_browser_extensions,
    is_registered,
    is_extension_registered,
    get_status,
    generate_launcher_batch,
    generate_host_manifest,
    get_default_extension_origins,
    compute_unpacked_extension_id,
    get_project_root,
    HOST_NAME,
    HOST_DESCRIPTION,
    APP_VERSION,
    CHROME_REG_KEY,
    EDGE_REG_KEY,
)

if __name__ == "__main__":
    import smart_download.services.browser.registry as _r
    if hasattr(_r, "main"):
        _r.main()
