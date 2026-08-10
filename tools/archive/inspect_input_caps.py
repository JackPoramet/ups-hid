import sys
import pywinusb.hid as pyhid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
dev = devices[0]
dev.open()

print("\n--- INPUT REPORTS SUMMARY ---")
for r in dev.find_input_reports():
    print(f"\nInput Report ID={r.report_id}: ({len(r.items())} items)")
    for key, item in r.items():
        print(f"  Item 0x{item.page_id:02x}:0x{item.usage_id:04x}: usage_str='{item.get_usage_string()}'")

dev.close()

