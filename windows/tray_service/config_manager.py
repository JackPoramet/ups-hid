"""
UPS Monitor — Configuration Manager
=====================================
จัดการการตั้งค่าของแอปพลิเคชันทั้งหมด บันทึกลงไฟล์ JSON ใน AppData

Location:
    %APPDATA%\\UPS-Monitor\\config.json

Default Config:
    - port: 48655               — Port ของ Flask Web Server
    - poll_interval_s: 1        — ความถี่การอ่านค่า UPS (วินาที)
    - auto_shutdown_enabled: False
    - shutdown_delay_minutes: 5 — นับถอยหลังก่อนปิด PC (หลังไฟดับ)
    - shutdown_battery_threshold: 20  — ปิด PC เมื่อแบตเหลือน้อยกว่า X%
    - notifications_enabled: True
    - start_minimized: True     — เริ่มต้นเป็น tray (ไม่เปิด browser)
    - auto_start_monitoring: True
    - startup_with_windows: False — ลงทะเบียน Windows startup

Usage:
    >>> from tray_service.config_manager import ConfigManager
    >>> cfg = ConfigManager()
    >>> print(cfg.get("port"))
    48655
    >>> cfg.set("auto_shutdown_enabled", True)
    >>> cfg.save()
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Default configuration values ─────────────────────────────────────────────
DEFAULT_CONFIG: dict[str, Any] = {
    "port": 48655,
    "poll_interval_s": 1,
    "auto_shutdown_enabled": False,
    "shutdown_delay_minutes": 5,
    "shutdown_battery_threshold": 20,
    "notifications_enabled": True,
    "notify_on_ac_fail": True,
    "notify_on_ac_restore": True,
    "notify_on_low_battery": True,
    "start_minimized": True,
    "auto_start_monitoring": True,
    "startup_with_windows": False,
    "vid": 0x06DA,
    "pid": 0xFFFF,
    "log_level": "INFO",
    "db_enabled": True,
    "db_telemetry_interval_s": 10,
    "db_retention_days": 30,
}

_APP_DIR_NAME = "UPS-Monitor"


class ConfigManager:
    """
    จัดการ config ของ UPS Monitor ทั้งหมด

    อ่านจาก/เขียนไปยัง JSON file ใน %APPDATA%\\UPS-Monitor\\config.json
    ถ้าไม่มีไฟล์ จะสร้างใหม่ด้วยค่า default อัตโนมัติ

    Attributes:
        config_path (Path): Path ไปยัง config file
        _data (dict): ข้อมูล config ใน memory

    Example:
        >>> cfg = ConfigManager()
        >>> cfg.get("port")
        48655
        >>> cfg.set("shutdown_delay_minutes", 10)
        >>> cfg.save()
    """

    def __init__(self, config_path: Path | None = None) -> None:
        """
        สร้าง ConfigManager instance

        Args:
            config_path: Path ไปยัง config file (ถ้า None จะใช้ default AppData path)
        """
        if config_path is None:
            appdata = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
            config_path = Path(appdata) / _APP_DIR_NAME / "config.json"

        self.config_path = config_path
        self._data: dict[str, Any] = {}
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """
        อ่านค่า config

        Args:
            key:     ชื่อ key ที่ต้องการ
            default: ค่าที่จะ return ถ้าไม่พบ key (ถ้า None จะดึงจาก DEFAULT_CONFIG)

        Returns:
            ค่า config ที่ต้องการ
        """
        if default is None:
            default = DEFAULT_CONFIG.get(key)
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        ตั้งค่า config (ใน memory เท่านั้น ต้องเรียก save() เพื่อบันทึกลงไฟล์)

        Args:
            key:   ชื่อ key
            value: ค่าใหม่
        """
        self._data[key] = value

    def update(self, data: dict[str, Any]) -> None:
        """
        อัปเดตหลาย key พร้อมกัน (ใน memory เท่านั้น)

        Args:
            data: dict ของ {key: value} ที่ต้องการอัปเดต
        """
        self._data.update(data)

    def save(self) -> bool:
        """
        บันทึก config ลงไฟล์ JSON

        Returns:
            True ถ้าบันทึกสำเร็จ, False ถ้า error

        Raises:
            ไม่ raise — บันทึก error log แทน
        """
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Config saved → {self.config_path}")
            return True
        except Exception as exc:
            logger.error(f"Failed to save config: {exc}")
            return False

    def as_dict(self) -> dict[str, Any]:
        """
        Return config ทั้งหมดเป็น dict (copy)

        Returns:
            dict ของ config ปัจจุบัน
        """
        return dict(self._data)

    def reset_to_defaults(self) -> None:
        """
        Reset config ทั้งหมดกลับเป็นค่า default แล้วบันทึก
        """
        self._data = dict(DEFAULT_CONFIG)
        self.save()
        logger.info("Config reset to defaults")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """โหลด config จากไฟล์ ถ้าไม่มีหรือ error จะใช้ DEFAULT_CONFIG"""
        self._data = dict(DEFAULT_CONFIG)  # เริ่มต้นด้วย default เสมอ

        if not self.config_path.exists():
            logger.info(f"Config file not found — creating defaults at {self.config_path}")
            self.save()
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            # Merge: ใช้ค่าจาก file เป็นหลัก แต่ถ้ามี key ใหม่ใน DEFAULT ให้เติมลงไปด้วย
            for key, default_val in DEFAULT_CONFIG.items():
                if key not in loaded:
                    loaded[key] = default_val

            self._data = loaded
            logger.debug(f"Config loaded from {self.config_path}")

        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Failed to load config ({exc}) — using defaults")
            self._data = dict(DEFAULT_CONFIG)
