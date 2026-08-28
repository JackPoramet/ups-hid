# 📋 คู่มือและ Checklist ตรวจสอบค่า Telemetry แยกรายเครื่อง (NUT Standard)

เอกสารนี้ใช้สำหรับไล่ตรวจสอบความถูกต้องของค่าตัวแปรและสถานะการทำงานของ UPS แต่ละเครื่อง โดยอ้างอิงตามมาตรฐานของ Network UPS Tools (`usbhid-ups.c`)

---

## 🔍 รายการตรวจสอบความถูกต้องแยกรายเครื่อง (Per-Device Checklist)

### 1. 🏢 **Innova Unity** (Online UPS 3kVA)
- **สถานะการทำงาน (Operating Status):**
  - [x] `ups.status: OL` — สถานะไฟหลวงปกติ (จ่ายไฟตรง)
  - [x] `ups.status: OL BYPASS` / `BYPASS` — สถานะเมื่อเปิดใช้งานโหมดบายพาส
  - [x] `ups.status: OB DISCHRG LB` — สถานะเตือนแบตเตอรี่เหลือน้อย (วิกฤต)
  - [x] `ups.status: OB DISCHRG`

- **ระบบไฟฟ้าขาเข้า (Input Power):**
  - [x] `input.voltage` (~213.5 - 230.0 V) — แรงดันไฟฟ้าขาเข้า
  - [x] `input.voltage.nominal` (230 V) — แรงดันไฟเข้าพิกัด
  - [x] `input.frequency` (50.0 Hz) — ความถี่ไฟฟ้าขาเข้า
  - [x] `input.frequency.nominal` (50 Hz) — ความถี่ไฟเข้าพิกัด
  - [x] `input.transfer.low` (180 V) — จุดตัดเข้าแบตเตอรี่ต่ำสุด
- **ระบบไฟฟ้าขาออก (Output Power):**
  - [x] `output.voltage` (~230.2 V) — แรงดันไฟฟ้าขาออก
  - [x] `output.voltage.nominal` (220 V) — แรงดันไฟออกพิกัด
  - [x] `output.frequency` (50.0 Hz) — ความถี่ไฟฟ้าขาออก
  - [x] `output.frequency.nominal` (50 Hz) — ความถี่ไฟออกพิกัด
  - [x] `output.current` (0.5 A) — กระแสไฟฟ้าขาออก
  - [x] `output.power` (100 W) — กำลังไฟฟ้าจริง (Active Power)
  - [x] `output.power.apparent` (130 VA) — กำลังไฟฟ้าปรากฏ (Apparent Power)
  - [x] `outlet.1.status` (`on`) — สถานะเต้ารับจ่ายไฟ
- **ระบบแบตเตอรี่ (Battery Subsystem):**
  - [x] `battery.charge` (100 %) — เปอร์เซ็นต์แบตเตอรี่
  - [x] `battery.voltage` (41.2 V) — แรงดันไฟฟ้ากระแสตรงแบตเตอรี่
  - [x] `battery.runtime` (~5435 วินาที) — เวลาสำรองไฟที่เหลือ
  - [x] `battery.runtime.low` (180 วินาที) — เกณฑ์เตือนแบตใกล้หมด
  - [x] `battery.charger.status` (`floating` / `charging` / `discharging`) — สถานะการชาร์จ
  - [x] `battery.type` (`PbAc`) — ชนิดแบตเตอรี่
  - [ ] `battery.test.status` (`passed` / `failed`) — ผลการทดสอบแบตเตอรี่
- **ข้อมูลตัวเครื่องและระบบ (Device & System Info):**
  - [x] `ups.load` (13 %) — ภาระโหลดเทียบกับพิกัด
  - [x] `ups.temperature` (31.9 °C) — อุณหภูมิภายในตัวเครื่อง
  - [x] `ups.power.nominal` (2700 VA) / `ups.realpower.nominal` (2700 W)
  - [x] `ups.firmware` (4.3.18) — เวอร์ชันเฟิร์มแวร์
  - [x] `device.mfr` (`PHOENIXTEC`) / `device.model` (`Innova Unity`)
  - [x] `device.serial` (`CP10T2354690002`) — Serial Number
  - [x] `ups.beeper.status` (`enabled`) — สถานะเสียงเตือน

---

