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
    main()
