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
## 3. รายการ Path ในระบบที่เกี่ยวข้อง (System Paths & Actions)
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
## 4. การตรวจสอบสถานะการทำงาน (Monitoring & Logs)
-----------------------------------------------------------------------------

# ตรวจสอบข้อมูล Telemetry จาก NUT (ค่าแรงดัน, โหลด, แบตเตอรี่)
$ upsc myups

# ตรวจสอบสถานะการทำงานของ Bridge Service
$ sudo systemctl status enerex-ups-bridge

# ดู Log การทำงานแบบ Real-time
$ sudo journalctl -u enerex-ups-bridge -f

# ตรวจสอบสถานะของ NUT Server
$ sudo systemctl status nut-server

-----------------------------------------------------------------------------
## 5. สถาปัตยกรรมและคุณลักษณะทางเทคนิค (Technical Features)
-----------------------------------------------------------------------------
Flow:
  [UPS Device] <--(USB)--> [enerex_ups_bridge.py] --(Atomic Write)--> [/etc/nut/myups.dev] --> [NUT dummy-ups] --> [upsd] --> [upsc / Clients]

คุณลักษณะสำคัญ:
1. Atomic File Replacement : ใช้ os.rename ป้องกัน NUT อ่านข้อมูลไม่สมบูรณ์
2. Auto-Recovery           : ตรวจจับสายหลุด/เสียบใหม่ และปรับสถานะเป็น OFF อัตโนมัติ
3. Single Instance Lock    : ใช้ fcntl.flock ป้องกันการรันโปรเซสซ้อนทับ
4. Graceful Shutdown       : รองรับ SIGTERM/SIGINT คืน Resource และปิด Handle สะอาด
