import sys
import time
import pywinusb.hid as pyhid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== TESTING FEATURE REPORT ITEMS FOR MEC MEC0003 ===")

devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
if not devices:
    print("No device found!")
    sys.exit(1)

dev = devices[0]
dev.open()

for r in dev.find_feature_reports():
    print(f"\n--- Feature Report ID={r.report_id} ---")
    try:
        # Get report data
        raw_data = r.get()
        print(f"  Current raw feature data: {bytes(raw_data).hex()}")
    except Exception as e:
        print(f"  r.get() error: {e}")

    # Inspect items in report
    for key, item in r.items():
        print(f"  Item 0x{item.page_id:02x}:0x{item.usage_id:04x} -> current_val={item.get_value()}")

dev.close()
print("\nDone!")

