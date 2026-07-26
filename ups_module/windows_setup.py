"""
ups_module/windows_setup.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Windows-only: ติดตั้ง libusb0.sys filter driver ผ่าน UAC prompt

บน Linux ไม่ต้องใช้ไฟล์นี้ — ใช้ linux_setup.py แทน
"""

import logging
import os
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def install_filter(vid: int, pid: int) -> bool:
    """
    Triggers the UAC prompt to install the libusb0.sys filter driver.

    Windows-only — บน Linux จะ return False ทันที
    Uses install-filter-win.exe from the libusb-win32 project.
    """
    if sys.platform != "win32":
        return False

    import ctypes
        
    drivers_dir = Path(__file__).parent / "drivers" / "windows"
    installer_exe = drivers_dir / "install-filter-win.exe"
    
    if not installer_exe.exists():
        logger.error("install-filter-win.exe not found at %s", installer_exe)
        return False

    hwid = f"USB\\VID_{vid:04X}&PID_{pid:04X}"
    logger.info("Attempting to install libusb0 filter driver for %s", hwid)
    
    # Request UAC elevation via ShellExecuteW
    # verb 'runas' forces the UAC prompt.
    ret = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        str(installer_exe),
        f'install --device="{hwid}"',
        None,
        0  # SW_HIDE
    )
    
    # ShellExecuteW returns > 32 on success.
    if ret > 32:
        logger.info("Filter driver installation launched successfully. Waiting for completion...")
        # Give it a few seconds to install and OS to reload the device stack
        time.sleep(3.0)
        return True
    else:
        logger.error("Failed to launch filter installer (User might have cancelled UAC). Code: %d", ret)
        return False