### 2. 🏢 **InnovaBasicG2** (Line-Interactive / Basic G2)
- **สถานะการทำงาน (Operating Status):**
  - [x] `ups.status: OL` — สถานะไฟหลวงปกติ (จ่ายไฟตรง)
  - [x] `ups.status: OB DISCHRG` — สถานะเมื่อถอดปลั๊ก / ไฟดับ (ดึงไฟจากแบตเตอรี่)
  - [x] `ups.status: OL BYPASS`  — สถานะเมื่อเปิดใช้งานโหมดบายพาส (Report 0x07 `d[6]=2`)
  - [x] `ups.status: OB DISCHRG LB` — สถานะเตือนแบตเตอรี่เหลือน้อย
- **ระบบไฟฟ้าขาเข้า (Input Power):**
  - [x] `input.voltage` (~229.1 - 230.0 V) — แรงดันไฟฟ้าขาเข้า (Report 0x31 Little-Endian)
  - [x] `input.voltage.nominal` (230 V) — แรงดันไฟเข้าพิกัด
  - [x] `input.frequency` (49.9 - 50.0 Hz) — ความถี่ไฟฟ้าขาเข้า
  - [x] `input.frequency.nominal` (50 Hz) — ความถี่ไฟเข้าพิกัด
- **ระบบไฟฟ้าขาออก (Output Power):**
  - [x] `output.voltage` (~228.0 - 231.2 V) — แรงดันไฟฟ้าขาออก (Report 0x42 `d[11..12]`)
  - [x] `output.voltage.nominal` (220 V) — แรงดันไฟออกพิกัด
  - [x] `output.frequency` (49.9 - 50.0 Hz) — ความถี่ไฟฟ้าขาออก (Report 0x42 `d[8..9]`)
  - [x] `output.frequency.nominal` (50 Hz) — ความถี่ไฟออกพิกัด
  - [x] `output.current` (~0.0 - 0.2 A) — กระแสไฟฟ้าขาออก (Report 0x42 `d[6..7]`)
  - [x] `output.power` (0 - 20 W)
  - [x] `output.power.apparent` — กำลังไฟฟ้าปรากฏ (Apparent Power)
  - [x] `outlet.1.status` (`on`) — สถานะเต้ารับจ่ายไฟ
- **ระบบแบตเตอรี่ (Battery Subsystem):**
  - [x] `battery.charge` (100 %) — เปอร์เซ็นต์แบตเตอรี่
  - [x] `battery.voltage` (~27.0 - 30.2 V) — แรงดันแบตเตอรี่ (Report 0x07 `d[15..16]`)
  - [x] `battery.runtime` (~15146 - 59940 วินาที) — เวลาสำรองไฟที่เหลือ
  - [x] `battery.charger.status` (`floating` / `charging`) — สถานะการชาร์จ
  - [x] `battery.type` (`PbAc`) — ชนิดแบตเตอรี่
  - [ ] `battery.test.status` (`passed`) — ผลการทดสอบแบตเตอรี่
- **ข้อมูลตัวเครื่องและระบบ (Device & System Info):**
  - [x] `ups.load` (ตรงกับหน้าจอเครื่องจริง เช่น 4%, 9%) — ภาระโหลด (Report 0x07 `d[7]`)
  - [x] `ups.temperature` (28.9 °C) — อุณหภูมิเครื่อง (Report 0x07 `d[9..10]`)
  - [x] `ups.power.nominal` (2700 VA) / `ups.realpower.nominal` (2700 W)
  - [x] `device.mfr` (`PHOENIXTEC`) / `device.model` (`InnovaBasicG2`)
  - [x] `device.serial` (`CPLUV1279190013`) — Serial Number
  - [x] `ups.beeper.status` (`enabled`) — สถานะเสียงเตือน

---

### 3. 🏢 **Offline UPS 2000D** (Offline / Line-Interactive 2000D)
- **สถานะการทำงาน (Operating Status):**
  - [x] `ups.status: OFF` — ปิด UPS
  - [x] `ups.status: OL` — สถานะไฟหลวงปกติ
  - [x] `ups.status: OB DISCHRG` — สถานะเมื่อไฟดับ / สลับเข้าแบตเตอรี่
  - [ ] `ups.status: OB LB` — สถานะแบตเตอรี่เหลือน้อย
- **ระบบไฟฟ้าขาเข้า (Input Power):**
  - [x] `input.voltage` (231.0 V) — แรงดันไฟฟ้าขาเข้า
  - [x] `input.voltage.nominal` (220 V) — แรงดันไฟเข้าพิกัด
  - [x] `input.frequency` (50.0 Hz) — ความถี่ไฟฟ้าขาเข้า (Smart Fallback)
  - [x] `input.frequency.nominal` (50 Hz) — ความถี่ไฟเข้าพิกัด
