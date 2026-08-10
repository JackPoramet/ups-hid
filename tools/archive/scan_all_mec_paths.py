import sys
import pywinusb.hid as pyhid
import hid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== SEARCHING ALL HID PATHS FOR VID_0001 PID_0000 ===")

raw_hid = hid.enumerate()
print(f"\nHIDAPI enumerations matching VID 0x0001:")
for d in raw_hid:
    if d.get("vendor_id") == 1 or d.get("product_id") == 0 or "mec" in (d.get("product_string") or "").lower():
        print(f"  Path: {d.get('path')}")
        print(f"  VID: 0x{d.get('vendor_id'):04x}, PID: 0x{d.get('product_id'):04x}")
        print(f"  Usage Page: 0x{d.get('usage_page'):04x}, Usage: 0x{d.get('usage'):04x}")
        print(f"  Interface: {d.get('interface_number')}")
        print(f"  Manufacturer: {d.get('manufacturer_string')}")
        print(f"  Product: {d.get('product_string')}")
        print("-" * 50)

py_devs = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
print(f"\nPyWinUSB devices matching VID 0x0001 PID 0x0000: {len(py_devs)}")
for d in py_devs:
    print(f"  Path: {d.device_path}")
    print(f"  Vendor: {d.vendor_name}, Product: {d.product_name}")
    print("-" * 50)

