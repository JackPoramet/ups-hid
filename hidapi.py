"""
Read HID report descriptor from USB UPS on Windows.

Scope for this script:
- Discover target HID interface by VID/PID (+ optional usage_page/usage filter)
- Read raw HID report descriptor bytes via DeviceIoControl
- Fallback to HID caps dump via HidD/HidP APIs if raw descriptor read fails
- Export results to txt/bin/meta files
"""

import argparse
import ctypes
import json
import platform
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import hid


# -----------------------------
# Defaults
# -----------------------------
DEFAULT_VID = 0x06DA
DEFAULT_PID = 0xFFFF
DEFAULT_USAGE_PAGE = 0x0084
DEFAULT_USAGE = 0x0004

DEFAULT_TXT = "report_descriptor_live.txt"
DEFAULT_BIN = "report_descriptor_live.bin"
DEFAULT_META = "report_descriptor_meta.json"


# -----------------------------
# Windows constants
# -----------------------------
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

FILE_DEVICE_KEYBOARD = 0x0000000B
METHOD_BUFFERED = 0
METHOD_NEITHER = 3
FILE_ANY_ACCESS = 0


def ctl_code(device_type: int, function: int, method: int, access: int) -> int:
    return (device_type << 16) | (access << 14) | (function << 2) | method


# From HID headers: IOCTL_HID_GET_REPORT_DESCRIPTOR = HID_CTL_CODE(1)
IOCTL_HID_GET_REPORT_DESCRIPTOR = ctl_code(
    FILE_DEVICE_KEYBOARD,
    1,
    METHOD_NEITHER,
    FILE_ANY_ACCESS,
)

# HID class IOCTLs used for fallback (preparsed / collection info)
IOCTL_HID_GET_COLLECTION_DESCRIPTOR = ctl_code(
    FILE_DEVICE_KEYBOARD,
    100,
    METHOD_NEITHER,
    FILE_ANY_ACCESS,
)
IOCTL_HID_GET_COLLECTION_INFORMATION = ctl_code(
    FILE_DEVICE_KEYBOARD,
    106,
    METHOD_BUFFERED,
    FILE_ANY_ACCESS,
)

# HidP_GetCaps returns this code on success
HIDP_STATUS_SUCCESS = 0x00110000


# -----------------------------
# ctypes structures
# -----------------------------
class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
    ]


