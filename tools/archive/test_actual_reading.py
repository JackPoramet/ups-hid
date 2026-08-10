import sys
import time
import pywinusb.hid as pyhid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== VERIFYING ACTUAL READINGS FROM MEC MEC0003 ===")

devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
if not devices:
    print("❌ No device found with VID=0x0001 PID=0x0000!")
    sys.exit(1)

dev = devices[0]
dev.open()

print(f"✅ Device Connected: {dev.product_name} (Path: {dev.device_path})")

# Let's inspect raw feature reports and input reports
raw_packets = []

def raw_cb(data):
    raw_packets.append(data)
    print(f"  [RAW PACKET RECEIVED]: RepID={data[0]}, Len={len(data)}, Hex={bytes(data).hex()}")

dev.set_raw_data_handler(raw_cb)

print("\n--- Feature Reports Raw Data ---")
for r in dev.find_feature_reports():
    try:
        data = r.get()
        print(f"Feature Report ID={r.report_id}: Len={len(data)}, Hex={bytes(data).hex()}")
    except Exception as e:
        print(f"Feature Report ID={r.report_id} read error: {e}")

print("\n--- Input Reports Current State ---")
for r in dev.find_input_reports():
    print(f"\nInput Report ID={r.report_id}:")
    for key, item in r.items():
        val = item.get_value()
        print(f"  Item 0x{item.page_id:02x}:0x{item.usage_id:04x} -> Raw Value: {val} (0x{val:x})")

print("\nWaiting 2 seconds for any raw background packets...")
time.sleep(2.0)

dev.close()
print(f"\nTotal background raw packets captured: {len(raw_packets)}")
print("Done!")

