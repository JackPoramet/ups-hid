# -*- mode: python ; coding: utf-8 -*-
"""
UPS Monitor — PyInstaller Build Spec
======================================
สร้าง single-file .exe สำหรับ Windows

Build:
    pyinstaller windows/build_exe.spec --noconfirm

Output:
    windows/dist/UPS-Monitor.exe

Flags:
    --noconsole   ไม่แสดง terminal window (tray app)
    --onefile     รวมทุกอย่างใน .exe เดียว
"""

import sys
from pathlib import Path

# Root ของโปรเจค (UPS/)
ROOT = Path(SPECPATH).parent  # build_exe.spec อยู่ใน windows/

block_cipher = None

a = Analysis(
    # Entry point
    [str(ROOT / 'windows' / 'tray_service' / 'main.py')],

    pathex=[
        str(ROOT),                          # สำหรับ import core_hid_ups, win32_hid_wrapper
        str(ROOT / 'windows'),              # สำหรับ import tray_service.*
    ],

    binaries=[],

    datas=[
        # Web UI templates + static files
        (str(ROOT / 'windows' / 'tray_service' / 'templates'), 'tray_service/templates'),
        (str(ROOT / 'windows' / 'tray_service' / 'static'),    'tray_service/static'),

        # Icons
        (str(ROOT / 'windows' / 'assets'), 'assets'),
    ] + (
        [(str(ROOT / 'ups_module' / 'drivers'), 'ups_module/drivers')] if (ROOT / 'ups_module' / 'drivers').exists() else []
    ) + (
        [(str(ROOT / 'report_descriptor_live.bin'), '.')] if (ROOT / 'report_descriptor_live.bin').exists() else []
    ),

    hiddenimports=[
        # HID & USB
        'hid',
        'usb',
        'usb.core',

        # Flask
        'flask',
        'flask.templating',
        'jinja2',
        'werkzeug',
        'werkzeug.serving',

        # Windows notifications
        'plyer',
        'plyer.platforms',
        'plyer.platforms.win.notification',

        # System tray
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',

        # Core modules
        'core_hid_ups',
        'win32_hid_wrapper',

        # tray_service modules
        'sqlite3',
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

        # Windows APIs
        'ctypes',
        'ctypes.wintypes',
        'winreg',
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    excludes=[
        # ไม่รวม module ที่ไม่จำเป็น (ลดขนาด exe)
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
    icon=str(ROOT / 'windows' / 'assets' / 'ups_icon.ico') if (ROOT / 'windows' / 'assets' / 'ups_icon.ico').exists() else None,  # App icon
    version_file=None,
    onefile=True,       # Single .exe
)
