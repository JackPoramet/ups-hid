#!/usr/bin/env python3
"""
tools/scan_hid.py
~~~~~~~~~~~~~~~~~
USB HID Device Scanner for UPS Monitoring.
Scans all connected USB HID devices, checks for Power Device (UPS) interfaces,
and cross-references detected devices with meta.json profiles.

Usage:
    python tools/scan_hid.py
    python tools/scan_hid.py --all
    python tools/scan_hid.py --json
    python tools/scan_hid.py --vid 0x06DA --pid 0xFFFF
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Ensure stdout supports UTF-8 on Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


try:
    import hid
except ImportError:
    print("Error: 'hidapi' (hid) package is not installed.")
    print("Please install via: pip install hidapi")
    sys.exit(1)


def load_meta_profiles() -> List[dict]:
    """Load registered device profiles from meta.json."""
    meta_paths = [
        ROOT_DIR / "meta.json",
        ROOT_DIR / "windows" / "meta.json",
        ROOT_DIR / "linux" / "ups_module" / "meta.json",
    ]
    for p in meta_paths:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return data.get("devices", [])
            except Exception:
                pass
    return []


def decode_path(path_val: any) -> str:
    """Decode raw device path byte string to unicode string."""
    if isinstance(path_val, bytes):
        try:
            return path_val.decode("utf-8")
        except Exception:
            return path_val.decode("latin-1", errors="ignore")
    return str(path_val or "")


def match_profile(vid: int, pid: int, profiles: List[dict]) -> Optional[dict]:
    """Check if device (VID/PID) matches any registered profile in meta.json."""
    for p in profiles:
        try:
            p_vid = int(p.get("vid", "0"), 0)
            p_pid = int(p.get("pid", "0"), 0)
            if p_vid == vid and (p_pid == pid or p_pid == 0xFFFF):
                return p
        except (ValueError, TypeError):
            pass
    return None


def scan_devices(
    target_vid: Optional[int] = None,
    target_pid: Optional[int] = None,
    power_only: bool = True,
) -> List[dict]:
    """Scan connected USB HID devices."""
    raw_devices = hid.enumerate()
    profiles = load_meta_profiles()
    results = []

    for d in raw_devices:
        vid = d.get("vendor_id", 0)
        pid = d.get("product_id", 0)
        usage_page = d.get("usage_page", 0)
        usage = d.get("usage", 0)

        # Filter by VID/PID if requested
        if target_vid is not None and vid != target_vid:
            continue
        if target_pid is not None and pid != target_pid:
            continue

        # Check if Power Device (Usage Page 0x0084, 0x0085, 0x0086) or known profile
        matched = match_profile(vid, pid, profiles)
        is_power_device = usage_page in (0x0084, 0x0085, 0x0086) or (matched is not None)

        if power_only and not is_power_device:
            continue

        item = {
            "vendor_id": f"0x{vid:04X}",
            "product_id": f"0x{pid:04X}",
            "vendor_id_int": vid,
            "product_id_int": pid,
            "manufacturer": d.get("manufacturer_string") or "Unknown",
            "product": d.get("product_string") or "Unknown",
            "serial_number": d.get("serial_number") or "",
            "usage_page": f"0x{usage_page:04X}",
            "usage": f"0x{usage:04X}",
            "interface_number": d.get("interface_number", -1),
            "release_number": f"0x{d.get('release_number', 0):04X}",
            "path": decode_path(d.get("path")),
            "is_power_device": is_power_device,
            "matched_profile": matched["id"] if matched else None,
            "profile_name": f"{matched['manufacturer']} {matched['model']}" if matched else None,
        }
        results.append(item)

    return results


def print_console_report(devices: List[dict]) -> None:
    """Print readable report to terminal."""
    print("=" * 80)
    print(" 🔍 USB HID Device Scanner — UPS Device Discovery")
    print("=" * 80)

    if not devices:
        print("\n❌ No matching HID devices found.")
        print("   Tips: Connect your UPS via USB cable or use '--all' to list all HID devices.")
        print("=" * 80)
        return

    print(f"\nFound {len(devices)} device(s):\n")

    for i, dev in enumerate(devices, start=1):
        print(f"[{i}] {dev['product']} ({dev['manufacturer']})")
        print(f"    VID: {dev['vendor_id']} ({dev['vendor_id_int']}) | PID: {dev['product_id']} ({dev['product_id_int']})")
        print(f"    Usage Page: {dev['usage_page']} | Usage: {dev['usage']} | Interface: {dev['interface_number']}")
        print(f"    Serial: {dev['serial_number'] or 'N/A'}")
        print(f"    Path: {dev['path']}")

        if dev["matched_profile"]:
            print(f"    ✅ Matched Profile: {dev['matched_profile']} ({dev['profile_name']})")
        elif dev["is_power_device"]:
            print(f"    ⚠️ Power Device detected (Not in meta.json yet)")
        else:
            print(f"    ℹ️ Standard HID Device")
        print("-" * 80)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="USB HID Device Scanner for UPS Monitoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="List all HID devices (default filters for UPS/Power Devices)",
    )
    parser.add_argument(
        "--vid",
        type=lambda x: int(x, 0),
        default=None,
        help="Filter by Vendor ID in hex (e.g. 0x06DA or 0x0001)",
    )
    parser.add_argument(
        "--pid",
        type=lambda x: int(x, 0),
        default=None,
        help="Filter by Product ID in hex (e.g. 0xFFFF or 0x0000)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    devices = scan_devices(
        target_vid=args.vid,
        target_pid=args.pid,
        power_only=not args.all,
    )

    if args.json:
        print(json.dumps(devices, indent=2, ensure_ascii=False))
    else:
        print_console_report(devices)

    return 0


if __name__ == "__main__":
    sys.exit(main())
