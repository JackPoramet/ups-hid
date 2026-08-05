# ENEREX UPS Monitor — Windows Tray Service

โปรแกรม Monitor UPS สำหรับ Windows ที่ทำงานเป็น **System Tray**  
เข้าใช้งานผ่าน Web UI ที่ `http://localhost:48655`

---

## คุณสมบัติ (Key Features)

| ฟีเจอร์ | รายละเอียด |
|---------|-----------|
| **System Tray** | ทำงานเบื้องหลัง ไอคอนเปลี่ยนสีตามสถานะ UPS |
| **Web Dashboard** | แสดงสถานะ UPS real-time ผ่าน `localhost:48655` |
| **UPS Device Selection** | เมนูสแกนและเลือกอุปกรณ์ UPS USB HID (คัดกรอง VID `0x06DA` Phoenixtec / ENEREX) ผ่านปุ่มมุมขวาบน |
| **Persistent Device Memory** | ระบบจดจำอุปกรณ์ล่าสุด (`selected_device_serial` / `selected_device_path`) และสลับการเชื่อมต่อให้อัตโนมัติเมื่ออุปกรณ์นั้นกลับมาออนไลน์ (Auto-Preemption) |
| **Disconnected State Handling** | แสดงผลแจ้งเตือนและสถานะ "ไม่ได้เชื่อมต่ออุปกรณ์ UPS" ชัดเจนบน Dashboard เมื่อไม่ได้เสียบสาย USB หรืออุปกรณ์ไม่ออนไลน์ |
| **SQLite Persistent Log** | บันทึกประวัติสถานะ (Telemetry) และเหตุการณ์ (Event Logs) ในฐานข้อมูล SQLite พร้อมกราฟย้อนหลัง |
| **Notification** | Windows Toast เมื่อไฟดับ / ไฟกลับมา / แบตเตอรี่ต่ำ |
| **Auto-Shutdown PC** | ปิดเครื่อง PC อัตโนมัติเมื่อไฟดับหรือแบตเตอรี่ต่ำ |
| **Windows Startup** | เปิดโปรแกรมพร้อมกับ Windows ผ่าน Registry อัตโนมัติ (สลับเปิด/ปิดได้ทาง Web UI) |
| **Enterprise Slate UI** | ดีไซน์สไตล์ Enterprise รองรับการสลับโหมดมืด (Dark Mode) และโหมดสว่าง (Light Mode) คมชัด อ่านง่ายสบายตา |
| **Settings Control** | ตั้งค่าทุกอย่างผ่าน Web UI ไม่ต้องแก้ไขไฟล์ |
| **Setup Wizard & Executable** | ไฟล์ `.exe` เดี่ยว + ตัวติดตั้งแบบ Setup Wizard (`ENEREX-UPS-Monitor-Setup.exe`) |

---

## คู่มือการใช้งาน (User Guide)

### 1. การเปิดใช้งาน Web Dashboard
- เมื่อเปิดโปรแกรม โปรแกรมจะทำงานในเบื้องหลังเป็น **System Tray Icon** ที่มุมขวาล่างของ Windows Taskbar
- คลิกขวาที่ไอคอนแล้วเลือก **"Open Web Dashboard"** หรือเปิดเบราว์เซอร์ไปที่ `http://localhost:48655`

### 2. การเลือกอุปกรณ์ UPS (Device Selection)
- คลิกปุ่ม **"เลือกอุปกรณ์ UPS"** ที่ **มุมขวาบน (Top-Right Header Bar)** ของหน้า Web Dashboard
- หน้าต่าง Modal จะสแกนหาอุปกรณ์ UPS USB HID ในระบบ (เน้นคัดกรอง VID `0x06DA` Phoenixtec / ENEREX)
- ตรวจสอบข้อมูลอุปกรณ์ (Manufacturer, Model, VID/PID, Serial Number, Usage Page)
- คลิกปุ่ม **"เลือกเชื่อมต่ออุปกรณ์นี้"** เพื่อสลับไปใช้งานอุปกรณ์ที่เลือก
- **ระบบจดจำอุปกรณ์อัตโนมัติ (Auto-Switching Memory)**: ระบบจะบันทึกอุปกรณ์ล่าสุดไว้ หากอุปกรณ์หลุดไปแล้วกลับมาออนไลน์ใหม่ ระบบจะสลับการเชื่อมต่อกลับมายังอุปกรณ์ที่เลือกไว้โดยอัตโนมัติ

