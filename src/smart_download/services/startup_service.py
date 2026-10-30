"""
Windows startup registry, Task Scheduler, and Startup shortcut management.
"""
import os
import sys
import subprocess
import shutil
from typing import Optional, Dict, Any, Tuple

from ..config import IS_WINDOWS

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    try:
        import winreg
    except ImportError:
        winreg = None
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_MINIMIZEBOX = 0x00020000
    WS_SYSMENU = 0x00080000
    SW_HIDE = 0
    SW_MINIMIZE = 6
    SW_RESTORE = 9
    SW_SHOW = 5
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
    except Exception:
        user32 = None
        kernel32 = None
else:
    winreg = None
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_MINIMIZEBOX = 0x00020000
    WS_SYSMENU = 0x00080000
    SW_HIDE = 0
    SW_MINIMIZE = 6
    SW_RESTORE = 9
    SW_SHOW = 5
    user32 = None
    kernel32 = None

# WINDOWS STARTUP REGISTRY INTEGRATION (AUTO-RUN ON BOOT)
# ======================================================================================

WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_KEY_NAME = "SmartDownload"
LEGACY_STARTUP_REG_KEY_NAME = "TurboDownloader"
TASK_NAME = "SmartDownloadAutoStart"
LEGACY_TASK_NAME = "TurboDownloaderAutoStart"
STARTUP_APPROVED_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
STARTUP_APPROVED_FOLDER_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"
EXPLORER_SERIALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize"
ENABLED_STARTUP_BINARY = b"\x02" + b"\x00" * 11


