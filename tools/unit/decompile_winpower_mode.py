#!/usr/bin/env python3
"""
tools/unit/decompile_winpower_mode.py
Decompiles Winpower classes related to WorkMode, DataTag, EventCode, and DeviceControl
"""
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"
LIB_DIR = r"C:\Program Files\WinpowerG2\lib"

CLASSES_TO_INSPECT = [
    "com.etn.wp.common.core.constant.ups.WorkMode",
    "com.etn.wp.common.core.constant.ups.data.DataTag",
    "com.etn.wp.common.core.constant.ups.EventCode",
    "com.etn.wp.comms.util.DeviceControlUtils",
    "com.etn.wp.businessService.DeviceControlManager"
]

def decompile():
    cp = f"{LIB_DIR}\\winpower-common-core-1.0.0.jar;{LIB_DIR}\\winpower-comms-1.0.0.jar;{LIB_DIR}\\winpower-service-1.0.0.jar;{LIB_DIR}\\winpower-bean-1.0.0.jar;{LIB_DIR}\\usbcomm-1.0.0.jar"
    for cls in CLASSES_TO_INSPECT:
        print("==============================================================================")
        print(f" 📄 Decompiling: {cls}")
        print("==============================================================================")
        cmd = [JAVA_EXE, "-cp", cp, "-p", "-c", cls]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            print(res.stdout[:3000]) # print first 3000 chars of disassembly
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    decompile()
