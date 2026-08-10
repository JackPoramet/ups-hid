import sys
import time
import pywinusb.hid as pyhid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== READING LIVE DATA FROM MEC MEC0003 (VID=0x0001 PID=0x0000) ===")

devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
if not devices:
    print("No device found!")
    sys.exit(1)

dev = devices[0]
dev.open()

print(f"Connected to: {dev.product_name} ({dev.vendor_name})")

received_reports = []

def raw_handler(data):
    # data is a list of byte integers [report_id, b1, b2, ...]
    rep_id = data[0]
    raw_bytes = bytes(data)
    print(f"\n[RECEIVED INPUT REPORT ID {rep_id}]: len={len(data)}")
    print(f"  HEX: {raw_bytes.hex()}")
    print(f"  BYTES: {list(data)}")
    received_reports.append((rep_id, data))

dev.set_raw_data_handler(raw_handler)

print("\nListening for Input Reports from UPS for 5 seconds...")
start = time.time()
while time.time() - start < 5:
    time.sleep(0.1)

print("\n--- Summary of Received Reports ---")
print(f"Total reports received: {len(received_reports)}")

# Let's also inspect values in Input Reports
for r in dev.find_input_reports():
    print(f"\nInput Report ID={r.report_id}:")
    for key, item in r.items():
        val = item.get_value()
        print(f"  Usage 0x{item.page_id:02x}:0x{item.usage_id:04x} -> Value: {val} (0x{val:x})")

dev.close()
print("\nDone!")

