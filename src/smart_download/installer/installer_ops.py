"""
Core installation and uninstallation logic for Smart Download (SD).
"""
import os
import sys
import shutil
import json
import time
import subprocess
from typing import Dict, List, Optional, Callable, Any

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

from .installer_registry import (
    APP_NAME,
    APP_ID,
    APP_VERSION,
    APP_PUBLISHER,
    APP_URL,
    LEGACY_APP_ID,
    LEGACY_UNINSTALL_REG_KEY,
    UNINSTALL_REG_KEY,
    STARTUP_REG_KEY,
    STARTUP_REG_KEY_NAME,
    LEGACY_STARTUP_REG_KEY_NAME,
    TASK_NAME,
    LEGACY_TASK_NAME,
    enable_high_dpi_awareness,
    create_windows_shortcut,
    register_startup_entries,
    unregister_startup_entries,
    register_uninstall_entry,
    unregister_uninstall_entry,
)

def get_default_install_dir() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.expanduser(r"~\AppData\Local")
    return os.path.normpath(os.path.join(local_app_data, "Programs", APP_ID))

DEFAULT_INSTALL_DIR = get_default_install_dir()
UNINSTALL_REG_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"

STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_KEY_NAME = "SmartDownload"
LEGACY_STARTUP_REG_KEY_NAME = "TurboDownloader"
TASK_NAME = "SmartDownloadAutoStart"
LEGACY_TASK_NAME = "TurboDownloaderAutoStart"


def get_desktop_dir() -> str:
    """Gets the actual Desktop directory path, resolving OneDrive and Windows Shell redirection."""
    if HAS_WINREG and sys.platform.startswith("win"):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            raw_path, _ = winreg.QueryValueEx(k, "Desktop")
            winreg.CloseKey(k)
            expanded = os.path.normpath(os.path.expandvars(raw_path))
            if os.path.isdir(expanded):
                return expanded
        except Exception:
            pass
    # Fallback
    userprofile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    onedrive_desktop = os.path.join(userprofile, "OneDrive", "Desktop")
    if os.path.isdir(onedrive_desktop):
        return onedrive_desktop
    return os.path.join(userprofile, "Desktop")


def get_start_menu_programs_dir() -> str:
    """Gets the user Start Menu Programs directory path."""
    if HAS_WINREG and sys.platform.startswith("win"):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            raw_path, _ = winreg.QueryValueEx(k, "Programs")
            winreg.CloseKey(k)
            expanded = os.path.normpath(os.path.expandvars(raw_path))
            if os.path.isdir(expanded):
                return expanded
        except Exception:
            pass
    # Fallback
    return os.path.normpath(os.path.join(os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming")),
                                        "Microsoft", "Windows", "Start Menu", "Programs"))


