#!/usr/bin/env python3
"""
tools/unit/inspect_winpower_mode5.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
สแกนค้นหาการตีความ "mode": "5" / protocolId 4 (LINE-INT)
และหาว่าฟังก์ชันไหนที่คำนวณ mode = 5 หรือส่งคำสั่ง Test แบตเตอรี่
"""

import zipfile
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAR_DIR = Path(r"C:\Program Files\WinpowerG2\lib")
TARGET_JARS = [
    "winpower-comms-1.0.0.jar",
    "winpower-service-1.0.0.jar",
    "usbcomm-1.0.0.jar",
    "winpower-bean-1.0.0.jar",
    "winpower-common-core-1.0.0.jar"
]

def search_jars():
    print("==============================================================================")
    print(" 🔍 Searching Winpower JAR files for mode 5 / protocolId 4 / Battery Test...")
    print("==============================================================================")
    
    keywords = [
        b"BatteryTestInProgress",
        b"protocolId",
        b"supportQuickTest",
        b"LINE-INT",
        b"deviceControl/test",
        b"testStatus",
        b"batteryStatus",
        b"mode"
    ]

    for jar_name in TARGET_JARS:
        jar_path = JAR_DIR / jar_name
        if not jar_path.exists():
            continue
        print(f"\n📦 Checking {jar_name}...")
        try:
            with zipfile.ZipFile(jar_path, 'r') as z:
                for filename in z.namelist():
                    if filename.endswith('.class'):
                        data = z.read(filename)
                        # Check for mode or protocolId or test references
                        matches = [kw for kw in keywords if kw in data]
                        if matches:
                            print(f"  --> Found in {filename}: {[m.decode('utf-8') for m in matches]}")
        except Exception as e:
            print(f"  Error reading {jar_name}: {e}")

if __name__ == "__main__":
    search_jars()
