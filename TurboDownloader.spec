# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

yt_hidden = collect_submodules('yt_dlp')
yt_datas = collect_data_files('yt_dlp')

a = Analysis(
    ['turbo_downloader.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('extension', 'extension'),
        ('app_icon.ico', '.'),
        ('app_icon.png', '.'),
    ] + yt_datas,
    hiddenimports=[
        'youtube_resolver',
        'browser_bridge',
        'native_messaging_host',
        'register_browser',
        'yt_dlp',
        'PIL',
        'PIL.ImageTk',
    ] + yt_hidden,
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
    name='TurboDownloader',
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
    icon='app_icon.ico',
    manifest='app.manifest',
)
