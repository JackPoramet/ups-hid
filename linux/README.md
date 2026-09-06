# =============================================================================
# Universal UPS Bridge for Linux (NUT Integration)
# =============================================================================
ระบบบริดจ์สำหรับเชื่อมต่อเครื่องสำรองไฟฟ้า (UPS) แบรนด์ Enerex, Phoenixtec และ MEC
เข้ากับระบบจัดการพลังงาน Network UPS Tools (NUT) บน Linux

-----------------------------------------------------------------------------
## 1. อุปกรณ์ที่รองรับ (Supported Hardware)
-----------------------------------------------------------------------------
* Innova Unity IOT Tower : USB 0x06DA:0xFFFF | phoenixtec_hid | 3000VA / 2700W
* Innova Basic G2        : USB 0x06DA:0xFFFF | phoenixtec_hid | 2700VA / 2700W
* Offline UPS 2000D      : USB 0x06DA:0xFFFF | phoenixtec_hid | 2000VA / 1200W
* MEC0003 (800E)         : USB 0x0001:0x0000 | megatec_q1     |  880VA /  528W

-----------------------------------------------------------------------------
## 2. การติดตั้งและถอนการติดตั้ง (Installation & Uninstallation)
-----------------------------------------------------------------------------

[ ติดตั้งระบบ ]
  $ chmod +x install.sh uninstall.sh
  $ sudo ./install.sh

[ ถอนการติดตั้งระบบ ]
  $ sudo ./uninstall.sh

-----------------------------------------------------------------------------
## 3. เซอร์วิสที่ทำงานในระบบหลังติดตั้ง (Running Services)
-----------------------------------------------------------------------------
เมื่อรันสคริปต์ install.sh เสร็จสมบูรณ์ จะมี 3 เซอร์วิสหลักที่ทำงานอยู่บน Linux:

1. enerex-ups-bridge.service
   - ประเภท : Background Daemon (Python Bridge)
   - หน้าที่ : เชื่อมต่อ USB ดึงค่า Telemetry จาก UPS แปลงและเขียนลง /etc/nut/myups.dev
   - คำสั่ง : sudo systemctl status enerex-ups-bridge

2. nut-driver.service
   - ประเภท : NUT Driver Daemon (dummy-ups / enerex)
   - หน้าที่ : อ่านไฟล์สถานะ /etc/nut/myups.dev แบบ Real-time
   - คำสั่ง : sudo systemctl status nut-driver

3. nut-server.service
   - ประเภท : NUT Data Server (upsd Daemon)
   - หน้าที่ : ให้บริการข้อมูล Telemetry บน TCP Port 3493 แก่คำสั่ง upsc และระบบเครือข่าย
   - คำสั่ง : sudo systemctl status nut-server

-----------------------------------------------------------------------------
## 4. รายการ Path ในระบบที่เกี่ยวข้อง (System Paths & Actions)
-----------------------------------------------------------------------------

* Systemd Service File:
  - Path      : /etc/systemd/system/enerex-ups-bridge.service
  - install   : สร้างไฟล์ Service และเปิดใช้งาน Auto-start ตอนบูตระบบ
  - uninstall : สั่ง stop, disable และลบไฟล์ Service ทิ้ง

* โฟลเดอร์โปรแกรมหลัก:
  - Path      : /opt/enerex-ups/
  - install   : คัดลอก enerex_ups_bridge.py และ ups_module/
  - uninstall : ลบไดเรกทอรีและไฟล์โปรแกรมทั้งหมดออก

* Driver Symlink ของ NUT:
  - Path      : /lib/nut/enerex
  - install   : สร้าง Symbolic Link ชี้ไปที่ /lib/nut/dummy-ups
  - uninstall : ลบ Symbolic Link ออก

* upscmd Interceptor Wrapper:
  - Path      : /usr/local/bin/upscmd
  - install   : ดักจับคำสั่ง instant command จากเว็บ/ระบบแล้วส่ง Signal ควบคุมฮาร์ดแวร์จริง
  - uninstall : ลบไฟล์ Wrapper ทิ้ง

