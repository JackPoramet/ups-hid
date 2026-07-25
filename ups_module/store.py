"""
ups_module/store.py
~~~~~~~~~~~~~~~~~~~
Thread-safe in-memory data store for the UPS poller.

Replaces the module-level ``_api_store`` / ``_api_lock`` globals
that were embedded in ``web_daemon.py``.

Usage::

    store = DataStore()
    store.update(device_info, ups_dict, "Connected")
    snapshot = store.get_snapshot()
    data: UPSData = store.get_ups_data()
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from .models import UPSData, ups_data_from_raw
from .serializer import sanitize_for_json


class DataStore:
    """
    Thread-safe store for the latest UPS poll result.

    All public methods acquire ``_lock`` before reading or writing,
    so they are safe to call from both the poller thread and Flask
    request handlers concurrently.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._device: Dict[str, Any] = {}
        self._ups: Dict[str, Any] = {}
        self._ups_raw: Dict[str, Any] = {}   # unmodified raw dict for UPSData
        self._timestamp: Optional[str] = None
        self._status_message: str = "Starting..."

    # -------------------------------------------------------------------------
    # Write methods (called from poller thread)
    # -------------------------------------------------------------------------

    def update(
        self,
        device_info: Dict[str, Any],
        ups_raw: Dict[str, Any],
        status_message: str = "Connected",
    ) -> None:
        """Store a successful poll result."""
        with self._lock:
            self._device = sanitize_for_json(device_info)
            self._ups = sanitize_for_json(ups_raw)
            self._ups_raw = dict(ups_raw)   # keep original for UPSData
            self._timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._status_message = status_message

    def set_error(self, message: str) -> None:
        """Mark the store as disconnected with an error message."""
        with self._lock:
            self._status_message = message
            self._timestamp = None

    # -------------------------------------------------------------------------
    # Read methods (called from Flask routes / UPSClient)
    # -------------------------------------------------------------------------

    def get_snapshot(self) -> Dict[str, Any]:
        """
        Return a thread-safe snapshot of the current store state.

        Returns a dict with keys: ``device``, ``ups``, ``timestamp``,
        ``status_message``, ``connected``.
        """
        with self._lock:
            return {
                "device": dict(self._device),
                "ups": dict(self._ups),
                "timestamp": self._timestamp,
                "status_message": self._status_message,
                "connected": self._timestamp is not None,
            }

    def get_ups_data(self) -> UPSData:
        """
        Return the latest poll result as a typed :class:`UPSData` instance.

        Returns an empty ``UPSData()`` when no data has been received yet.
        """
        with self._lock:
            raw = dict(self._ups_raw)
        if not raw:
            return UPSData()
        return ups_data_from_raw(raw)

    def get_device(self) -> Dict[str, Any]:
        """Return a copy of the sanitized device info dict."""
        with self._lock:
            return dict(self._device)

    def get_ups_dict(self) -> Dict[str, Any]:
        """Return a copy of the sanitized UPS data dict."""
        with self._lock:
            return dict(self._ups)

    @property
    def timestamp(self) -> Optional[str]:
        """ISO timestamp of the last successful poll, or None."""
        with self._lock:
            return self._timestamp

    @property
    def status_message(self) -> str:
        """Human-readable connection status."""
        with self._lock:
            return self._status_message

    @property
    def is_connected(self) -> bool:
        """True when the last poll succeeded."""
        with self._lock:
            return self._timestamp is not None
