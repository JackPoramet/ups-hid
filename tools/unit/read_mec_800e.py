#!/usr/bin/env python3
"""
tools/read_mec_800e.py
~~~~~~~~~~~~~~~~~~~~~~
MEC MEC0003 (800E) USB HID UPS Live Reader.
Reads telemetry via HID Indexed String Descriptors (Q1 Protocol).

Usage:
    python tools/read_mec_800e.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from tools.unit.read_mec_ups import read_ups_data as read_mec_once


def read_mec_800e() -> None:
    print("=" * 76)
    print(" 🔌 MEC MEC0003 (800E) — USB HID Live Reader")
    print(" Profile: mec0003_800e (VID=0x0001, PID=0x0000)")
    print("=" * 76)

    read_mec_once()


if __name__ == "__main__":
    read_mec_800e()
