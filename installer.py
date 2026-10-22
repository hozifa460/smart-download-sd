"""
========================================================================================
🚀 SMART DOWNLOAD (SD) — Windows Standalone Installer & Uninstaller
========================================================================================
Zero-admin / UAC-free User-Level Windows Installer:
1. Installs to %LocalAppData%\\Programs\\SmartDownload (like VS Code / Discord / Chrome).
2. Copies SmartDownload.exe, app icons, browser extension files, and host manifests.
3. Creates Desktop Shortcut and Start Menu Shortcut with app_icon.ico.
4. Registers Windows Uninstall entry in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SmartDownload.
5. Registers Chrome & Edge browser extension and native messaging host during setup.
6. Clean uninstallation support via GUI or command-line (--uninstall / /S).
7. Modern, sleek High-DPI aware, grab-free Tkinter dark aesthetic with smooth progress.
========================================================================================
"""

import os
import sys
import shutil
import json
import time
import threading
import argparse
import subprocess
from typing import Dict, List, Optional, Callable, Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

# Application Constants
APP_NAME = "Smart Download (SD)"
APP_ID = "SmartDownload"
APP_VERSION = "2.0.0"
APP_PUBLISHER = "Smart Download Team"
APP_URL = "https://github.com/hozifa460/smart-download-sd"

LEGACY_APP_ID = "TurboDownloader"
LEGACY_UNINSTALL_REG_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{LEGACY_APP_ID}"

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


