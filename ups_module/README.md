# ups_module — UPS HID Python Library

Pure Python library สำหรับสื่อสาร UPS ผ่าน USB HID โดยตรง  
ใช้ key naming แบบ **NUT (Network UPS Tools)** — ไม่ต้องรัน daemon ใดๆ

## ติดตั้ง

```bash
pip install hidapi
```

> `ups_module` เป็น local package — copy โฟลเดอร์ `ups_module/` ไปวางข้างๆ `core_hid_ups.py` ใน project ได้เลย

---

## Quick Start

```python
from ups_module import UPSClient

with UPSClient() as client:
    print(client.get_status())                # "OL"
    print(client.get_var("battery.charge"))   # 95
    print(client.get_vars())                  # {"ups.status": "OL", "battery.charge": 95, ...}
```

---

## รูปแบบการใช้งาน

### 1. One-shot read (เปิด → อ่าน → ปิด)

```python
from ups_module import UPSClient

with UPSClient() as client:
    data = client.get_data()
    print(data.ups_status)         # "OL"
    print(data.battery_charge)     # 95
    print(data.input_voltage)      # 220.5
    print(data.to_json())          # NUT JSON string
```

### 2. Persistent connection (ค้างเชื่อมต่อ + poll ด้วยตัวเอง)

```python
import time
from ups_module import UPSClient

client = UPSClient().connect()
try:
    while True:
        vars = client.get_vars()
        print(f"Status: {vars['ups.status']}  Battery: {vars.get('battery.charge')}%")
        time.sleep(5)
finally:
    client.disconnect()
```

### 3. Event monitoring (upsmon-style)

```python
from ups_module import UPSClient, NotifyType

client = UPSClient().connect()

@client.on(NotifyType.ONBATT)
def power_failed(event):
    print(f"ไฟดับ! {event.message}")

@client.on(NotifyType.ONLINE)
def power_restored(event):
    print("ไฟกลับมาแล้ว")

@client.on(NotifyType.LOWBATT)
def low_battery(event):
    print("แบตเตอรี่ต่ำ — กำลังสั่ง shutdown!")

client.start_monitor(interval=1.0)

# ... โปรแกรมทำงานต่อ ...

client.stop_monitor()
client.disconnect()
```

---

## API Reference

### `UPSClient`

```python
UPSClient(vid=0x06DA, pid=0xFFFF, name="ups@local")
```

| Parameter | Type | Default | คำอธิบาย |
|-----------|------|---------|----------|
| `vid` | `int` | `0x06DA` | USB Vendor ID |
| `pid` | `int` | `0xFFFF` | USB Product ID |
| `name` | `str` | `"ups@local"` | ชื่อ UPS (เหมือน `<upsname>` ใน NUT) |

#### Connection

| Method | Return | คำอธิบาย |
|--------|--------|----------|
| `connect()` | `UPSClient` | เปิด HID device (chainable) |
| `disconnect()` | `None` | ปิด device + หยุด monitor |
| `is_connected` | `bool` | property — สถานะการเชื่อมต่อ |

รองรับ context manager: `with UPSClient() as client:`

#### Data Read (Synchronous)

ทุก method อ่านจาก HID device โดยตรง — ไม่มี cache

| Method | Return | เทียบ NUT | คำอธิบาย |
|--------|--------|-----------|----------|
| `get_status()` | `str` | `upsc ups@local ups.status` | NUT status string |
| `get_var(name)` | `Any` | `upsc ups@local <name>` | ค่าตัวแปรเดียว |
| `get_vars()` | `dict` | `upsc ups@local` | dict ทุกตัวแปร |
| `get_data()` | `UPSData` | — | typed object พร้อม helper methods |
| `get_device_info()` | `dict` | `upsc -l` | ข้อมูล manufacturer/model/serial |

#### Control Commands

ทุก method return `tuple[bool, str]` → `(success, message)`

| Method | คำอธิบาย |
|--------|----------|
| `run_self_test()` | สั่งทดสอบแบตเตอรี่ |
| `abort_self_test()` | ยกเลิก self-test |
| `schedule_shutdown(delay_seconds)` | ตั้งเวลาปิดเอาต์พุต |
| `cancel_shutdown()` | ยกเลิกคำสั่ง shutdown |
| `schedule_startup(delay_seconds)` | ตั้งเวลาเปิดเอาต์พุต |
| `sync_time()` | ตั้งนาฬิกา UPS ตาม system time |
| `set_voltage(voltage)` | ตั้งแรงดันอ้างอิง (220/230) |
| `set_frequency(freq_hz)` | ตั้งความถี่ (50/60 Hz) |
| `set_runtime_limit(minutes)` | ตั้ง runtime threshold |

#### Event Monitor (Optional)

| Method | คำอธิบาย |
|--------|----------|
| `start_monitor(interval=1.0)` | เริ่ม background polling + event detection |
| `stop_monitor()` | หยุด monitor thread |
| `on(notify_type)` | decorator ลงทะเบียน event handler |
| `subscribe(handler, notify_type=None)` | ลงทะเบียน handler แบบ function call |
| `unsubscribe(handler)` | ถอน handler |

---

### `UPSData`

Typed dataclass สำหรับข้อมูล UPS — ได้จาก `client.get_data()`

#### Properties

