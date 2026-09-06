import sys
import usb.core
import usb.util

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import libusb_package
    backend = libusb_package.get_libusb1_backend()
    dev = usb.core.find(idVendor=0x0001, idProduct=0x0000, backend=backend)
except Exception as e:
    dev = usb.core.find(idVendor=0x0001, idProduct=0x0000)

if not dev:
    print("Device not found via pyusb!")
    sys.exit(1)

print("Found MEC0003 via PyUSB:")
print(f"  bDeviceClass: {dev.bDeviceClass}")
print(f"  bDeviceSubClass: {dev.bDeviceSubClass}")
print(f"  bDeviceProtocol: {dev.bDeviceProtocol}")
print(f"  bMaxPacketSize0: {dev.bMaxPacketSize0}")
print(f"  idVendor: 0x{dev.idVendor:04x}")
print(f"  idProduct: 0x{dev.idProduct:04x}")

for cfg in dev:
    print(f"  Configuration: {cfg.bConfigurationValue}")
    for intf in cfg:
        print(f"    Interface: {intf.bInterfaceNumber}, Alt: {intf.bAlternateSetting}, Class: {intf.bInterfaceClass}, SubClass: {intf.bInterfaceSubClass}")
        for ep in intf:
            print(f"      Endpoint: 0x{ep.bEndpointAddress:02x}, Attr: 0x{ep.bmAttributes:02x}, MaxPacket: {ep.wMaxPacketSize}")