### 3. การเฝ้าระวังสถานะ (Dashboard Monitoring)
- **สถานะปกติ (Online Mode)**: แสดงสถานะกระแสไฟหลัก AC Input, ระดับแบตเตอรี่ (%), เวลาสำรองไฟคงเหลือ (Runtime) และโหลดไฟฟ้า (%)
- **สถานะไม่ได้เชื่อมต่อ (Disconnected State)**: หากไม่ได้เสียบสาย USB หรืออุปกรณ์ไม่ออนไลน์ การ์ดแจ้งเตือนและป้ายสถานะทั้งหมดจะแสดงคำว่า **"ไม่ได้เชื่อมต่ออุปกรณ์ UPS"** พร้อมคำแนะนำ

### 4. เมนูต่างๆ บน Web Dashboard
- **Dashboard**: หน้าหลักแสดงสถานะกระแสไฟฟ้า แบตเตอรี่ และโหลดแบบ Real-time
- **Device Info**: แสดงรายละเอียดรุ่นอุปกรณ์เชิงลึก (Firmware, Report Descriptor Profiles, USB Attributes)
- **Control**: สั่งการทดสอบแบตเตอรี่ (Battery Self Test), สั่งปิดไฟออก UPS (Output Shutdown) และซิงค์เวลานาฬิกา PC ไปยัง UPS
- **History & Logs**: ดึงกราฟประวัติแรงดันไฟ/ระดับแบตเตอรี่ย้อนหลัง และบันทึกเหตุการณ์ (Event Logs)
- **Settings**: ตั้งค่าเวลานับถอยหลัง Auto PC Shutdown, ตั้งค่าการแจ้งเตือน Toast Notification และเปิด/ปิด Windows Startup

---

## โครงสร้างโปรเจค (Project Structure)

```
windows/
├── tray_service/                  ← Python package หลัก
│   ├── main.py                    ← Entry Point (รวมทุก component)
│   ├── tray_app.py                ← System Tray (pystray)
│   ├── poller.py                  ← UPS HID Poller Thread (รองรับ Target Switching & Device Memory)
│   ├── database.py                ← SQLite Database Engine (Telemetry & Events)
│   ├── startup_manager.py         ← Windows Registry Startup Manager
│   ├── notifications.py           ← Windows Toast Notifications
│   ├── auto_shutdown.py           ← PC Auto-Shutdown Manager
│   ├── config_manager.py          ← Config read/write (JSON)
│   ├── web_server.py              ← Flask Web Server + REST API
│   ├── templates/
│   │   └── dashboard.html         ← Web UI Dashboard (Device Selection Modal & Topbar)
│   └── static/
│       ├── css/style.css          ← Web UI Enterprise Stylesheet (Dark/Light themes)
│       └── js/app.js              ← Web UI JavaScript (Canvas Chart, Device Modal & API)
├── assets/                        ← Icons (ups_icon.ico)
├── installer/
│   └── installer.iss              ← Inno Setup script
├── tests/                         ← Unit tests (test_database, test_startup ฯลฯ)
├── build_exe.spec                 ← PyInstaller spec
└── build.ps1                      ← Build automation
```

---

## การติดตั้งและการรันพัฒนา (Development)

### 1. เตรียม Virtual Environment

```powershell
# จาก root ของโปรเจค (UPS/)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. รันโปรแกรม (Development Mode)

```powershell
# จาก root ของโปรเจค (UPS/)
python -X utf8 -m windows.tray_service.main

# หรือรันตรง
python -X utf8 windows/tray_service/main.py
```

เปิด Web Browser ไปที่ **http://localhost:48655**

---

## Build & Distribution

```powershell
# รัน build ทั้งหมด (.exe + Setup Installer)
.\windows\build.ps1

# Build แบบ clean (ลบ artifacts เก่าก่อน)
.\windows\build.ps1 -Clean

