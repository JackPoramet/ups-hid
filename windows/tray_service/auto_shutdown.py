"""
UPS Monitor — PC Auto-Shutdown Manager
========================================
ปิดเครื่อง PC อัตโนมัติเมื่อไฟฟ้าดับ หรือแบตเตอรี่ต่ำกว่า threshold

Flow:
    1. ตรวจ AC Fail → เริ่มนับถอยหลัง (shutdown_delay_minutes)
    2. ถ้าไฟกลับมาระหว่างนับถอยหลัง → ยกเลิก shutdown
    3. ถ้าแบตต่ำกว่า battery_threshold → shutdown ทันที (ถ้า on battery)
    4. ส่งคำสั่งผ่าน: ``shutdown /s /t <seconds> /c "<reason>"``
    5. ยกเลิกด้วย: ``shutdown /a``

Safety Features:
    * ปิดเครื่องก็ต่อเมื่อ enabled=True เท่านั้น
    * ยกเลิกอัตโนมัติเมื่อไฟกลับ (ถ้ายังไม่เกิน deadline)
    * บันทึก log ทุกขั้นตอน

Dependencies:
    - subprocess (built-in)
    - threading (built-in)

Usage:
    >>> from tray_service.auto_shutdown import AutoShutdownManager
    >>> mgr = AutoShutdownManager(
    ...     enabled=True,
    ...     shutdown_delay_minutes=5,
    ...     battery_threshold_percent=20,
    ... )
    >>> mgr.on_ac_fail()         # เริ่มนับถอยหลัง
    >>> mgr.on_ac_restore()      # ยกเลิก
    >>> mgr.on_low_battery(15)   # shutdown ทันที (ถ้า on battery)
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class AutoShutdownManager:
    """
    จัดการการปิดเครื่อง PC อัตโนมัติเมื่อ UPS สถานะผิดปกติ

    ใช้คำสั่ง Windows ``shutdown.exe`` เพื่อ schedule และยกเลิก shutdown

    Attributes:
        enabled (bool):                  เปิด/ปิดฟีเจอร์ทั้งหมด
        shutdown_delay_minutes (int):    หน่วงเวลาก่อนปิดเครื่อง (นาที) หลังไฟดับ
        battery_threshold_percent (int): ปิดเครื่องทันทีถ้าแบตต่ำกว่า % นี้
        on_shutdown_scheduled_cb:        callback เมื่อ schedule shutdown สำเร็จ
        on_shutdown_cancelled_cb:        callback เมื่อยกเลิก shutdown

    Example:
        >>> mgr = AutoShutdownManager(
        ...     enabled=True,
        ...     shutdown_delay_minutes=3,
        ...     battery_threshold_percent=15,
        ... )
        >>> mgr.on_ac_fail()   # ไฟดับ — นับถอยหลัง 3 นาที
        >>> time.sleep(30)
        >>> mgr.on_ac_restore()  # ไฟกลับ — ยกเลิก shutdown
    """

    def __init__(
        self,
        enabled: bool = False,
        shutdown_delay_minutes: int = 5,
        battery_threshold_percent: int = 20,
        shutdown_on_ac_fail: bool = True,
        shutdown_on_low_battery: bool = True,
        on_shutdown_scheduled_cb: Optional[Callable[[int], None]] = None,
        on_shutdown_cancelled_cb: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        สร้าง AutoShutdownManager

        Args:
            enabled:                    True = เปิดใช้ฟีเจอร์ auto-shutdown
            shutdown_delay_minutes:     นาทีก่อนปิดเครื่องหลังไฟดับ (default: 5)
            battery_threshold_percent:  % แบตที่จะปิดเครื่องทันที (default: 20)
            shutdown_on_ac_fail:        เปิด/ปิดการปิดเครื่องเมื่อไฟดับ
            shutdown_on_low_battery:    เปิด/ปิดการปิดเครื่องเมื่อแบตต่ำ
            on_shutdown_scheduled_cb:   callback(delay_minutes) เมื่อ schedule สำเร็จ
            on_shutdown_cancelled_cb:   callback() เมื่อยกเลิก shutdown
        """
        self.enabled = enabled
        self.shutdown_delay_minutes = shutdown_delay_minutes
        self.battery_threshold_percent = battery_threshold_percent
        self.shutdown_on_ac_fail = shutdown_on_ac_fail
        self.shutdown_on_low_battery = shutdown_on_low_battery

        self._on_shutdown_scheduled = on_shutdown_scheduled_cb
        self._on_shutdown_cancelled = on_shutdown_cancelled_cb

        self._shutdown_pending = False
        self._shutdown_deadline = 0.0
        self._shutdown_total_delay = 0
        self._shutdown_reason = ""
        self._shutdown_trigger_type = ""

        self._on_battery = False           # True = AC fail
        self._low_battery_triggered = False
        self._lock = threading.Lock()

    # ── Public API — เรียกจาก UPS Poller callbacks ────────────────────────────

    def on_ac_fail(self) -> None:
        """
        เรียกเมื่อไฟฟ้าดับ (AC Present: True → False)

        ถ้า enabled และ shutdown_on_ac_fail=True จะ schedule PC shutdown
        หลังจาก shutdown_delay_minutes นาที
        """
        with self._lock:
            self._on_battery = True
            self._low_battery_triggered = False

        if not self.enabled or not self.shutdown_on_ac_fail:
            logger.info("Auto-shutdown: AC fail detected but feature disabled")
            return

        delay_seconds = self.shutdown_delay_minutes * 60
        logger.warning(
            f"Auto-shutdown: AC FAIL — scheduling PC shutdown in {self.shutdown_delay_minutes} min"
        )
        self._schedule_shutdown(delay_seconds, reason="UPS ไฟฟ้าดับ (AC Fail)", trigger_type="ac_fail")

    def on_ac_restore(self) -> None:
        """
        เรียกเมื่อไฟฟ้ากลับมา (AC Present: False → True)

        ยกเลิก shutdown ที่ scheduled ไว้ (ถ้ายังไม่เกิด)
        """
        with self._lock:
            self._on_battery = False
            self._low_battery_triggered = False

        if self._shutdown_pending:
            logger.info("Auto-shutdown: AC restored — cancelling scheduled shutdown")
            self._cancel_shutdown()

    def on_low_battery(self, charge_percent: float) -> None:
        """
        เรียกเมื่อแบตเตอรี่ต่ำกว่า threshold ขณะไฟดับ

        ถ้า enabled และ shutdown_on_low_battery=True และยังไม่ได้ shutdown
        จะสั่ง shutdown ทันที (delay 30 วินาที เพื่อให้ user เห็น notification)

        Args:
            charge_percent: % แบตเตอรี่ปัจจุบัน
        """
        with self._lock:
            if self._low_battery_triggered:
                return
            if not self._on_battery:
                return  # ไม่สั่ง shutdown ถ้าไฟปกติ

        if not self.enabled or not self.shutdown_on_low_battery:
            return

        with self._lock:
            self._low_battery_triggered = True

        logger.warning(
            f"Auto-shutdown: Battery LOW ({charge_percent:.0f}%) — "
            f"scheduling immediate shutdown (30s grace)"
        )
        self._schedule_shutdown(
            delay_seconds=30,
            reason=f"UPS แบตเตอรี่ต่ำ ({charge_percent:.0f}%)",
            trigger_type="low_battery",
        )

    def trigger_manual_pc_shutdown(
        self,
        delay_seconds: int = 60,
        reason: str = "Manual PC Shutdown command via Web UI",
    ) -> bool:
        """
        สั่ง PC Shutdown ด้วยมือจาก Web UI พร้อมตั้งเวลานับถอยหลัง

        Args:
            delay_seconds: วินาทีที่นับถอยหลังก่อนปิดเครื่อง (default: 60)
            reason: เหตุผลในการสั่งปิดเครื่อง

        Returns:
            bool: True ถ้าสั่ง schedule สำเร็จ
        """
        logger.warning(f"Auto-shutdown: Manual trigger requested ({delay_seconds}s)")
        return self._schedule_shutdown(delay_seconds, reason=reason, trigger_type="manual")

    def cancel(self) -> None:
        """
        ยกเลิก shutdown ที่ scheduled ไว้ด้วยมือ (เช่น จากปุ่มใน Web UI)
        """
        if self._shutdown_pending:
            logger.info("Auto-shutdown: Manual cancel")
            self._cancel_shutdown()

    def is_pending(self) -> bool:
        """Return True ถ้ามี shutdown ที่ scheduled และยังไม่ได้เกิด"""
        return self._shutdown_pending

    def is_on_battery(self) -> bool:
        """Return True ถ้า UPS กำลังใช้แบตเตอรี่ (ไฟดับ)"""
        return self._on_battery

    def get_status(self) -> dict:
        """
        ดึงข้อมูลสถานะ Auto PC Shutdown ปัจจุบัน รวมทั้งเวลา remaining seconds สำหรับ countdown

        Returns:
            dict: {
                "pending": bool,
                "deadline_timestamp": float,
                "remaining_seconds": int,
                "total_seconds": int,
                "reason": str,
                "trigger_type": str,
                "enabled": bool,
            }
        """
        now = time.time()
        remaining = max(0, int(self._shutdown_deadline - now)) if self._shutdown_pending else 0
        return {
            "pending": self._shutdown_pending and remaining > 0,
            "deadline_timestamp": self._shutdown_deadline if self._shutdown_pending else 0.0,
            "remaining_seconds": remaining,
            "total_seconds": self._shutdown_total_delay,
            "reason": self._shutdown_reason if self._shutdown_pending else "",
            "trigger_type": self._shutdown_trigger_type if self._shutdown_pending else "",
            "enabled": self.enabled,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _schedule_shutdown(
        self,
        delay_seconds: int,
        reason: str = "UPS ไฟฟ้าดับ / แบตเตอรี่ต่ำ",
        trigger_type: str = "auto",
    ) -> bool:
        """
        ส่งคำสั่ง shutdown ไปยัง Windows

        Args:
            delay_seconds: วินาทีที่จะรอก่อนปิดเครื่อง
            reason:        ข้อความแสดงเหตุผล (แสดงใน Windows dialog)
            trigger_type:  ประเภทของการสั่ง shutdown ("ac_fail", "low_battery", "manual")
        """
        cmd = [
            "shutdown", "/s",
            "/t", str(delay_seconds),
            "/c", reason[:512],  # Windows จำกัดความยาว comment ที่ 512 ตัวอักษร
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,  # ไม่แสดง console window
            )
            if result.returncode == 0:
                self._shutdown_pending = True
                self._shutdown_total_delay = delay_seconds
                self._shutdown_deadline = time.time() + delay_seconds
                self._shutdown_reason = reason
                self._shutdown_trigger_type = trigger_type

                delay_min = delay_seconds // 60
                logger.info(f"Shutdown scheduled: {delay_seconds}s ({delay_min} min)")
                if self._on_shutdown_scheduled:
                    try:
                        self._on_shutdown_scheduled(delay_min)
                    except Exception as exc:
                        logger.error(f"Shutdown scheduled callback error: {exc}")
                return True
            else:
                logger.error(f"shutdown.exe failed (rc={result.returncode}): {result.stderr}")
                return False
        except FileNotFoundError:
            logger.error("shutdown.exe not found — auto-shutdown unavailable")
            return False
        except Exception as exc:
            logger.error(f"Failed to schedule shutdown: {exc}")
            return False

    def _cancel_shutdown(self) -> None:
        """ส่งคำสั่ง ``shutdown /a`` เพื่อยกเลิก"""
        try:
            result = subprocess.run(
                ["shutdown", "/a"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._shutdown_pending = False
            self._shutdown_deadline = 0.0
            self._shutdown_total_delay = 0
            self._shutdown_reason = ""
            self._shutdown_trigger_type = ""
            if result.returncode == 0:
                logger.info("Shutdown cancelled successfully")
                if self._on_shutdown_cancelled:
                    try:
                        self._on_shutdown_cancelled()
                    except Exception as exc:
                        logger.error(f"Shutdown cancelled callback error: {exc}")
            else:
                logger.debug(f"shutdown /a: rc={result.returncode} (may be no pending shutdown)")
        except Exception as exc:
            self._shutdown_pending = False
            self._shutdown_deadline = 0.0
            logger.error(f"Failed to cancel shutdown: {exc}")
