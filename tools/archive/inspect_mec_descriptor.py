import sys
import pywinusb.hid as pyhid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
dev = devices[0]
dev.open()

caps = dev.hid_caps
for f_name, _ in caps._fields_:
    print(f"{f_name}: {getattr(caps, f_name)}")

dev.close()

