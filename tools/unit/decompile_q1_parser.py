#!/usr/bin/env python3
"""
tools/unit/decompile_q1_parser.py
Decompiles Q1CommandParser and QProtocolCommandParser to see how Q1 response bits map to WorkMode 5 (BatteryTestMode)
"""
import zipfile
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAR_DIR = Path(r"C:\Program Files\WinpowerG2\lib")
JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"
CP = f"{JAR_DIR}\\winpower-comms-1.0.0.jar;{JAR_DIR}\\winpower-service-1.0.0.jar;{JAR_DIR}\\winpower-common-core-1.0.0.jar;{JAR_DIR}\\winpower-bean-1.0.0.jar;{LIB_DIR if 'LIB_DIR' in locals() else JAR_DIR}\\usbcomm-1.0.0.jar"

with zipfile.ZipFile(JAR_DIR / "winpower-comms-1.0.0.jar", 'r') as z:
    classes = [name[:-6].replace('/', '.') for name in z.namelist() if "parser" in name and name.endswith('.class')]

print("Parsers in winpower-comms:")
for c in classes:
    if "Q1" in c or "QProtocol" in c or "Qu" in c or "Bit" in c or "Char" in c:
        print(f"\n==============================================================================")
        print(f" 📄 Class: {c}")
        print(f"==============================================================================")
        cmd = [JAVA_EXE, "-cp", CP, "-p", "-c", c]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(res.stdout[:5000])

