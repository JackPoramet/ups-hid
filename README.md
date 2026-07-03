# UPS Monitor — USB HID (Phoenixtec Innova Unity)

โปรแกรม Monitor สำหรับ UPS ผ่านการสื่อสาร USB HID  
แสดงผลแบบ Real-time ด้วย GUI (PySide6) รองรับทั้ง **Windows** และ **Linux**

---

## อุปกรณ์ที่รองรับ

| รายการ | ค่า |
|--------|-----|
| Vendor | Phoenixtec Power Co., Ltd. |
| VID | `0x06DA` |
| PID | `0xFFFF` |
| Usage Page | `0x0084` (HID Power Device) |
| รุ่น | Innova Unity IOT Tower |

---

## ความสามารถ

- **แสดงค่าพื้นฐานของ UPS แบบ Real-time** (ทุก 1 วินาที)
  - แรงดันไฟขาออก (Output Voltage)
  - เปอร์เซ็นต์แบตเตอรี่
  - สถานะไฟบ้าน (AC Present / AC Fail)
  - สถานะการ Discharge
  - แรงดันไฟขาเข้า (Input Voltage) — รองรับเฉพาะ Linux
- **เมนู Control**
  - สั่ง Self Test
  - ตั้งเวลาปิด/เปิด UPS
  - ปรับแรงดันอ้างอิง (220V / 230V)
  - ปรับความถี่ (50Hz / 60Hz)
  - ปรับนาฬิกาของ UPS
- **REST API** (Flask) เปิด endpoint HTTP สำหรับดึงข้อมูล UPS จากระบบอื่น
- **Mapping Cache** บันทึกผล descriptor profile ต่อ device เพื่อเร่งการเปิดครั้งต่อไป
- ค่าที่อ่านได้ผ่านการตรวจสอบกับโปรแกรม **WinPower G2** แล้ว ✔

---

## โครงสร้างโปรเจกต์

```
UPS/
├── ups_monitor_gui.py          # GUI หลัก (Windows)
├── ups_monitor_gui_linux.py    # GUI สำหรับ Linux (อ่าน descriptor จาก sysfs)
├── hid_ups.py                  # HID core: descriptor parsing, report decode, mapping cache
├── hidapi.py                   # Windows WinHidApi wrapper (DeviceIoControl)
├── requirements.txt            # Python dependencies
├── guide.md                    # คู่มือพัฒนา Auto-Discovery
├── how to use.md               # วิธีติดตั้งและใช้งาน
├── data_dump/cache/            # Mapping cache ต่อ device (JSON)
└── doc/                        # ข้อมูล HID descriptor และ data poll logs
```

---

## การติดตั้ง

### 1. สร้าง Virtual Environment

```bash
python -m venv .venv
```

### 2. เปิดใช้งาน

```bash
# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3. ติดตั้ง Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies หลัก:**

| Package | วัตถุประสงค์ |
|---------|-------------|
| `hidapi` | สื่อสารกับ HID device |
| `PySide6` | Qt6 GUI framework |
| `pyusb` | USB access (Input Voltage บน Linux) |
| `libusb-package` | bundles libusb DLL สำหรับ Windows |
| `flask` | REST API server *(optional)* |

---

## การใช้งาน

```bash
# รัน GUI (ใช้ได้ทั้ง Windows และ Linux)
python ups_monitor_gui_linux.py

# รัน GUI เวอร์ชัน Windows
python ups_monitor_gui.py
```

> **หมายเหตุ:** บน Windows ค่า Input Voltage ยังไม่สามารถแสดงได้ (HID class driver limitation)  
> บน Linux สามารถอ่านได้ตามปกติผ่าน sysfs (`/sys/class/hidraw/hidrawN/device/report_descriptor`)

---

## ข้อกำหนดระบบ

| ระบบปฏิบัติการ | รองรับ | หมายเหตุ |
|----------------|--------|----------|
| Windows 10/11 | ✔ | ใช้ `hidapi.py` (WinHidApi/DeviceIoControl) |
| Linux | ✔ | อ่าน descriptor จาก sysfs โดยตรง |

> **Windows:** แนะนำให้รันด้วย interpreter ใน `.venv` เนื่องจาก global interpreter อาจไม่พบ `hid` หรือ `PySide6`

---

## REST API

เมื่อรันโปรแกรม Flask จะเปิด HTTP server อัตโนมัติที่ `http://127.0.0.1:5000` (local only)

### Endpoints

| Method | URL | คำอธิบาย |
|--------|-----|-----------|
| GET | `/api/health` | ตรวจสอบสถานะ server และเวลา update ล่าสุด |
| GET | `/api/ups` | ข้อมูลทั้งหมด — device info + ค่า UPS ทุกตัว |
| GET | `/api/ups/status` | สถานะหลัก (AC present, charging, discharging) |
| GET | `/api/ups/battery` | ข้อมูลแบตเตอรี่ (charge %, runtime, voltage) |

### ตัวอย่าง Response — `/api/ups/status`

```json
{
  "ups.status": "OL",
  "ac_present": true,
  "charging": false,
  "discharging": false,
  "below_capacity_limit": false,
  "status_good": true,
  "timestamp": "2026-07-03T10:30:00"
}
```

### การตั้งค่า

ค่า default คือ `127.0.0.1:5000` (เฉพาะ local)  
ถ้าต้องการเปิดให้เครื่องอื่นใน LAN เข้าถึงได้ แก้บรรทัดนี้ใน [ups_monitor_gui_linux.py](ups_monitor_gui_linux.py):

```python
start_api_thread(host="0.0.0.0", port=5000)
```

> **หมายเหตุ:** Flask เป็น dependency แบบ optional — ถ้าไม่ได้ติดตั้งโปรแกรมจะแจ้งเตือนและข้ามการเปิด API โดย GUI ยังทำงานได้ปกติ
