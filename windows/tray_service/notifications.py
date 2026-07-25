"""
UPS Monitor — Windows Toast Notification Manager
==================================================
ส่ง Windows Toast Notification เมื่อสถานะ UPS เปลี่ยน

Events ที่แจ้งเตือน:
    * AC Fail      — ไฟฟ้าดับ, UPS ใช้แบตเตอรี่
    * AC Restore   — ไฟฟ้ากลับมา
    * Battery Low  — แบตเตอรี่ต่ำกว่า threshold
    * Battery Critical — แบตเตอรี่วิกฤต (ต่ำมาก)

Features:
    * Debounce — ป้องกันแจ้งเตือนซ้ำในช่วงเวลาสั้น (cooldown_s)
    * Enable/Disable แยกตาม event type
    * ใช้ plyer.notification สำหรับ Windows Toast

Dependencies:
    - plyer (pip install plyer)

Usage:
    >>> from tray_service.notifications import NotificationManager
    >>> notif = NotificationManager(app_name="UPS Monitor")
    >>> notif.notify_ac_fail(battery_charge=85)
    >>> notif.notify_ac_restore()
    >>> notif.notify_low_battery(charge=18)
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Attempt import plyer ─────────────────────────────────────────────────────
try:
    from plyer import notification as _plyer_notif
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False
    logger.warning("plyer not found — notifications disabled. Run: pip install plyer")


# ── Notification icons / titles ───────────────────────────────────────────────
_ICON_PATH = ""  # จะตั้งค่าเมื่อรู้ path จริง

class NotificationManager:
    """
    จัดการ Windows Toast Notification สำหรับ UPS Monitor

    ใช้ plyer.notification เพื่อส่ง Windows Toast
    มีระบบ cooldown (debounce) ป้องกันแจ้งซ้ำในช่วงเวลาสั้น

    Attributes:
        app_name (str): ชื่อที่แสดงใน notification (default: "UPS Monitor")
        cooldown_s (float): ระยะเวลา (วินาที) ระหว่างการแจ้งเตือนประเภทเดียวกัน (default: 30)
        enabled (bool): เปิด/ปิด notification ทั้งหมด
        notify_ac_fail_enabled (bool): เปิด/ปิดแจ้งเตือนไฟดับ
        notify_ac_restore_enabled (bool): เปิด/ปิดแจ้งเตือนไฟกลับ
        notify_low_battery_enabled (bool): เปิด/ปิดแจ้งเตือนแบตต่ำ
        icon_path (str): Path ไปยัง .ico file สำหรับ notification icon

    Example:
        >>> nm = NotificationManager(cooldown_s=60)
        >>> nm.notify_ac_fail(battery_charge=72)
        >>> nm.notify_low_battery(charge=15, runtime_s=300)
    """

    def __init__(
        self,
        app_name: str = "UPS Monitor",
        cooldown_s: float = 30.0,
        enabled: bool = True,
        notify_ac_fail_enabled: bool = True,
        notify_ac_restore_enabled: bool = True,
        notify_low_battery_enabled: bool = True,
        icon_path: str = "",
    ) -> None:
        """
        สร้าง NotificationManager

        Args:
            app_name:                   ชื่อแอปที่แสดงใน notification
            cooldown_s:                 ห้ามแจ้งซ้ำภายใน N วินาที (per event type)
            enabled:                    เปิด/ปิด notification ทั้งหมด
            notify_ac_fail_enabled:     เปิด/ปิดแจ้งเตือนเฉพาะ AC fail
            notify_ac_restore_enabled:  เปิด/ปิดแจ้งเตือนเฉพาะ AC restore
            notify_low_battery_enabled: เปิด/ปิดแจ้งเตือนเฉพาะ battery low
            icon_path:                  Path ไปยัง .ico file (ถ้าว่างจะใช้ default)
        """
        self.app_name = app_name
        self.cooldown_s = cooldown_s
        self.enabled = enabled
        self.notify_ac_fail_enabled = notify_ac_fail_enabled
        self.notify_ac_restore_enabled = notify_ac_restore_enabled
        self.notify_low_battery_enabled = notify_low_battery_enabled
        self.icon_path = icon_path

        # Cooldown tracking: {event_key: last_sent_timestamp}
        self._last_sent: dict[str, float] = {}

    # ── Public notification methods ───────────────────────────────────────────

    def notify_ac_fail(
        self,
        battery_charge: Optional[float] = None,
        runtime_s: Optional[float] = None,
    ) -> None:
        """
        แจ้งเตือน: ไฟฟ้าดับ!

        Args:
            battery_charge: % แบตเตอรี่ปัจจุบัน (ถ้ามี)
            runtime_s:      เวลาสำรองไฟที่เหลือ (วินาที, ถ้ามี)
        """
        if not self.notify_ac_fail_enabled:
            return

        msg_parts = ["UPS กำลังทำงานด้วยแบตเตอรี่"]
        if battery_charge is not None:
            msg_parts.append(f"แบตเตอรี่: {battery_charge:.0f}%")
        if runtime_s is not None and runtime_s > 0:
            mins = int(runtime_s) // 60
            secs = int(runtime_s) % 60
            msg_parts.append(f"เวลาสำรองไฟ: {mins} นาที {secs} วินาที")

        self._send(
            event_key="ac_fail",
            title="[ALERT] ไฟฟ้าดับ!",
            message="\n".join(msg_parts),
            timeout=10,
        )

    def notify_ac_restore(self) -> None:
        """แจ้งเตือน: ไฟฟ้ากลับมาแล้ว"""
        if not self.notify_ac_restore_enabled:
            return
        self._send(
            event_key="ac_restore",
            title="[INFO] ไฟฟ้ากลับมาแล้ว",
            message="ระบบไฟฟ้ากลับสู่ภาวะปกติ\nUPS กำลังชาร์จแบตเตอรี่",
            timeout=7,
        )

    def notify_low_battery(
        self,
        charge: Optional[float] = None,
        runtime_s: Optional[float] = None,
    ) -> None:
        """
        แจ้งเตือน: แบตเตอรี่ต่ำ

        Args:
            charge:    % แบตเตอรี่ปัจจุบัน
            runtime_s: เวลาสำรองไฟที่เหลือ (วินาที)
        """
        if not self.notify_low_battery_enabled:
            return

        msg_parts = ["กรุณาเซฟงานและเตรียมปิดเครื่อง"]
        if charge is not None:
            msg_parts.insert(0, f"แบตเตอรี่เหลือ {charge:.0f}%")
        if runtime_s is not None and runtime_s > 0:
            mins = int(runtime_s) // 60
            msg_parts.append(f"เวลาสำรองไฟ: ~{mins} นาที")

        self._send(
            event_key="low_battery",
            title="[WARNING] แบตเตอรี่ต่ำ!",
            message="\n".join(msg_parts),
            timeout=10,
        )

    def notify_critical_battery(
        self,
        charge: Optional[float] = None,
    ) -> None:
        """
        แจ้งเตือน: แบตเตอรี่วิกฤต (ต่ำมาก — กำลังจะปิดเครื่อง)

        Args:
            charge: % แบตเตอรี่ปัจจุบัน
        """
        charge_str = f"{charge:.0f}%" if charge is not None else "—"
        self._send(
            event_key="critical_battery",
            title="[CRITICAL] แบตเตอรี่วิกฤต!",
            message=f"แบตเตอรี่เหลือ {charge_str}\nระบบจะปิดเครื่องอัตโนมัติเร็วๆ นี้!",
            timeout=15,
            cooldown_override=10.0,  # ลด cooldown สำหรับสถานการณ์วิกฤต
        )

    def notify_shutdown_scheduled(self, delay_minutes: int) -> None:
        """
        แจ้งเตือน: กำลังจะปิดเครื่อง PC

        Args:
            delay_minutes: จำนวนนาทีที่จะปิดเครื่อง
        """
        self._send(
            event_key="shutdown_scheduled",
            title="[WARNING] กำลังจะปิดเครื่อง PC",
            message=f"UPS Monitor จะปิดเครื่องใน {delay_minutes} นาที\nเนื่องจากไฟฟ้าดับ / แบตเตอรี่ต่ำ",
            timeout=10,
        )

    def notify_shutdown_cancelled(self) -> None:
        """แจ้งเตือน: ยกเลิกการปิดเครื่อง PC แล้ว"""
        self._send(
            event_key="shutdown_cancelled",
            title="[INFO] ยกเลิกการปิดเครื่องแล้ว",
            message="ไฟฟ้ากลับมา — ยกเลิก shutdown อัตโนมัติ",
            timeout=7,
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _send(
        self,
        event_key: str,
        title: str,
        message: str,
        timeout: int = 7,
        cooldown_override: Optional[float] = None,
    ) -> None:
        """
        ส่ง notification พร้อม cooldown check

        Args:
            event_key:        key สำหรับ track cooldown (เช่น "ac_fail")
            title:            หัวข้อ notification
            message:          เนื้อหา notification
            timeout:          เวลาแสดง notification (วินาที)
            cooldown_override: cooldown ที่ override ค่า default (ถ้าต้องการ)
        """
        if not self.enabled:
            return

        # Cooldown check
        cooldown = cooldown_override if cooldown_override is not None else self.cooldown_s
        last = self._last_sent.get(event_key, 0.0)
        now = time.monotonic()
        if (now - last) < cooldown:
            logger.debug(f"Notification '{event_key}' suppressed (cooldown {cooldown}s)")
            return

        self._last_sent[event_key] = now

        if not PLYER_AVAILABLE:
            logger.info(f"[NOTIFICATION] {title}: {message}")
            return

        try:
            _plyer_notif.notify(
                title=title,
                message=message,
                app_name=self.app_name,
                app_icon=self.icon_path or None,
                timeout=timeout,
            )
            logger.debug(f"Notification sent: {title}")
        except Exception as exc:
            logger.error(f"Failed to send notification: {exc}")
