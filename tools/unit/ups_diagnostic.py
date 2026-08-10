#!/usr/bin/env python3
"""UPS diagnostic helper

Runs a few checks to help debug why Feature Report 0x24 doesn't show test state.

Usage:
    python tools/unit/ups_diagnostic.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from windows.win32_hid_wrapper import WinHidApi, normalize_path
from windows.core_hid_ups import list_ups_devices, open_ups_device, read_all_feature_reports


def main():
    print("UPS Diagnostic Helper")
    devices = list_ups_devices()
    if not devices:
        print("No UPS HID devices found")
        return 1

    for idx, d in enumerate(devices, start=1):
        print(f"\n[{idx}] {d.get('manufacturer_string')} / {d.get('product_string')} SN={d.get('serial_number')}")
        print(f"    path: {d.get('path_str')}")
        print(f"    usage_page=0x{(d.get('usage_page') or 0):04X} usage=0x{(d.get('usage') or 0):04X}")

    target = devices[0]
    print("\nOpening first device via hid library...")
    h, info = open_ups_device(vid=target.get('vendor_id', 0x06DA), pid=target.get('product_id', 0xFFFF), target_path=target.get('path_str'), target_serial=target.get('serial_number'))
    if not h:
        print("open_ups_device failed")
        return 2

    print("Opened OK. Trying to read feature reports (include zeros)...")
    rids = [0x24, 0x01, 0x07, 0x27, 0x31]
    raw, meta = read_all_feature_reports(h, report_ids=rids, sizes=(64,), retries=2, include_zero=True)
    for rid in rids:
        if rid in raw:
            data = raw[rid]
            print(f"  Feature 0x{rid:02X}: len={len(data)} hex={' '.join(f'{b:02X}' for b in data)} meta={meta.get(rid)}")
        else:
            print(f"  Feature 0x{rid:02X}: NOT READ")

    # Try WinHidApi open and direct HidD_GetFeature
    try:
        print("\nAttempting WinHidApi direct HidD_GetFeature (requires Admin)...")
        api = WinHidApi()
        path = normalize_path(target.get('path'))
        hndl = api.create_file(path)
        caps, err = api.get_caps(hndl)
        print(f"  Caps: {caps} err={err}")
        for rid in [0x24, 0x01, 0x07, 0x31]:
            got = api.get_feature_report(hndl, rid, 64)
            print(f"  HidD_GetFeature 0x{rid:02X}: {got}")
        api.close_handle(hndl)
    except Exception as exc:
        print(f"  WinHidApi direct read failed: {exc}")

    # Try reading input reports for potential Q1 strings
    print("\nTry reading input reports (non-blocking few reads)...")
    try:
        for i in range(8):
            data = h.read(64, 200)
            if data:
                arr = list(data)
                print(f"  Input[{i}] len={len(arr)} hex={' '.join(f'{b:02X}' for b in arr)} ascii={''.join(chr(b) if 32<=b<127 else '.' for b in arr[:64])}")
            else:
                print(f"  Input[{i}] NO DATA")
            time.sleep(0.2)
    except Exception as exc:
        print(f"  read input reports failed: {exc}")

    try:
        h.close()
    except Exception:
        pass

    print("\nDiagnostic complete")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
