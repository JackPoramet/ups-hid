import sys
import time
import pywinusb.hid as pyhid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== EXACT HID REPORT TEST FOR MEC MEC0003 ===")

devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
if not devices:
    print("No device found!")
    sys.exit(1)

dev = devices[0]
dev.open()

print(f"Device: {dev.product_name} (VID=0x{dev.vendor_id:04x}, PID=0x{dev.product_id:04x})")

def raw_input_handler(data):
    print(f"  [Input Report Callback]: len={len(data)} hex={bytes(data).hex()} str='{bytes(data)}'")

dev.set_raw_data_handler(raw_input_handler)

feature_reports = dev.find_feature_reports()
print(f"\nFound {len(feature_reports)} feature report definition(s):")

for r in feature_reports:
    print(f"\n--- Testing Feature Report ID={r.report_id} ---")
    try:
        data = r.get()
        print(f"  GET Report ID={r.report_id}: hex={bytes(data).hex()} str='{bytes(data)}'")
    except Exception as e:
        print(f"  GET Report ID={r.report_id} error: {e}")

    # Now let's try sending Q1\r
    for cmd in [b"Q1\r", b"Q1", b"I\r", b"F\r"]:
        try:
            # Payload array of bytes (length 16 including report_id)
            payload = [r.report_id] + list(cmd) + [0] * (15 - len(cmd))
            print(f"  Sending {cmd} to Report ID={r.report_id}: {payload}")
            r.set(payload)
            r.send()
            time.sleep(0.1)
            
            data_back = r.get()
            print(f"  READBACK Report ID={r.report_id}: hex={bytes(data_back).hex()} str='{bytes(data_back)}'")
        except Exception as e:
            print(f"  SEND/READBACK error: {e}")

print("\nWaiting 2 seconds for any input report callbacks...")
time.sleep(2)

dev.close()
print("Done!")

