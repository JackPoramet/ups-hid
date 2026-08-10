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

try:
    from .device_registry import DeviceRegistry
except ImportError:
    from device_registry import DeviceRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ค่าคงที่
# ---------------------------------------------------------------------------

_registry = DeviceRegistry()
_default_profile = _registry.get_default()

DEFAULT_VID = _default_profile.vid
DEFAULT_PID = _default_profile.pid

UDEV_RULE_PATH = Path("/etc/udev/rules.d/99-ups-hid.rules")
UDEV_GROUP = "ups-hid"

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
    """Create a least-privilege hidraw rule for a registered UPS.

    The dedicated group works for headless/SSH services, unlike ``uaccess``
    alone which only grants an ACL to an active local console session. Raw USB
    is deliberately not exposed because it permits arbitrary control transfers.
    """
    vid_hex = f"{vid:04x}"
    pid_hex = f"{pid:04x}"
    return (
        f'KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{vid_hex}", '
        f'ATTRS{{idProduct}}=="{pid_hex}", GROUP="{UDEV_GROUP}", MODE="0660", TAG+="uaccess"\n'
    )


def generate_udev_rules_all() -> str:
    """สร้างเนื้อหา udev rule สำหรับทุก device ที่ลงทะเบียนใน meta.json"""
    lines = [
        "# UPS HID devices — auto-generated from meta.json",
        "# Generated by: python -m ups_module.linux_setup",
        "#",
        f"# Grant members of the {UDEV_GROUP} group access only to the HID interface",
        "# TAG+=\"uaccess\" additionally supports an active local console session.",
        "# hidraw: for hidapi (read Feature Reports)",
        "# Raw USB is intentionally not exposed: it permits control commands.",
        "",
    ]
    for profile in _registry.devices:
        lines.append(f"# {profile.manufacturer} {profile.model} (VID={profile.vid:04x} PID={profile.pid:04x})")
        lines.append(generate_udev_rule(profile.vid, profile.pid))
    return "\n".join(lines) + "\n"


