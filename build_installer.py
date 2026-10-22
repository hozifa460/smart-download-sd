"""
========================================================================================
🔨 AUTOMATED BUILDER — TurboDownloader & TurboDownloader-Setup
========================================================================================
Automates the build process for:
1. Standalone Application: dist/TurboDownloader.exe (via TurboDownloader.spec)
2. Standalone Windows Installer: dist/TurboDownloader-Setup.exe (via TurboDownloader-Setup.spec)
========================================================================================
"""

import os
import sys
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
PAYLOAD_DIR = os.path.join(BASE_DIR, "installer_payload")


def build_app(rebuild: bool = False):
    """Compiles dist/TurboDownloader.exe using PyInstaller."""
    exe_path = os.path.join(DIST_DIR, "TurboDownloader.exe")
    if not rebuild and os.path.isfile(exe_path):
        print(f"[+] TurboDownloader.exe already exists at {exe_path} ({os.path.getsize(exe_path):,} bytes)")
        return exe_path

    print("[*] Building TurboDownloader.exe via PyInstaller...")
    spec_path = os.path.join(BASE_DIR, "TurboDownloader.spec")
    res = subprocess.run([sys.executable, "-m", "PyInstaller", spec_path, "--noconfirm"], cwd=BASE_DIR)
    if res.returncode != 0:
        raise RuntimeError(f"PyInstaller failed to build TurboDownloader.exe with returncode {res.returncode}")

    if not os.path.isfile(exe_path):
        raise FileNotFoundError(f"Expected binary not found after build: {exe_path}")

    print(f"[+] TurboDownloader.exe successfully built: {os.path.getsize(exe_path):,} bytes")
    return exe_path


def prepare_payload():
    """Assembles all files needed in the installer payload directory."""
    print("[*] Preparing installer payload directory...")
    os.makedirs(PAYLOAD_DIR, exist_ok=True)

    # 1. Main executable
    src_exe = os.path.join(DIST_DIR, "TurboDownloader.exe")
    if not os.path.isfile(src_exe):
        raise FileNotFoundError(f"Missing {src_exe}. Build it first.")
    shutil.copy2(src_exe, os.path.join(PAYLOAD_DIR, "TurboDownloader.exe"))

    # 2. Icons
    for icon_name in ("app_icon.ico", "app_icon.png"):
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
    import register_browser as rb
    rb.generate_launcher_batch(os.path.join(PAYLOAD_DIR, "turbo_host.bat"))
    reg_script = os.path.join(BASE_DIR, "register_browser.py")
    if os.path.isfile(reg_script):
        shutil.copy2(reg_script, os.path.join(PAYLOAD_DIR, "register_browser.py"))

    print(f"[+] Installer payload prepared at: {PAYLOAD_DIR}")


def build_installer():
    """Compiles dist/TurboDownloader-Setup.exe using PyInstaller."""
    print("[*] Building TurboDownloader-Setup.exe via PyInstaller...")
    spec_path = os.path.join(BASE_DIR, "TurboDownloader-Setup.spec")
    res = subprocess.run([sys.executable, "-m", "PyInstaller", spec_path, "--noconfirm"], cwd=BASE_DIR)
    if res.returncode != 0:
        raise RuntimeError(f"PyInstaller failed to build TurboDownloader-Setup.exe with returncode {res.returncode}")

    setup_path = os.path.join(DIST_DIR, "TurboDownloader-Setup.exe")
    if not os.path.isfile(setup_path):
        raise FileNotFoundError(f"Installer binary not found: {setup_path}")

    print(f"[+] TurboDownloader-Setup.exe successfully built: {os.path.getsize(setup_path):,} bytes")
    return setup_path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    import argparse
    parser = argparse.ArgumentParser(description="TurboDownloader Build Automation")
    parser.add_argument("--rebuild-all", action="store_true", help="Force rebuild of TurboDownloader.exe")
    parser.add_argument("--installer-only", action="store_true", help="Only build TurboDownloader-Setup.exe")
    args = parser.parse_args()

    print("=" * 70)
    print("[*] TURBO DOWNLOAD MANAGER PRO - BUILD PIPELINE")
    print("=" * 70)

    if not args.installer_only:
        build_app(rebuild=args.rebuild_all)

    prepare_payload()
    setup_exe = build_installer()

    print("\n" + "=" * 70)
    print("[+] BUILD COMPLETE")
    print(f"App Binary:      {os.path.join(DIST_DIR, 'TurboDownloader.exe')}")
    print(f"Setup Installer: {setup_exe}")
    print("=" * 70)


if __name__ == "__main__":
    main()
