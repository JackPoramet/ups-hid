#!/usr/bin/env python3
"""
tools/unit/inspect_device_control_api.py
Find and decompile all classes related to DeviceControlApi or protocolId 4 (LINE-INT Q1 protocol)
"""
import zipfile
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAR_DIR = Path(r"C:\Program Files\WinpowerG2\lib")
JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"

def search_classes():
    cp = f"{JAR_DIR}\\winpower-comms-1.0.0.jar;{JAR_DIR}\\winpower-service-1.0.0.jar;{JAR_DIR}\\winpower-common-core-1.0.0.jar;{JAR_DIR}\\winpower-bean-1.0.0.jar;{JAR_DIR}\\usbcomm-1.0.0.jar"
    
    with zipfile.ZipFile(JAR_DIR / "winpower-comms-1.0.0.jar", 'r') as z:
        classes = [name[:-6].replace('/', '.') for name in z.namelist() if name.endswith('.class')]
        
    print("Found classes in winpower-comms-1.0.0.jar:")
    control_classes = [c for c in classes if "Control" in c or "Protocol" in c or "Handler" in c or "Test" in c or "Line" in c or "Megatec" in c or "Q1" in c]
    for c in control_classes:
        print("  -", c)

    print("\n------------------------------------------------------------------------------")
    print("Decompiling key control classes...")
    for c in control_classes[:15]:
        print(f"\n--- Class: {c} ---")
        cmd = [JAVA_EXE, "-cp", cp, "-p", c]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(res.stdout)

if __name__ == "__main__":
    search_classes()
