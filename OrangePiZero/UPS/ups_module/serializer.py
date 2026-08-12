"""
JSON serialization helpers for raw HID data.
"""

from __future__ import annotations

import json
from typing import Any, Dict


def sanitize_for_json(d: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively convert raw UPS dict values to JSON-serializable types."""
    return {k: _sanitize_value(v) for k, v in d.items()}


def _sanitize_value(v: Any) -> Any:
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", errors="ignore")
    if isinstance(v, (int, float, str, bool, type(None))):
        return v
    if isinstance(v, list):
        return [_sanitize_value(x) for x in v]
    if isinstance(v, dict):
        return sanitize_for_json(v)
    return str(v)


def build_response_envelope(
    device: Dict[str, Any],
    ups: Dict[str, Any],
    status_message: str,
    timestamp: str | None,
    driver_name: str = "ups-hid",
    driver_version: str = "1.0.0",
) -> Dict[str, Any]:
    """Build the standard NUT-style JSON response envelope."""
    mfr = device.get("manufacturer_string") or device.get("manufacturer", "")
    model = device.get("product_string") or device.get("model", "")
    serial = device.get("serial_number") or device.get("serial", "")

    return {
        "driver": {
            "name": driver_name,
            "version": driver_version,
        },
        "device": {
            "manufacturer": mfr,
            "model": model,
            "serial": serial,
            "type": "ups",
        },
        "ups": ups,
        "meta": {
            "timestamp": timestamp,
            "connected": timestamp is not None,
            "status_message": status_message,
        },
    }


def to_json_string(data: Dict[str, Any], indent: int = 2) -> str:
    """Serialize data dict to JSON string."""
    return json.dumps(data, ensure_ascii=False, indent=indent, default=str)