class HIDP_CAPS(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


class HID_COLLECTION_INFORMATION(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("DescriptorSize", wintypes.ULONG),
        ("Polled", wintypes.BOOLEAN),
        ("Reserved1", wintypes.BYTE),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
        ("Reserved", wintypes.BYTE * 4),
    ]


# -----------------------------
# WinAPI binding
# -----------------------------
class WinHidApi:
    def __init__(self):
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.hid_dll = ctypes.WinDLL("hid", use_last_error=True)

        self.kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        self.kernel32.CreateFileW.restype = wintypes.HANDLE

        self.kernel32.DeviceIoControl.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        self.kernel32.DeviceIoControl.restype = wintypes.BOOL

        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

        self.hid_dll.HidD_GetAttributes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(HIDD_ATTRIBUTES),
        ]
        self.hid_dll.HidD_GetAttributes.restype = wintypes.BOOLEAN

        self.hid_dll.HidD_GetPreparsedData.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.hid_dll.HidD_GetPreparsedData.restype = wintypes.BOOLEAN

        self.hid_dll.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
        self.hid_dll.HidD_FreePreparsedData.restype = wintypes.BOOLEAN

        self.hid_dll.HidP_GetCaps.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(HIDP_CAPS),
        ]
        self.hid_dll.HidP_GetCaps.restype = wintypes.ULONG

    def create_file(self, path: str) -> wintypes.HANDLE:
        handle = self.kernel32.CreateFileW(
            path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def close_handle(self, handle: wintypes.HANDLE) -> None:
        if handle and handle != INVALID_HANDLE_VALUE:
            self.kernel32.CloseHandle(handle)

    def get_attributes(self, handle: wintypes.HANDLE) -> Optional[Dict[str, int]]:
        attrs = HIDD_ATTRIBUTES()
        attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)

        ok = self.hid_dll.HidD_GetAttributes(handle, ctypes.byref(attrs))
        if not ok:
            return None

        return {
            "VendorID": int(attrs.VendorID),
            "ProductID": int(attrs.ProductID),
            "VersionNumber": int(attrs.VersionNumber),
        }

    def get_report_descriptor(self, handle: wintypes.HANDLE, sizes: Sequence[int]) -> Tuple[Optional[bytes], Optional[str]]:
        last_err = None
        for size in sizes:
            out_buf = ctypes.create_string_buffer(size)
            returned = wintypes.DWORD(0)

            ok = self.kernel32.DeviceIoControl(
                handle,
                IOCTL_HID_GET_REPORT_DESCRIPTOR,
                None,
                0,
                out_buf,
                size,
                ctypes.byref(returned),
                None,
            )

            if ok and returned.value > 0:
                return out_buf.raw[: returned.value], None

            err_code = ctypes.get_last_error()
            last_err = f"DeviceIoControl failed (size={size}, winerr={err_code})"

        return None, last_err

    def get_collection_information(self, handle: wintypes.HANDLE) -> Tuple[Optional[Dict[str, int]], Optional[str]]:
        info = HID_COLLECTION_INFORMATION()
        returned = wintypes.DWORD(0)

        ok = self.kernel32.DeviceIoControl(
            handle,
            IOCTL_HID_GET_COLLECTION_INFORMATION,
            None,
            0,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(returned),
            None,
        )

        if not ok:
            err_code = ctypes.get_last_error()
            return None, f"IOCTL_HID_GET_COLLECTION_INFORMATION failed (winerr={err_code})"

        return {
            "DescriptorSize": int(info.DescriptorSize),
            "Polled": bool(info.Polled),
            "VendorID": int(info.VendorID),
            "ProductID": int(info.ProductID),
            "VersionNumber": int(info.VersionNumber),
        }, None

    def get_collection_descriptor(self, handle: wintypes.HANDLE, size: int) -> Tuple[Optional[bytes], Optional[str]]:
        if size <= 0:
            return None, "Invalid descriptor size from collection info"

        out_buf = ctypes.create_string_buffer(size)
        returned = wintypes.DWORD(0)

        ok = self.kernel32.DeviceIoControl(
            handle,
            IOCTL_HID_GET_COLLECTION_DESCRIPTOR,
            None,
            0,
            out_buf,
            size,
            ctypes.byref(returned),
            None,
        )

        if not ok:
            err_code = ctypes.get_last_error()
            return None, f"IOCTL_HID_GET_COLLECTION_DESCRIPTOR failed (winerr={err_code})"

        if returned.value <= 0:
            return None, "IOCTL_HID_GET_COLLECTION_DESCRIPTOR returned 0 bytes"

        return out_buf.raw[: returned.value], None

    def get_caps(self, handle: wintypes.HANDLE) -> Tuple[Optional[Dict[str, int]], Optional[str]]:
        preparsed = ctypes.c_void_p()
        ok = self.hid_dll.HidD_GetPreparsedData(handle, ctypes.byref(preparsed))
        if not ok:
            err_code = ctypes.get_last_error()
            return None, f"HidD_GetPreparsedData failed (winerr={err_code})"

        try:
            caps = HIDP_CAPS()
            status = self.hid_dll.HidP_GetCaps(preparsed, ctypes.byref(caps))
            if status != HIDP_STATUS_SUCCESS:
                return None, f"HidP_GetCaps failed (status=0x{status:08X})"

            info = {
                "UsagePage": int(caps.UsagePage),
                "Usage": int(caps.Usage),
                "InputReportByteLength": int(caps.InputReportByteLength),
                "OutputReportByteLength": int(caps.OutputReportByteLength),
                "FeatureReportByteLength": int(caps.FeatureReportByteLength),
                "NumberLinkCollectionNodes": int(caps.NumberLinkCollectionNodes),
                "NumberInputValueCaps": int(caps.NumberInputValueCaps),
                "NumberFeatureValueCaps": int(caps.NumberFeatureValueCaps),
            }
            return info, None
        finally:
            self.hid_dll.HidD_FreePreparsedData(preparsed)


# -----------------------------
# Helpers
# -----------------------------
def auto_int(s: str) -> int:
    return int(s, 0)


def normalize_path(raw_path) -> str:
    if isinstance(raw_path, bytes):
        try:
            return raw_path.decode("utf-8")
        except Exception:
            return raw_path.decode("latin-1", errors="ignore")
    return str(raw_path)


