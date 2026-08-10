"""
UPS Monitor — System Tray Application
=======================================
จัดการ System Tray Icon และ Context Menu ด้วย pystray

Features:
    - ไอคอนสี 4 แบบตามสถานะ: OK (เขียว), Fail (แดง), Charging (เหลือง), Disconnected (เทา)
    - Context menu: Open Web UI, Start/Stop monitoring, Exit
    - Tooltip แสดงสถานะ UPS แบบย่อ
    - เปิด browser อัตโนมัติเมื่อเลือก "Open Web UI"

Dependencies:
    - pystray (pip install pystray)
    - Pillow (pip install Pillow) — สร้าง icon แบบ programmatic

Usage:
    >>> from tray_service.tray_app import TrayApp
    >>> tray = TrayApp(port=48655, poller=poller)
    >>> tray.run()  # blocking — รันบน main thread (pystray requirement)
"""

from __future__ import annotations

import logging
import sys
import threading
import webbrowser
from io import BytesIO
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# ── pystray + Pillow ──────────────────────────────────────────────────────────
try:
    import pystray
    from pystray import MenuItem as item, Menu
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False
    logger.error("pystray not found — run: pip install pystray")

try:
    from PIL import Image, ImageDraw
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.error("Pillow not found — run: pip install Pillow")

# ── Icon colors ──────────────────────────────────────────────────────────────
_COLOR_OK           = (78, 202, 110)   # เขียว — AC OK
_COLOR_FAIL         = (224, 74, 74)    # แดง — AC Fail / ไฟดับ
_COLOR_CHARGING     = (245, 166, 35)   # เหลือง — กำลังชาร์จ
_COLOR_DISCONNECTED = (96, 96, 128)    # เทา — ไม่ได้เชื่อมต่อ
_COLOR_CRITICAL     = (200, 40, 40)    # แดงเข้ม — Critical


