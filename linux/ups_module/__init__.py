"""
ups_module — Pure Python HID-UPS client library (NUT-compatible API)
"""

from .client import UPSClient
from .device_registry import DeviceProfile, DeviceRegistry
from .models import NotifyType, UPSData, UPSEvent, ups_data_from_raw
from .store import DataStore
from .events import EventBus, EventDetector

__all__ = [
    "UPSClient",
    "UPSData",
    "UPSEvent",
    "NotifyType",
    "ups_data_from_raw",
    "DataStore",
    "EventBus",
    "EventDetector",
    "DeviceProfile",
    "DeviceRegistry",
]

__version__ = "1.1.0"