def enable_high_dpi_awareness():
    """Configures Per-Monitor V2 High-DPI awareness on Windows."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def create_windows_shortcut(
    target_exe: str,
    shortcut_path: str,
    icon_path: str = "",
    description: str = APP_NAME,
    working_dir: str = "",
    arguments: str = ""
) -> bool:
    """Creates a Windows .lnk shortcut file with target, arguments, icon, and working directory."""
    if not sys.platform.startswith("win"):
        return False

    try:
        os.makedirs(os.path.dirname(os.path.abspath(shortcut_path)), exist_ok=True)
    except Exception:
        pass

    if not working_dir:
        working_dir = os.path.dirname(os.path.abspath(target_exe))

    # 1. Try win32com WScript.Shell
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(os.path.abspath(shortcut_path))
        shortcut.TargetPath = os.path.abspath(target_exe)
        shortcut.WorkingDirectory = os.path.abspath(working_dir)
        if arguments:
            shortcut.Arguments = arguments
        if icon_path and os.path.exists(icon_path):
            shortcut.IconLocation = f"{os.path.abspath(icon_path)},0"
        if description:
            shortcut.Description = description
        shortcut.Save()
        if os.path.exists(shortcut_path):
            return True
    except Exception:
        pass

    # 2. Fallback to PowerShell
    try:
        ps_icon = f"$s.IconLocation = '{os.path.abspath(icon_path)},0'; " if (icon_path and os.path.exists(icon_path)) else ""
        ps_args = f"$s.Arguments = '{arguments}'; " if arguments else ""
        ps_script = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{os.path.abspath(shortcut_path)}'); "
            f"$s.TargetPath = '{os.path.abspath(target_exe)}'; "
            f"$s.WorkingDirectory = '{os.path.abspath(working_dir)}'; "
            f"{ps_args}"
            f"{ps_icon}"
            f"$s.Description = '{description}'; "
            f"$s.Save();"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            timeout=10
        )
        return res.returncode == 0 and os.path.exists(shortcut_path)
    except Exception:
        return False


def register_startup_entries(exe_path: str, icon_path: str = "") -> Dict[str, bool]:
    """
    Registers automatic, zero-elevation background startup on Windows boot:
    1. Register binary in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run with --minimized.
    2. Register standard user Scheduled Task (SmartDownloadAutoStart) via schtasks.exe with /SC ONLOGON.
    3. Create silent background startup shortcut in shell:startup (%APPDATA%\\...\\Startup).
    """
    results = {"run_key": False, "scheduled_task": False, "startup_shortcut": False}
    if not sys.platform.startswith("win"):
        return results

    abs_exe = os.path.abspath(exe_path)
    cmd = f'"{abs_exe}" --minimized'

    # 1. Register in HKCU Run Key
    if HAS_WINREG:
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY) as key:
                winreg.SetValueEx(key, STARTUP_REG_KEY_NAME, 0, winreg.REG_SZ, cmd)
                # Clean up legacy key if present
                try:
                    winreg.DeleteValue(key, LEGACY_STARTUP_REG_KEY_NAME)
                except (FileNotFoundError, OSError):
                    pass
            results["run_key"] = True
        except Exception:
            pass

    # 2. Register Windows Scheduled Task (SmartDownloadAutoStart)
    try:
        tr_arg = f'"{abs_exe}" --minimized'
        task_cmd = [
            "schtasks.exe", "/Create", "/F",
            "/SC", "ONLOGON",
            "/TN", TASK_NAME,
            "/TR", tr_arg
        ]
        res = subprocess.run(task_cmd, capture_output=True, text=True, timeout=10)
        results["scheduled_task"] = (res.returncode == 0)
    except Exception:
        pass

    # 3. Create silent startup shortcut in shell:startup
    try:
        startup_dir = get_startup_dir()
        os.makedirs(startup_dir, exist_ok=True)
        for old_name in ("Turbo Download Manager Pro.lnk", "TurboDownloader.lnk", "SmartDownload.lnk"):
            old_p = os.path.join(startup_dir, old_name)
            if os.path.isfile(old_p):
                try:
                    os.remove(old_p)
                except Exception:
                    pass
        startup_lnk = os.path.join(startup_dir, f"{APP_NAME}.lnk")
        ok_lnk = create_windows_shortcut(
            target_exe=abs_exe,
            shortcut_path=startup_lnk,
            icon_path=icon_path,
            description=f"{APP_NAME} AutoStart",
            arguments="--minimized"
        )
        results["startup_shortcut"] = ok_lnk
    except Exception:
        pass

    return results


def unregister_startup_entries() -> Dict[str, bool]:
    """
    Cleanly removes all auto-start entries on uninstallation:
    1. HKCU Run registry keys (SmartDownload and legacy TurboDownloader).
    2. Scheduled Task (SmartDownloadAutoStart and legacy TurboDownloaderAutoStart).
    3. Startup folder shortcuts.
    """
    results = {"run_key": False, "scheduled_task": False, "startup_shortcut": False}
    if not sys.platform.startswith("win"):
        return results

    # 1. HKCU Run registry
    if HAS_WINREG:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
                for k_name in (STARTUP_REG_KEY_NAME, LEGACY_STARTUP_REG_KEY_NAME):
                    try:
                        winreg.DeleteValue(key, k_name)
                    except (FileNotFoundError, OSError):
                        pass
            results["run_key"] = True
        except FileNotFoundError:
            results["run_key"] = True
        except Exception:
            pass

    # 2. Windows Scheduled Task
    try:
        for tname in (TASK_NAME, LEGACY_TASK_NAME):
            try:
                subprocess.run(
                    ["schtasks.exe", "/Delete", "/TN", tname, "/F"],
                    capture_output=True,
                    timeout=10
                )
            except Exception:
                pass
        results["scheduled_task"] = True
    except Exception:
        pass

    # 3. Startup folder shortcuts
    try:
        startup_dir = get_startup_dir()
        for name in (APP_NAME, "SmartDownload", "TurboDownloader", "Turbo Download Manager Pro"):
            lnk_path = os.path.join(startup_dir, f"{name}.lnk")
            if os.path.isfile(lnk_path):
                try:
                    os.remove(lnk_path)
                except Exception:
                    pass
        results["startup_shortcut"] = True
    except Exception:
        pass

    return results


def register_uninstall_entry(
    install_dir: str,
    exe_path: str,
    uninstaller_path: str,
    icon_path: str = ""
) -> bool:
    """Registers the application in Windows HKCU Uninstall registry for Add/Remove Programs."""
    if not HAS_WINREG or not sys.platform.startswith("win"):
        return False

    try:
        total_size_bytes = 0
        if os.path.isdir(install_dir):
            for dirpath, _, filenames in os.walk(install_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.isfile(fp):
                        total_size_bytes += os.path.getsize(fp)
        size_kb = max(1, total_size_bytes // 1024)

        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_KEY)
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, os.path.abspath(install_dir))
        
        display_ico = icon_path if (icon_path and os.path.exists(icon_path)) else exe_path
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, f"{os.path.abspath(display_ico)},0")

        uninstall_cmd = f'"{os.path.abspath(uninstaller_path)}" --uninstall'
        quiet_uninstall_cmd = f'"{os.path.abspath(uninstaller_path)}" --uninstall --silent'
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninstall_cmd)
        winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, quiet_uninstall_cmd)

        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        winreg.SetValueEx(key, "URLInfoAbout", 0, winreg.REG_SZ, APP_URL)
        winreg.CloseKey(key)

        # Clean up legacy TurboDownloader uninstall registry entry if migrating
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, LEGACY_UNINSTALL_REG_KEY)
        except Exception:
            pass
        return True
    except Exception:
        return False


def unregister_uninstall_entry() -> bool:
    """Removes the Windows HKCU Uninstall registry key (including legacy key)."""
    if not HAS_WINREG or not sys.platform.startswith("win"):
        return False
    ok = True
    for k in (UNINSTALL_REG_KEY, LEGACY_UNINSTALL_REG_KEY):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, k)
        except FileNotFoundError:
            pass
        except Exception:
            ok = False
    return ok


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
    base_dirs.append(os.path.join(current_dir, "installer_payload"))
    base_dirs.append(os.path.join(current_dir, "dist"))
    base_dirs.append(current_dir)

    for b in base_dirs:
        cand = os.path.join(b, "SmartDownload.exe")
        if os.path.isfile(cand) and "SmartDownload.exe" not in sources:
            sources["SmartDownload.exe"] = cand
        cand_legacy = os.path.join(b, "TurboDownloader.exe")
        if os.path.isfile(cand_legacy) and "TurboDownloader.exe" not in sources:
            sources["TurboDownloader.exe"] = cand_legacy

    for b in base_dirs:
        cand = os.path.join(b, "app_icon.ico")
        if os.path.isfile(cand) and "app_icon.ico" not in sources:
            sources["app_icon.ico"] = cand

    for b in base_dirs:
        cand = os.path.join(b, "app_icon.png")
        if os.path.isfile(cand) and "app_icon.png" not in sources:
            sources["app_icon.png"] = cand

    for b in base_dirs:
        cand = os.path.join(b, "extension")
        if os.path.isdir(cand) and "extension" not in sources:
            sources["extension"] = cand

    for b in base_dirs:
        cand = os.path.join(b, "sd_host.bat")
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

    # Backward compatibility: Provide TurboDownloader.exe link or copy at install time
    legacy_dest = os.path.join(target_dir, "TurboDownloader.exe")
    if os.path.exists(exe_dest):
        if os.path.exists(legacy_dest):
            try:
                os.chmod(legacy_dest, 0o777)
                os.remove(legacy_dest)
            except Exception:
                pass
        try:
            os.link(exe_dest, legacy_dest)
        except Exception:
            try:
                shutil.copy2(exe_dest, legacy_dest)
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

    # 4. Copy register_browser.py if present
    if "register_browser.py" in sources:
        shutil.copy2(sources["register_browser.py"], os.path.join(target_dir, "register_browser.py"))

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
    for dt_candidate in {get_desktop_dir(), os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")}:
        old_lnk = os.path.join(dt_candidate, "Turbo Download Manager Pro.lnk")
        if os.path.isfile(old_lnk):
            try:
                os.chmod(old_lnk, 0o777)
                os.remove(old_lnk)
            except Exception:
                pass

    for sm_candidate in {get_start_menu_programs_dir(), os.path.join(os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming")),
                                                                    "Microsoft", "Windows", "Start Menu", "Programs")}:
        old_lnk = os.path.join(sm_candidate, "Turbo Download Manager Pro.lnk")
        if os.path.isfile(old_lnk):
            try:
                os.chmod(old_lnk, 0o777)
                os.remove(old_lnk)
            except Exception:
                pass

    if create_desktop:
        desktop_dir = get_desktop_dir()
        dt_lnk = os.path.join(desktop_dir, f"{APP_NAME}.lnk")
        if create_windows_shortcut(exe_dest, dt_lnk, ico_dest):
            shortcuts_created.append(dt_lnk)

    if create_start_menu:
        sm_dir = get_start_menu_programs_dir()
        sm_lnk = os.path.join(sm_dir, f"{APP_NAME}.lnk")
        if create_windows_shortcut(exe_dest, sm_lnk, ico_dest):
            shortcuts_created.append(sm_lnk)

    _notify(0.85, "Registering automatic background startup on Windows boot...")
    startup_res = {}
    if register_startup:
        startup_res = register_startup_entries(exe_dest, ico_dest)

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
    for dt_dir in {get_desktop_dir(), os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")}:
        for name in (APP_NAME, "Turbo Download Manager Pro"):
            dt_lnk = os.path.join(dt_dir, f"{name}.lnk")
            if os.path.isfile(dt_lnk):
                try:
                    os.remove(dt_lnk)
                except Exception:
                    pass

    # Start menu shortcut
    for sm_dir in {get_start_menu_programs_dir(), os.path.join(os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming")),
                                                               "Microsoft", "Windows", "Start Menu", "Programs")}:
        for name in (APP_NAME, "Turbo Download Manager Pro"):
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


# ======================================================================================
# SLEEK MODERN TKINTER INSTALLER GUI (GRAB-FREE & HIGH-DPI AWARE)
# ======================================================================================

class InstallerGUI:
    """Modern dark-themed Tkinter installer and uninstaller interface."""

    def __init__(self, root, mode: str = "install", target_dir: str = DEFAULT_INSTALL_DIR):
        self.root = root
        self.mode = mode  # "install" or "uninstall"
        self.target_dir = target_dir
        self.launch_after = True

        enable_high_dpi_awareness()

        # Modern Dark Color Palette
        self.BG_MAIN = "#18191c"
        self.BG_CARD = "#222428"
        self.BG_INPUT = "#131417"
        self.TEXT_MAIN = "#ffffff"
        self.TEXT_MUTED = "#9da5b4"
        self.ACCENT = "#0078d4"
        self.ACCENT_HOVER = "#106ebe"
        self.SUCCESS = "#00c853"
        self.DANGER = "#e81123"
        self.BORDER = "#333842"

        self.root.title(f"{APP_NAME} Setup" if mode == "install" else f"{APP_NAME} Uninstall")
        self.root.configure(bg=self.BG_MAIN)
        self.root.resizable(False, False)

        # High DPI Window Size
        scale = 1.0
        try:
            dpi = self.root.winfo_fpixels('1i')
            scale = max(1.0, dpi / 96.0)
        except Exception:
            pass
        self.scale = scale

        width = int(580 * scale)
        height = int(460 * scale)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - width) // 2
        y = (sh - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # Set Window Icon
        sources = find_payload_sources()
        ico = sources.get("app_icon.ico", "")
        if ico and os.path.isfile(ico):
            try:
                self.root.iconbitmap(ico)
            except Exception:
                pass

        self.is_running = False
        self._closing = False
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self._build_ui()

    def _on_window_close(self):
        if getattr(self, "is_running", False):
            return
        self._closing = True
        try:
            self.root.destroy()
        except Exception:
            pass

    def _build_ui(self):
        import tkinter as tk
        from tkinter import ttk

        # Custom ttk styles
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.Horizontal.TProgressbar",
                        troughcolor=self.BG_CARD,
                        background=self.ACCENT,
                        lightcolor=self.ACCENT,
                        darkcolor=self.ACCENT,
                        bordercolor=self.BORDER)

        self.container = tk.Frame(self.root, bg=self.BG_MAIN)
        self.container.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        # Header Frame
        header = tk.Frame(self.container, bg=self.BG_MAIN)
        header.pack(fill=tk.X, pady=(0, 16))

        title_text = f"Install {APP_NAME}" if self.mode == "install" else f"Uninstall {APP_NAME}"
        lbl_title = tk.Label(header, text=title_text, font=("Segoe UI", 16, "bold"),
                             bg=self.BG_MAIN, fg=self.TEXT_MAIN)
        lbl_title.pack(anchor="w")

        sub_text = "Fast, Resumable Multi-Chunk Download Accelerator" if self.mode == "install" \
            else "Cleanly remove application, browser integration, and shortcuts"
        lbl_sub = tk.Label(header, text=sub_text, font=("Segoe UI", 9),
                           bg=self.BG_MAIN, fg=self.TEXT_MUTED)
        lbl_sub.pack(anchor="w", pady=(2, 0))

        # Dynamic Content Frame
        self.content_frame = tk.Frame(self.container, bg=self.BG_CARD, bd=1, relief="solid")
        self.content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 16))

        if self.mode == "install":
            self._render_install_options()
        else:
            self._render_uninstall_options()

        # Footer Frame
        self.footer = tk.Frame(self.container, bg=self.BG_MAIN)
        self.footer.pack(fill=tk.X)

        self.btn_cancel = tk.Button(self.footer, text="Cancel", font=("Segoe UI", 9),
                                    bg=self.BG_CARD, fg=self.TEXT_MAIN, activebackground=self.BORDER,
                                    activeforeground=self.TEXT_MAIN, bd=0, padx=16, pady=6,
                                    cursor="hand2", command=self.root.destroy)
        self.btn_cancel.pack(side=tk.RIGHT, padx=(8, 0))

        action_btn_text = "Install Now" if self.mode == "install" else "Uninstall"
        action_color = self.ACCENT if self.mode == "install" else self.DANGER
        self.btn_action = tk.Button(self.footer, text=action_btn_text, font=("Segoe UI", 9, "bold"),
                                    bg=action_color, fg="#ffffff", activebackground=self.ACCENT_HOVER,
                                    activeforeground="#ffffff", bd=0, padx=20, pady=6,
                                    cursor="hand2", command=self._start_action)
        self.btn_action.pack(side=tk.RIGHT)

    def _render_install_options(self):
        import tkinter as tk
        from tkinter import filedialog

        for w in self.content_frame.winfo_children():
            w.destroy()

        pad_f = tk.Frame(self.content_frame, bg=self.BG_CARD)
        pad_f.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # Destination Folder
        lbl_dir = tk.Label(pad_f, text="Destination Folder (User-Level / Zero UAC Elevation):",
                           font=("Segoe UI", 9, "bold"), bg=self.BG_CARD, fg=self.TEXT_MAIN)
        lbl_dir.pack(anchor="w", pady=(0, 6))

        dir_box = tk.Frame(pad_f, bg=self.BG_INPUT, bd=1, relief="solid")
        dir_box.pack(fill=tk.X, pady=(0, 14))

        self.var_dir = tk.StringVar(value=self.target_dir)
        self.entry_dir = tk.Entry(dir_box, textvariable=self.var_dir, font=("Segoe UI", 9),
                                  bg=self.BG_INPUT, fg=self.TEXT_MAIN, insertbackground=self.TEXT_MAIN,
                                  bd=0, relief="flat")
        self.entry_dir.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=6)

        def _browse():
            chosen = filedialog.askdirectory(initialdir=self.var_dir.get(), title="Select Install Folder")
            if chosen:
                self.var_dir.set(chosen)

        btn_browse = tk.Button(dir_box, text="Browse...", font=("Segoe UI", 8),
                               bg=self.BORDER, fg=self.TEXT_MAIN, bd=0, padx=10, pady=2,
                               cursor="hand2", command=_browse)
        btn_browse.pack(side=tk.RIGHT, padx=4, pady=3)

        # Options Checkboxes
        self.var_desktop = tk.BooleanVar(value=True)
        self.var_startmenu = tk.BooleanVar(value=True)
        self.var_startup = tk.BooleanVar(value=True)
        self.var_browser = tk.BooleanVar(value=True)
        self.var_launch = tk.BooleanVar(value=True)

        for text, var in [
            ("Create Desktop Shortcut", self.var_desktop),
            ("Create Start Menu Shortcut", self.var_startmenu),
            ("Start Smart Download on Windows startup (Silent background)", self.var_startup),
            ("Enable Chrome & Microsoft Edge Browser Integration", self.var_browser),
            (f"Launch {APP_NAME} after installation", self.var_launch)
        ]:
            cb = tk.Checkbutton(pad_f, text=text, variable=var, font=("Segoe UI", 9),
                                bg=self.BG_CARD, fg=self.TEXT_MAIN, selectcolor=self.BG_INPUT,
                                activebackground=self.BG_CARD, activeforeground=self.TEXT_MAIN,
                                bd=0, highlightthickness=0)
            cb.pack(anchor="w", pady=3)

    def _render_uninstall_options(self):
        import tkinter as tk
        for w in self.content_frame.winfo_children():
            w.destroy()

        pad_f = tk.Frame(self.content_frame, bg=self.BG_CARD)
        pad_f.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)

        lbl_warn = tk.Label(pad_f, text=f"Are you sure you want to completely uninstall {APP_NAME}?",
                            font=("Segoe UI", 11, "bold"), bg=self.BG_CARD, fg=self.TEXT_MAIN, wraplength=480, justify="left")
        lbl_warn.pack(anchor="w", pady=(0, 12))

        desc = (
            f"This will remove the application from:\n{self.target_dir}\n\n"
            "It will also:\n"
            "• Unregister Chrome & Microsoft Edge Native Messaging Host\n"
            "• Remove Desktop and Start Menu shortcuts\n"
            "• Remove Windows 'Installed Apps' entry"
        )
        lbl_desc = tk.Label(pad_f, text=desc, font=("Segoe UI", 9),
                            bg=self.BG_CARD, fg=self.TEXT_MUTED, justify="left")
        lbl_desc.pack(anchor="w")

    def _render_progress_screen(self):
        import tkinter as tk
        from tkinter import ttk

        for w in self.content_frame.winfo_children():
            w.destroy()

        pad_f = tk.Frame(self.content_frame, bg=self.BG_CARD)
        pad_f.pack(fill=tk.BOTH, expand=True, padx=24, pady=32)

        title = "Installing..." if self.mode == "install" else "Uninstalling..."
        lbl_st = tk.Label(pad_f, text=title, font=("Segoe UI", 12, "bold"),
                          bg=self.BG_CARD, fg=self.TEXT_MAIN)
        lbl_st.pack(anchor="w", pady=(0, 12))

        self.progress_bar = ttk.Progressbar(pad_f, orient="horizontal", mode="determinate",
                                            style="Dark.Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))

        self.lbl_detail = tk.Label(pad_f, text="Initializing...", font=("Segoe UI", 9),
                                   bg=self.BG_CARD, fg=self.TEXT_MUTED)
        self.lbl_detail.pack(anchor="w")

    def _render_completed_screen(self, success: bool, message: str, exe_path: str = ""):
        import tkinter as tk

        for w in self.content_frame.winfo_children():
            w.destroy()

        pad_f = tk.Frame(self.content_frame, bg=self.BG_CARD)
        pad_f.pack(fill=tk.BOTH, expand=True, padx=24, pady=36)

        color = self.SUCCESS if success else self.DANGER
        header = "Completed Successfully!" if success else "Operation Failed"
        lbl_h = tk.Label(pad_f, text=header, font=("Segoe UI", 15, "bold"),
                         bg=self.BG_CARD, fg=color)
        lbl_h.pack(anchor="w", pady=(0, 10))

        lbl_m = tk.Label(pad_f, text=message, font=("Segoe UI", 9),
                         bg=self.BG_CARD, fg=self.TEXT_MAIN, wraplength=480, justify="left")
        lbl_m.pack(anchor="w", pady=(0, 16))

        # Update Buttons
        self.btn_cancel.pack_forget()
        self.btn_action.config(text="Finish", bg=self.ACCENT, command=lambda: self._on_finish(exe_path))

    def _start_action(self):
        self.is_running = True
        self.btn_action.config(state="disabled")
        self.btn_cancel.config(state="disabled")
        self._render_progress_screen()

        def _bg_worker():
            def _cb(pct, msg):
                if not getattr(self, "_closing", False):
                    try:
                        self.root.after(0, lambda: self._update_progress(pct, msg))
                    except Exception:
                        pass

            try:
                if self.mode == "install":
                    target = self.var_dir.get().strip()
                    res = install_application(
                        target_dir=target,
                        create_desktop=self.var_desktop.get(),
                        create_start_menu=self.var_startmenu.get(),
                        register_browser=self.var_browser.get(),
                        register_startup=self.var_startup.get(),
                        progress_cb=_cb
                    )
                    self.launch_after = self.var_launch.get()
                    if not getattr(self, "_closing", False):
                        self.root.after(0, lambda: self._render_completed_screen(
                            res.get("success", False),
                            f"{APP_NAME} has been successfully installed on your computer.",
                            res.get("exe_path", "")
                        ))
                else:
                    res = uninstall_application(
                        target_dir=self.target_dir,
                        progress_cb=_cb
                    )
                    if not getattr(self, "_closing", False):
                        self.root.after(0, lambda: self._render_completed_screen(
                            res.get("success", False),
                            f"{APP_NAME} has been completely removed from your computer."
                        ))
            finally:
                self.is_running = False

        threading.Thread(target=_bg_worker, daemon=True).start()

    def _update_progress(self, pct: float, msg: str):
        try:
            self.progress_bar["value"] = int(pct * 100)
            self.lbl_detail.config(text=msg)
        except Exception:
            pass

    def _on_finish(self, exe_path: str):
        if self.mode == "install" and self.launch_after and exe_path and os.path.isfile(exe_path):
            try:
                subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
            except Exception:
                pass
        self.root.destroy()


# ======================================================================================
# CLI & LAUNCHER ENTRYPOINT
# ======================================================================================

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

    # Determine mode
    exe_name = os.path.basename(sys.executable).lower()
    script_name = os.path.basename(__file__).lower()
    is_uninstaller_binary = "uninstall" in exe_name or "uninstall" in script_name
    mode = "uninstall" if (args.uninstall or "/U" in sys.argv or "--uninstall" in sys.argv or is_uninstaller_binary) else "install"
    silent = args.silent or "/S" in sys.argv or "--silent" in sys.argv

    # If running as uninstaller from within an installed directory, default target_dir to that directory
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

    # Launch Tkinter GUI
    import tkinter as tk
    root = tk.Tk()
    app = InstallerGUI(root, mode=mode, target_dir=target_dir)
    root.mainloop()


if __name__ == "__main__":
    main()