* State Pipe File (ท่อส่งข้อมูล):
  - Path      : /etc/nut/myups.dev
  - install   : สร้างไฟล์สำหรับส่งผ่านข้อมูล Telemetry แบบ Real-time
  - uninstall : ลบไฟล์สถานะทิ้ง

* Lock File:
  - Path      : /run/enerex_ups_bridge.lock
  - install   : Kernel File Lock ป้องกันการรัน Service ซ้ำซ้อน
  - uninstall : ลบ Lock File ออก

* Systemd Patch:
  - Path      : /lib/systemd/system/nut-driver.service
  - install   : ใส่เครื่องหมาย '-' หน้า upsdrvctl start ป้องกัน Service Crash
  - uninstall : กู้คืนคำสั่งกลับเป็นค่าดั้งเดิมของระบบ

* System Packages:
  - Path      : APT (python3-hid, python3-usb)
  - install   : ติดตั้งอัตโนมัติผ่าน apt-get
  - uninstall : ถามยืนยัน [y/N] ก่อนสั่ง apt-get remove

-----------------------------------------------------------------------------
## 5. การตรวจสอบสถานะการทำงาน (Monitoring & Logs)
-----------------------------------------------------------------------------

# ตรวจสอบข้อมูล Telemetry ทั้งหมดจาก NUT (แรงดัน, โหลด, แบตเตอรี่, ผลการทดสอบ)
$ upsc myups

# ตรวจสอบผลการทดสอบแบตเตอรี่และสถานะเฉพาะจุด
$ upsc myups battery.test.status
$ upsc myups ups.test.result
$ upsc myups ups.status

# ตรวจสอบสถานะการทำงานของ Bridge Service
$ sudo systemctl status enerex-ups-bridge

# ดู Log การทำงานแบบ Real-time
$ sudo journalctl -u enerex-ups-bridge -f

# ตรวจสอบสถานะของ NUT Server
$ sudo systemctl status nut-server

-----------------------------------------------------------------------------
## 6. สถาปัตยกรรมและคุณลักษณะทางเทคนิค (Technical Features)
-----------------------------------------------------------------------------
Flow:
  [UPS Device] <--(USB)--> [enerex_ups_bridge.py] --(Atomic Write)--> [/etc/nut/myups.dev] --> [NUT dummy-ups] --> [upsd] --> [upsc / Clients]

คุณลักษณะสำคัญ:
1. Atomic File Replacement : ใช้ os.rename ป้องกัน NUT อ่านข้อมูลไม่สมบูรณ์
2. Disconnect & Auto-Recovery : ตรวจจับสายหลุดทันที และปรับสถานะเป็น DNC (Driver Not Connected) พร้อมรีสตาร์ต nut-driver/nut-server เพื่อล้างตัวแปรค้างในแคชทั้งหมด 100%
3. Single Instance Lock    : ใช้ fcntl.flock ป้องกันการรันโปรเซสซ้อนทับ
4. Graceful Shutdown       : รองรับ SIGTERM/SIGINT คืน Resource และปิด Handle สะอาด
5. Multi-Model Resolution  : ตรวจสอบ profile ร่วมกับ VID:PID เพื่อแยกแยะรุ่น Unity, Basic G2, 2000D และ MEC0003 ได้ถูกต้อง
6. Battery Self-Test Bridge : ตรวจจับคำสั่งทดสอบแบตเตอรี่จาก Web/MariaDB, Signals, File Queue หรือ upscmd แล้วส่งคำสั่งควบคุมฮาร์ดแวร์จริง พร้อมอัปเดตสถานะ CAL เข้า NUT อัตโนมัติ

-----------------------------------------------------------------------------
## 7. คู่มือการสั่งทดสอบแบตเตอรี่ (Battery Self-Test Integration)
-----------------------------------------------------------------------------

ระบบรองรับการสั่งทดสอบแบตเตอรี่ (Battery Self-Test) และคำสั่งยกเลิก (Abort) ผ่าน 4 ช่องทางหลัก:

