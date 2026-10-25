"""
========================================================================================
🚀 SMART DOWNLOAD (SD) — Windows Standalone Installer & Uninstaller Entrypoint
========================================================================================
Clean <120-line entry point and backward compatibility shim.
Core installation logic resides in smart_download.installer.
========================================================================================
"""
import os
import sys
import json
import types
import argparse
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_src_dir) and _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from smart_download.installer import (
    APP_NAME, APP_ID, APP_VERSION, APP_PUBLISHER, APP_URL,
    LEGACY_APP_ID, LEGACY_UNINSTALL_REG_KEY, UNINSTALL_REG_KEY,
    STARTUP_REG_KEY, STARTUP_REG_KEY_NAME, LEGACY_STARTUP_REG_KEY_NAME,
    TASK_NAME, LEGACY_TASK_NAME, HAS_WINREG,
    get_default_install_dir, DEFAULT_INSTALL_DIR,
    get_desktop_dir, get_start_menu_programs_dir, get_startup_dir,
    enable_high_dpi_awareness, create_windows_shortcut,
    register_startup_entries, unregister_startup_entries,
    register_uninstall_entry, unregister_uninstall_entry,
    find_payload_sources, terminate_running_app,
    install_application, uninstall_application,
    is_admin, run_silent_install, get_payload_dir,
    kill_running_instances, create_shortcut, register_uninstaller,
    perform_installation, InstallerGUI, InstallerWizardGUI,
)
import smart_download.installer.installer_ops as _installer_ops
import smart_download.installer.installer_registry as _installer_reg
import smart_download.installer.installer_gui as _installer_gui

class _InstallerShim(types.ModuleType):
    """Synchronizes monkeypatches across installer modules for backward test compatibility."""
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for sub in (_installer_ops, _installer_reg, _installer_gui):
            if hasattr(sub, name):
                setattr(sub, name, value)

    def __getattribute__(self, name):
        if not name.startswith("__"):
            for sub in (_installer_ops, _installer_reg, _installer_gui):
                if hasattr(sub, name):
                    return getattr(sub, name)
        return super().__getattribute__(name)

sys.modules[__name__].__class__ = _InstallerShim



def main():
    parser = argparse.ArgumentParser(description=f"{APP_NAME} Installer & Setup Utility", prefix_chars="-/")
    parser.add_argument("--silent", "/S", "-s", action="store_true", help="Run unattended installation/uninstallation")
    parser.add_argument("--uninstall", "/U", "-u", action="store_true", help="Uninstall application")
    parser.add_argument("--dir", type=str, default=DEFAULT_INSTALL_DIR, help="Target installation folder")
    parser.add_argument("--no-launch", action="store_true", help="Do not launch application after installation")
    parser.add_argument("--launch", action="store_true", help="Launch application after silent installation")
    parser.add_argument("--no-shortcuts", action="store_true", help="Do not create desktop or start menu shortcuts")
    parser.add_argument("--no-browser", action="store_true", help="Do not register browser native messaging")
    parser.add_argument("--no-startup", action="store_true", help="Do not register auto-start on boot")

    args, unknown = parser.parse_known_args()

    exe_name = os.path.basename(sys.executable).lower()
    script_name = os.path.basename(__file__).lower()
    is_uninstaller_binary = "uninstall" in exe_name or "uninstall" in script_name
    mode = "uninstall" if (args.uninstall or "/U" in sys.argv or "--uninstall" in sys.argv or is_uninstaller_binary) else "install"
    silent = args.silent or "/S" in sys.argv or "--silent" in sys.argv

    target_dir = args.dir
    if mode == "uninstall" and args.dir == DEFAULT_INSTALL_DIR:
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.isfile(os.path.join(exe_dir, "SmartDownload.exe")) or os.path.isfile(os.path.join(exe_dir, "TurboDownloader.exe")):
            target_dir = exe_dir

    if silent:
        if mode == "install":
            res = install_application(
                target_dir=target_dir,
                create_desktop=not args.no_shortcuts,
                create_start_menu=not args.no_shortcuts,
                register_browser=not args.no_browser,
                register_startup=not args.no_startup
            )
            if args.launch and res.get("success") and os.path.isfile(res.get("exe_path", "")):
                try:
                    subprocess.Popen([res["exe_path"]], cwd=os.path.dirname(res["exe_path"]))
                except Exception:
                    pass
            print(json.dumps(res, indent=2))
            sys.exit(0 if res.get("success") else 1)
        else:
            res = uninstall_application(target_dir=target_dir)
            print(json.dumps(res, indent=2))
            sys.exit(0 if res.get("success") else 1)

    import tkinter as tk
    root = tk.Tk()
    app = InstallerGUI(root, mode=mode, target_dir=target_dir)
    root.mainloop()


if __name__ == "__main__":
    main()