def get_startup_dir() -> str:
    """Gets the user Startup directory path (shell:startup)."""
    if HAS_WINREG and sys.platform.startswith("win"):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            raw_path, _ = winreg.QueryValueEx(k, "Startup")
            winreg.CloseKey(k)
            if raw_path and str(raw_path).strip():
                expanded = os.path.normpath(os.path.expandvars(str(raw_path).strip()))
                if os.path.isabs(expanded) and os.path.isdir(expanded):
                    return expanded
        except Exception:
            pass
    # Fallback
    return os.path.normpath(os.path.join(os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming")),
                                        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"))


def find_payload_sources() -> Dict[str, str]:
    """Finds payload files from PyInstaller bundle, dist folder, or current project root."""
    sources = {}
    base_dirs = []

    # 1. PyInstaller _MEIPASS bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dirs.append(os.path.join(sys._MEIPASS, "payload"))
        base_dirs.append(sys._MEIPASS)

    # 2. Local workspace directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    proj_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
    for d in [proj_root, current_dir, os.getcwd()]:
        base_dirs.append(os.path.join(d, "installer_payload"))
        base_dirs.append(os.path.join(d, "dist"))
        base_dirs.append(os.path.join(d, "assets"))
        base_dirs.append(os.path.join(d, "scripts"))
        base_dirs.append(d)

    for b in base_dirs:
        cand = os.path.join(b, "SmartDownload.exe")
        if os.path.isfile(cand) and "SmartDownload.exe" not in sources:
            sources["SmartDownload.exe"] = cand
        cand_legacy = os.path.join(b, "TurboDownloader.exe")
        if os.path.isfile(cand_legacy) and "TurboDownloader.exe" not in sources:
            sources["TurboDownloader.exe"] = cand_legacy

    for b in base_dirs:
        for cand in [os.path.join(b, "app_icon.ico"), os.path.join(b, "assets", "app_icon.ico")]:
            if os.path.isfile(cand) and "app_icon.ico" not in sources:
                sources["app_icon.ico"] = cand

    for b in base_dirs:
        for cand in [os.path.join(b, "app_icon.png"), os.path.join(b, "assets", "app_icon.png")]:
            if os.path.isfile(cand) and "app_icon.png" not in sources:
                sources["app_icon.png"] = cand

    for b in base_dirs:
        cand = os.path.join(b, "extension")
        if os.path.isdir(cand) and "extension" not in sources:
            sources["extension"] = cand

    for b in base_dirs:
        for cand in [os.path.join(b, "sd_host.bat"), os.path.join(b, "scripts", "sd_host.bat")]:
            if os.path.isfile(cand) and "sd_host.bat" not in sources:
                sources["sd_host.bat"] = cand
        cand_legacy = os.path.join(b, "turbo_host.bat")
        if os.path.isfile(cand_legacy) and "turbo_host.bat" not in sources:
            sources["turbo_host.bat"] = cand_legacy

    for b in base_dirs:
        cand = os.path.join(b, "com.smartdownload.host.json")
        if os.path.isfile(cand) and "com.smartdownload.host.json" not in sources:
            sources["com.smartdownload.host.json"] = cand
        cand_legacy = os.path.join(b, "com.turbodownloader.host.json")
        if os.path.isfile(cand_legacy) and "com.turbodownloader.host.json" not in sources:
            sources["com.turbodownloader.host.json"] = cand

    for b in base_dirs:
        cand = os.path.join(b, "register_browser.py")
        if os.path.isfile(cand) and "register_browser.py" not in sources:
            sources["register_browser.py"] = cand
        cand_hm = os.path.join(b, "host_manifest.py")
        if os.path.isfile(cand_hm) and "host_manifest.py" not in sources:
            sources["host_manifest.py"] = cand_hm

    return sources



def terminate_running_app():
    """Terminates any active SmartDownload.exe or TurboDownloader.exe processes to allow overwriting."""
    if not sys.platform.startswith("win"):
        return
    for proc in ("SmartDownload.exe", "TurboDownloader.exe"):
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", proc],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5
            )
        except Exception:
            pass
    time.sleep(0.3)


def install_application(
    target_dir: str = DEFAULT_INSTALL_DIR,
    create_desktop: bool = True,
    create_start_menu: bool = True,
    register_browser: bool = True,
    register_startup: bool = True,
    progress_cb: Optional[Callable[[float, str], None]] = None
) -> Dict[str, Any]:
    """
    Core installation workflow:
    1. Terminate running instance
    2. Create target directory
    3. Copy application binaries, assets, and extensions
    4. Copy uninstaller
    5. Create Desktop and Start Menu shortcuts
    6. Register Chrome/Edge Native Messaging Host and Extensions
    7. Register Windows Uninstall entry
    """
    def _notify(pct: float, msg: str):
        if progress_cb:
            try:
                progress_cb(pct, msg)
            except Exception:
                pass

    _notify(0.05, "Stopping active application instances...")
    terminate_running_app()

    _notify(0.15, "Preparing destination directory...")
    target_dir = os.path.abspath(target_dir)
    os.makedirs(target_dir, exist_ok=True)

    _notify(0.30, "Extracting application binaries and resources...")
    sources = find_payload_sources()

    # Purge stale core_plugin so fresh install is never overridden by older plugin
    try:
        try:
            from ..services.core_patch_updater import get_core_plugin_dir
            stale_plugin_dir = get_core_plugin_dir()
        except Exception:
            try:
                from smart_download.services.core_patch_updater import get_core_plugin_dir
                stale_plugin_dir = get_core_plugin_dir()
            except Exception:
                appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
                stale_plugin_dir = os.path.join(appdata, "SmartDownload", "core_plugin")
        if stale_plugin_dir and os.path.isdir(stale_plugin_dir):
            shutil.rmtree(stale_plugin_dir, ignore_errors=True)
    except Exception:
        pass

    # 1. Copy SmartDownload.exe
    exe_dest = os.path.join(target_dir, "SmartDownload.exe")
    if "SmartDownload.exe" in sources:
        shutil.copy2(sources["SmartDownload.exe"], exe_dest)
    elif "TurboDownloader.exe" in sources:
        shutil.copy2(sources["TurboDownloader.exe"], exe_dest)
    else:
        # If running from source and SmartDownload.exe not pre-built, create a placeholder/copy
        if not os.path.exists(exe_dest):
            with open(exe_dest, "wb") as f:
                f.write(b"")

    # Clean up legacy binary names from previous installations so install folder only contains SmartDownload.exe
    for legacy_name in ("TurboDownloader.exe", "turbo_downloader.exe"):
        legacy_dest = os.path.join(target_dir, legacy_name)
        if os.path.exists(legacy_dest):
            try:
                os.chmod(legacy_dest, 0o777)
                os.remove(legacy_dest)
            except Exception:
                pass

    # 2. Copy icons
    ico_dest = os.path.join(target_dir, "app_icon.ico")
    if "app_icon.ico" in sources:
        shutil.copy2(sources["app_icon.ico"], ico_dest)

    png_dest = os.path.join(target_dir, "app_icon.png")
    if "app_icon.png" in sources:
        shutil.copy2(sources["app_icon.png"], png_dest)

    # 3. Copy extension directory
    ext_dest = os.path.join(target_dir, "extension")
    if "extension" in sources:
        if os.path.isdir(ext_dest):
            shutil.rmtree(ext_dest, ignore_errors=True)
        shutil.copytree(sources["extension"], ext_dest)

    # 4. Copy register_browser.py and host_manifest.py if present
    if "register_browser.py" in sources:
        shutil.copy2(sources["register_browser.py"], os.path.join(target_dir, "register_browser.py"))
    if "host_manifest.py" in sources:
        shutil.copy2(sources["host_manifest.py"], os.path.join(target_dir, "host_manifest.py"))

    # 5. Place uninstaller executable
    uninstaller_dest = os.path.join(target_dir, "Uninstall.exe")
    if getattr(sys, "frozen", False):
        try:
            shutil.copy2(sys.executable, uninstaller_dest)
        except Exception:
            pass
    if not os.path.exists(uninstaller_dest):
        # Fallback runner batch or placeholder
        bat_uninst = os.path.join(target_dir, "uninstall.bat")
        with open(bat_uninst, "w", encoding="utf-8") as f:
            f.write(f'@echo off\r\n"{sys.executable}" "{os.path.abspath(__file__)}" --uninstall %*\r\n')
        uninstaller_dest = bat_uninst

    _notify(0.60, "Configuring browser integration and Windows Registry...")
    if register_browser:
        try:
            import register_browser as rb
            rb.register_native_host(target_dir=target_dir)
            rb.register_browser_extensions(extension_dir=ext_dest)
        except Exception:
            pass

    _notify(0.75, "Creating desktop and start menu shortcuts...")
    shortcuts_created = []

    # Clean up legacy shortcuts upon upgrade
    for dt_candidate in {getattr(sys.modules.get("installer"), "get_desktop_dir", get_desktop_dir)(), os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")}:
        old_lnk = os.path.join(dt_candidate, "Turbo Download Manager Pro.lnk")
        if os.path.isfile(old_lnk):
            try:
                os.chmod(old_lnk, 0o777)
                os.remove(old_lnk)
            except Exception:
                pass

    for sm_candidate in {getattr(sys.modules.get("installer"), "get_start_menu_programs_dir", get_start_menu_programs_dir)(), os.path.join(os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming")),
                                                                    "Microsoft", "Windows", "Start Menu", "Programs")}:
        old_lnk = os.path.join(sm_candidate, "Turbo Download Manager Pro.lnk")
        if os.path.isfile(old_lnk):
            try:
                os.chmod(old_lnk, 0o777)
                os.remove(old_lnk)
            except Exception:
                pass

    if create_desktop:
        _get_dt = getattr(sys.modules.get("installer"), "get_desktop_dir", get_desktop_dir)
        desktop_dir = _get_dt()
        dt_lnk = os.path.join(desktop_dir, f"{APP_NAME}.lnk")
        if create_windows_shortcut(exe_dest, dt_lnk, ico_dest):
            shortcuts_created.append(dt_lnk)

    if create_start_menu:
        _get_sm = getattr(sys.modules.get("installer"), "get_start_menu_programs_dir", get_start_menu_programs_dir)
        sm_dir = _get_sm()
        sm_lnk = os.path.join(sm_dir, f"{APP_NAME}.lnk")
        if create_windows_shortcut(exe_dest, sm_lnk, ico_dest):
            shortcuts_created.append(sm_lnk)

    _notify(0.85, "Registering automatic background startup on Windows boot...")
    startup_res = {}
    if register_startup:
        startup_res = register_startup_entries(exe_dest, ico_dest)
    else:
        startup_res = unregister_startup_entries()

    _notify(0.95, "Registering Windows Uninstall entry...")
    reg_ok = register_uninstall_entry(target_dir, exe_dest, uninstaller_dest, ico_dest)

    _notify(1.0, "Installation complete!")
    return {
        "success": True,
        "install_dir": target_dir,
        "exe_path": exe_dest,
        "uninstaller_path": uninstaller_dest,
        "shortcuts": shortcuts_created,
        "registry_registered": reg_ok,
        "startup_registered": startup_res
    }


def uninstall_application(
    target_dir: Optional[str] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None
) -> Dict[str, Any]:
    """
    Core uninstallation workflow:
    1. Terminate running TurboDownloader.exe
    2. Unregister Chrome & Edge native messaging hosts
    3. Unregister Chrome & Edge extensions
    4. Remove Desktop and Start Menu shortcuts
    5. Delete Windows Uninstall registry key
    6. Remove installed files and folder cleanly
    """
    def _notify(pct: float, msg: str):
        if progress_cb:
            try:
                progress_cb(pct, msg)
            except Exception:
                pass

    if not target_dir:
        target_dir = DEFAULT_INSTALL_DIR
    target_dir = os.path.abspath(target_dir)

    _notify(0.10, "Closing active application instances...")
    terminate_running_app()

    _notify(0.30, "Removing browser integration from registry...")
    try:
        import register_browser as rb
        rb.unregister_native_host(unregister_extensions=True)
    except Exception:
        pass

    _notify(0.50, "Removing application shortcuts...")
    # Desktop shortcut (check both shell resolved and userprofile)
    for dt_dir in {getattr(sys.modules.get("installer"), "get_desktop_dir", get_desktop_dir)(), os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")}:
        for name in (APP_NAME, "SmartDownload", "TurboDownloader", "Turbo Download Manager Pro"):
            dt_lnk = os.path.join(dt_dir, f"{name}.lnk")
            if os.path.isfile(dt_lnk):
                try:
                    os.remove(dt_lnk)
                except Exception:
                    pass

    # Start menu shortcut
    for sm_dir in {getattr(sys.modules.get("installer"), "get_start_menu_programs_dir", get_start_menu_programs_dir)(), os.path.join(os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming")),
                                                               "Microsoft", "Windows", "Start Menu", "Programs")}:
        for name in (APP_NAME, "SmartDownload", "TurboDownloader", "Turbo Download Manager Pro"):
            sm_lnk = os.path.join(sm_dir, f"{name}.lnk")
            if os.path.isfile(sm_lnk):
                try:
                    os.remove(sm_lnk)
                except Exception:
                    pass

    _notify(0.65, "Removing automatic background startup entries...")
    unregister_startup_entries()

    _notify(0.75, "Unregistering Windows Uninstall entry...")
    unregister_uninstall_entry()

    _notify(0.90, "Cleaning up installed files...")
    # If the uninstaller process itself is running from within target_dir,
    # clean up all other files and schedule a detached watcher to delete
    # the uninstaller binary and folder once this process terminates.
    running_in_target = False
    if getattr(sys, "frozen", False):
        try:
            running_in_target = (os.path.commonpath([os.path.abspath(sys.executable), os.path.abspath(target_dir)]) == os.path.abspath(target_dir))
        except Exception:
            running_in_target = False

    if running_in_target and sys.platform.startswith("win"):
        current_exe = os.path.normcase(os.path.abspath(sys.executable))
        if os.path.isdir(target_dir):
            for item in os.listdir(target_dir):
                item_path = os.path.join(target_dir, item)
                if os.path.normcase(os.path.abspath(item_path)) == current_exe:
                    continue
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                    else:
                        os.remove(item_path)
                except Exception:
                    pass
        pid = os.getpid()
        clean_ps = (
            f"Start-Sleep -Milliseconds 400; "
            f"while (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 250 }}; "
            f"Start-Sleep -Milliseconds 200; "
            f"Remove-Item -Recurse -Force -LiteralPath '{target_dir}'"
        )
        del_cmd = f'powershell -NoProfile -WindowStyle Hidden -Command "{clean_ps}"'
        subprocess.Popen(del_cmd, shell=True, creationflags=0x08000000)  # CREATE_NO_WINDOW
    else:
        if os.path.isdir(target_dir):
            try:
                shutil.rmtree(target_dir, ignore_errors=True)
            except Exception:
                pass

    _notify(1.0, "Uninstallation complete!")
    return {
        "success": True,
        "target_dir": target_dir
    }



def is_admin() -> bool:
    """Checks whether the current process has administrative elevation."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_silent_install(target_dir: str = DEFAULT_INSTALL_DIR, **kwargs) -> Dict[str, Any]:
    """Runs unattended silent installation."""
    return install_application(target_dir=target_dir, **kwargs)


get_payload_dir = find_payload_sources
kill_running_instances = terminate_running_app
create_shortcut = create_windows_shortcut
register_uninstaller = register_uninstall_entry
perform_installation = install_application
