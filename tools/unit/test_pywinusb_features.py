import pywinusb.hid as pyhid
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
if not devices:
    print("Device not found")
    sys.exit(1)

dev = devices[0]
dev.open()
print("PyWinUSB opened successfully.")
print(f"Feature reports: {dev.find_feature_reports()}")
print(f"Input reports: {dev.find_input_reports()}")
print(f"Output reports: {dev.find_output_reports()}")

for rep in dev.find_feature_reports():
    print(f"Trying to get feature report: report_id={rep.report_id}")
    try:
        data = rep.get()
        print(f"  Got data: {data}")
    except Exception as e:
        print(f"  Get failed: {e}")

for rep in dev.find_feature_reports():
    print(f"Trying to send feature report: report_id={rep.report_id}")
    try:
        rep.set_raw_data([0x00] * 16)
        res = rep.send()
        print(f"  Send result: {res}")
    except Exception as e:
        print(f"  Send failed: {e}")

dev.close()
