# -*- mode: python ; coding: utf-8 -*-
import os
import sys

_src_path = os.path.abspath('src')
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

yt_hidden = collect_submodules('yt_dlp')
yt_datas = collect_data_files('yt_dlp')
pystray_hidden = collect_submodules('pystray')
sd_hidden = collect_submodules('smart_download')

extra_binaries = []


a = Analysis(
    ['turbo_downloader.py'],
    pathex=[_src_path],
    binaries=extra_binaries,
    datas=[
        ('extension', 'extension'),
        ('assets/app_icon.ico', 'assets'),
        ('assets/app_icon.png', 'assets'),
        ('assets/app_icon.ico', '.'),
        ('assets/app_icon.png', '.'),
        ('src/smart_download/locales', 'smart_download/locales'),
    ] + yt_datas,
    hiddenimports=[
        'smart_download',
        'smart_download.services.media_extractor',
        'smart_download.services.preview_stream_bridge',
        'smart_download.ui.modals.preview_html_builder',
        'updater',
        'youtube_resolver',
        'browser_bridge',
        'native_messaging_host',
        'register_browser',
        'yt_dlp',
        'PIL',
        'PIL.ImageTk',
        'pystray',
        'pystray._win32',
    ] + yt_hidden + pystray_hidden + sd_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Strip redundant Tcl/Tk tzdata, msgs, and demos to prevent extracting 700+ unnecessary files on startup
a.datas = [d for d in a.datas if not any(k in d[0].replace('\\', '/').lower().split('/') for k in ('tzdata', 'msgs', 'demos'))]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SmartDownload',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
    manifest='assets/app.manifest',
)
