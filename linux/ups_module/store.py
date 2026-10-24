"""
Thread-safe in-memory data store for UPS poll results.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from .models import UPSData, ups_data_from_raw
from .serializer import sanitize_for_json


class DataStore:
    """Thread-safe store for the latest UPS poll result."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._device: Dict[str, Any] = {}
        self._ups: Dict[str, Any] = {}
        self._ups_raw: Dict[str, Any] = {}
        self._timestamp: Optional[str] = None
        self._status_message: str = "Starting..."

    def update(
        self,
        device_info: Dict[str, Any],
        ups_raw: Dict[str, Any],
        status_message: str = "Connected",
    ) -> None:
        with self._lock:
            self._device = sanitize_for_json(device_info)
            self._ups = sanitize_for_json(ups_raw)
            self._ups_raw = dict(ups_raw)
            self._timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._status_message = status_message

    def set_error(self, message: str) -> None:
        with self._lock:
            self._status_message = message
            self._timestamp = None

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "device": dict(self._device),
                "ups": dict(self._ups),
                "timestamp": self._timestamp,
                "status_message": self._status_message,
                "connected": self._timestamp is not None,
            }

    def get_ups_data(self) -> UPSData:
        with self._lock:
            raw = dict(self._ups_raw)
        return ups_data_from_raw(raw) if raw else UPSData()

    def get_device(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._device)

    def get_ups_dict(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._ups)

    @property
    def timestamp(self) -> Optional[str]:
        with self._lock:
            return self._timestamp

    @property
    def status_message(self) -> str:
        with self._lock:
            return self._status_message

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._timestamp is not None
