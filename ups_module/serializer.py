"""
ups_module/serializer.py
~~~~~~~~~~~~~~~~~~~~~~~~
JSON serialization helpers.

Converts raw HID data (which may contain bytes/bytearrays) to
JSON-safe Python types.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict


def sanitize_for_json(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively convert a dict of raw UPS values to JSON-serializable types.

    - bytes/bytearray   -> utf-8 decoded string
    - int/float/str/bool/None -> unchanged
    - list              -> sanitized element-by-element
    - anything else     -> str(value)
    """
    out: Dict[str, Any] = {}
    for k, v in d.items():
        out[k] = _sanitize_value(v)
    return out


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
    """
    Build the full NUT-style JSON response envelope used by the REST API.

    Structure::

        {
          "driver":  { "name": "ups-hid", "version": "1.0.0" },
          "device":  { "manufacturer": ..., "model": ..., ... },
          "ups":     { "ups.status": "OL", "battery.charge": 95, ... },
          "meta":    { "timestamp": ..., "connected": true, "message": ... }
        }
    """
    manufacturer = device.get("manufacturer_string", "")
    model = device.get("product_string", "")
    serial = device.get("serial_number", "")

    return {
        "driver": {
            "name": driver_name,
            "version": driver_version,
        },
        "device": {
            "manufacturer": manufacturer,
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
    """Serialize *data* to a JSON string, handling non-serializable types."""
    return json.dumps(data, ensure_ascii=False, indent=indent, default=str)
