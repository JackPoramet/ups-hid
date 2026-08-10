import sys
import pywinusb.hid as pyhid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
dev = devices[0]
dev.open()

for r in dev.find_feature_reports():
    print(f"\nFeature Report ID={r.report_id}:")
    for key, item in r.items():
        print(f"  Item key={key}: {item}")
        for attr in dir(item):
            if not attr.startswith("_"):
                print(f"    {attr}: {getattr(item, attr)}")

dev.close()

