"""
========================================================================================
🔨 AUTOMATED BUILDER — SmartDownload & SmartDownload-Setup
========================================================================================
Automates the build process for:
1. Standalone Application: dist/SmartDownload.exe (via SmartDownload.spec)
2. Standalone Windows Installer: dist/SmartDownload-Setup.exe (via SmartDownload-Setup.spec)
========================================================================================
"""

import os
import sys
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
DIST_DIR = os.path.join(BASE_DIR, "dist")
PAYLOAD_DIR = os.path.join(BASE_DIR, "installer_payload")


STALE_DIST_ARTIFACTS = (
    "TurboDownloader.exe",
    "TurboDownloader-Setup.exe",
    "com.turbodownloader.host.json",
    "turbo_host.bat",
)


def clean_stale_dist_artifacts():
    """Removes legacy TurboDownloader artifacts from dist/ and syncs the Smart Download extension folder."""
    if not os.path.isdir(DIST_DIR):
        return
    for name in STALE_DIST_ARTIFACTS:
        p = os.path.join(DIST_DIR, name)
        if os.path.exists(p):
            try:
                os.chmod(p, 0o777)
                os.remove(p)
            except Exception:
                pass
    src_ext = os.path.join(BASE_DIR, "extension")
    dist_ext = os.path.join(DIST_DIR, "extension")
    if os.path.isdir(src_ext):
        try:
            shutil.copytree(src_ext, dist_ext, dirs_exist_ok=True)
        except Exception:
            pass


def build_app(rebuild: bool = False):
    """Compiles dist/SmartDownload.exe using PyInstaller."""
    exe_path = os.path.join(DIST_DIR, "SmartDownload.exe")
    if not rebuild and os.path.isfile(exe_path):
        clean_stale_dist_artifacts()
        print(f"[+] SmartDownload.exe already exists at {exe_path} ({os.path.getsize(exe_path):,} bytes)")
        return exe_path

    print("[*] Building SmartDownload.exe via PyInstaller...")
    spec_path = os.path.join(BASE_DIR, "SmartDownload.spec")
    res = subprocess.run([sys.executable, "-m", "PyInstaller", spec_path, "--noconfirm"], cwd=BASE_DIR)
    if res.returncode != 0:
        raise RuntimeError(f"PyInstaller failed to build SmartDownload.exe with returncode {res.returncode}")

    if not os.path.isfile(exe_path):
        raise FileNotFoundError(f"Expected binary not found after build: {exe_path}")

    clean_stale_dist_artifacts()
    print(f"[+] SmartDownload.exe successfully built: {os.path.getsize(exe_path):,} bytes")
    return exe_path


def prepare_payload():
    """Assembles all files needed in the installer payload directory."""
    print("[*] Preparing installer payload directory...")
    # Clean payload directory completely to prevent bundling stale or duplicate binaries
    if os.path.isdir(PAYLOAD_DIR):
        shutil.rmtree(PAYLOAD_DIR, ignore_errors=True)
    os.makedirs(PAYLOAD_DIR, exist_ok=True)

    # 1. Main executable: Bundle ONLY SmartDownload.exe (installer.py links TurboDownloader.exe at install time)
    src_exe = os.path.join(DIST_DIR, "SmartDownload.exe")
    if not os.path.isfile(src_exe):
        legacy_src = os.path.join(DIST_DIR, "TurboDownloader.exe")
        if os.path.isfile(legacy_src):
            src_exe = legacy_src
        else:
            raise FileNotFoundError(f"Missing {src_exe}. Build it first.")
    shutil.copy2(src_exe, os.path.join(PAYLOAD_DIR, "SmartDownload.exe"))

    # 2. Icons
    for icon_name in ("app_icon.ico", "app_icon.png"):
        src = os.path.join(BASE_DIR, "assets", icon_name)
        if not os.path.isfile(src):
            src = os.path.join(BASE_DIR, icon_name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(PAYLOAD_DIR, icon_name))

    # 3. Extension directory
    src_ext = os.path.join(BASE_DIR, "extension")
    dest_ext = os.path.join(PAYLOAD_DIR, "extension")
    if os.path.isdir(dest_ext):
        shutil.rmtree(dest_ext, ignore_errors=True)
    if os.path.isdir(src_ext):
        shutil.copytree(src_ext, dest_ext)

    # 4. Host launcher batch and registration script
    try:
        from smart_download.services.browser import registry as rb
    except ImportError:
        import register_browser as rb
    rb.generate_launcher_batch(os.path.join(PAYLOAD_DIR, "sd_host.bat"))
    src_json = os.path.join(BASE_DIR, "com.smartdownload.host.json")
    if os.path.isfile(src_json):
        shutil.copy2(src_json, os.path.join(PAYLOAD_DIR, "com.smartdownload.host.json"))
    reg_script = os.path.join(BASE_DIR, "src", "smart_download", "services", "browser", "registry.py")
    if not os.path.isfile(reg_script):
        reg_script = os.path.join(BASE_DIR, "register_browser.py")
    if os.path.isfile(reg_script):
        shutil.copy2(reg_script, os.path.join(PAYLOAD_DIR, "register_browser.py"))
    hm_script = os.path.join(BASE_DIR, "src", "smart_download", "services", "browser", "host_manifest.py")
    if os.path.isfile(hm_script):
        shutil.copy2(hm_script, os.path.join(PAYLOAD_DIR, "host_manifest.py"))

    print(f"[+] Installer payload prepared at: {PAYLOAD_DIR}")


def build_installer():
    """Compiles dist/SmartDownload-Setup.exe using PyInstaller."""
    print("[*] Building SmartDownload-Setup.exe via PyInstaller...")
    spec_path = os.path.join(BASE_DIR, "SmartDownload-Setup.spec")
    res = subprocess.run([sys.executable, "-m", "PyInstaller", spec_path, "--noconfirm"], cwd=BASE_DIR)
    if res.returncode != 0:
        raise RuntimeError(f"PyInstaller failed to build SmartDownload-Setup.exe with returncode {res.returncode}")

    setup_path = os.path.join(DIST_DIR, "SmartDownload-Setup.exe")
    if not os.path.isfile(setup_path):
        raise FileNotFoundError(f"Installer binary not found: {setup_path}")

    clean_stale_dist_artifacts()
    print(f"[+] SmartDownload-Setup.exe successfully built: {os.path.getsize(setup_path):,} bytes")
    return setup_path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    import argparse
    parser = argparse.ArgumentParser(description="SmartDownload Build Automation")
    parser.add_argument("--rebuild-all", action="store_true", help="Force rebuild of SmartDownload.exe")
    parser.add_argument("--installer-only", action="store_true", help="Only build SmartDownload-Setup.exe")
    args = parser.parse_args()

    print("=" * 70)
    print("[*] SMART DOWNLOAD (SD) - BUILD PIPELINE")
    print("=" * 70)

    if not args.installer_only:
        build_app(rebuild=args.rebuild_all)

    prepare_payload()
    setup_exe = build_installer()

    print("\n" + "=" * 70)
    print("[+] BUILD COMPLETE")
    print(f"App Binary:      {os.path.join(DIST_DIR, 'SmartDownload.exe')}")
    print(f"Setup Installer: {setup_exe}")
    print("=" * 70)


if __name__ == "__main__":
    main()