- **ระบบไฟฟ้าขาออก (Output Power):**
  - [x] `output.voltage` (231.0 V) — แรงดันไฟฟ้าขาออก
  - [x] `output.voltage.nominal` (220 V) — แรงดันไฟออกพิกัด
  - [x] `output.frequency` (50.2 Hz) — ความถี่ไฟฟ้าขาออก
  - [x] `output.frequency.nominal` (50 Hz) — ความถี่ไฟออกพิกัด
  - [x] `outlet.1.status` (`on` `off`) — สถานะเต้ารับจ่ายไฟ
- **ระบบแบตเตอรี่ (Battery Subsystem):**
  - [x] `battery.charge` (100 %) — เปอร์เซ็นต์แบตเตอรี่
  - [x] `battery.voltage` (27.7 V) — แรงดันไฟฟ้าแบตเตอรี่
  - [x] `battery.runtime` (~3359 วินาที) — เวลาสำรองไฟที่เหลือ
  - [x] `battery.charger.status` (`resting` / `floating` / `charging`) — สถานะการชาร์จ
  - [x] `battery.type` (`PbAc`) — ชนิดแบตเตอรี่
  - [ ] `battery.test.status` (`passed`) — ผลการทดสอบแบตเตอรี่
- **ข้อมูลตัวเครื่องและระบบ (Device & System Info):**
  - [x] `ups.load` (0 % เมื่อไม่มีโหลด / แสดงค่าจริงเมื่อต่อโหลด)
  - [ไม่มี] `ups.temperature` (25.0 °C) — อุณหภูมิ Fallback
  - [x] `ups.power.nominal` (2700 VA) / `ups.realpower.nominal` (2700 W)
  - [x] `device.mfr` (`PPC`) / `device.model` (`Offline UPS`)
  - [x] `device.serial` (`000000000`) — Serial Number จากโรงงาน

---

### 4. 🏢 **MEC0003** (Megatec Q1 Protocol)
- **สถานะการทำงาน (Operating Status):**
  - [x] `ups.status: OL` — สถานะไฟหลวงปกติ
  - [ ] `ups.status: OB` — สถานะเมื่อไฟดับ / สลับเข้าแบตเตอรี่
  - [ ] `ups.status: OB LB` — สถานะแบตเตอรี่เหลือน้อย
  - [ ] `ups.status: BYPASS` — สถานะเมื่อเข้า Bypass
- **ระบบไฟฟ้าขาเข้า (Input Power):**
  - [x] `input.voltage` (230.8 V) — แรงดันไฟฟ้าขาเข้า
  - [x] `input.voltage.nominal` (220.0 V) — แรงดันไฟเข้าพิกัด
  - [x] `input.frequency` (50.1 Hz) — ความถี่ไฟฟ้าขาเข้า
  - [x] `input.frequency.nominal` (50.0 Hz) — ความถี่ไฟเข้าพิกัด
- **ระบบไฟฟ้าขาออก (Output Power):**
  - [x] `output.voltage` (230.9 V) — แรงดันไฟฟ้าขาออก
  - [x] `output.voltage.nominal` (220 V) — แรงดันไฟออกพิกัด
  - [x] `output.frequency` (50.1 Hz) — ความถี่ไฟฟ้าขาออก
  - [x] `output.frequency.nominal` (50 Hz) — ความถี่ไฟออกพิกัด
  - [x] `outlet.1.status` (`on` / `off`) — สถานะเต้ารับจ่ายไฟ
- **ระบบแบตเตอรี่ (Battery Subsystem):**
  - [x] `battery.charge` (100.0 %) — เปอร์เซ็นต์แบตเตอรี่
  - [ ] `battery.voltage` (27.6 V) — แรงดันไฟฟ้าแบตเตอรี่ (Megatec `v_bat`)
  - [ไม่มี] `battery.runtime` — เวลาสำรองไฟที่เหลือ
  - [ ] `battery.charger.status` (`floating` / `charging`) — สถานะการชาร์จ
  - [x] `battery.type` (`PbAc`) — ชนิดแบตเตอรี่
  - [ ] `battery.voltage.nominal` (12.0 V / 24.0 V) — แรงดันแบตเตอรี่พิกัด
- **ข้อมูลตัวเครื่องและระบบ (Device & System Info):**
  - [ ] `ups.load` (แสดงค่าโหลด % จาก Megatec Q1)
  - [ไม่มี] `ups.temperature` (25.0 °C) — อุณหภูมิ Fallback
  - [ ] `ups.power.nominal` (2700 VA) / `ups.realpower.nominal` (2700 W)
  - [x] `device.mfr` (`MEC`) / `device.model` (`MEC0003`)
  - [x] `device.serial` (`MEC0003`) — Serial Number ถูกต้อง (ไม่ถูกทับด้วย 2700)
