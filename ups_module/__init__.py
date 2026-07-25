"""
ups_module/__init__.py
~~~~~~~~~~~~~~~~~~~~~~
UPS HID Python library — NUT-compatible Python API.

ไม่มี daemon, ไม่มี HTTP server.
Import แล้วใช้งานได้เลยแบบ library ทั่วไป

เปรียบเทียบกับ NUT / PyNUT
---------------------------
  NUT (network):         PyNUT.PyNUTClient(host='...')
  ups_module (HID):      ups_module.UPSClient()        ← ไม่ต้องมี upsd

Usage::

    from ups_module import UPSClient, NotifyType

    # --- แบบที่ 1: one-shot read ---
    with UPSClient() as client:
        print(client.get_status())                # "OL"
        print(client.get_var("battery.charge"))   # 95
        print(client.get_vars())                  # {"ups.status": "OL", ...}
        print(client.get_data().to_json())        # NUT JSON

    # --- แบบที่ 2: ค้างการเชื่อมต่อ ---
    client = UPSClient()
    client.connect()

    while True:
        vars = client.get_vars()
        print(vars["ups.status"])
        time.sleep(5)

    client.disconnect()

    # --- แบบที่ 3: event monitoring (upsmon-style) ---
    client = UPSClient()
    client.connect()

    @client.on(NotifyType.ONBATT)
    def power_failed(event):
        print("Power failure!", event.message)

    @client.on(NotifyType.ONLINE)
    def power_restored(event):
        print("Power restored.")

    @client.on(NotifyType.LOWBATT)
    def low_battery(event):
        print("Battery low — initiating shutdown!")

    client.start_monitor(interval=1.0)

    # ... โปรแกรมทำงานต่อไป ...

    client.stop_monitor()
    client.disconnect()
"""

from .client import UPSClient
from .models import NotifyType, UPSData, UPSEvent, ups_data_from_raw
from .store import DataStore
from .events import EventBus, EventDetector

__all__ = [
    # Primary interface
    "UPSClient",

    # Data model
    "UPSData",
    "UPSEvent",
    "NotifyType",
    "ups_data_from_raw",

    # Lower-level components (for advanced use)
    "DataStore",
    "EventBus",
    "EventDetector",
]

__version__ = "1.0.0"
__author__ = "CoE Team"