def get_installed_exe_path() -> Optional[str]:
    """Returns the canonical installed executable path if present on disk."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.expanduser(r"~\AppData\Local")
    installed_exe = os.path.normpath(os.path.join(local_app_data, "Programs", "SmartDownload", "SmartDownload.exe"))
    if os.path.isfile(installed_exe):
        return installed_exe
    return None


def get_startup_folder() -> str:
    """Returns the user Startup folder path (shell:startup)."""
    if IS_WINDOWS and winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
                raw_path, _ = winreg.QueryValueEx(k, "Startup")
                if raw_path and str(raw_path).strip():
                    expanded = os.path.normpath(os.path.expandvars(str(raw_path).strip()))
                    if os.path.isabs(expanded) and os.path.isdir(expanded):
                        return expanded
        except Exception:
            pass
    return os.path.normpath(os.path.join(
        os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming")),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    ))


get_startup_dir = get_startup_folder


def _parse_startup_cmd(cmd_str: str) -> Tuple[str, str, str, str]:
    """
    Parses a startup command string into:
    (exe_path, args, script_path, working_dir)
    Handles:
    - Standalone executables with/without quotes and arguments
    - Python script launches (e.g. "pythonw.exe" "script.py" --minimized)
    """
    if not cmd_str:
        return "", "", "", ""
    s = str(cmd_str).strip()
    if s.startswith('"'):
        end_idx = s.find('"', 1)
        if end_idx != -1:
            exe_path = s[1:end_idx].strip()
            rest = s[end_idx + 1:].strip()
        else:
            exe_path = s.strip('"')
            rest = ""
    else:
        parts = s.split(None, 1)
        exe_path = parts[0].strip()
        rest = parts[1].strip() if len(parts) > 1 else ""

    script_path = ""
    if os.path.basename(exe_path).lower() in ("python.exe", "pythonw.exe"):
        if rest.startswith('"'):
            s_end = rest.find('"', 1)
            if s_end != -1:
                script_path = rest[1:s_end].strip()
        elif rest:
            script_path = rest.split()[0].strip()

    working_dir = ""
    if script_path and os.path.isfile(script_path):
        working_dir = os.path.dirname(os.path.abspath(script_path))
    elif exe_path and os.path.isfile(exe_path):
        working_dir = os.path.dirname(os.path.abspath(exe_path))

    return exe_path, rest, script_path, working_dir


def _extract_exe_from_cmd(cmd_str: str) -> str:
    """Extracts target executable file path from command string."""
    exe_path, _, _, _ = _parse_startup_cmd(cmd_str)
    return exe_path


def _create_startup_shortcut(
    target_exe: str,
    shortcut_path: str,
    arguments: str = "",
    working_dir: str = "",
    icon_path: str = "",
    description: str = "Smart Download (SD) AutoStart"
) -> bool:
    """Creates a Windows shortcut (.lnk) with win32com and PowerShell fallback."""
    if not IS_WINDOWS:
        return False
    try:
        os.makedirs(os.path.dirname(os.path.abspath(shortcut_path)), exist_ok=True)
    except Exception:
        pass

    clean_target = str(target_exe).strip('"\'')
    clean_shortcut = str(shortcut_path).strip('"\'')
    clean_working = str(working_dir).strip('"\'') if working_dir else os.path.dirname(os.path.abspath(clean_target))

    # 1. Try win32com WScript.Shell
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(os.path.abspath(clean_shortcut))
        shortcut.TargetPath = os.path.abspath(clean_target)
        shortcut.WorkingDirectory = os.path.abspath(clean_working)
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

    # 2. PowerShell fallback with single quote escaping
    try:
        def _ps_quote(s: str) -> str:
            return str(s).replace("'", "''")

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


def get_startup_command(minimized: bool = True) -> str:
    """
    Constructs the command line string to launch SmartDownload on system startup.
    Accurately resolves executable path prioritizing:
    1. Active standalone frozen binary (.exe) if already running as frozen executable
    2. Canonical installed executable (%LocalAppData%\\Programs\\SmartDownload\\SmartDownload.exe)
    3. Standalone binary in dist/ directory or adjacent to script
    4. Python script fallback with pythonw.exe
    """
    flag = " --minimized" if minimized else ""
    if getattr(sys, "frozen", False):
        exe_path = os.path.abspath(str(sys.executable).strip('"'))
        return f'"{exe_path}"{flag}'

    # Check installed location first (%LOCALAPPDATA%\Programs\SmartDownload\SmartDownload.exe)
    installed_exe = get_installed_exe_path()
    if installed_exe:
        return f'"{installed_exe}"{flag}'

    # Prioritize compiled standalone binary in dist/ directory or adjacent to script
    search_dirs = [os.getcwd()]
    if "__file__" in globals() and isinstance(__file__, str):
        b = os.path.dirname(os.path.abspath(__file__))
        search_dirs.extend([b, os.path.abspath(os.path.join(b, "..")), os.path.abspath(os.path.join(b, "..", "..")), os.path.abspath(os.path.join(b, "..", "..", ".."))])
    for sd in search_dirs:
        for exe_name in ("SmartDownload.exe", "TurboDownloader.exe"):
            cand = os.path.join(sd, "dist", exe_name)
            if os.path.isfile(cand):
                return f'"{os.path.abspath(cand)}"{flag}'
            cand2 = os.path.join(sd, exe_name)
            if os.path.isfile(cand2):
                return f'"{os.path.abspath(cand2)}"{flag}'

    # Script mode fallback: prefer pythonw.exe if available so no console window flashes
    py_exe = str(sys.executable).strip('"')
    py_dir = os.path.dirname(py_exe)
    pyw_exe = os.path.join(py_dir, "pythonw.exe")
    if os.path.isfile(pyw_exe):
        py_exe = pyw_exe
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() and isinstance(__file__, str) else os.getcwd()
    script_path = os.path.abspath(os.path.join(base_dir, "turbo_downloader.py"))
    return f'"{py_exe}" "{script_path}"{flag}'

def is_startup_enabled() -> bool:
    """
    Checks if SmartDownload is currently registered to auto-run on Windows startup.
    Checks HKCU Run registry key and cleans up stale or broken keys pointing to missing binaries.
    Returns True if an active, valid auto-start mechanism exists, False otherwise.
    """
    if not IS_WINDOWS or winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ) as key:
            for k_name in (STARTUP_REG_KEY_NAME, LEGACY_STARTUP_REG_KEY_NAME):
                try:
                    val, _ = winreg.QueryValueEx(key, k_name)
                    if val and str(val).strip():
                        exe_path, args, script_path, _ = _parse_startup_cmd(str(val))
                        is_valid = False
                        if exe_path:
                            if script_path:
                                is_valid = os.path.isfile(exe_path) and os.path.isfile(script_path)
                            else:
                                is_valid = os.path.isfile(exe_path)

                        if is_valid:
                            return True
                        elif exe_path:
                            # Stale or broken key pointing to a missing binary or script: clean it up
                            try:
                                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as wkey:
                                    winreg.DeleteValue(wkey, k_name)
                            except Exception:
                                pass
                        else:
                            return True
                except FileNotFoundError:
                    pass
    except (FileNotFoundError, OSError):
        pass

    try:
        startup_dir = get_startup_folder()
        if os.path.isdir(startup_dir):
            for sname in ("Smart Download (SD).lnk", "SmartDownload.lnk"):
                if os.path.isfile(os.path.join(startup_dir, sname)):
                    return True
    except Exception:
        pass
    return False


def enable_startup(minimized: bool = True) -> bool:
    """
    Registers SmartDownload in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
    When minimized=True, adds the --minimized flag so it starts silently in background.
    Cleans up any legacy (TurboDownloader) or stale keys, and coordinates with Scheduled
    Tasks and Startup folder shortcuts.
    Returns True on success, False otherwise.
    """
    if not IS_WINDOWS or winreg is None:
        return False
    cmd = get_startup_command(minimized=minimized)
    reg_ok = False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
            winreg.SetValueEx(key, STARTUP_REG_KEY_NAME, 0, winreg.REG_SZ, cmd)
            # Clean up legacy key
            try:
                winreg.DeleteValue(key, LEGACY_STARTUP_REG_KEY_NAME)
            except (FileNotFoundError, OSError):
                pass
        reg_ok = True
    except Exception:
        reg_ok = False

    if reg_ok:
        # Disable Windows 10/11 Explorer's 10-second artificial startup delay
        try:
            reg_dword = getattr(winreg, "REG_DWORD", 4)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, EXPLORER_SERIALIZE_KEY) as key:
                winreg.SetValueEx(key, "StartupDelayInMSec", 0, reg_dword, 0)
                winreg.SetValueEx(key, "WaitForIdleState", 0, reg_dword, 0)
        except Exception:
            pass

        # Windows 10/11 StartupApproved binary registration
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_RUN_KEY) as key:
                winreg.SetValueEx(key, STARTUP_REG_KEY_NAME, 0, winreg.REG_BINARY, ENABLED_STARTUP_BINARY)
                try:
                    winreg.DeleteValue(key, LEGACY_STARTUP_REG_KEY_NAME)
                except (FileNotFoundError, OSError):
                    pass
        except Exception:
            pass

        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_FOLDER_KEY) as key:
                winreg.SetValueEx(key, "Smart Download (SD).lnk", 0, winreg.REG_BINARY, ENABLED_STARTUP_BINARY)
                for leg in (LEGACY_STARTUP_REG_KEY_NAME, "TurboDownloader.lnk", "Turbo Download Manager Pro.lnk"):
                    try:
                        winreg.DeleteValue(key, leg)
                    except (FileNotFoundError, OSError):
                        pass
        except Exception:
            pass

        # Canonical Run key succeeded: delete duplicate Scheduled Tasks so Windows only launches 1 process
        try:
            for tname in (TASK_NAME, LEGACY_TASK_NAME):
                subprocess.run(
                    ["schtasks.exe", "/Delete", "/TN", tname, "/F"],
                    capture_output=True,
                    timeout=5
                )
        except Exception:
            pass

        # Actively clean up / remove duplicate Startup folder shortcuts
        try:
            startup_dir = get_startup_folder()
            if os.path.isdir(startup_dir):
                for old in ("Smart Download (SD).lnk", "Turbo Download Manager Pro.lnk", "TurboDownloader.lnk", "SmartDownload.lnk"):
                    old_p = os.path.join(startup_dir, old)
                    if os.path.isfile(old_p):
                        try:
                            os.remove(old_p)
                        except Exception:
                            pass
        except Exception:
            pass
        return True

    exe_path, args, script_path, working_dir = _parse_startup_cmd(cmd)

    # Fallback 1: Scheduled Task
    try:
        if exe_path and os.path.isfile(exe_path):
            res = subprocess.run(
                ["schtasks.exe", "/Create", "/F", "/SC", "ONLOGON", "/TN", TASK_NAME, "/TR", cmd],
                capture_output=True,
                timeout=5
            )
            if res.returncode == 0:
                return True
    except Exception:
        pass

    # Fallback 2: Startup folder shortcut
    try:
        if exe_path and os.path.isfile(exe_path):
            startup_dir = get_startup_folder()
            if os.path.isdir(startup_dir):
                for old in ("Turbo Download Manager Pro.lnk", "TurboDownloader.lnk", "SmartDownload.lnk"):
                    old_p = os.path.join(startup_dir, old)
                    if os.path.isfile(old_p):
                        try:
                            os.remove(old_p)
                        except Exception:
                            pass
                lnk_path = os.path.join(startup_dir, "Smart Download (SD).lnk")
                icon_path = ""
                for ico_cand in (
                    os.path.join(os.path.dirname(os.path.abspath(exe_path)), "app_icon.ico"),
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico") if "__file__" in globals() else "",
                    os.path.join(os.getcwd(), "app_icon.ico")
                ):
                    if ico_cand and os.path.isfile(ico_cand):
                        icon_path = os.path.abspath(ico_cand)
                        break

                return _create_startup_shortcut(
                    target_exe=exe_path,
                    shortcut_path=lnk_path,
                    arguments=args,
                    working_dir=working_dir,
                    icon_path=icon_path,
                    description="Smart Download (SD) AutoStart"
                )
    except Exception:
        pass

    return False


def disable_startup() -> bool:
    """
    Removes SmartDownload from HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
    Also cleans up Scheduled Tasks and Startup folder shortcuts.
    Returns True on success or if already absent, False on unexpected error.
    """
    if not IS_WINDOWS or winreg is None:
        return False

    reg_ok = True
    # 1. Clean up Run registry keys
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for k_name in (STARTUP_REG_KEY_NAME, LEGACY_STARTUP_REG_KEY_NAME):
                try:
                    winreg.DeleteValue(key, k_name)
                except FileNotFoundError:
                    pass
    except FileNotFoundError:
        pass
    except (OSError, PermissionError):
        reg_ok = False
    except Exception:
        reg_ok = False

    # 2. Clean up Scheduled Tasks
    try:
        for tname in (TASK_NAME, LEGACY_TASK_NAME):
            try:
                subprocess.run(
                    ["schtasks.exe", "/Delete", "/TN", tname, "/F"],
                    capture_output=True,
                    timeout=5
                )
            except Exception:
                pass
    except Exception:
        pass

    # 3. Clean up Startup folder shortcuts
    try:
        startup_dir = get_startup_folder()
        for name in ("Smart Download (SD).lnk", "SmartDownload.lnk", "TurboDownloader.lnk", "Turbo Download Manager Pro.lnk"):
            p = os.path.join(startup_dir, name)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
    except Exception:
        pass

    # 4. Clean up StartupApproved registry keys
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for k in (STARTUP_REG_KEY_NAME, LEGACY_STARTUP_REG_KEY_NAME):
                try:
                    winreg.DeleteValue(key, k)
                except Exception:
                    pass
    except Exception:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_FOLDER_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for k in ("Smart Download (SD).lnk", LEGACY_STARTUP_REG_KEY_NAME, "SmartDownload.lnk", "TurboDownloader.lnk"):
                try:
                    winreg.DeleteValue(key, k)
                except Exception:
                    pass
    except Exception:
        pass

    return reg_ok


def get_startup_entry() -> Optional[str]:
    """Returns the registered command string from Windows Run registry, or None."""
    if not IS_WINDOWS or winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ) as key:
            for k_name in (STARTUP_REG_KEY_NAME, LEGACY_STARTUP_REG_KEY_NAME):
                try:
                    val, _ = winreg.QueryValueEx(key, k_name)
                    if val and str(val).strip():
                        return str(val)
                except FileNotFoundError:
                    pass
            return None
    except (FileNotFoundError, OSError):
        return None