def select_hid_device(
    vid: int,
    pid: int,
    usage_page: Optional[int],
    usage: Optional[int],
    verbose: bool = False,
) -> dict:
    devices = hid.enumerate(vid, pid)
    if not devices:
        raise RuntimeError(f"No HID device found for VID=0x{vid:04X} PID=0x{pid:04X}")

    if verbose:
        print("Matched HID devices:")
        for i, d in enumerate(devices, start=1):
            print(
                f"  [{i}] usage_page=0x{(d.get('usage_page') or 0):04X} "
                f"usage=0x{(d.get('usage') or 0):04X} "
                f"interface={d.get('interface_number')} "
                f"path={normalize_path(d.get('path'))}"
            )

    target = None
    if usage_page is not None and usage is not None:
        target = next(
            (
                d
                for d in devices
                if d.get("usage_page") == usage_page and d.get("usage") == usage
            ),
            None,
        )

    if target is None and usage_page is not None:
        target = next((d for d in devices if d.get("usage_page") == usage_page), None)

    if target is None:
        target = devices[0]

    return target


def hex_dump(data: bytes, width: int = 16) -> str:
    lines = []
    for off in range(0, len(data), width):
        chunk = data[off : off + width]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"{off:04X}  {hex_part:<{width * 3}}  {ascii_part}")
    return "\n".join(lines)


def write_outputs(
    txt_path: Path,
    bin_path: Path,
    meta_path: Path,
    descriptor_bytes: Optional[bytes],
    descriptor_source: str,
    meta: dict,
) -> None:
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    if descriptor_bytes:
        txt_content = []
        txt_content.append("HID Descriptor Bytes")
        txt_content.append(f"Source: {descriptor_source}")
        txt_content.append(f"Length: {len(descriptor_bytes)} bytes")
        txt_content.append("")
        txt_content.append(hex_dump(descriptor_bytes))
        txt_path.write_text("\n".join(txt_content) + "\n", encoding="utf-8")
        bin_path.write_bytes(descriptor_bytes)
    else:
        txt_path.write_text(
            "No raw descriptor bytes captured. Check meta file for fallback details.\n",
            encoding="utf-8",
        )
        bin_path.write_bytes(b"")

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# -----------------------------
# Main
# -----------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read HID report descriptor from USB HID device (Windows)")
    p.add_argument("--vid", type=auto_int, default=DEFAULT_VID, help="USB Vendor ID (e.g. 0x06DA)")
    p.add_argument("--pid", type=auto_int, default=DEFAULT_PID, help="USB Product ID (e.g. 0xFFFF)")
    p.add_argument("--usage-page", type=auto_int, default=DEFAULT_USAGE_PAGE, help="Preferred HID usage page")
    p.add_argument("--usage", type=auto_int, default=DEFAULT_USAGE, help="Preferred HID usage")

    p.add_argument("--out-txt", default=DEFAULT_TXT, help="Output text file for descriptor dump")
    p.add_argument("--out-bin", default=DEFAULT_BIN, help="Output binary file for descriptor bytes")
    p.add_argument("--out-meta", default=DEFAULT_META, help="Output metadata JSON file")

    p.add_argument(
        "--max-sizes",
        default="256,512,1024,2048,4096",
        help="Comma-separated output buffer sizes for descriptor IOCTL",
    )
    p.add_argument("--verbose", action="store_true", help="Show more device selection details")
    return p


def parse_sizes(csv_text: str) -> Tuple[int, ...]:
    vals = []
    for token in csv_text.split(","):
        token = token.strip()
        if not token:
            continue
        vals.append(int(token, 0))
    if not vals:
        vals = [256, 512, 1024, 2048, 4096]
    return tuple(vals)


