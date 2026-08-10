#!/usr/bin/env python3
"""
tools/unit/decompile_test_cmd.py
Decompiles FieldToCommand and QSetCommandUtils convertTestCommand
"""
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"
LIB_DIR = r"C:\Program Files\WinpowerG2\lib"
CP = f"{LIB_DIR}\\winpower-comms-1.0.0.jar;{LIB_DIR}\\winpower-service-1.0.0.jar;{LIB_DIR}\\winpower-common-core-1.0.0.jar;{LIB_DIR}\\winpower-bean-1.0.0.jar;{LIB_DIR}\\usbcomm-1.0.0.jar"

for cls in [
    "com.etn.wp.comms.spec.qprotocol.command.set.rule.FieldToCommand",
    "com.etn.wp.comms.spec.qprotocol.util.QSetCommandUtils",
    "com.etn.wp.comms.spec.qprotocol.command.profile.CommandID"
]:
    print(f"==============================================================================")
    print(f" 📄 Class: {cls}")
    print(f"==============================================================================")
    cmd = [JAVA_EXE, "-cp", CP, "-p", "-c", cls]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(res.stdout[:6000])