| Field | Type | NUT Key | คำอธิบาย |
|-------|------|---------|----------|
| `ups_status` | `str` | `ups.status` | `"OL"`, `"OB"`, `"OB LB"`, `"OL CHRG"` |
| `battery_charge` | `float` | `battery.charge` | เปอร์เซ็นต์แบต (0–100) |
| `battery_runtime` | `int` | `battery.runtime` | เวลาสำรองเหลือ (วินาที) |
| `battery_voltage` | `float` | `battery.voltage` | แรงดันแบตเตอรี่ (V) |
| `input_voltage` | `float` | `input.voltage` | แรงดันไฟเข้า (V) |
| `input_frequency` | `float` | `input.frequency` | ความถี่ไฟเข้า (Hz) |
| `output_voltage` | `float` | `output.voltage` | แรงดันไฟออก (V) |
| `output_frequency` | `float` | `output.frequency` | ความถี่ไฟออก (Hz) |
| `output_current` | `float` | `output.current` | กระแสไฟออก (A) |
| `output_power` | `int` | `output.power` | กำลังไฟ (W) |
| `ups_load` | `float` | `ups.load` | โหลด (%) |
| `ups_temperature` | `float` | `ups.temperature` | อุณหภูมิ (°C) |
| `ups_firmware` | `str` | `ups.firmware` | เวอร์ชัน firmware |

ดู field เพิ่มเติมใน `models.py` — fields ทั้งหมดเป็น `Optional`

#### Helper Methods

| Method | Return | คำอธิบาย |
|--------|--------|----------|
| `to_nut_dict()` | `dict` | NUT-style dict (เฉพาะ non-None) |
| `to_full_dict()` | `dict` | dict ทุก field (รวม None + flags) |
| `to_json(indent=2)` | `str` | JSON string ของ NUT dict |
| `is_online()` | `bool` | ไฟปกติ? |
| `is_on_battery()` | `bool` | ทำงานบนแบต? |
| `is_low_battery()` | `bool` | แบตเตอรี่ต่ำ? |
| `is_charging()` | `bool` | กำลังชาร์จ? |

---

### `NotifyType` — Event Types

| Constant | Trigger | เทียบ NUT upsmon |
|----------|---------|-----------------|
| `ONLINE` | ไฟกลับมา (OB → OL) | `NOTIFYMSG ONLINE` |
| `ONBATT` | ไฟดับ (OL → OB) | `NOTIFYMSG ONBATT` |
| `LOWBATT` | แบตต่ำ | `NOTIFYMSG LOWBATT` |
| `FSD` | Forced shutdown | `NOTIFYMSG FSD` |
| `COMMOK` | เชื่อมต่อ device สำเร็จ | `NOTIFYMSG COMMOK` |
| `COMMBAD` | การเชื่อมต่อหลุด | `NOTIFYMSG COMMBAD` |
| `REPLBATT` | ต้องเปลี่ยนแบตเตอรี่ | `NOTIFYMSG REPLBATT` |
| `CHARGING` | กำลังชาร์จ | extension |
| `OVERLOAD` | โหลดเกิน | extension |
| `OVER_TEMP` | อุณหภูมิสูงเกิน | extension |

### `UPSEvent`

Object ที่ส่งมากับทุก event handler:

```python
@client.on(NotifyType.ONBATT)
def handler(event: UPSEvent):
    event.notify_type   # "ONBATT"
    event.message       # "UPS is on battery power."
    event.timestamp     # "2026-07-16T21:00:00"
    event.data          # UPSData snapshot ณ เวลาที่เกิด event
    event.to_dict()     # {"event": "ONBATT", "message": "...", "timestamp": "..."}
```

---

## NUT Status String Reference

| Status | ความหมาย |
|--------|----------|
| `OL` | On Line — ไฟปกติ |
| `OB` | On Battery — ทำงานบนแบตเตอรี่ |
| `LB` | Low Battery |
| `CHRG` | Charging |
| `DISCHRG` | Discharging |
| `OVER` | Overloaded |

รวมกันได้: `"OL CHRG"`, `"OB DISCHRG LB"`, `"OB LB OVER"`

---

## โครงสร้าง Module

```
ups_module/
├── __init__.py       # Public API: UPSClient, UPSData, NotifyType
├── client.py         # UPSClient — interface หลัก
├── models.py         # UPSData dataclass, UPSEvent, NotifyType
├── events.py         # EventBus + EventDetector
├── store.py          # Thread-safe DataStore (ใช้ภายใน)
├── serializer.py     # JSON sanitizer
├── poller.py         # UPSPoller thread (ใช้ภายใน)
└── tests/
    └── test_models.py
```

**Dependency:** ต้องมี `core_hid_ups.py` + `hidapi` อยู่ใน path เดียวกัน

---

## ตัวอย่างผสมกับระบบอื่น

### ส่ง alert ผ่าน LINE / Slack เมื่อไฟดับ

```python
import requests
from ups_module import UPSClient, NotifyType

client = UPSClient().connect()

@client.on(NotifyType.ONBATT)
def alert_power_fail(event):
    requests.post("https://notify-api.line.me/api/notify",
        headers={"Authorization": "Bearer <TOKEN>"},
        data={"message": f"⚡ UPS: {event.message}"})

client.start_monitor()
```

### Log ข้อมูล UPS ลง database ทุก 30 วินาที

```python
import time, sqlite3
from ups_module import UPSClient

client = UPSClient().connect()
db = sqlite3.connect("ups_log.db")
db.execute("CREATE TABLE IF NOT EXISTS log (ts TEXT, status TEXT, charge REAL, voltage REAL)")

while True:
    d = client.get_data()
    db.execute("INSERT INTO log VALUES (?, ?, ?, ?)",
        (time.strftime("%Y-%m-%d %H:%M:%S"), d.ups_status, d.battery_charge, d.input_voltage))
    db.commit()
    time.sleep(30)
```

### ตรวจสอบ UPS ก่อนสั่ง shutdown server

```python
from ups_module import UPSClient

with UPSClient() as client:
    if client.get_data().is_on_battery() and client.get_data().battery_charge < 20:
        print("Battery critical — initiating shutdown")
        client.schedule_shutdown(delay_seconds=60)
```
