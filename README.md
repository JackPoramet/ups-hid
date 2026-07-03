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
