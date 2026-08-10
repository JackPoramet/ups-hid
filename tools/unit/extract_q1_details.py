#!/usr/bin/env python3
"""
tools/unit/extract_q1_details.py
Search for exact text strings and method names in qprotocol classes
"""
import zipfile
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAR_PATH = Path(r"C:\Program Files\WinpowerG2\lib\winpower-comms-1.0.0.jar")

with zipfile.ZipFile(JAR_PATH, 'r') as z:
    for name in z.namelist():
        if "qprotocol" in name and name.endswith(".class"):
            data = z.read(name)
            # Find string constants in byte content
            strings = re.findall(b'[\x20-\x7e]{3,}', data)
            interesting = [s.decode('ascii') for s in strings if any(x in s for x in [b"mode", b"Mode", b"Test", b"test", b"STATUS", b"Status", b"Q1", b"T\r", b"TL\r", b"T<", b"T\n"])]
            if interesting:
                print(f"=== {name} ===")
                for s in set(interesting):
                    print("  ", s)

