"""
Backward compatibility entry-point for updater.
Logic has moved to smart_download.services.updater_service.
"""
import sys
import os

_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_src_dir) and _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

try:
    from smart_download.services.core_patch_updater import init_core_loader
    init_core_loader()
except Exception:
    pass

from smart_download.services.updater_service import *
from smart_download.services.updater_service import (
    APP_NAME,
    APP_ID,
    APP_VERSION,
    GITHUB_REPO_OWNER,
    GITHUB_REPO_NAME,
    GITHUB_LATEST_RELEASE_API,
    YTDLP_PYPI_JSON_API,
    YTDLP_GITHUB_LATEST_API,
    get_app_data_dir,
    get_ytdlp_plugin_dir,
    _get_ssl_context,
    _get_verified_ssl_context,
    _ExternalYtDlpFinder,
    parse_version,
    is_newer_version,
    is_version_ge,
    YtDlpAutoUpdater,
    AppAutoUpdater,
    build_core_patch_zip,
    CoreHotPatchUpdater,
    _ExternalCoreFinder,
    get_core_plugin_dir,
    init_core_loader,
)

if __name__ == "__main__":
    import smart_download.services.updater_service as _us
    if hasattr(_us, "main"):
        _us.main()
