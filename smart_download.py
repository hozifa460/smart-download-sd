"""
Root shim enabling 'import smart_download' directly from repository root.
Redirects to src/smart_download package.
"""
import os
import sys

_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_src_dir) and _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Remove this module from sys.modules temporarily so real package can be imported
this_module = sys.modules.pop("smart_download", None)
try:
    import smart_download
except Exception:
    if this_module:
        sys.modules["smart_download"] = this_module
    raise
