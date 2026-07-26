"""
ups_module/linux_setup.py
~~~~~~~~~~~~~~~~~~~~~~~~~
ตัวช่วยตั้งค่าระบบ Linux สำหรับใช้งาน ups_module

ฟังก์ชันหลัก:
  - check_system_deps()        ตรวจสอบว่า library ที่จำเป็นติดตั้งแล้วหรือยัง
  - install_udev_rule()        สร้าง udev rule เพื่อให้ user ทั่วไปเข้าถึง HID device ได้
  - check_device_permission()  ทดสอบว่าเข้าถึง device ได้จริงหรือไม่

CLI::

    sudo python -m ups_module.linux_setup          # ตั้งค่าทั้งหมด
    python -m ups_module.linux_setup --check        # เช็คสถานะเท่านั้น (ไม่ต้อง sudo)
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ค่าคงที่
# ---------------------------------------------------------------------------

DEFAULT_VID = 0x06DA
DEFAULT_PID = 0xFFFF

UDEV_RULE_PATH = Path("/etc/udev/rules.d/99-ups-hid.rules")

# Library ที่จำเป็นบน Linux
REQUIRED_SYSTEM_LIBS = [
    ("libhidapi-hidraw0", "libhidapi-hidraw.so"),
    ("libusb-1.0-0", "libusb-1.0.so"),
]

REQUIRED_PYTHON_PACKAGES = [
    ("hid", "hidapi"),
    ("usb.core", "pyusb"),
]


# ---------------------------------------------------------------------------
# ตรวจสอบ system dependencies
# ---------------------------------------------------------------------------

def check_system_deps() -> List[dict]:
    """
    ตรวจสอบว่า system library และ Python package ที่จำเป็นติดตั้งครบหรือยัง

    Returns
    -------
    list[dict]
        รายการผลตรวจ แต่ละรายการมี key: name, type, installed, detail
    """
    results: List[dict] = []

    # ตรวจ system shared libraries
    for pkg_name, lib_name in REQUIRED_SYSTEM_LIBS:
        found = _find_shared_lib(lib_name)
        results.append({
            "name": pkg_name,
            "type": "system_lib",
            "installed": found is not None,
            "detail": found or f"ไม่พบ {lib_name} ในระบบ",
        })

    # ดึง user site-packages เผื่อติดตั้งผ่าน pip install --user (รวมกรณีรันด้วย sudo)
    import site
    try:
        user_site = site.getusersitepackages()
        if user_site and user_site not in sys.path:
            sys.path.append(user_site)
    except Exception:
        pass

    if os.name == "posix":
        for p in Path("/home").glob("*/.local/lib/python*/site-packages"):
            p_str = str(p)
            if p_str not in sys.path:
                sys.path.append(p_str)

    # ตรวจ Python packages
    for module_name, pip_name in REQUIRED_PYTHON_PACKAGES:
        try:
            __import__(module_name)
            results.append({
                "name": pip_name,
                "type": "python_package",
                "installed": True,
                "detail": "import สำเร็จ",
            })
        except ImportError as e:
            results.append({
                "name": pip_name,
                "type": "python_package",
                "installed": False,
                "detail": str(e),
            })

    return results


def _find_shared_lib(lib_name: str) -> Optional[str]:
    """ค้นหา shared library ด้วย ldconfig หรือ find"""
    # ลองใช้ ldconfig
    try:
        result = subprocess.run(
            ["ldconfig", "-p"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if lib_name in line:
                # ดึง path จาก output เช่น "libhidapi-hidraw.so.0 (libc6,...) => /usr/lib/..."
                parts = line.split("=>")
                if len(parts) == 2:
                    return parts[1].strip()
                return line.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # fallback: ค้นหาใน path มาตรฐาน
    for search_dir in ["/usr/lib", "/usr/local/lib", "/usr/lib/aarch64-linux-gnu",
                       "/usr/lib/arm-linux-gnueabihf", "/usr/lib/x86_64-linux-gnu"]:
        search_path = Path(search_dir)
        if search_path.exists():
            matches = list(search_path.glob(f"{lib_name}*"))
            if matches:
                return str(matches[0])

    return None


# ---------------------------------------------------------------------------
# udev rule
# ---------------------------------------------------------------------------

def generate_udev_rule(vid: int = DEFAULT_VID, pid: int = DEFAULT_PID) -> str:
    """สร้างเนื้อหา udev rule สำหรับ VID/PID ที่กำหนด"""
    vid_hex = f"{vid:04x}"
    pid_hex = f"{pid:04x}"
    return (
        f"# UPS HID device — VID={vid_hex} PID={pid_hex}\n"
        f"# สร้างโดย: python -m ups_module.linux_setup\n"
        f"#\n"
        f"# อนุญาตให้ user ทั่วไปเข้าถึง HID device ได้โดยไม่ต้องใช้ sudo\n"
        f"# hidraw: สำหรับ hidapi (อ่าน Feature Report)\n"
        f"# usb:    สำหรับ pyusb fallback (อ่าน Input Voltage ผ่าน control transfer)\n"
        f"\n"
        f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{vid_hex}", '
        f'ATTRS{{idProduct}}=="{pid_hex}", MODE="0666"\n'
        f'SUBSYSTEM=="usb", ATTRS{{idVendor}}=="{vid_hex}", '
        f'ATTRS{{idProduct}}=="{pid_hex}", MODE="0666"\n'
    )


def install_udev_rule(
    vid: int = DEFAULT_VID,
    pid: int = DEFAULT_PID,
    rule_path: Path = UDEV_RULE_PATH,
) -> Tuple[bool, str]:
    """
    สร้างไฟล์ udev rule และ reload udevadm

    ต้องรันด้วย root (sudo)

    Returns
    -------
    tuple[bool, str]
        (success, message)
    """
    if os.geteuid() != 0:
        return False, "ต้องรันด้วย sudo เพื่อสร้าง udev rule"

    content = generate_udev_rule(vid, pid)

    try:
        rule_path.write_text(content, encoding="utf-8")
    except OSError as e:
        return False, f"เขียนไฟล์ {rule_path} ไม่สำเร็จ: {e}"

    # reload udev rules
    try:
        subprocess.run(
            ["udevadm", "control", "--reload-rules"],
            check=True, capture_output=True, timeout=10,
        )
        subprocess.run(
            ["udevadm", "trigger"],
            check=True, capture_output=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        return True, f"สร้าง udev rule สำเร็จ แต่ reload ไม่สำเร็จ: {e}\nลองถอดปลั๊ก USB แล้วเสียบใหม่"

    return True, f"สร้าง udev rule สำเร็จ: {rule_path}"


def check_udev_rule(rule_path: Path = UDEV_RULE_PATH) -> bool:
    """ตรวจสอบว่ามี udev rule อยู่แล้วหรือไม่"""
    return rule_path.exists()


# ---------------------------------------------------------------------------
# ตรวจสอบสิทธิ์การเข้าถึง device
# ---------------------------------------------------------------------------

def check_device_permission(
    vid: int = DEFAULT_VID,
    pid: int = DEFAULT_PID,
) -> Tuple[bool, str]:
    """
    ทดสอบว่าเข้าถึง UPS HID device ได้หรือไม่

    Returns
    -------
    tuple[bool, str]
        (accessible, message)
    """
    try:
        import hid
    except ImportError:
        return False, "ไม่สามารถ import hid ได้ — ลอง: pip install hidapi"

    devices = hid.enumerate(vid, pid)
    if not devices:
        return False, (
            f"ไม่พบ UPS device (VID=0x{vid:04X} PID=0x{pid:04X})\n"
            f"  - ตรวจสอบว่าต่อสาย USB แล้ว\n"
            f"  - ลอง: lsusb | grep {vid:04x}"
        )

    # ลองเปิด device
    target = next(
        (d for d in devices if d.get("usage_page") == 0x84 and d.get("usage") == 0x04),
        next((d for d in devices if d.get("usage_page") == 0x84), devices[0]),
    )

    try:
        h = hid.device()
        h.open_path(target["path"])
        h.close()
        mfr = target.get("manufacturer_string", "?")
        prod = target.get("product_string", "?")
        return True, f"เข้าถึงได้: {mfr} {prod}"
    except OSError as e:
        return False, (
            f"พบ device แต่เข้าถึงไม่ได้ (Permission denied)\n"
            f"  - ลอง: sudo python -m ups_module.linux_setup\n"
            f"  - หรือรันด้วย sudo ชั่วคราว\n"
            f"  - Error: {e}"
        )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def _print_header(text: str) -> None:
    print(f"\n--- {text} ---")


def _print_result(label: str, ok: bool, detail: str = "") -> None:
    mark = "[OK]" if ok else "[NG]"
    print(f"  {mark} {label}")
    if detail and not ok:
        for line in detail.splitlines():
            print(f"       {line}")


def main() -> int:
    """CLI entrypoint สำหรับตั้งค่า Linux"""
    import argparse

    parser = argparse.ArgumentParser(
        description="ตั้งค่าระบบ Linux สำหรับ ups_module",
        prog="python -m ups_module.linux_setup",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="เช็คสถานะเท่านั้น ไม่ติดตั้งอะไร (ไม่ต้อง sudo)",
    )
    parser.add_argument(
        "--vid", type=lambda x: int(x, 0), default=DEFAULT_VID,
        help=f"USB Vendor ID (default: 0x{DEFAULT_VID:04X})",
    )
    parser.add_argument(
        "--pid", type=lambda x: int(x, 0), default=DEFAULT_PID,
        help=f"USB Product ID (default: 0x{DEFAULT_PID:04X})",
    )
    args = parser.parse_args()

    if platform.system().lower() != "linux":
        print(f"[!] สคริปต์นี้สำหรับ Linux เท่านั้น (ตรวจพบ: {platform.system()})")
        return 1

    check_only = args.check

    # --- ตรวจสอบ system dependencies ---
    _print_header("ตรวจสอบ System Dependencies")
    deps = check_system_deps()
    all_deps_ok = True
    for dep in deps:
        _print_result(
            f"{dep['name']} ({dep['type']})",
            dep["installed"],
            dep["detail"],
        )
        if not dep["installed"]:
            all_deps_ok = False

    if not all_deps_ok:
        print("\n  วิธีติดตั้ง system dependencies:")
        print("    sudo apt update")
        print("    sudo apt install -y libhidapi-hidraw0 libhidapi-dev libusb-1.0-0")
        print("    pip install hidapi pyusb")

    # --- ตรวจสอบ udev rule ---
    _print_header("ตรวจสอบ udev Rule")
    has_rule = check_udev_rule()
    _print_result(
        f"udev rule ({UDEV_RULE_PATH})",
        has_rule,
        "ไม่พบ udev rule — ต้องสร้างก่อนจึงจะเข้าถึง device ได้โดยไม่ต้อง sudo",
    )

    if not has_rule and not check_only:
        print("\n  กำลังสร้าง udev rule...")
        ok, msg = install_udev_rule(args.vid, args.pid)
        _print_result("สร้าง udev rule", ok, msg)
        print(f"  {msg}")
    elif not has_rule and check_only:
        print("\n  สร้าง udev rule ด้วยคำสั่ง:")
        print(f"    sudo python -m ups_module.linux_setup --vid 0x{args.vid:04X} --pid 0x{args.pid:04X}")

    # --- ตรวจสอบสิทธิ์ device ---
    _print_header("ตรวจสอบการเข้าถึง UPS Device")
    accessible, msg = check_device_permission(args.vid, args.pid)
    _print_result(f"UPS (VID=0x{args.vid:04X} PID=0x{args.pid:04X})", accessible, msg)
    print(f"  {msg}")

    # --- สรุป ---
    _print_header("สรุป")
    if all_deps_ok and has_rule and accessible:
        print("  ระบบพร้อมใช้งาน ups_module แล้ว")
        return 0
    else:
        print("  ยังมีรายการที่ต้องแก้ไข ดูรายละเอียดด้านบน")
        if not check_only and os.geteuid() != 0:
            print("\n  TIP: ลองรันด้วย sudo:")
            print("    sudo python -m ups_module.linux_setup")
        return 1


if __name__ == "__main__":
    sys.exit(main())
