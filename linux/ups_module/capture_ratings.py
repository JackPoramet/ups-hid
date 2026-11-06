"""Maintenance-only Phoenixtec rating evidence; no control/output writes.

Run through update.sh --capture-ratings OUTPUT while it owns service shutdown.
Raw descriptor/response bytes are evidence, never inferred power ratings.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import struct
from pathlib import Path


def _advertised_report_length(extra):
    offset = 0
    extra = bytes(extra)
    while offset < len(extra):
        length = extra[offset]
        if length < 2 or offset + length > len(extra):
            raise ValueError("Malformed extra USB descriptor")
        item = extra[offset:offset+length]
        if item[1] == 0x21:
            if len(item) < 6 or 6 + item[5] * 3 > len(item):
                raise ValueError("Malformed HID class descriptor")
            for index in range(item[5]):
                start = 6 + index * 3
                if item[start] == 0x22:
                    size = item[start+1] | item[start+2] << 8
                    if not 0 < size <= 4096:
                        raise ValueError("Advertised HID report descriptor length is unsafe")
                    return size
        offset += length
    return None


def _find_hidraw_node(device, interface, sys_class=Path("/sys/class/hidraw"), dev_root=Path("/dev")):
    matches = []
    for entry in sys_class.glob("hidraw*"):
        physical = (entry / "device").resolve()
        for parent in (physical, *physical.parents):
            try:
                if int((parent / "bInterfaceNumber").read_text().strip(), 16) != interface:
                    continue
                usb = parent.parent
                if (int((usb / "busnum").read_text()), int((usb / "devnum").read_text())) == (device.bus, device.address):
                    matches.append(dev_root / entry.name)
                break
            except (OSError, ValueError):
                continue
    if len(matches) != 1:
        raise RuntimeError("Expected one kernel hidraw node for this USB interface; no detach attempted")
    return matches[0]


def _read_kernel_hidraw(device, interface):
    node = _find_hidraw_node(device, interface)
    import fcntl
    import usb.util
    # Close the unclaimed metadata handle before opening the kernel endpoint.
    usb.util.dispose_resources(device)
    result = {"transport": "hidraw", "hidraw_node": str(node),
              "report_descriptor_hex": None, "report_74_raw": [], "errors": {}}
    fd = os.open(node, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = bytearray(8)
        fcntl.ioctl(fd, 0x80084803, info, True)  # HIDIOCGRAWINFO
        bus, vid, pid = struct.unpack("IHH", info)
        if (bus, vid, pid) != (3, 0x06DA, 0xFFFF):
            raise RuntimeError("hidraw identity differs from the selected Phoenixtec USB device")
        try:
            size_buffer = bytearray(4)
            fcntl.ioctl(fd, 0x80044801, size_buffer, True)  # HIDIOCGRDESCSIZE
            size = struct.unpack("I", size_buffer)[0]
            if not 0 < size <= 4096:
                raise RuntimeError("Invalid kernel HID descriptor length")
            descriptor = bytearray(4100)
            struct.pack_into("I", descriptor, 0, size)
            fcntl.ioctl(fd, 0x90044802, descriptor, True)  # HIDIOCGRDESC
            actual_size = struct.unpack_from("I", descriptor)[0]
            if not 0 < actual_size <= size:
                raise RuntimeError("Invalid returned HID descriptor length")
            result["report_descriptor_hex"] = bytes(descriptor[4:4+actual_size]).hex()
        except Exception as exc:
            result["errors"]["report_descriptor"] = f"{type(exc).__name__}: {exc}"
        try:
            report = bytearray(64)
            report[0] = 0x74
            count = fcntl.ioctl(fd, 0xC0404807, report, True)  # HIDIOCGFEATURE(64), GET only
            if not 0 <= count <= len(report):
                raise RuntimeError("Invalid feature report transfer length")
            result["report_74_raw"] = list(report[:count])
        except Exception as exc:
            result["errors"]["report_74"] = f"{type(exc).__name__}: {exc}"
    finally:
        os.close(fd)
    return result


def capture_device(device):
    if (device.idVendor, device.idProduct) != (0x06DA, 0xFFFF):
        raise ValueError("Only Phoenixtec 06da:ffff is supported; MEC is excluded")
    interfaces = [i for i in device.get_active_configuration() if i.bInterfaceClass == 3]
    if len(interfaces) != 1:
        raise RuntimeError("Capture requires exactly one HID interface")
    interface = int(interfaces[0].bInterfaceNumber)
    advertised_length = _advertised_report_length(getattr(interfaces[0], "extra_descriptors", b""))
    result = {"schema_version": 1,
              "captured_at": datetime.datetime.now().astimezone().isoformat(),
              "device": {"vid": device.idVendor, "pid": device.idProduct,
                         "bus": device.bus, "address": device.address,
                         "interface": interface},
              "advertised_report_descriptor_bytes": advertised_length,
              "report_descriptor_hex": None, "report_74_raw": [], "errors": {}}
    for field in ("manufacturer", "product", "serial_number"):
        try:
            result["device"][field] = getattr(device, field)
        except Exception as exc:
            result["errors"][field] = f"{type(exc).__name__}: {exc}"
    if device.is_kernel_driver_active(interface):
        kernel_result = _read_kernel_hidraw(device, interface)
        result["errors"].update(kernel_result.pop("errors"))
        result.update(kernel_result)
        requests = ()
    else:
        result["transport"] = "pyusb"
        requests = (
        # Get the rating first so a descriptor timeout cannot hide obtainable data.
        ("report_74", dict(bmRequestType=0xA1, bRequest=0x01,
                          wValue=0x0374, wIndex=interface,
                          data_or_wLength=64, timeout=5000)),
        ("report_descriptor", dict(bmRequestType=0x81, bRequest=0x06,
                                  wValue=0x2200, wIndex=interface,
                                  data_or_wLength=advertised_length or 4096, timeout=5000)),
        )
    for label, request in requests:
        try:
            raw = bytes(device.ctrl_transfer(**request))
            if label == "report_descriptor":
                result["report_descriptor_hex"] = raw.hex() if raw else None
            else:
                result["report_74_raw"] = list(raw)
        except Exception as exc:
            result["errors"][label] = f"{type(exc).__name__}: {exc}"
    raw_report = result["report_74_raw"]
    valid_report = len(raw_report) >= 2 and raw_report[0] == 0x74
    if raw_report and not valid_report:
        result["errors"]["report_74"] = "Expected report ID 0x74 and a payload; raw bytes preserved"
    descriptor = result["report_descriptor_hex"]
    valid_descriptor = bool(descriptor) and (advertised_length is None or len(descriptor) // 2 == advertised_length)
    if descriptor and not valid_descriptor:
        result["errors"]["report_descriptor"] = "Returned descriptor length differs from the device advertisement"
    result["complete"] = bool(valid_descriptor and valid_report)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        parser.error("Output must be a new file in an existing directory")
    import usb.core
    import usb.util
    devices = list(usb.core.find(find_all=True, idVendor=0x06DA, idProduct=0xFFFF))
    if len(devices) != 1:
        parser.error("Exactly one Phoenixtec UPS must be connected")
    device = devices[0]
    try:
        result = capture_device(device)
    finally:
        usb.util.dispose_resources(device)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"output": str(args.output), "complete": result["complete"],
                      "device": result["device"], "report_74_raw": result["report_74_raw"],
                      "descriptor_bytes": len(result["report_descriptor_hex"] or "") // 2,
                      "errors": result["errors"]}, ensure_ascii=False))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
