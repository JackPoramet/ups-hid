"""
UPS Monitor — SQLite Database Manager
========================================
จัดการบันทึกประวัติค่าสถานะ (Telemetry) และประวัติเหตุการณ์สำคัญ (Event Logs)

Features:
    - WAL Mode (Write-Ahead Logging) เพื่อรองรับ Multi-threading อ่าน/เขียนลื่นไหล
    - บันทึกประวัติสถานะตามช่วงเวลา (Telemetry Metrics)
    - บันทึกประวัติเหตุการณ์ (AC Failure, Restore, Low Battery, System Shutdown ฯลฯ)
    - ระบบลบข้อมูลเก่าอัตโนมัติ (Data Pruning)
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_APP_DIR_NAME = "UPS-Monitor"


class DatabaseManager:
    """
    จัดการ SQLite Database สำหรับ UPS Monitor

    Attributes:
        db_path (Path): ตำแหน่งของไฟล์ sqlite3 (.db)
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            appdata = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
            db_path = Path(appdata) / _APP_DIR_NAME / "ups_monitor.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """สร้าง SQLite connection พร้อมตั้งค่า timeout และ row_factory"""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """สร้างตารางและเปิดใช้งาน WAL Mode"""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            # เปิดใช้งาน WAL (Write-Ahead Logging) และ Synchronous NORMAL
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")

            # 1. ตารางเก็บประวัติเหตุการณ์ (Event Logs)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ups_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    battery_level INTEGER,
                    ac_present INTEGER
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_ts ON ups_events(timestamp);"
            )

            # 2. ตารางเก็บประวัติสถานะ (Telemetry Metrics)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ups_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    ac_present INTEGER,
                    battery_charge INTEGER,
                    battery_runtime INTEGER,
                    input_voltage REAL,
                    output_voltage REAL,
                    output_load INTEGER
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON ups_telemetry(timestamp);"
            )

            conn.commit()
        logger.info(f"Database initialized at: {self.db_path}")

    # ── Logging Functions ──────────────────────────────────────────────────────

    def log_event(
        self,
        event_type: str,
        message: str,
        battery_level: Optional[int] = None,
        ac_present: Optional[bool] = None,
    ) -> None:
        """
        บันทึกเหตุการณ์สำคัญลง DB (เช่น AC_FAIL, AC_RESTORE, LOW_BATTERY)
        """
        now_str = datetime.now(timezone.utc).isoformat()
        ac_val = 1 if ac_present is True else (0 if ac_present is False else None)

        try:
            with self._lock, self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO ups_events (timestamp, event_type, message, battery_level, ac_present)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (now_str, event_type, message, battery_level, ac_val),
                )
                conn.commit()
            logger.debug(f"Logged DB event: {event_type} - {message}")
        except Exception as e:
            logger.error(f"Failed to log DB event: {e}")

    def log_telemetry(self, state: Dict[str, Any]) -> None:
        """
        บันทึกภาพรวมสถานะ UPS ลง DB
        """
        if not state:
            return

        now_str = datetime.now(timezone.utc).isoformat()
        ac_present_raw = state.get("ac_present")
        ac_val = 1 if ac_present_raw is True else (0 if ac_present_raw is False else None)

        charge = state.get("battery.charge")
        runtime = state.get("battery.runtime")
        in_v = state.get("input.voltage")
        out_v = state.get("output.voltage")
        load = state.get("output.load")

        try:
            with self._lock, self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO ups_telemetry (
                        timestamp, ac_present, battery_charge, battery_runtime,
                        input_voltage, output_voltage, output_load
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now_str,
                        ac_val,
                        int(charge) if charge is not None else None,
                        int(runtime) if runtime is not None else None,
                        float(in_v) if in_v is not None else None,
                        float(out_v) if out_v is not None else None,
                        int(load) if load is not None else None,
                    ),
                )
                conn.commit()
            logger.debug("Logged DB telemetry snapshot")
        except Exception as e:
            logger.error(f"Failed to log DB telemetry: {e}")

    # ── Query Functions ────────────────────────────────────────────────────────

    def get_telemetry_history(self, hours: float = 24.0) -> List[Dict[str, Any]]:
        """
        ดึงข้อมูล Telemetry ย้อนหลังตามจำนวนชั่วโมงที่กำหนด
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        results: List[Dict[str, Any]] = []

        try:
            with self._lock, self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT timestamp, ac_present, battery_charge, battery_runtime,
                           input_voltage, output_voltage, output_load
                    FROM ups_telemetry
                    WHERE timestamp >= ?
                    ORDER BY id ASC
                    """,
                    (cutoff,),
                )
                rows = cursor.fetchall()
                for r in rows:
                    results.append(
                        {
                            "timestamp": r["timestamp"],
                            "ac_present": bool(r["ac_present"]) if r["ac_present"] is not None else None,
                            "battery_charge": r["battery_charge"],
                            "battery_runtime": r["battery_runtime"],
                            "input_voltage": r["input_voltage"],
                            "output_voltage": r["output_voltage"],
                            "output_load": r["output_load"],
                        }
                    )
        except Exception as e:
            logger.error(f"Failed to fetch telemetry history: {e}")

        return results

    def get_events_history(self, limit: int = 100, page: int = 1) -> List[Dict[str, Any]]:
        """
        ดึงรายการ Log เหตุการณ์ย้อนหลัง (รองรับ Pagination)
        """
        offset = max(0, (page - 1) * limit)
        results: List[Dict[str, Any]] = []

        try:
            with self._lock, self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, timestamp, event_type, message, battery_level, ac_present
                    FROM ups_events
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
                rows = cursor.fetchall()
                for r in rows:
                    results.append(
                        {
                            "id": r["id"],
                            "timestamp": r["timestamp"],
                            "event_type": r["event_type"],
                            "message": r["message"],
                            "battery_level": r["battery_level"],
                            "ac_present": bool(r["ac_present"]) if r["ac_present"] is not None else None,
                        }
                    )
        except Exception as e:
            logger.error(f"Failed to fetch events history: {e}")

        return results

    def prune_old_data(self, retention_days: int = 30) -> int:
        """
        ลบข้อมูล Telemetry และ Events ที่เก่าเกิน retention_days วัน
        Returns: จำนวนแถวที่ถูกลบไป
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        deleted_count = 0

        try:
            with self._lock, self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM ups_telemetry WHERE timestamp < ?;", (cutoff,))
                del1 = cursor.rowcount
                cursor.execute("DELETE FROM ups_events WHERE timestamp < ?;", (cutoff,))
                del2 = cursor.rowcount
                conn.commit()
                deleted_count = max(0, del1) + max(0, del2)

            if deleted_count > 0:
                logger.info(f"Pruned {deleted_count} DB records older than {retention_days} days")
        except Exception as e:
            logger.error(f"Failed to prune DB data: {e}")

        return deleted_count

    def clear_all(self) -> None:
        """ล้างข้อมูลทั้งหมดใน DB (ใช้เมื่อต้องการ reset ข้อมูล)"""
        try:
            with self._lock, self._get_connection() as conn:
                conn.execute("DELETE FROM ups_telemetry;")
                conn.execute("DELETE FROM ups_events;")
                conn.commit()
            logger.info("Cleared all records in SQLite database")
        except Exception as e:
            logger.error(f"Failed to clear DB: {e}")