### 7.1 ช่องทางสั่งการ (Trigger Methods)
1. **ผ่านคำสั่ง CLI สะดวกสุด (enerex-test)**:
   - สั่งเริ่ม Quick Battery Test (10 วินาที):
     $ enerex-test quick
   - สั่งเริ่ม Deep Battery Test:
     $ enerex-test deep
   - สั่งยกเลิก Battery Test (Abort/Stop):
     $ enerex-test stop

2. **ผ่านหน้าเว็บ Web Dashboard**:
   - ไปที่เมนู `/pages/system/test/`
   - กดปุ่ม **Start Now** ในส่วน Quick Test หรือ Deep Test
   - ระบบเว็บจะบันทึกคำสั่งลงตาราง `system_command` ใน MariaDB (`run_python = 1`) ซึ่ง `enerex_ups_bridge.py` จะดักจับและสั่งงานฮาร์ดแวร์ทันที

3. **ผ่านคำสั่ง NUT upscmd Wrapper**:
   - สั่งเริ่ม Quick Test:
     $ upscmd myups test.battery.start.quick
   - สั่งเริ่ม Deep Test:
     $ upscmd myups test.battery.start.deep
   - สั่งยกเลิก:
     $ upscmd myups test.battery.stop

4. **ผ่าน Linux Signal**:
   - สั่งเริ่ม Quick Battery Test:
     $ pkill -SIGUSR1 -f enerex_ups_bridge.py
   - สั่งยกเลิก Battery Test (Abort):
     $ pkill -SIGUSR2 -f enerex_ups_bridge.py

### 7.2 สถานะและการเปลี่ยนแปลงของตัวแปร (Status Lifecycle)
* **ก่อนสั่งทดสอบ (Baseline / Idle)**:
  - `ups.status`          : `OL` (หรือ `OFF` หากปิดสวิตช์เครื่อง)
  - `battery.test.status` : `passed`
  - `ups.test.result`     : `Done and passed`
* **ระหว่างการทดสอบ (In Progress ~ 10 วินาที)**:
  - `ups.status`          : `OL CAL` (มีแฟล็ก `CAL` กำกับ)
  - `battery.test.status` : `in progress`
  - `ups.test.result`     : `In progress`
  - ตัวเครื่องดึงโหลดลงแบตเตอรี่จริง แรงดันแบตเตอรี่และแรงดันขาออกจะลดลงตามพฤติกรรมอินเวอร์เตอร์
* **หลังการทดสอบเสร็จสิ้น (Completed)**:
  - `ups.status`          : `OL` (แฟล็ก `CAL` ปลดออกอัตโนมัติ)
  - `battery.test.status` : `passed`
  - `ups.test.result`     : `Done and passed`
* **กรณียกเลิกการทดสอบกลางคัน (Aborted)**:
  - `ups.status`          : `OL`
  - `battery.test.status` : `abort`
  - `ups.test.result`     : `Aborted`

### 7.3 ตารางคำสั่งฮาร์ดแวร์จริงแยกรายรุ่น (Hardware Command Matrix)

| รุ่น UPS | โปรโตคอล | คำสั่ง Quick Test | คำสั่ง Deep Test | คำสั่ง Abort/Stop | ระยะเวลาทดสอบจริง |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Innova Unity** | Phoenixtec HID | Feature Report `0x24 [0x01]` | Feature Report `0x24 [0x02]` | Feature Report `0x24 [0x00]` | ~10 วินาที |
| **Innova Basic G2** | Phoenixtec HID | Feature Report `0x24 [0x01]` | Feature Report `0x24 [0x02]` | Feature Report `0x24 [0x00]` | ~3 - 10 วินาที |
| **Offline UPS 2000D** | Phoenixtec HID | Feature Report `0x24 [0x01]` | Feature Report `0x24 [0x02]` | Feature Report `0x24 [0x03]` | ~10 วินาที (สลับ Relay อินเวอร์เตอร์ 215V) |
| **MEC0003** | Megatec Q1 | ASCII Command `'T'` | ASCII Command `'TL'` | ASCII Command `'CT'` | ~10 วินาที (State Machine Index 3/13) |