class TrayApp:
    """
    System Tray Application สำหรับ UPS Monitor

    ใช้ pystray สร้าง tray icon พร้อม context menu
    เปลี่ยนสี icon ตามสถานะ UPS แบบ real-time

    Note:
        pystray ต้องรันบน **main thread** เพราะ Windows message loop
        ต้องการ main thread ดังนั้น TrayApp.run() จะ block

    Attributes:
        port (int): Port ของ Flask Web Server
        poller (Any): UPSPoller instance สำหรับดูสถานะ

    Example:
        >>> tray = TrayApp(port=48655, poller=ups_poller)
        >>> tray.run()  # blocking!
    """

    def __init__(
        self,
        port: int = 48655,
        poller: Optional[Any] = None,
        on_exit: Optional[callable] = None,
    ) -> None:
        """
        สร้าง TrayApp

        Args:
            port:    Port ของ Flask Web Server
            poller:  UPSPoller instance (ถ้ามี จะ update icon ตามสถานะ)
            on_exit: callback ที่จะเรียกเมื่อ user กด Exit
        """
        self.port = port
        self._poller = poller
        self._on_exit = on_exit
        self._icon: Optional[pystray.Icon] = None
        self._current_status = "disconnected"

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        เริ่ม tray icon (blocking — ต้องเรียกจาก main thread)

        จะ return เมื่อ user กด Exit หรือเรียก stop()
        """
        if not PYSTRAY_AVAILABLE or not PILLOW_AVAILABLE:
            logger.error("Cannot start tray: pystray or Pillow not available")
            return

        icon_image = _make_icon(_COLOR_DISCONNECTED)
        menu = self._build_menu()

        self._icon = pystray.Icon(
            name="UPS Monitor",
            icon=icon_image,
            title="UPS Monitor — กำลังเชื่อมต่อ...",
            menu=menu,
        )

        # เริ่ม update thread สำหรับ polling icon status
        if self._poller is not None:
            updater = threading.Thread(
                target=self._status_updater,
                daemon=True,
                name="TrayStatusUpdater",
            )
            updater.start()

        logger.info(f"Tray icon started — Web UI: http://127.0.0.1:{self.port}")
        self._icon.run()

    def stop(self) -> None:
        """หยุด tray icon"""
        if self._icon:
            self._icon.stop()

    def set_status(self, status: str, tooltip: str = "") -> None:
        """
        อัปเดตสถานะ tray icon

        Args:
            status:  "ok" | "fail" | "charging" | "disconnected" | "critical"
            tooltip: ข้อความ tooltip ที่แสดงเมื่อ hover บน tray icon
        """
        if not self._icon:
            return

        self._current_status = status
        color = {
            "ok":           _COLOR_OK,
            "fail":         _COLOR_FAIL,
            "charging":     _COLOR_CHARGING,
            "disconnected": _COLOR_DISCONNECTED,
            "critical":     _COLOR_CRITICAL,
        }.get(status, _COLOR_DISCONNECTED)

        self._icon.icon = _make_icon(color)
        self._icon.title = tooltip or f"UPS Monitor — {status.upper()}"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_device_menu(self) -> List["item"]:
        items = []
        try:
            from core_hid_ups import list_ups_devices
            devices = list_ups_devices(target_vid=None)

            sel_path = None
            sel_serial = None
            if self._poller:
                info = self._poller.get_device_info()
                sel_path = info.get("path")
                sel_serial = info.get("serial_number")

            for dev in devices:
                if not dev.get("is_ups", False):
                    continue
                mfr = dev.get("manufacturer_string") or "UPS"
                prod = dev.get("product_string") or "Device"
                vid = dev.get("vendor_id", 0)
                pid = dev.get("product_id", 0)
                path = dev.get("path_str")
                serial = dev.get("serial_number")

                is_active = False
                if sel_serial and serial and str(serial).strip() == str(sel_serial).strip():
                    is_active = True
                elif sel_path and (path == sel_path or str(dev.get("path")) == str(sel_path)):
                    is_active = True

                prefix = "✔ " if is_active else "  "
                label = f"{prefix}{mfr} {prod} (VID=0x{vid:04X} PID=0x{pid:04X})"

                def _make_handler(v, p, dev_p, s):
                    def _on_click(icon, item_obj):
                        if self._poller:
                            logger.info(f"Tray menu selected UPS: VID=0x{v:04X} PID=0x{p:04X} path={dev_p} serial={s}")
                            self._poller.select_device(vid=v, pid=p, path=dev_p, serial=s)
                    return _on_click

                items.append(item(label, _make_handler(vid, pid, path, serial)))
        except Exception as exc:
            logger.debug(f"Error building device menu: {exc}")

        if not items:
            items.append(item("ไม่พบบริการ UPS อุปกรณ์", lambda icon, item_obj: None, enabled=False))
        return items

    def _trigger_battery_test(self, test_type: str) -> None:
        """สั่งรัน Battery Test จาก Tray Icon Menu + Monitor ผลใน background thread"""
        if not self._poller or not self._poller.is_connected():
            logger.warning("Cannot trigger battery test: UPS not connected")
            return

        try:
            from tools.unit.live_battery_test_runner import send_universal_battery_test_command
            from core_hid_ups import monitor_ppc2000d_battery_test

            info = self._poller.get_device_info()
            h = getattr(self._poller, "_handle", None)
            if not h:
                logger.warning("Battery test: no HID handle available")
                return

            # อ่าน initial_val ของ 0x24 ก่อนส่งคำสั่ง (สำคัญ!)
            initial_val = 6  # default fallback
            try:
                r24 = h.get_feature_report(0x24, 8)
                if r24 and len(r24) >= 2:
                    initial_val = r24[1]
            except Exception:
                pass

            # ส่งคำสั่ง Test
            ok, msg = send_universal_battery_test_command(h, info, test_type)
            logger.info(f"Tray battery test command '{test_type}': {msg}")

            if not ok:
                logger.warning(f"Battery test command failed: {msg}")
                return

            # Monitor ผลใน background thread (ไม่บล็อก Tray UI)
            import threading

            def _monitor():
                max_s = 35 if test_type == "quick" else 3600

                def _on_started(mid_val):
                    logger.info(f"Battery test started (0x24: {initial_val}→{mid_val})")

                def _on_tick(tick):
                    logger.debug(
                        f"Battery test tick: {tick['elapsed_s']}s | "
                        f"0x24={tick['test_val']} status={tick['status']} "
                        f"batt={tick['battery_pct']}%"
                    )

                def _on_done(result):
                    if result["completed"]:
                        logger.info(
                            f"✅ Battery test completed in {result['elapsed_s']}s: "
                            f"{result['result_name']} | batt={result['battery_pct']}%"
                        )
                    else:
                        logger.warning(
                            f"⏰ Battery test monitor timeout: {result['result_name']}"
                        )

                monitor_ppc2000d_battery_test(
                    h,
                    initial_test_val=initial_val,
                    max_wait_s=max_s,
                    on_started=_on_started,
                    on_tick=_on_tick,
                    on_done=_on_done,
                )

            t = threading.Thread(target=_monitor, daemon=True, name="ups-test-monitor")
            t.start()

        except Exception as exc:
            logger.error(f"Tray battery test command error: {exc}")

    def _build_menu(self) -> "Menu":
        """สร้าง context menu"""
        return Menu(
            item("Open Web UI",      self._open_web_ui, default=True),
            item("Select UPS Device", Menu(lambda: self._build_device_menu())),
            item("Battery Self-Test", Menu(
                item("⚡ Quick Test (10s)", lambda icon, item_obj: self._trigger_battery_test("quick")),
                item("🔋 Deep Discharge Test", lambda icon, item_obj: self._trigger_battery_test("deep")),
                item("🚫 Cancel Test", lambda icon, item_obj: self._trigger_battery_test("cancel")),
            )),
            item("Exit",              self._exit),
        )


    def _open_web_ui(self) -> None:
        """เปิด Web UI ใน browser"""
        url = f"http://127.0.0.1:{self.port}"
        logger.info(f"Opening Web UI: {url}")
        webbrowser.open(url)

    def _start_monitoring(self) -> None:
        """เริ่ม UPS polling ต่อ"""
        if self._poller:
            self._poller.resume()
            logger.info("Monitoring started via tray menu")

    def _stop_monitoring(self) -> None:
        """หยุด UPS polling ชั่วคราว"""
        if self._poller:
            self._poller.pause()
            self.set_status("disconnected", "UPS Monitor — Monitoring paused")
            logger.info("Monitoring stopped via tray menu")

    def _exit(self) -> None:
        """ออกจากโปรแกรม"""
        logger.info("Exit requested via tray menu")
        if self._on_exit:
            try:
                self._on_exit()
            except Exception as exc:
                logger.error(f"Exit callback error: {exc}")
        self.stop()

    def _status_updater(self) -> None:
        """
        Thread ที่อัปเดต icon สถานะทุก 2 วินาที
        โดยอ่านจาก poller.get_state()
        """
        import time
        while True:
            try:
                if not self._icon:
                    break
                if not self._poller.is_connected():
                    self.set_status("disconnected", "UPS Monitor — ไม่ได้เชื่อมต่อ")
                elif not self._poller.is_monitoring():
                    self.set_status("disconnected", "UPS Monitor — หยุด Monitoring")
                else:
                    state = self._poller.get_state()
                    dev_info = self._poller.get_device_info()
                    status, tooltip = _interpret_state(state, dev_info)
                    self.set_status(status, tooltip)
            except Exception as exc:
                logger.debug(f"Status updater error: {exc}")
            time.sleep(2)


from pathlib import Path

_LOGO_PATH = Path(__file__).parent / "static" / "img" / "logo.png"


def _make_icon(color: tuple[int, int, int], size: int = 64) -> "Image.Image":
    """
    สร้าง tray icon จาก logo.png พร้อมแนบ status indicator dot ที่มุมล่างขวา

    Args:
        color: RGB tuple เช่น (78, 202, 110)
        size:  ขนาด icon ใน pixels (default: 64)

    Returns:
        PIL.Image.Image ขนาด size x size (RGBA)
    """
    img = None
    if _LOGO_PATH.exists():
        try:
            logo = Image.open(_LOGO_PATH).convert("RGBA")
            logo.thumbnail((size - 4, size - 4), Image.Resampling.LANCZOS)
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            offset_x = (size - logo.width) // 2
            offset_y = (size - logo.height) // 2
            img.paste(logo, (offset_x, offset_y), logo)
        except Exception as exc:
            logger.debug(f"Could not load logo.png for tray icon: {exc}")
            img = None

    if img is None:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        margin = 4
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=(*color, 255),
        )
        return img

    # Overlay status indicator dot at bottom right
    draw = ImageDraw.Draw(img)
    dot_radius = size // 5
    center_x = size - dot_radius - 2
    center_y = size - dot_radius - 2

    # Border for contrast
    draw.ellipse(
        [center_x - dot_radius - 2, center_y - dot_radius - 2, center_x + dot_radius + 2, center_y + dot_radius + 2],
        fill=(15, 23, 42, 255),
    )
    # Status dot fill
    draw.ellipse(
        [center_x - dot_radius, center_y - dot_radius, center_x + dot_radius, center_y + dot_radius],
        fill=(*color, 255),
    )

    return img


def _interpret_state(state: dict, device_info: Optional[dict] = None) -> tuple[str, str]:
    """
    แปลง UPS state dict และ device_info เป็น (status_key, tooltip_text)

    Args:
        state: UPS state dict จาก poller.get_state()
        device_info: device info dict จาก poller.get_device_info()

    Returns:
        (status, tooltip) เช่น ("ok", "ENEREX UPS (Innova Unity) | Batt: 100% | Load: 11% | 70W | ~152m — Online")
    """
    mfr = state.get("ups.mfr") or (device_info.get("manufacturer_string") if device_info else None) or "UPS"
    model = state.get("ups.model") or (device_info.get("product_string") if device_info else None) or ""
    dev_name = f"{mfr} {model}".strip()

    ac_present   = state.get("ac_present")
    charging     = state.get("charging")
    charge       = state.get("battery.charge")
    runtime      = state.get("battery.runtime")
    load         = state.get("percent_load")
    vout         = state.get("output_voltage_v") or state.get("output.voltage")
    power_w      = state.get("output_active_power_w")
    overload     = state.get("overload")
    shutdown_imm = state.get("shutdown_imminent")
    ups_status   = str(state.get("ups.status") or "")

    # Build rich tooltip
    parts = [f"UPS Monitor ({dev_name})"]
    if charge is not None:
        parts.append(f"Batt: {charge:.0f}%")
    if load is not None and load > 0:
        parts.append(f"Load: {load:.0f}%")
    if power_w is not None and power_w > 0:
        parts.append(f"{power_w:.0f}W")
    elif vout is not None and vout > 0:
        parts.append(f"{vout:.0f}V")
    if runtime is not None and runtime > 0:
        mins = int(runtime) // 60
        parts.append(f"~{mins}m")

    # Determine status
    if shutdown_imm or overload:
        return "critical", " | ".join(parts) + " [CRITICAL]"
    if "OFF" in ups_status:
        return "disconnected", " | ".join(parts) + " — Standby (Output Off)"
    if "BYPASS" in ups_status or "BYP" in ups_status:
        return "charging", " | ".join(parts) + " — Bypass Mode"
    if ac_present is False or "OB" in ups_status:
        return "fail", " | ".join(parts) + " — On Battery"
    if charging is True:
        return "charging", " | ".join(parts) + " — Charging"
    if ac_present is True:
        return "ok", " | ".join(parts) + " — Online"

    return "disconnected", f"UPS Monitor ({dev_name}) — Connecting..."
