# -*- mode: python ; coding: utf-8 -*-
import os

payload_dir = os.path.abspath('installer_payload')

a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    datas=[
        (payload_dir, 'payload'),
        ('app_icon.ico', '.'),
        ('app_icon.png', '.'),
    ],
    hiddenimports=[
        'win32com',
        'win32com.client',
        'register_browser',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Strip redundant Tcl/Tk tzdata, msgs, and demos
a.datas = [d for d in a.datas if not any(k in d[0].replace('\\', '/').lower().split('/') for k in ('tzdata', 'msgs', 'demos'))]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SmartDownload-Setup',
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
