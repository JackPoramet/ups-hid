#!/usr/bin/env python3
"""
tools/unit/analyze_jusb_dll.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
วิเคราะห์โครงสร้าง DLL Exports และ String ภายใน jusb.dll เพื่อหาวิธีเปิด Handle และส่ง OrderUPS("T") Direct Native
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

dll_path = r"C:\Program Files\WinpowerG2\jusb.dll"
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

with open(dll_path, "rb") as f:
    data = f.read()

print("🔍 สแกนหา ASCII Strings ภายใน jusb.dll:")
strings = []
curr = []
for b in data:
    if 32 <= b <= 126:
        curr.append(chr(b))
    else:
        if len(curr) >= 4:
            strings.append("".join(curr))
        curr = []

interesting = [s for s in strings if any(k in s.lower() for k in ["usb", "order", "hid", "write", "report", "control", "win", "dev"])]
for s in interesting[:50]:
    print(f"  • {s}")
