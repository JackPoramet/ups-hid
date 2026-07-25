# ENEREX UPS Monitor — Windows Tray Service

โปรแกรม Monitor UPS สำหรับ Windows ที่ทำงานเป็น **System Tray**  
เข้าใช้งานผ่าน Web UI ที่ `http://localhost:48655`

---

## ✨ คุณสมบัติ (Key Features)

| ฟีเจอร์ | รายละเอียด |
|---------|-----------|
| 🔲 **System Tray** | ทำงานเบื้องหลัง ไอคอนเปลี่ยนสีตามสถานะ UPS |
| 🌐 **Web Dashboard** | แสดงสถานะ UPS real-time ผ่าน `localhost:48655` |
| 📊 **SQLite Persistent Log** | บันทึกประวัติสถานะ (Telemetry) และเหตุการณ์ (Event Logs) ในฐานข้อมูล SQLite พร้อมกราฟย้อนหลัง |
| 🔔 **Notification** | Windows Toast เมื่อไฟดับ / ไฟกลับมา / แบตเตอรี่ต่ำ |
| ⏻ **Auto-Shutdown PC** | ปิดเครื่อง PC อัตโนมัติเมื่อไฟดับหรือแบตเตอรี่ต่ำ |
| 🚀 **Windows Startup** | เปิดโปรแกรมพร้อมกับ Windows ผ่าน Registry อัตโนมัติ (สลับเปิด/ปิดได้ทาง Web UI) |
| ⚙️ **Settings Control** | ตั้งค่าทุกอย่างผ่าน Web UI ไม่ต้องแก้ไขไฟล์ |
| 📦 **Setup Wizard & Executable** | ไฟล์ `.exe` เดี่ยว + ตัวติดตั้งแบบ Setup Wizard (`ENEREX-UPS-Monitor-Setup.exe`) |

---

## 🏗 โครงสร้างโปรเจค (Project Structure)

```
windows/
├── tray_service/                  ← Python package หลัก
│   ├── main.py                    ← Entry Point (รวมทุก component)
│   ├── tray_app.py                ← System Tray (pystray)
│   ├── poller.py                  ← UPS HID Poller Thread
│   ├── database.py                ← SQLite Database Engine (Telemetry & Events)
│   ├── startup_manager.py         ← Windows Registry Startup Manager
│   ├── notifications.py           ← Windows Toast Notifications
│   ├── auto_shutdown.py           ← PC Auto-Shutdown Manager
│   ├── config_manager.py          ← Config read/write (JSON)
│   ├── web_server.py              ← Flask Web Server + REST API
│   ├── templates/
│   │   └── dashboard.html         ← Web UI Dashboard (Charts & Tables)
│   └── static/
│       ├── css/style.css          ← Web UI Stylesheet (dark theme)
│       └── js/app.js              ← Web UI JavaScript (Canvas Chart & API)
├── assets/                        ← Icons (ups_icon.ico)
├── installer/
│   └── installer.iss              ← Inno Setup script
├── tests/                         ← Unit tests (test_database, test_startup ฯลฯ)
├── build_exe.spec                 ← PyInstaller spec
└── build.ps1                      ← Build automation
```

---

## ⚡ การติดตั้งและการรันพัฒนา (Development)

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

## 🏭 Build & Distribution

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

## 🌐 REST API

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

## ⚙️ Configuration & Storage

- Config บันทึกที่ `%APPDATA%\Roaming\UPS-Monitor\config.json`
- SQLite Database บันทึกที่ `%APPDATA%\Roaming\UPS-Monitor\ups_monitor.db`
- Logs บันทึกที่ `%APPDATA%\Roaming\UPS-Monitor\logs\ups_monitor.log`

| Key | Type | Default | คำอธิบาย |
|-----|------|---------|----------|
| `port` | int | `48655` | Port ของ Web Server |
| `poll_interval_s` | float | `1` | ความถี่การอ่าน UPS (วินาที) |
| `db_enabled` | bool | `true` | เปิด/ปิด การบันทึก SQLite Database |
| `db_telemetry_interval_s` | int | `10` | ความถี่การบันทึกประวัติค่าสถานะ (วินาที) |
| `db_retention_days` | int | `30` | ระยะเวลาเก็บรักษาข้อมูล (วัน) |
| `auto_shutdown_enabled` | bool | `false` | เปิด/ปิด Auto PC Shutdown |
| `shutdown_delay_minutes` | int | `5` | Delay (นาที) ก่อนปิด PC หลังไฟดับ |
| `shutdown_battery_threshold` | int | `20` | ปิด PC เมื่อแบตเหลือ < N% |
| `notifications_enabled` | bool | `true` | เปิด/ปิด Notifications ทั้งหมด |
| `startup_with_windows` | bool | `true` | เปิดทำงานอัตโนมัติพร้อม Windows |

---
