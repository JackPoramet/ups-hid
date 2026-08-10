import sys
import time
import hid
import pywinusb.hid as pyhid

print("=== HIDAPI ENUMERATION ===")
all_devs = hid.enumerate()
print(f"Total HIDAPI devices: {len(all_devs)}")
mec_devs = []
for d in all_devs:
    vid = d.get('vendor_id', 0)
    pid = d.get('product_id', 0)
    if vid == 0x0001 or pid == 0x0000 or "mec" in (d.get('product_string') or "").lower():
        print(f"Match in hidapi: VID={hex(vid)} PID={hex(pid)} Path={d.get('path')} Product={d.get('product_string')}")
        mec_devs.append(d)

print("\n=== PYWINUSB ENUMERATION ===")
all_pyhid = pyhid.HidDeviceFilter().get_devices()
print(f"Total PyWinUSB devices: {len(all_pyhid)}")
for d in all_pyhid:
    vid = d.vendor_id
    pid = d.product_id
    print(f"PyWinUSB device: VID=0x{vid:04x} PID=0x{pid:04x} Vendor={d.vendor_name} Product={d.product_name} Path={d.device_path}")

