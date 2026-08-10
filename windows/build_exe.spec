# -*- mode: python ; coding: utf-8 -*-
"""
UPS Monitor — PyInstaller Build Spec
======================================
สร้าง single-file .exe สำหรับ Windows

Build:
    pyinstaller windows/build_exe.spec --noconfirm

Output:
    windows/dist/ENEREX-UPS-Monitor.exe
"""

import sys
from pathlib import Path

# Spec directory is windows/
SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent  # UPS/

block_cipher = None

a = Analysis(
    # Entry point
    [str(SPEC_DIR / 'tray_service' / 'main.py')],

    pathex=[
        str(ROOT),                          # Root (UPS/)
        str(SPEC_DIR),                      # windows/ (สำหรับ core_hid_ups, win32_hid_wrapper)
        str(SPEC_DIR / 'tray_service'),     # windows/tray_service/
    ],

    binaries=[],

    datas=[
        # Web UI templates + static files
        (str(SPEC_DIR / 'tray_service' / 'templates'), 'tray_service/templates'),
        (str(SPEC_DIR / 'tray_service' / 'static'),    'tray_service/static'),

        # Icons & assets
        (str(SPEC_DIR / 'assets'), 'assets'),
    ] + (
        [(str(SPEC_DIR / 'meta.json'), '.')] if (SPEC_DIR / 'meta.json').exists() else []
    ) + (
        [(str(ROOT / 'ups_module' / 'drivers'), 'ups_module/drivers')] if (ROOT / 'ups_module' / 'drivers').exists() else []
    ),

    hiddenimports=[
        # Core HID & Win32 APIs
        'core_hid_ups',
        'win32_hid_wrapper',
        'check_ups_status',
        'hid',
        'usb',
        'usb.core',
        'ctypes',
        'ctypes.wintypes',
        'winreg',

        # Flask & Web Server
        'flask',
        'flask.templating',
        'jinja2',
        'werkzeug',
        'werkzeug.serving',

        # Windows Notifications & System Tray
        'plyer',
        'plyer.platforms',
        'plyer.platforms.win.notification',
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',

        # Standard Modules & Database
        'sqlite3',
        'json',
        'logging',
        'threading',
        'subprocess',
        'dataclasses',

        # tray_service package modules
        'tray_service',
        'tray_service.main',
        'tray_service.database',
        'tray_service.startup_manager',
        'tray_service.config_manager',
        'tray_service.poller',
        'tray_service.notifications',
        'tray_service.auto_shutdown',
        'tray_service.web_server',
        'tray_service.tray_app',
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    excludes=[
        'PySide6',
        'PyQt5',
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'jupyter',
        'IPython',
        'test',
        'unittest',
    ],

    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ENEREX-UPS-Monitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # บีบอัด exe ด้วย UPX (ถ้ามี)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # ไม่แสดง console window (tray app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(SPEC_DIR / 'assets' / 'ups_icon.ico') if (SPEC_DIR / 'assets' / 'ups_icon.ico').exists() else None,  # App icon
    version_file=None,
    onefile=True,       # Single .exe
)
