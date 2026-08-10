#!/usr/bin/env python3
"""
tools/unit/inspect_qprotocol.py
Decompiles all QProtocol classes in winpower-comms-1.0.0.jar to find the exact commands, response parsers, and mode calculations.
"""
import zipfile
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAR_DIR = Path(r"C:\Program Files\WinpowerG2\lib")
JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"

def search_qprotocol():
    cp = f"{JAR_DIR}\\winpower-comms-1.0.0.jar;{JAR_DIR}\\winpower-service-1.0.0.jar;{JAR_DIR}\\winpower-common-core-1.0.0.jar;{JAR_DIR}\\winpower-bean-1.0.0.jar;{JAR_DIR}\\usbcomm-1.0.0.jar"
    
    with zipfile.ZipFile(JAR_DIR / "winpower-comms-1.0.0.jar", 'r') as z:
        classes = [name[:-6].replace('/', '.') for name in z.namelist() if "qprotocol" in name and name.endswith('.class')]
        
    print(f"Found {len(classes)} classes in qprotocol package:")
    for c in classes:
        print("  -", c)

    print("\n------------------------------------------------------------------------------")
    print("Decompiling key QProtocol classes...")
    for c in classes:
        print(f"\n==============================================================================")
        print(f" 📄 Class: {c}")
        print(f"==============================================================================")
        cmd = [JAVA_EXE, "-cp", cp, "-p", "-c", c]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(res.stdout[:5000])

if __name__ == "__main__":
    search_qprotocol()
