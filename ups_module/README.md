# ups_module -- UPS HID Python Library

## สารบัญ

- [ภาพรวม](#ภาพรวม)
- [ความเข้ากันได้](#ความเขากันได)
- [การติดตั้ง](#การติดตั้ง)
- [ตั้งค่า Linux (ARM / RPi4)](#ตั้งค่า-linux-arm--rpi4)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [NUT Variable Mapping](#nut-variable-mapping)
- [ระบบ Event (upsmon-style)](#ระบบ-event-upsmon-style)
- [โครงสร้าง Module](#โครงสร้าง-module)
- [Migration จาก NUT/PyNUT](#migration-จาก-nutpynut)
- [Troubleshooting](#troubleshooting)
- [ตัวอย่างการใช้งาน](#ตัวอย่างการใช้งาน)

---

## ภาพรวม

`ups_module` เป็น Python library ที่อ่านข้อมูล UPS ผ่าน USB HID interface โดยตรง
ออกแบบมาเพื่อใช้แทน NUT daemon (`upsd` / `usbhid-ups`) ในสถานการณ์ที่:

- ต้องการ **embedded solution** บน SBC (เช่น Raspberry Pi, Orange Pi) โดยไม่ต้องติดตั้ง NUT ทั้งระบบ
- ต้องการ **Python-native API** ที่ import แล้วใช้งานได้ทันที
- ต้องการ **real-time event monitoring** พร้อม callback function

### Python

- Python 3.9 ขึ้นไป

---

## การติดตั้ง

### วิธีที่ 1: pip install (แนะนำ)

```bash
pip install ups-hid
```

หรือติดตั้งจาก source:

```bash
cd /path/to/UPS
pip install .
```

ติดตั้งพร้อม pyusb (สำหรับอ่าน input voltage ผ่าน USB control transfer):

```bash
pip install "ups-hid[all]"
```

### วิธีที่ 2: Copy โฟลเดอร์

คัดลอกโฟลเดอร์ `ups_module/` ไปวางใน project ของคุณ:

```bash
cp -r ups_module/ /path/to/your/project/
```

ติดตั้ง dependencies:

```bash
pip install hidapi pyusb
```

### System Dependencies (Linux เท่านั้น)

```bash
sudo apt update
sudo apt install -y libhidapi-hidraw0 libhidapi-dev libusb-1.0-0
```

---

## ตั้งค่า Linux (ARM / RPi4)

บน Linux ต้องตั้งค่าเพิ่มเติม 2 อย่าง:

### 1. udev Rule (สิทธิ์การเข้าถึง USB device)

ปกติ Linux จะจำกัดสิทธิ์ `/dev/hidraw*` ให้เฉพาะ root
ต้องสร้าง udev rule เพื่อให้ user ทั่วไปเข้าถึงได้:

**วิธี A: ใช้สคริปต์อัตโนมัติ (แนะนำ)**

```bash
sudo python -m ups_module.linux_setup
```

**วิธี B: สร้างเอง**

```bash
sudo nano /etc/udev/rules.d/99-ups-hid.rules
```

ใส่เนื้อหา:

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="06da", ATTRS{idProduct}=="ffff", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="06da", ATTRS{idProduct}=="ffff", MODE="0666"
```

Reload:

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 2. ตรวจสอบระบบ

```bash
python -m ups_module.linux_setup --check
```

หรือตรวจสอบด้วย demo script:

```bash
python -m ups_module.demo --check
```

### สรุปขั้นตอนติดตั้งบน RPi4 / Linux

**วิธีอัตโนมัติด้วย Auto-Installer Script (แนะนำ):**

```bash
cd ups_module
chmod +x install.sh
./install.sh
```

**หรือวิธีด้วยตัวเอง (Manual):**

```bash
# 1. ติดตั้ง system dependencies
sudo apt update
sudo apt install -y libhidapi-hidraw0 libhidapi-dev libusb-1.0-0

# 2. ติดตั้ง Python dependencies
pip install -r requirements.txt

# 3. ตั้งค่า udev rule
sudo env "PATH=$PATH" python3 linux_setup.py

# 4. ถอด USB แล้วเสียบใหม่ (หรือ reload udev)
sudo udevadm control --reload-rules && sudo udevadm trigger

# 5. ทดสอบ
python3 demo.py --check
python3 demo.py
```

---

## Quick Start

### อ่านค่าครั้งเดียว (เทียบ `upsc ups@local`)

```python
from ups_module import UPSClient

with UPSClient() as client:
    print(client.get_status())                # "OL"
    print(client.get_var("battery.charge"))    # 95
    print(client.get_vars())                   # {"ups.status": "OL", ...}
```

### อ่านค่าต่อเนื่อง (เทียบ `upsmon` polling)

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

### Event monitoring (เทียบ `upsmon NOTIFYCMD`)

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
    print("แบตเตอรี่ต่ำ!")

client.start_monitor(interval=1.0)

# ... โปรแกรมทำงานต่อ ...

client.stop_monitor()
client.disconnect()
```

---

## API Reference

### UPSClient

```python
UPSClient(vid=0x06DA, pid=0xFFFF, name="ups@local")
```

| Parameter | Type | Default | คำอธิบาย |
|-----------|------|---------|----------|
| `vid` | `int` | `0x06DA` | USB Vendor ID |
| `pid` | `int` | `0xFFFF` | USB Product ID |
| `name` | `str` | `"ups@local"` | ชื่อ UPS (เทียบ `<upsname>` ใน NUT) |

#### Connection

| Method | Return | คำอธิบาย |
|--------|--------|----------|
| `connect()` | `UPSClient` | เปิด HID device (chainable) |
| `disconnect()` | `None` | ปิด device + หยุด monitor |
| `is_connected` | `bool` | property -- สถานะการเชื่อมต่อ |

รองรับ context manager: `with UPSClient() as client:`

#### Data Read (Synchronous)

ทุก method อ่านจาก HID device โดยตรง -- ไม่มี cache

| Method | Return | เทียบ NUT | คำอธิบาย |
|--------|--------|-----------|----------|
| `get_status()` | `str` | `upsc ups@local ups.status` | NUT status string |
| `get_var(name)` | `Any` | `upsc ups@local <name>` | ค่าตัวแปรเดียว |
| `get_vars()` | `dict` | `upsc ups@local` | dict ทุกตัวแปร |
| `get_data()` | `UPSData` | -- | typed object พร้อม helper methods |
| `get_device_info()` | `dict` | `upsc -l` | ข้อมูล manufacturer/model/serial |

#### Control Commands

ทุก method return `tuple[bool, str]` (success, message)

| Method | คำอธิบาย |
|--------|----------|
| `run_self_test()` | สั่งทดสอบแบตเตอรี่ |
| `abort_self_test()` | ยกเลิก self-test |
| `schedule_shutdown(delay_seconds)` | ตั้งเวลาปิด output |
| `cancel_shutdown()` | ยกเลิกคำสั่ง shutdown |
| `schedule_startup(delay_seconds)` | ตั้งเวลาเปิด output |
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

### UPSData

Typed dataclass สำหรับข้อมูล UPS -- ได้จาก `client.get_data()`

#### Properties

| Field | Type | NUT Key | คำอธิบาย |
|-------|------|---------|----------|
| `ups_status` | `str` | `ups.status` | `"OL"`, `"OB"`, `"OB LB"`, `"OL CHRG"` |
| `battery_charge` | `float` | `battery.charge` | เปอร์เซ็นต์แบต (0-100) |
| `battery_runtime` | `int` | `battery.runtime` | เวลาสำรองเหลือ (วินาที) |
| `battery_voltage` | `float` | `battery.voltage` | แรงดันแบตเตอรี่ (V) |
| `input_voltage` | `float` | `input.voltage` | แรงดันไฟเข้า (V) |
| `input_frequency` | `float` | `input.frequency` | ความถี่ไฟเข้า (Hz) |
| `output_voltage` | `float` | `output.voltage` | แรงดันไฟออก (V) |
| `output_frequency` | `float` | `output.frequency` | ความถี่ไฟออก (Hz) |
| `output_current` | `float` | `output.current` | กระแสไฟออก (A) |
| `output_power` | `int` | `output.power` | กำลังไฟ (W) |
| `ups_load` | `float` | `ups.load` | โหลด (%) |
| `ups_temperature` | `float` | `ups.temperature` | อุณหภูมิ (C) |
| `ups_firmware` | `str` | `ups.firmware` | เวอร์ชัน firmware |

ดู field เพิ่มเติมใน `models.py` -- fields ทั้งหมดเป็น `Optional`

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

## NUT Variable Mapping

ตาราง mapping ระหว่าง NUT variable names กับ `UPSData` fields:

| NUT Variable | UPSData Field | HID Report | คำอธิบาย |
|-------------|--------------|------------|----------|
| `ups.status` | `ups_status` | 0x01, 0x42 | สถานะ: OL, OB, LB, CHRG |
| `battery.charge` | `battery_charge` | 0x06 | เปอร์เซ็นต์แบต |
| `battery.runtime` | `battery_runtime` | 0x06 | เวลาสำรอง (วินาที) |
| `battery.voltage` | `battery_voltage` | 0x07 | แรงดันแบต (V) |
| `battery.charge.low` | `battery_charge_low` | 0x0C | threshold ต่ำ (%) |
| `battery.charge.high` | `battery_charge_high` | 0x0C | threshold สูง (%) |
| `battery.test.status` | `battery_test_status` | 0x24 | ผล self-test |
| `input.voltage` | `input_voltage` | 0x31 | แรงดันไฟเข้า (V) |
| `input.frequency` | `input_frequency` | 0x0D, 0x31 | ความถี่ไฟเข้า (Hz) |
| `input.voltage.nominal` | `input_voltage_nominal` | 0x14 | แรงดัน nominal (V) |
| `input.frequency.nominal` | `input_frequency_nominal` | 0x14 | ความถี่ nominal (Hz) |
| `input.transfer.low` | `input_transfer_low` | 0x17 | จุด transfer ต่ำ (V) |
| `output.voltage` | `output_voltage` | 0x42 | แรงดันไฟออก (V) |
| `output.frequency` | `output_frequency` | 0x42 | ความถี่ไฟออก (Hz) |
| `output.current` | `output_current` | 0x42 | กระแสไฟออก (A) |
| `output.power` | `output_power` | 0x42 | กำลังไฟ active (W) |
| `output.power.apparent` | `output_power_apparent` | 0x42 | กำลังไฟ apparent (VA) |
| `ups.load` | `ups_load` | 0x07 | โหลด (%) |
| `ups.temperature` | `ups_temperature` | 0x07 | อุณหภูมิ (C) |
| `ups.firmware` | `ups_firmware` | 0x26 | firmware version |

---

## ระบบ Event (upsmon-style)

### NotifyType -- Event Types

| Constant | เงื่อนไข | เทียบ NUT upsmon |
|----------|---------|-----------------|
| `ONLINE` | ไฟกลับมา (OB -> OL) | `NOTIFYMSG ONLINE` |
| `ONBATT` | ไฟดับ (OL -> OB) | `NOTIFYMSG ONBATT` |
| `LOWBATT` | แบตต่ำ | `NOTIFYMSG LOWBATT` |
| `FSD` | Forced shutdown | `NOTIFYMSG FSD` |
| `COMMOK` | เชื่อมต่อ device สำเร็จ | `NOTIFYMSG COMMOK` |
| `COMMBAD` | การเชื่อมต่อหลุด | `NOTIFYMSG COMMBAD` |
| `REPLBATT` | ต้องเปลี่ยนแบตเตอรี่ | `NOTIFYMSG REPLBATT` |
| `CHARGING` | กำลังชาร์จ | extension |
| `OVERLOAD` | โหลดเกิน | extension |
| `OVER_TEMP` | อุณหภูมิสูงเกิน | extension |

### UPSEvent

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

## โครงสร้าง Module

```
ups_module/
  __init__.py         # Public API: UPSClient, UPSData, NotifyType
  client.py           # UPSClient -- interface หลัก
  core.py             # HID protocol decoder (bundled core engine)
  models.py           # UPSData dataclass, UPSEvent, NotifyType
  events.py           # EventBus + EventDetector
  store.py            # Thread-safe DataStore (ใช้ภายใน)
  serializer.py       # JSON sanitizer
  poller.py           # UPSPoller thread (ใช้ภายใน)
  linux_setup.py      # ตัวช่วยตั้งค่า Linux (udev rule, deps check)
  windows_setup.py    # ตัวช่วยตั้งค่า Windows (libusb0 filter driver)
  demo.py             # ตัวอย่างการใช้งาน (Cross-Platform)
  drivers/
    windows/          # Windows driver files
  tests/
    test_models.py    # Unit tests
```

### Architecture

```
   +------------------+
   |  Your Application |
   +--------+---------+
            |
            v
   +--------+---------+
   |   UPSClient      |  <-- public API (client.py)
   +--------+---------+
            |
   +--------+---------+
   |     core.py      |  <-- HID protocol: open, read, decode
   +--------+---------+
            |
   +--------+---------+
   | hidapi (hid.device)|  <-- C library binding
   +--------+---------+
            |
   +--------+---------+
   | /dev/hidrawN     |  <-- Linux kernel HID driver
   | (USB HID)        |
   +------------------+
```

---

## Migration จาก NUT/PyNUT

### เปรียบเทียบ API

| PyNUT (NUT client) | ups_module | หมายเหตุ |
|-------------------|------------|----------|
| `PyNUTClient(host=...)` | `UPSClient()` | ไม่ต้องมี upsd |
| `client.GetUPSVars('ups')` | `client.get_vars()` | dict เหมือนกัน |
| `client.GetVar('ups', 'battery.charge')` | `client.get_var('battery.charge')` | ไม่ต้องระบุ ups name |
| `client.GetUPSStatus('ups')` | `client.get_status()` | return string เหมือนกัน |
| -- | `client.get_data()` | typed object (UPSData) |
| upsmon.conf NOTIFYCMD | `@client.on(NotifyType.ONBATT)` | Python decorator |
| `upsc ups@local` | `python -m ups_module.demo --mode oneshot` | CLI |

### ตัวอย่าง Migration

**ก่อน (PyNUT):**

```python
from PyNUT import PyNUTClient

client = PyNUTClient(host="localhost")
vars = client.GetUPSVars("ups")
status = vars.get("ups.status", b"").decode()
charge = int(vars.get("battery.charge", b"0").decode())
```

**หลัง (ups_module):**

```python
from ups_module import UPSClient

with UPSClient() as client:
    vars = client.get_vars()
    status = vars.get("ups.status", "")
    charge = vars.get("battery.charge", 0)
```

---

## NUT Status String Reference

| Status | ความหมาย |
|--------|----------|
| `OL` | On Line -- ไฟปกติ |
| `OB` | On Battery -- ทำงานบนแบตเตอรี่ |
| `LB` | Low Battery |
| `CHRG` | Charging |
| `DISCHRG` | Discharging |
| `OVER` | Overloaded |
| `BYPASS` | Bypass Mode |
| `OFF` | Standby (ปิดเครื่อง) |

รวมกันได้: `"OL CHRG"`, `"OB DISCHRG LB"`, `"OB LB OVER"`

---

## Troubleshooting

### ปัญหาที่พบบ่อย

**1. `PermissionError` หรือ `hid.enumerate()` ได้ list ว่าง**

สาเหตุ: ไม่มีสิทธิ์เข้าถึง `/dev/hidraw*`

```bash
# วิธีแก้
sudo python -m ups_module.linux_setup
# หรือรันด้วย sudo ชั่วคราว
sudo python your_script.py
```

**2. `ImportError: No module named 'hid'`**

```bash
sudo apt install libhidapi-hidraw0 libhidapi-dev
pip install hidapi
```

**3. `RuntimeError: UPS device not found`**

ตรวจสอบว่า UPS ต่อสาย USB อยู่:

```bash
lsusb | grep 06da
# ควรเห็น: Bus 001 Device 003: ID 06da:ffff ...
```

**4. `input.voltage` เป็น None**

บาง UPS firmware ส่งค่า Input Voltage ผ่าน USB control transfer แทน HID Feature Report
ติดตั้ง pyusb เพิ่ม:

```bash
pip install pyusb
```

**5. Device ที่หายไปหลังตั้ง udev rule**

ถอด USB แล้วเสียบใหม่ หรือ:

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

---

## ตัวอย่างการใช้งาน

### ส่ง alert ผ่าน LINE / Slack เมื่อไฟดับ

```python
import requests
from ups_module import UPSClient, NotifyType

client = UPSClient().connect()

@client.on(NotifyType.ONBATT)
def alert_power_fail(event):
    requests.post("https://notify-api.line.me/api/notify",
        headers={"Authorization": "Bearer <TOKEN>"},
        data={"message": f"UPS: {event.message}"})

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
    data = client.get_data()
    if data.is_on_battery() and (data.battery_charge or 100) < 20:
        print("Battery critical")
        client.schedule_shutdown(delay_seconds=60)
```

### Auto-shutdown สำหรับ RPi4

```python
import os
from ups_module import UPSClient, NotifyType

client = UPSClient().connect()

@client.on(NotifyType.LOWBATT)
def shutdown_rpi(event):
    print(f"Low battery detected: {event.message}")
    client.disconnect()
    os.system("sudo shutdown -h now")

client.start_monitor(interval=1.0)

# รันใน background (เช่น systemd service)
import time
while True:
    time.sleep(60)
```