def main() -> int:
    if platform.system().lower() != "windows":
        print("This script currently supports Windows only.")
        return 2

    args = build_parser().parse_args()
    sizes = parse_sizes(args.max_sizes)

    txt_path = Path(args.out_txt)
    bin_path = Path(args.out_bin)
    meta_path = Path(args.out_meta)

    api = WinHidApi()

    descriptor_bytes: Optional[bytes] = None
    descriptor_source = "none"
    descriptor_error: Optional[str] = None
    collection_info: Optional[dict] = None
    collection_info_error: Optional[str] = None
    collection_desc_error: Optional[str] = None
    caps_info: Optional[dict] = None
    caps_error: Optional[str] = None
    attrs: Optional[dict] = None

    target = select_hid_device(
        vid=args.vid,
        pid=args.pid,
        usage_page=args.usage_page,
        usage=args.usage,
        verbose=args.verbose,
    )

    dev_path = normalize_path(target.get("path"))
    print(f"Selected HID path: {dev_path}")

    handle = None
    try:
        handle = api.create_file(dev_path)

        attrs = api.get_attributes(handle)
        if attrs:
            print(
                "Device attributes: "
                f"VID=0x{attrs['VendorID']:04X} PID=0x{attrs['ProductID']:04X} "
                f"REV=0x{attrs['VersionNumber']:04X}"
            )

        descriptor_bytes, descriptor_error = api.get_report_descriptor(handle, sizes=sizes)

        if descriptor_bytes:
            descriptor_source = "report_descriptor"
            print(f"Read HID report descriptor: {len(descriptor_bytes)} bytes")
        else:
            print("Raw report descriptor read failed, trying collection descriptor fallback...")
            if descriptor_error:
                print(f"  Detail: {descriptor_error}")

            collection_info, collection_info_error = api.get_collection_information(handle)
            if collection_info:
                print(
                    "Collection info: "
                    f"DescriptorSize={collection_info['DescriptorSize']} "
                    f"VID=0x{collection_info['VendorID']:04X} "
                    f"PID=0x{collection_info['ProductID']:04X}"
                )
                descriptor_bytes, collection_desc_error = api.get_collection_descriptor(
                    handle,
                    size=collection_info["DescriptorSize"],
                )
                if descriptor_bytes:
                    descriptor_source = "collection_descriptor_preparsed"
                    print(f"Read collection descriptor bytes: {len(descriptor_bytes)} bytes")
                elif collection_desc_error:
                    print(f"Collection descriptor fallback failed: {collection_desc_error}")
            elif collection_info_error:
                print(f"Collection info fallback failed: {collection_info_error}")

        if not descriptor_bytes:
            print("Trying caps fallback...")

        caps_info, caps_error = api.get_caps(handle)
        if caps_info:
            print(
                "HID caps: "
                f"UsagePage=0x{caps_info['UsagePage']:04X} "
                f"Usage=0x{caps_info['Usage']:04X} "
                f"InputLen={caps_info['InputReportByteLength']} "
                f"FeatureLen={caps_info['FeatureReportByteLength']}"
            )
        elif caps_error:
            print(f"Caps fallback failed: {caps_error}")

    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    finally:
        api.close_handle(handle)

    meta = {
        "platform": platform.platform(),
        "target": {
            "vid": args.vid,
            "pid": args.pid,
            "usage_page": args.usage_page,
            "usage": args.usage,
            "device_path": dev_path,
            "manufacturer": target.get("manufacturer_string"),
            "product": target.get("product_string"),
            "serial": target.get("serial_number"),
            "release_number": target.get("release_number"),
            "interface_number": target.get("interface_number"),
        },
        "winapi": {
            "ioctl_hid_get_report_descriptor": f"0x{IOCTL_HID_GET_REPORT_DESCRIPTOR:08X}",
            "ioctl_hid_get_collection_descriptor": f"0x{IOCTL_HID_GET_COLLECTION_DESCRIPTOR:08X}",
            "ioctl_hid_get_collection_information": f"0x{IOCTL_HID_GET_COLLECTION_INFORMATION:08X}",
            "descriptor_sizes_tried": list(sizes),
        },
        "result": {
            "descriptor_read_ok": descriptor_bytes is not None,
            "descriptor_length": len(descriptor_bytes) if descriptor_bytes else 0,
            "descriptor_source": descriptor_source,
            "descriptor_error": descriptor_error,
            "collection_info": collection_info,
            "collection_info_error": collection_info_error,
            "collection_descriptor_error": collection_desc_error,
            "caps_ok": caps_info is not None,
            "caps_error": caps_error,
            "attributes": attrs,
            "caps": caps_info,
        },
    }

    write_outputs(
        txt_path=txt_path,
        bin_path=bin_path,
        meta_path=meta_path,
        descriptor_bytes=descriptor_bytes,
        descriptor_source=descriptor_source,
        meta=meta,
    )

    print(f"Exported txt : {txt_path}")
    print(f"Exported bin : {bin_path}")
    print(f"Exported meta: {meta_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
