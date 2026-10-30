"""
Smart Download entry point script.
"""
import sys
import os

_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from smart_download.ui.main_window import main

if __name__ == "__main__":
    if "--preview-html" in sys.argv:
        try:
            idx = sys.argv.index("--preview-html")
            if idx + 1 < len(sys.argv):
                html_target = sys.argv[idx + 1]
                import webview
                webview.create_window("Smart Download — Video Preview", html_target, width=860, height=560)
                webview.start()
        except Exception:
            pass
    from smart_download.services.single_instance import early_single_instance_guard
    early_single_instance_guard()
    main()
