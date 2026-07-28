# ups_module -- UPS HID Python Library

Pure Python library สำหรับสื่อสารกับ UPS ผ่าน USB HID (รองรับ NUT variable naming) โดยไม่ต้องติดตั้ง `upsd` daemon

---

## Quick Start & Installation

### ติดตั้งบน Linux (คำสั่งเดียว)

```bash
cd ups_module
chmod +x install.sh
./install.sh
```

> **หมายเหตุ (System Dependencies):** `install.sh` จะทำการติดตั้ง `pkg-config`, `build-essential`, `python3-dev`, `libhidapi-dev` และ `libusb-1.0-0-dev` ให้อัตโนมัติ (หากยังไม่ได้ติดตั้งแพ็กเกจ dev อาจเจอข้อผิดพลาด `Exception: pkg-config package 'libusb-1.0 >= 1.0.9' not found`)

### ติดตั้งแบบ Manual (กรณีไม่ใช้ install.sh)

```bash
sudo apt-get update
sudo apt-get install -y pkg-config build-essential python3-dev libhidapi-hidraw0 libhidapi-dev libusb-1.0-0-dev
pip install -r requirements.txt
sudo python3 linux_setup.py
```

### ทดสอบการใช้โมดูล

```bash
python3 demo.py
```

### การเรียกใช้งานใน Python

```python
from ups_module import UPSClient, NotifyType

# 1. อ่านค่าครั้งเดียว (เทียบ upsc)
with UPSClient() as client:
    print(client.get_status())               # "OL"
    print(client.get_var("battery.charge"))   # 100
    print(client.get_vars())                  # {"ups.status": "OL", ...}

# 2. ดักจับ Events (เทียบ upsmon)
client = UPSClient().connect()

@client.on(NotifyType.ONBATT)
def power_failed(event):
    print(f"ไฟดับ: {event.message}")

@client.on(NotifyType.ONLINE)
def power_restored(event):
    print("ไฟปกติ")

client.start_monitor(interval=1.0)
```

---

## API Reference

### `UPSClient`

| Method / Property | Return | คำอธิบาย |
|---|---|---|
| `connect()` | `UPSClient` | เปิดเชื่อมต่อ HID device |
| `disconnect()` | `None` | ปิดเชื่อมต่อ |
| `get_status()` | `str` | สถานะ UPS เช่น `"OL"`, `"OB"`, `"LB"` |
| `get_var(name)` | `Any` | อ่านตัวแปร NUT รายตัว |
| `get_vars()` | `dict` | อ่านตัวแปร NUT ทั้งหมด |
| `get_data()` | `UPSData` | ดึงวัตถุ `UPSData` (Typed Dataclass) |
| `get_device_info()` | `dict` | ดึงข้อมูล Manufacturer / Model / Serial |
| `start_monitor(interval)` | `None` | เริ่ม Background Event Monitoring Thread |
| `stop_monitor()` | `None` | หยุด Event Monitoring Thread |
| `@client.on(notify_type)` | Decorator | ลงทะเบียน Event Handler |

---

## NUT Variable Mapping

| NUT Variable Name | UPSData Field | คำอธิบาย |
|---|---|---|
| `ups.status` | `ups_status` | สถานะหลัก (`OL`, `OB`, `LB`, `CHRG`) |
| `battery.charge` | `battery_charge` | % แบตเตอรี่คงเหลือ (0-100) |
| `battery.runtime` | `battery_runtime` | เวลาสำรองไฟคงเหลือ (วินาที) |
| `battery.voltage` | `battery_voltage` | แรงดันแบตเตอรี่ (V) |
| `input.voltage` | `input_voltage` | แรงดันไฟเข้า (V) |
| `input.frequency` | `input_frequency` | ความถี่ไฟเข้า (Hz) |
| `output.voltage` | `output_voltage` | แรงดันไฟออก (V) |
| `output.frequency` | `output_frequency` | ความถี่ไฟออก (Hz) |
| `output.current` | `output_current` | กระแสไฟออก (A) |
| `output.power` | `output_power` | กำลังไฟออก (W) |
| `ups.load` | `ups_load` | ภาระโหลด (%) |
| `ups.temperature` | `ups_temperature` | อุณหภูมิเครื่อง (°C) |
| `ups.firmware` | `ups_firmware` | เวอร์ชัน Firmware |

---

## โครงสร้างไฟล์ใน `ups_module`

```
ups_module/
├── __init__.py         # Export Public API (UPSClient, UPSData, NotifyType)
├── client.py           # Class หลัก UPSClient
├── core.py             # Core Protocol Engine (HID Operations)
├── models.py           # UPSData, UPSEvent, NotifyType
├── events.py           # EventBus & EventDetector
├── store.py            # Thread-safe DataStore
├── serializer.py       # JSON Helper
├── poller.py           # Background Polling Thread
├── linux_setup.py      # udev rule & Linux dependency checker
├── windows_setup.py    # Windows filter driver installer
├── demo.py             # Cross-platform Demo (python3 demo.py)
├── install.sh          # Auto setup script สำหรับ Linux
└── requirements.txt    # Python dependencies
```