# Build .exe อย่างเดียว (ข้าม Inno Setup)
.\windows\build.ps1 -SkipInstaller
```

### Output Files

- `windows/dist/ENEREX-UPS-Monitor.exe` — Executable file
- `windows/installer/Output/ENEREX-UPS-Monitor-Setup.exe` — Setup Wizard Installer

### Requirements สำหรับการ Build

| Tool | ดาวน์โหลด |
|------|----------|
| PyInstaller | `pip install pyinstaller` |
| Inno Setup 6 / 7 | https://jrsoftware.org/isinfo.php |

---

## REST API

### Device Scanning & Selection

| Method | URL | คำอธิบาย |
|--------|-----|----------|
| `GET`  | `/api/ups/devices` | ดึงรายการอุปกรณ์ USB HID / UPS ทั้งหมด (คัดกรอง VID `0x06DA`) พร้อมสถานะการเลือกใช้งาน |
| `POST` | `/api/ups/select_device` | สลับอุปกรณ์ UPS เป้าหมายและบันทึกค่าลง Config (`selected_device_path`, `selected_device_serial`) |

### Status & Health

| Method | URL | คำอธิบาย |
|--------|-----|----------|
| `GET` | `/api/health` | สถานะ server |
| `GET` | `/api/ups` | ข้อมูล UPS ทั้งหมด |
| `GET` | `/api/ups/status` | สถานะหลัก (AC, charging) |
| `GET` | `/api/ups/battery` | ข้อมูลแบตเตอรี่ |
| `GET` | `/api/ups/device` | รายละเอียดรุ่น UPS |
| `GET` | `/api/ups/power` | ข้อมูลไฟเข้า/ออก |

### History & Database

| Method | URL | คำอธิบาย |
|--------|-----|----------|
| `GET` | `/api/history?hours=24` | ดึงประวัติ Telemetry ย้อนหลังสำหรับกราฟ |
| `GET` | `/api/events?limit=50` | ดึงรายการ Event Logs ย้อนหลัง |
| `POST` | `/api/database/clear` | ล้างข้อมูลในฐานข้อมูล SQLite |

### Config & Control

| Method | URL | คำอธิบาย |
|--------|-----|----------|
| `GET`  | `/api/config` | อ่าน config ปัจจุบัน |
| `POST` | `/api/config` | อัปเดต config (JSON body) |
| `POST` | `/api/control/shutdown/cancel` | ยกเลิก PC auto-shutdown |
| `GET`  | `/api/ups/time` | อ่านเวลานาฬิกา UPS (`RID 0x29`) |
| `POST` | `/api/ups/time/sync` | ซิงค์เวลานาฬิกา PC ไปยัง UPS (`RID 0x29`) |
| `POST` | `/api/ups/control/shutdown` | สั่ง UPS Output Shutdown |

---

## Configuration & Storage

- Config บันทึกที่ `%APPDATA%\Roaming\UPS-Monitor\config.json`
- SQLite Database บันทึกที่ `%APPDATA%\Roaming\UPS-Monitor\ups_monitor.db`
- Logs บันทึกที่ `%APPDATA%\Roaming\UPS-Monitor\logs\ups_monitor.log`

| Key | Type | Default | คำอธิบาย |
|-----|------|---------|----------|
| `port` | int | `48655` | Port ของ Web Server |
| `poll_interval_s` | float | `1` | ความถี่การอ่าน UPS (วินาที) |
| `selected_device_path` | string | `null` | Device Path ของ UPS อุปกรณ์เป้าหมายที่เลือกไว้ |
| `selected_device_serial` | string | `null` | Serial Number ของ UPS อุปกรณ์เป้าหมายที่เลือกไว้ |
| `db_enabled` | bool | `true` | เปิด/ปิด การบันทึก SQLite Database |
| `db_telemetry_interval_s` | int | `10` | ความถี่การบันทึกประวัติค่าสถานะ (วินาที) |
| `db_retention_days` | int | `30` | ระยะเวลาเก็บรักษาข้อมูล (วัน) |
| `auto_shutdown_enabled` | bool | `false` | เปิด/ปิด Auto PC Shutdown |
| `shutdown_delay_minutes` | int | `5` | Delay (นาที) ก่อนปิด PC หลังไฟดับ |
| `shutdown_battery_threshold` | int | `20` | ปิด PC เมื่อแบตเหลือ < N% |
| `notifications_enabled` | bool | `true` | เปิด/ปิด Notifications ทั้งหมด |
| `startup_with_windows` | bool | `true` | เปิดทำงานอัตโนมัติพร้อม Windows |
