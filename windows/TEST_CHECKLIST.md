# 📋 UPS Monitor — รายการทดสอบระบบ (Verification Test Checklist)

เอกสารนี้ใช้สำหรับตรวจสอบความถูกต้องสมบูรณ์ของการทำงานโปรแกรม **UPS Monitor Windows System Tray Service & Web UI**

---

## 1. 🖥 การเริ่มต้นทำงานและ System Tray (Startup & Tray)

- [/] **การเปิดโปรแกรม:** รันคำสั่ง `.venv\Scripts\python.exe -X utf8 windows\tray_service\main.py` หรือรันไฟล์ `UPS-Monitor.exe`
- [/] **การแสดงผล Tray Icon:** มีไอคอนปรากฏที่แถบ Taskbar มุมขวาล่าง (System Tray)
- [/] **การคลิกขวา Tray Menu:** แสดงเมนูบริบทอย่างถูกต้อง:
  - `Open Web UI`
  - `Exit`
- [/] **การเปิด Web UI จาก Tray:** คลิกที่ `Open Web UI` แล้วเบราว์เซอร์เปิดไปยัง `http://localhost:48655` อัตโนมัติ

---

## 2. 🔌 การเชื่อมต่อและการดึงข้อมูล UPS (HID Hardware Connection)

- [ ] **การตรวจหาอุปกรณ์:** ระบบตรวจเจอ UPS รุ่น **PHOENIXTEC Innova Unity** (VID: `0x06DA`, PID: `0xFFFF`)
- [ ] **การอ่านแรงดันไฟเข้า ($V_{IN}$):** แสดงค่า **Input Voltage** (เช่น `214V - 220V`) ผ่านระบบ libusb0 fallback
- [ ] **การอัปเดตข้อมูล Real-time:** ค่าแรงดันไฟ, % แบตเตอรี่, และ Load อัปเดตทุกๆ 1 วินาทีแบบไม่ต้องกด Refresh

---

## 3. 🚦 การตรวจจับสภาวะการทำงาน (Operating Status Detection)

- [ ] **โหมดไฟปกติ (Line Mode / Online):**
  - หน้า Dashboard แสดงสถานะ: **`Online (OL)`** (สีเขียว 🟢)
  - แถบไฟเข้า/ออก และ % แบตเตอรี่แสดงผลปกติ
- [ ] **โหมดสำรองไฟ (On Battery Mode):**
  - *วิธีทดสอบ:* ถอดปลั๊กไฟบ้านของ UPS ออก
  - หน้า Dashboard เปลี่ยนสถานะเป็น: **`On Battery (OB)`** (สีแดง 🔴)
  - มี Windows Toast Notification แจ้งเตือน *"ไฟดับ! UPS สลับใช้แบตเตอรี่"*
- [ ] **โหมดบายพาส (Bypass Mode):**
  - *วิธีทดสอบ:* กดปุ่มสลับโหมด Bypass ที่หน้าจอ/สวิตช์ของตัวเครื่อง UPS
  - หน้า Dashboard เปลี่ยนสถานะเป็น: **`Bypass Mode (BYPASS)`** (สีส้ม 🟧)
  - เมื่อสลับกลับโหมดปกติ สถานะคืนค่าเป็น **`Online (OL)`**

---

## 4. 🕒 การตั้งเวลานาฬิกา UPS (UPS Clock Sync - RID `0x29`)

- [ ] **การอ่านเวลา UPS:** กดปุ่ม `📖 Read UPS Time` หน้าจอแสดงเวลาล่าสุดของ UPS
- [ ] **การซิงค์เวลา PC $\rightarrow$ UPS:** กดปุ่ม `🕒 Sync Time = PC Time`
  - มีกล่องข้อความยื่นยันก่อนดำเนินการ
  - ตัวเลขเวลาบนหน้าจอ LCD ของตัวเครื่อง UPS เปลี่ยนเป็นเวลาบ่าย (ตรงกับเวลาเครื่อง PC)
  - ไม่แสดงเวลาผิดพลาด 7 ชั่วโมง ( Timezone Offset ตรงตามเวลาไทย UTC+7)

---

## 5. ⏻ การตั้งค่าและ PC Auto-Shutdown (Settings & PC Protection)

- [ ] **การบันทึกการตั้งค่า (Settings Tab):**
  - ทดลองปรับค่า Delay ชัตดาวน์ PC (เช่น 5 นาที) หรือ % แบตเตอรี่ต่ำ
  - กดปุ่ม `💾 Save Settings` แล้วแสดงข้อความบันทึกสำเร็จ
- [ ] **การยกเลิก PC Shutdown (Control Tab):**
  - เมื่อเกิดสภาวะไฟดับและระบบเริ่มนับถอยหลังปิด PC
  - กดปุ่ม `✖ Cancel PC Shutdown` ในหน้า Control สามารถสั่งยกเลิกการปิดเครื่องได้ทันที

---

## 6. 🔌 การสั่งปิดการจ่ายไฟ UPS (UPS Output Shutdown)

- [ ] **การทดสอบ Delay Shutdown:** 
  - *คำเตือน:* UPS จะหยุดจ่ายไฟไปยังอุปกรณ์ที่เชื่อมต่ออยู่ทั้งหมด
  - ระบุเวลา Delay (เช่น 60 วินาที) แล้วกด `Shutdown UPS Output`
  - กดปุ่ม `✖ Cancel UPS Shutdown` เพื่อยกเลิกคำสั่งปิดการจ่ายไฟ

---

## 7. 📦 การ Build และตัวติดตั้ง (Packaging & Installer)

- [ ] **การสร้างไฟล์ executable:** รัน `.\windows\build.ps1` สามารถสร้างไฟล์ `windows/dist/UPS-Monitor.exe` ได้สำเร็จ
- [ ] **การสร้างตัวติดตั้ง Setup:** รัน Inno Setup ผ่าน build script สร้าง `UPS-Monitor-Setup.exe`
- [ ] **การทดสอบติดตั้ง:** ติดตั้งไปยัง `Program Files\UPS Monitor` และเปิดใช้งานได้ปกติ
- [ ] **การถอนการติดตั้ง (Uninstall):** ถอนการติดตั้งผ่าน Apps & Features / Control Panel ได้สมบูรณ์ ไร้ไฟล์ค้าง
