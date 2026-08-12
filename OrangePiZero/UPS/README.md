# Enerex Universal UPS Bridge

โฟลเดอร์นี้รวบรวมไฟล์สำหรับ Deploy ระบบ UPS Telemetry Bridge บนบอร์ด Orange Pi Zero เพื่อใช้ในการอ่านค่า UPS รุ่นต่างๆ (Phoenixtec, Enerex, MEC) ผ่าน USB HID และแปลงข้อมูลส่งเข้าสู่ระบบ NUT (`upsd`) แบบอัตโนมัติ

## โครงสร้างไฟล์
- `enerex_ups_bridge.py` : สคริปต์หลักที่ทำหน้าที่สแกนหา UPS, เชื่อมต่อ, อ่านค่าผ่านโปรโตคอล, และแปลงเป็นไฟล์สำหรับ `dummy-ups`
- `install.sh` : สคริปต์สำหรับติดตั้ง Service, จัดการสิทธิ์การเข้าถึง, และจัดการคอนฟิกของ NUT (`/etc/nut/ups.conf`)
- `ups_module/` : ไลบรารีหลัก (core) ที่ใช้ในการดึงข้อมูลจากฮาร์ดแวร์ UPS ตามโปรไฟล์รุ่นต่างๆ (รองรับทั้ง Megatec และ HID)

## หลักการทำงาน (Architecture & Workflow)
ระบบนี้ถูกออกแบบมาเพื่อเป็น **"สะพานเชื่อม" (Bridge)** ระหว่างอุปกรณ์ฮาร์ดแวร์ UPS (ที่มีโปรโตคอลเฉพาะตัวและไม่รองรับ NUT โดยตรง) กับระบบจัดการพลังงาน NUT (Network UPS Tools) โดยมีลำดับการทำงานดังนี้:

1. **Auto-Detection:** สคริปต์ `enerex_ups_bridge.py` จะคอยสแกนหาอุปกรณ์ USB HID ที่เสียบเข้ามา (ดูจาก VID/PID) เมื่อพบอุปกรณ์ จะตรวจสอบโปรไฟล์ผ่าน `ups_module/device_registry.py` ว่าตรงกับรุ่นไหน (เช่น Innova Unity, Basic G2, Offline 2000D)
2. **Data Polling & Decoding:** สคริปต์จะวนลูปอ่านค่าจาก UPS ทุกๆ 2 วินาที (Poll Interval) โดยส่งคำสั่งดึงข้อมูล (Feature Reports) ไปยังฮาร์ดแวร์ จากนั้น `ups_module/core.py` จะทำหน้าที่ **ถอดรหัส (Decode)** ข้อมูลดิบที่ได้มา เช่น โวลต์, เฮิรตซ์, ระดับแบตเตอรี่ โดยปรับการถอดรหัสให้ตรงกับ Endianness และ Offset ของแต่ละรุ่น
3. **NUT Translation:** ข้อมูลที่ถอดรหัสแล้ว จะถูกแปลงให้อยู่ในรูปแบบตัวแปรมาตรฐานของ NUT (เช่น `input.voltage`, `ups.status`)
4. **Dummy-UPS Interfacing:** ข้อมูลทั้งหมดจะถูกเขียนลงไปในไฟล์ชั่วคราว แล้วสลับ (Atomic Rename) ไปที่ `/etc/nut/enerex-ups.dev` 
5. **NUT Integration:** ไดรเวอร์ `dummy-ups` ของระบบ NUT จะเข้ามาอ่านไฟล์ `.dev` นี้ ทำให้เซอร์วิส `upsd` (NUT Server) นำข้อมูลไปใช้ต่อได้ทันที เสมือนว่า UPS ตัวนี้รองรับ NUT แบบ Native

## วิธีการใช้งาน (Deployment)

1. นำโฟลเดอร์นี้ทั้งหมด (`UPS`) หรือเฉพาะโฟลเดอร์/ไฟล์ ที่ต้องการแก้ไข ไปวางที่ `/home/UPS/` บนบอร์ด Orange Pi
2. รันคำสั่งติดตั้งและรีสตาร์ทเซอร์วิส:
   ```bash
   cd /home/UPS
   sudo bash install.sh
   ```
3. ตรวจสอบความถูกต้องของข้อมูล (รอประมาณ 2-5 วินาทีหลังรันสคริปต์เพื่อให้ระบบตั้งไข่):
   ```bash
   upsc enerex-ups
   ```
