"""
Windows Registry, shortcut creation, and startup registration for Smart Download Installer.
"""
import os
import sys
import shutil
import subprocess
from typing import Dict, List, Optional, Callable, Any

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

APP_NAME = "Smart Download (SD)"
APP_ID = "SmartDownload"
APP_VERSION = "2.0.0"
APP_PUBLISHER = "Smart Download Team"
APP_URL = "https://github.com/hozifa460/smart-download-sd"

LEGACY_APP_ID = "TurboDownloader"
LEGACY_UNINSTALL_REG_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{LEGACY_APP_ID}"
UNINSTALL_REG_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"

STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_KEY_NAME = "SmartDownload"
LEGACY_STARTUP_REG_KEY_NAME = "TurboDownloader"
TASK_NAME = "SmartDownloadAutoStart"
LEGACY_TASK_NAME = "TurboDownloaderAutoStart"

def get_startup_dir() -> str:
    inst = sys.modules.get("installer")
    if inst and hasattr(inst, "get_startup_dir") and inst.get_startup_dir is not get_startup_dir:
        return inst.get_startup_dir()
    from .installer_ops import get_startup_dir as _gsd
    return _gsd()

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
        def _ps_quote(s: str) -> str:
            return str(s).replace("'", "''")

        clean_target = str(target_exe).strip('"\'')
        clean_shortcut = str(shortcut_path).strip('"\'')
        clean_working = str(working_dir).strip('"\'')

        ps_icon = f"$s.IconLocation = '{_ps_quote(os.path.abspath(icon_path))},0'; " if (icon_path and os.path.exists(icon_path)) else ""
        ps_args = f"$s.Arguments = '{_ps_quote(arguments)}'; " if arguments else ""
        ps_script = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{_ps_quote(os.path.abspath(clean_shortcut))}'); "
            f"$s.TargetPath = '{_ps_quote(os.path.abspath(clean_target))}'; "
            f"$s.WorkingDirectory = '{_ps_quote(os.path.abspath(clean_working))}'; "
            f"{ps_args}"
            f"{ps_icon}"
            f"$s.Description = '{_ps_quote(description)}'; "
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

    clean_exe = str(exe_path).strip('"\'')
    abs_exe = os.path.abspath(clean_exe)
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