def install_udev_rule(
    vid: int = DEFAULT_VID,
    pid: int = DEFAULT_PID,
    rule_path: Path = UDEV_RULE_PATH,
    all_devices: bool = False,
) -> Tuple[bool, str]:
    """
    สร้างไฟล์ udev rule และ reload udevadm

    ต้องรันด้วย root (sudo)

    Parameters
    ----------
    all_devices : bool
        If True, generate rules for all devices in the registry.
        If False, generate a rule for the specified VID/PID only.

    Returns
    -------
    tuple[bool, str]
        (success, message)
    """
    if os.geteuid() != 0:
        return False, "ต้องรันด้วย sudo เพื่อสร้าง udev rule"

    if all_devices:
        content = generate_udev_rules_all()
    else:
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
        subprocess.run(
            ["udevadm", "settle", "--timeout=10"],
            check=True, capture_output=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        return True, f"สร้าง udev rule สำเร็จ แต่ reload ไม่สำเร็จ: {e}\nลองถอดปลั๊ก USB แล้วเสียบใหม่"

    return True, f"สร้าง udev rule สำเร็จ: {rule_path}"


def check_udev_rule(rule_path: Path = UDEV_RULE_PATH) -> bool:
    """ตรวจสอบว่ามี udev rule อยู่แล้วหรือไม่"""
    if not rule_path.exists():
        return False
    try:
        content = rule_path.read_text(encoding="utf-8")
    except OSError:
        return False
    # A stale/empty rule should not be reported as usable.  The extra
    # markers identify the current rule format and make an existing rule from
    # an older installation get regenerated by install.sh.
    return (
        "KERNEL==\"hidraw*\"" in content
        and "SUBSYSTEM==\"hidraw\"" in content
        and "ATTRS{idVendor}" in content
        and f'GROUP="{UDEV_GROUP}"' in content
        and 'MODE="0660"' in content
        and "TAG+=\"uaccess\"" in content
    )


def ensure_udev_group(user: Optional[str] = None) -> Tuple[bool, str]:
    """Create the dedicated HID group and optionally add an application user.

    Group access is required for headless boards because ``uaccess`` does not
    grant ACLs to a user connected only through SSH. The caller must be root.
    """
    if os.geteuid() != 0:
        return False, "ต้องรันด้วย sudo เพื่อสร้าง group สำหรับ UPS HID"

    try:
        import grp
        grp.getgrnam(UDEV_GROUP)
    except KeyError:
        try:
            subprocess.run(["groupadd", "--system", UDEV_GROUP], check=True, timeout=10)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            return False, f"สร้าง group {UDEV_GROUP} ไม่สำเร็จ: {exc}"

    if not user or user == "root":
        return True, f"group {UDEV_GROUP} พร้อมใช้งาน"

    try:
        import pwd
        pwd.getpwnam(user)
    except KeyError:
        return False, f"ไม่พบ user: {user}"

    try:
        subprocess.run(["usermod", "-a", "-G", UDEV_GROUP, user], check=True, timeout=10)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        return False, f"เพิ่ม user {user} เข้า group {UDEV_GROUP} ไม่สำเร็จ: {exc}"
    return True, f"group {UDEV_GROUP} พร้อมใช้งาน; เพิ่ม user {user} แล้ว"


def check_udev_group_access(user: Optional[str] = None) -> Tuple[bool, str]:
    """Check whether the requested application account can use HID rules."""
    try:
        import grp
        group = grp.getgrnam(UDEV_GROUP)
    except KeyError:
        return False, f"ไม่พบ group {UDEV_GROUP}"

    if not user or user == "root":
        return True, f"พบ group {UDEV_GROUP} (gid={group.gr_gid})"

    try:
        import pwd
        account = pwd.getpwnam(user)
    except KeyError:
        return False, f"ไม่พบ user: {user}"

    groups = set()
    try:
        groups.update(os.getgrouplist(user, account.pw_gid))
    except AttributeError:
        if user in group.gr_mem or account.pw_gid == group.gr_gid:
            groups.add(group.gr_gid)
    if group.gr_gid not in groups:
        return False, f"user {user} ไม่ได้อยู่ใน group {UDEV_GROUP}"
    return True, f"user {user} อยู่ใน group {UDEV_GROUP}"


def _device_path_text(path: object) -> str:
    """Return a readable representation of a hidapi device path."""
    if isinstance(path, (bytes, bytearray)):
        return path.decode("utf-8", errors="replace")
    return str(path)


def _hid_path_arg(path: object) -> bytes:
    """Normalize hidapi paths for ARM/Linux bindings requiring bytes."""
    if isinstance(path, bytes):
        return path
    if isinstance(path, bytearray):
        return bytes(path)
    if path is None:
        raise TypeError("HID device path is missing")
    return os.fsencode(str(path))


def _ordered_device_candidates(devices: List[dict]) -> List[dict]:
    """Use the same interface preference as the core HID opener."""
    preferred = [
        d for d in devices
        if d.get("usage_page") == 0x84 and d.get("usage") == 0x04
    ]
    power_page = [
        d for d in devices
        if d.get("usage_page") == 0x84 and d not in preferred
    ]
    remaining = [d for d in devices if d not in preferred and d not in power_page]
    return preferred + power_page + remaining


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

    errors = []
    for target in _ordered_device_candidates(devices):
        path = target.get("path")
        path_text = _device_path_text(path)
        node_info = ""
        try:
            st = os.stat(path)
            node_info = f" mode={oct(st.st_mode & 0o777)} uid={st.st_uid} gid={st.st_gid}"
        except (OSError, TypeError):
            node_info = " node-stat=unavailable"

        try:
            h = hid.device()
            h.open_path(_hid_path_arg(path))
            h.close()
            mfr = target.get("manufacturer_string") or "PHOENIXTEC"
            prod = target.get("product_string") or "Innova Unity"
            return True, f"เข้าถึงได้: {mfr} {prod} ({path_text})"
        except Exception as exc:
            errors.append(f"{path_text}: {exc}{node_info}")
            try:
                h.close()
            except Exception:
                pass

    detail = "พบ device แต่ไม่สามารถเปิด HID interface ใด ๆ ได้\n"
    for error in errors:
        detail += f"  - {error}\n"
    detail += (
        "  - หากรันด้วย root แล้วยังเปิดไม่ได้ ปัญหาอาจไม่ใช่ permission แต่เป็น interface/driver/device state\n"
        "  - ตรวจสอบสิทธิ์ด้วย: ls -l /dev/hidraw*\n"
        "  - ตรวจสอบ process ที่ใช้ device ด้วย: sudo fuser -v /dev/hidrawX\n"
        f"  - ตรวจว่า node เป็น group {UDEV_GROUP}, mode 0660 และ user อยู่ใน group นี้\n"
        "  - หลังเพิ่ม group ให้ logout/login ใหม่ หรือเริ่ม service ใหม่ก่อนทดสอบ\n"
        "  - หลัง reload udev rules ให้ถอด/เสียบ USB ใหม่หาก node ยังใช้ rule เก่า\n"
        "  - ลอง: sudo udevadm test /sys/class/hidraw/hidrawX"
    )
    return False, detail


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
        "--vid", type=lambda x: int(x, 0), default=None,
        help="USB Vendor ID (override; default: all devices from meta.json)",
    )
    parser.add_argument(
        "--pid", type=lambda x: int(x, 0), default=None,
        help="USB Product ID (override; default: all devices from meta.json)",
    )
    parser.add_argument(
        "--user", default=os.environ.get("SUDO_USER") or os.environ.get("USER"),
        help=f"เพิ่ม user นี้เข้า group {UDEV_GROUP} (default: SUDO_USER)",
    )
    args = parser.parse_args()

    if platform.system().lower() != "linux":
        print(f"[!] สคริปต์นี้สำหรับ Linux เท่านั้น (ตรวจพบ: {platform.system()})")
        return 1

    check_only = args.check

    # Determine which devices to check
    if args.vid is not None and args.pid is not None:
        # Manual override: single device
        check_targets = [(args.vid, args.pid)]
        use_all_devices = False
    else:
        # Use all devices from registry
        check_targets = _registry.get_all_vid_pid_pairs()
        use_all_devices = True

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
        print("    sudo apt install -y pkg-config build-essential python3-dev libudev-dev libhidapi-hidraw0 libhidapi-dev libusb-1.0-0-dev")
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
        group_ok, group_message = ensure_udev_group(args.user)
        _print_result(f"group {UDEV_GROUP}", group_ok, group_message)
        if not group_ok:
            return 1
        print("\n  กำลังสร้าง udev rule...")
        if use_all_devices:
            ok, msg = install_udev_rule(all_devices=True)
        else:
            ok, msg = install_udev_rule(args.vid, args.pid)
        _print_result("สร้าง udev rule", ok, msg)
        print(f"  {msg}")
        if ok:
            has_rule = True
    elif not has_rule and check_only:
        print("\n  สร้าง udev rule ด้วยคำสั่ง:")
        print("    sudo python -m ups_module.linux_setup")

    group_ok, group_message = check_udev_group_access(args.user)
    _print_result(f"group {UDEV_GROUP}", group_ok, group_message)

    # --- ตรวจสอบสิทธิ์ device ---
    _print_header("ตรวจสอบการเข้าถึง UPS Device")
    any_accessible = False
    for vid, pid in check_targets:
        accessible, msg = check_device_permission(vid, pid)
        profile = _registry.get_by_vid_pid(vid, pid)
        label = f"{profile.model} (VID=0x{vid:04X} PID=0x{pid:04X})" if profile else f"UPS (VID=0x{vid:04X} PID=0x{pid:04X})"
        _print_result(label, accessible, msg)
        if accessible:
            print(f"  {msg}")
            any_accessible = True

    # --- สรุป ---
    _print_header("สรุป")
    if all_deps_ok and has_rule and group_ok and any_accessible:
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
