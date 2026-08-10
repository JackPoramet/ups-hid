#!/usr/bin/env python3
"""
tools/unit/decompile_win_hid.py
Decompiles santak.hid classes in usbcomm-1.0.0.jar
"""
import zipfile
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"
JAR_PATH = r"C:\Program Files\WinpowerG2\lib\usbcomm-1.0.0.jar"

with zipfile.ZipFile(JAR_PATH, 'r') as z:
    for name in z.namelist():
        if name.endswith('.class') and 'santak/hid' in name:
            cls_name = name.replace('/', '.').replace('.class', '')
            print(f"--- Class: {cls_name} ---")
            cmd = [JAVA_EXE, "-cp", JAR_PATH, cls_name]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            for line in res.stdout.splitlines():
                if "class " in line or "interface " in line or "implements " in line:
                    print(" ", line)
