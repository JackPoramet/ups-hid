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
from typing import Any, Optional

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

    def _build_menu(self) -> "Menu":
        """สร้าง context menu"""
        return Menu(
            item("Open Web UI",      self._open_web_ui, default=True),
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
                    status, tooltip = _interpret_state(state)
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


def _interpret_state(state: dict) -> tuple[str, str]:
    """
    แปลง UPS state dict เป็น (status_key, tooltip_text)

    Args:
        state: UPS state dict จาก poller.get_state()

    Returns:
        (status, tooltip) เช่น ("ok", "UPS Monitor — AC OK | 85% | 2h")
    """
    ac_present   = state.get("ac_present")
    charging     = state.get("charging")
    charge       = state.get("battery.charge")
    runtime      = state.get("battery.runtime")
    overload     = state.get("overload")
    shutdown_imm = state.get("shutdown_imminent")
    ups_status   = str(state.get("ups.status") or "")

    # Build tooltip
    parts = ["UPS Monitor"]
    if charge is not None:
        parts.append(f"Batt: {charge:.0f}%")
    if runtime is not None and runtime > 0:
        mins = int(runtime) // 60
        parts.append(f"Runtime: ~{mins}m")

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

    return "disconnected", "UPS Monitor — Connecting..."
