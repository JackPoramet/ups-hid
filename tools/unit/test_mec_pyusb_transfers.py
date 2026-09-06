import sys
import usb.core
import usb.util
import libusb_package

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backend = libusb_package.get_libusb1_backend()
dev = usb.core.find(idVendor=0x0001, idProduct=0x0000, backend=backend)

if not dev:
    print("Device not found!")
    sys.exit(1)

print("Device opened.")

# 1. Test reading from Bulk IN Endpoint 0x82
print("\n--- 1. Testing Bulk IN Endpoint 0x82 read ---")
try:
    data = dev.read(0x82, 64, timeout=1000)
    print(f"  Bulk read 0x82 SUCCESS! len={len(data)}, hex={bytes(data).hex()} data={bytes(data)}")
except Exception as e:
    print(f"  Bulk read 0x82 failed: {e}")

# 2. Test HID SET_REPORT via Control Transfer
print("\n--- 2. Testing HID SET_REPORT (0x21, 0x09) ---")
# bmRequestType: 0x21 (Host to Device, Class, Interface)
# bRequest: 0x09 (SET_REPORT)
# wValue: (ReportType << 8) | ReportID
# ReportType: 1=Input, 2=Output, 3=Feature
for rep_type, type_name in [(2, "Output"), (3, "Feature")]:
    for rid in [0, 1]:
        wval = (rep_type << 8) | rid
        for payload in [b"T\r", b"T", bytes([0x00, ord('T'), 0x0D])]:
            try:
                ret = dev.ctrl_transfer(
                    bmRequestType=0x21,
                    bRequest=0x09,
                    wValue=wval,
                    wIndex=0,
                    data_or_wLength=payload,
                    timeout=1000
                )
                print(f"  SET_REPORT {type_name} RID={rid} payload={payload} -> SUCCESS! ret={ret}")
            except Exception as e:
                # STALL or Error
                pass

# 3. Test Vendor Requests (0x40, 0x41)
print("\n--- 3. Testing Vendor Requests (0x40, 0x41) ---")
for bm in [0x40, 0x41]:
    for req in range(0, 16):
        try:
            ret = dev.ctrl_transfer(
                bmRequestType=bm,
                bRequest=req,
                wValue=0,
                wIndex=0,
                data_or_wLength=b"T\r",
                timeout=500
            )
            print(f"  Vendor Request bm=0x{bm:02x} req=0x{req:02x} -> SUCCESS! ret={ret}")
        except Exception:
            pass

print("\nFinished Control Transfer and Endpoint checks.")
