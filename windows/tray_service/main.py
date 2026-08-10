"""
UPS Monitor — Main Entry Point (Windows Tray Service)
=======================================================
เริ่มต้นระบบทั้งหมดและเชื่อม components เข้าด้วยกัน:

    1. ConfigManager    — โหลดการตั้งค่า
    2. UPSPoller        — เริ่ม background thread อ่านค่า UPS
    3. NotificationManager — เตรียมระบบแจ้งเตือน
    4. AutoShutdownManager — เตรียมระบบปิดเครื่องอัตโนมัติ
    5. WebServer        — เริ่ม Flask ใน background thread
    6. TrayApp          — เริ่ม System Tray (blocking บน main thread)

Run:
    python -m tray_service.main
    — หรือ —
    python windows/tray_service/main.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# ── Force UTF-8 ทั่วทั้งโปรแกรม (ก่อน import อื่นๆ) ───────────────────────────
# แก้ปัญหา 'charmap' codec error บน Windows ที่ใช้ cp874/cp1252
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

# ── เพิ่ม paths เข้า sys.path ──────────────────────────────────────────────
#   _WINDOWS_DIR  = UPS/windows/   → ทำให้ import tray_service.* ได้
#   _ROOT         = UPS/           → ทำให้ import core_hid_ups, win32_hid_wrapper ได้
_WINDOWS_DIR = Path(__file__).resolve().parent.parent    # UPS/windows/
_ROOT        = _WINDOWS_DIR.parent                       # UPS/

for _p in (_WINDOWS_DIR, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from tray_service.config_manager import ConfigManager
from tray_service.database import DatabaseManager
from tray_service.poller import UPSPoller
from tray_service.notifications import NotificationManager
from tray_service.auto_shutdown import AutoShutdownManager
from tray_service.web_server import WebServer
from tray_service.tray_app import TrayApp


def _setup_logging(level: str = "INFO") -> None:
    """
    ตั้งค่า logging ให้บันทึกลงไฟล์และ console

    ใช้ encoding="utf-8" สำหรับทั้ง FileHandler และ StreamHandler
    เพื่อป้องกัน 'charmap' codec error บน Windows
    """
    log_dir = Path(os.environ.get("APPDATA", Path.home())) / "UPS-Monitor" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ups_monitor.log"

    # StreamHandler: force UTF-8 บน Windows (reconfigure stdout ถ้าจำเป็น)
    stream_handler = logging.StreamHandler(sys.stdout)
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[file_handler, stream_handler],
    )
    logging.getLogger("werkzeug").setLevel(logging.ERROR)


import argparse


def main() -> None:
    """
    Entry point หลักของ UPS Monitor Windows Tray Service

    ลำดับการเริ่มต้น:
        1. โหลด config & Database
        2. รองรับ CLI arguments สำหรับเลือก UPS หรือดูรายการอุปกรณ์
        3. สร้าง components
        4. เชื่อม callbacks ระหว่าง components
        5. เริ่ม WebServer (background thread)
        6. เริ่ม UPSPoller (background thread)
        7. เริ่ม TrayApp (main thread — blocking)
    """
    parser = argparse.ArgumentParser(description="ENEREX UPS Monitor Service")
    parser.add_argument("--vid", type=lambda x: int(x, 0), default=None, help="Target USB Vendor ID in hex (e.g. 0x06DA or 0x0001)")
    parser.add_argument("--pid", type=lambda x: int(x, 0), default=None, help="Target USB Product ID in hex (e.g. 0xFFFF or 0x0000)")
    parser.add_argument("--serial", type=str, default=None, help="Target UPS Serial Number")
    parser.add_argument("--path", type=str, default=None, help="Target USB Device Path")
    parser.add_argument("--list-devices", action="store_true", help="List connected UPS devices and exit")
    args, _ = parser.parse_known_args()

    # ── 1. Config & Database ──────────────────────────────────────────────────
    cfg = ConfigManager()
    _setup_logging(cfg.get("log_level", "INFO"))
    logger = logging.getLogger(__name__)
    logger.info("UPS Monitor starting...")

    if args.list_devices:
        try:
            from core_hid_ups import list_ups_devices
            devices = list_ups_devices(target_vid=None)
            print("\n=== Connected UPS Devices ===")
            if not devices:
                print("No UPS devices found.")
            else:
                for idx, d in enumerate(devices, 1):
                    print(f"[{idx}] {d.get('manufacturer_string')} {d.get('product_string')}")
                    print(f"    VID=0x{d.get('vendor_id'):04X} PID=0x{d.get('product_id'):04X} Serial={d.get('serial_number') or 'N/A'}")
                    print(f"    Path={d.get('path_str')}")
        except Exception as exc:
            print(f"Error listing devices: {exc}")
        return

    # หากมีการระบุตัวเลือกจาก CLI ให้อัปเดตและบันทึกลง Config
    if args.vid is not None:
        cfg.set("vid", args.vid)
    if args.pid is not None:
        cfg.set("pid", args.pid)
    if args.serial is not None:
        cfg.set("selected_device_serial", args.serial)
    if args.path is not None:
        cfg.set("selected_device_path", args.path)
    if any(k is not None for k in (args.vid, args.pid, args.serial, args.path)):
        cfg.save()
        logger.info(f"Updated UPS selection from CLI: VID={args.vid} PID={args.pid} serial={args.serial} path={args.path}")

    db = None
    if cfg.get("db_enabled", True):
        try:
            db = DatabaseManager()
            db.prune_old_data(retention_days=cfg.get("db_retention_days", 30))
            db.log_event("SYSTEM_START", "UPS Monitor Service started")
        except Exception as err:
            logger.error(f"Failed to initialize SQLite Database: {err}")

    # ── 2. Notification Manager ───────────────────────────────────────────────
    icon_path = str(Path(__file__).parent.parent / "assets" / "ups_icon.ico")
    notif = NotificationManager(
        app_name="ENEREX UPS Monitor",
        enabled=cfg.get("notifications_enabled", True),
        notify_ac_fail_enabled=cfg.get("notify_on_ac_fail", True),
        notify_ac_restore_enabled=cfg.get("notify_on_ac_restore", True),
        notify_low_battery_enabled=cfg.get("notify_on_low_battery", True),
        icon_path=icon_path if Path(icon_path).exists() else "",
    )

    # ── 3. Auto Shutdown Manager ──────────────────────────────────────────────
    shutdown_mgr = AutoShutdownManager(
        enabled=cfg.get("auto_shutdown_enabled", False),
        shutdown_delay_minutes=cfg.get("shutdown_delay_minutes", 5),
        battery_threshold_percent=cfg.get("shutdown_battery_threshold", 20),
        shutdown_on_ac_fail=cfg.get("shutdown_on_ac_fail", True),
        shutdown_on_low_battery=cfg.get("shutdown_on_low_battery", True),
        on_shutdown_scheduled_cb=lambda mins: notif.notify_shutdown_scheduled(mins),
        on_shutdown_cancelled_cb=lambda: notif.notify_shutdown_cancelled(),
    )

    # ── 4. UPS Poller ─────────────────────────────────────────────────────────
    target_vid = args.vid if args.vid is not None else cfg.get("vid", None)
    target_pid = args.pid if args.pid is not None else cfg.get("pid", None)
    target_path = args.path if args.path is not None else cfg.get("selected_device_path")
    target_serial = args.serial if args.serial is not None else cfg.get("selected_device_serial")

    poller = UPSPoller(
        vid=target_vid,
        pid=target_pid,
        target_path=target_path,
        target_serial=target_serial,
        poll_interval_s=cfg.get("poll_interval_s", 1.0),
        battery_low_threshold=cfg.get("shutdown_battery_threshold", 20),
        battery_critical_threshold=max(cfg.get("shutdown_battery_threshold", 20) - 10, 5),
        db=db,
        telemetry_interval_s=float(cfg.get("db_telemetry_interval_s", 10.0)),

        # Callbacks → Notification + AutoShutdown
        on_ac_fail=lambda state: _on_ac_fail(state, notif, shutdown_mgr),
        on_ac_restore=lambda state: _on_ac_restore(state, notif, shutdown_mgr),
        on_low_battery=lambda state: _on_low_battery(state, notif, shutdown_mgr),
        on_critical_battery=lambda state: _on_critical_battery(state, notif),
    )


    # ── 5. Web Server ─────────────────────────────────────────────────────────
    port = cfg.get("port", 48655)
    web = WebServer(
        poller=poller,
        config=cfg,
        shutdown_mgr=shutdown_mgr,
        db=db,
        port=port,
    )
    web.start()

    # ── 6. System Tray (main thread — blocking) ───────────────────────────────
    tray = TrayApp(
        port=port,
        poller=poller,
        on_exit=lambda: _shutdown_all(poller, web, logger),
    )

    # เริ่ม UPS Poller ก่อน tray
    poller.start()

    logger.info(f"All services started — Web UI: http://127.0.0.1:{port}")

    if cfg.get("start_minimized", True):
        logger.info("Starting minimized to tray (start_minimized=True)")
    else:
        # เปิด browser อัตโนมัติถ้า start_minimized=False
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{port}")

    tray.run()  # blocking — รัน pystray main loop
    logger.info("UPS Monitor exited")


# ── Event Handlers ────────────────────────────────────────────────────────────

def _on_ac_fail(state: dict, notif: NotificationManager, shutdown_mgr: AutoShutdownManager) -> None:
    """เรียกเมื่อไฟฟ้าดับ"""
    charge = state.get("battery.charge")
    runtime = state.get("battery.runtime")
    notif.notify_ac_fail(battery_charge=charge, runtime_s=runtime)
    shutdown_mgr.on_ac_fail()


def _on_ac_restore(state: dict, notif: NotificationManager, shutdown_mgr: AutoShutdownManager) -> None:
    """เรียกเมื่อไฟฟ้ากลับมา"""
    notif.notify_ac_restore()
    shutdown_mgr.on_ac_restore()


def _on_low_battery(state: dict, notif: NotificationManager, shutdown_mgr: AutoShutdownManager) -> None:
    """เรียกเมื่อแบตเตอรี่ต่ำ"""
    charge = state.get("battery.charge")
    runtime = state.get("battery.runtime")
    notif.notify_low_battery(charge=charge, runtime_s=runtime)
    if charge is not None:
        shutdown_mgr.on_low_battery(float(charge))


def _on_critical_battery(state: dict, notif: NotificationManager) -> None:
    """เรียกเมื่อแบตเตอรี่วิกฤต"""
    charge = state.get("battery.charge")
    notif.notify_critical_battery(charge=charge)


def _shutdown_all(poller: UPSPoller, web: WebServer, logger: logging.Logger) -> None:
    """หยุดทุก service อย่างปลอดภัยเมื่อ Exit"""
    logger.info("Shutting down all services...")
    poller.stop()
    web.stop()


if __name__ == "__main__":
    main()
