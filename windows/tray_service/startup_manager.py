"""
UPS Monitor — Windows Startup Manager
========================================
จัดการการเปิดใช้งานโปรแกรมอัตโนมัติเมื่อเริ่มต้นระบบ Windows (Windows Startup)

ใช้ Windows Registry:
    Root: HKCU (HKEY_CURRENT_USER)
    Subkey: Software\\Microsoft\\Windows\\CurrentVersion\\Run
    ValueName: UPS Monitor
"""

from __future__ import annotations

import logging
import os
import sys
import winreg
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REG_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "ENEREX UPS Monitor"


def get_current_exe_path() -> str:
    """
    คืนค่า absolute path ของ executable ปัจจุบัน
    - ถ้าคอมไพล์ด้วย PyInstaller: sys.executable
    - ถ้ารันจาก python script: sys.executable พร้อม -m tray_service.main
    """
    if getattr(sys, "frozen", False):
        return sys.executable
    return f'"{sys.executable}" "{Path(__file__).resolve().parent / "main.py"}"'


def is_startup_enabled(app_name: str = _APP_NAME) -> bool:
    """
    ตรวจสอบว่ามีการตั้งค่า Startup ใน Windows Registry หรือไม่

    Returns:
        bool: True หากมี key ใน Registry
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_SUBKEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, app_name)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.error(f"Error checking Windows startup registry: {e}")
        return False


def set_startup(enable: bool, app_name: str = _APP_NAME, exe_path: Optional[str] = None) -> bool:
    """
    เปิดหรือปิดการทำงานแบบ Windows Startup

    Args:
        enable: True เพื่อเปิดใช้งาน, False เพื่อยกเลิก
        app_name: ชื่อแอพใน Registry
        exe_path: Path ไปยังไฟล์ .exe (ถ้าเป็น None จะคำนวณให้อัตโนมัติ)

    Returns:
        bool: True หากดำเนินการสำเร็จ
    """
    target_path = exe_path or get_current_exe_path()
    if not target_path.startswith('"') and " " in target_path:
        target_path = f'"{target_path}"'

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_SUBKEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, target_path)
                logger.info(f"Windows Startup ENABLED: {app_name} -> {target_path}")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    logger.info(f"Windows Startup DISABLED: {app_name}")
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        logger.error(f"Failed to set Windows startup registry ({enable}): {e}")
        return False
