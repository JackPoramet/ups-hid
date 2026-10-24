# คู่มือและ Checklist ตรวจสอบค่า Telemetry แยกรายเครื่อง (NUT Standard)

เอกสารนี้ใช้สำหรับบันทึกและตรวจสอบความถูกต้องของค่าตัวแปรและสถานะการทำงานของ UPS แต่ละเครื่องที่ผ่านการทดสอบจริง โดยอ้างอิงตามมาตรฐานของ **Network UPS Tools (`usbhid-ups` / `blazer_usb`)**

---

## รายการตรวจสอบความถูกต้องแยกรายเครื่อง (Per-Device Checklist)

### 1. **Innova Unity** (Online Double-Conversion 3kVA)
* **สถานะการทำงาน (Operating Status):**
  - [x] `ups.status: OL` — สถานะไฟหลวงปกติ จ่ายไฟตรง (ข้อมูลจริง)
  - [x] `ups.status: OL BYPASS` / `BYPASS` — สถานะเมื่อเปิดใช้งานโหมดบายพาส (ข้อมูลจริง)
  - [x] `ups.status: OB DISCHRG` — สถานะเมื่อถอดปลั๊กหรือไฟดับ (ข้อมูลจริง)
  - [x] `ups.status: OB DISCHRG LB` — สถานะเตือนแบตเตอรี่เหลือน้อยระดับวิกฤต (ข้อมูลจริง และ Fallback ตรวจสอบเกณฑ์แบตเตอรี่)
  - [x] `ups.status: OL CAL` — สถานะเมื่อกำลังทดสอบแบตเตอรี่ Self-Test (ข้อมูลจริง จาก Report 0x24 / Report 0x27)
* **ระบบไฟฟ้าขาเข้า (Input Power):**
  - [x] `input.voltage` (~213.5 - 230.0 V) — แรงดันไฟฟ้าขาเข้าจริง (ข้อมูลจริง จาก USB Control Transfer Report 0x31)
  - [x] `input.voltage.nominal` (230 V) — แรงดันไฟเข้าพิกัด (ข้อมูลจริง)
  - [x] `input.frequency` (50.0 Hz) — ความถี่ไฟฟ้าขาเข้า (ข้อมูลจริง)
  - [x] `input.frequency.nominal` (50 Hz) — ความถี่ไฟเข้าพิกัด (ข้อมูลจริง)
  - [x] `input.transfer.low` (180 V) — จุดตัดเข้าแบตเตอรี่ต่ำสุด (ข้อมูลจริง)
* **ระบบไฟฟ้าขาออก (Output Power):**
  - [x] `output.voltage` (~230.2 V) — แรงดันไฟฟ้าขาออก (ข้อมูลจริง)
  - [x] `output.voltage.nominal` (220 V) — แรงดันไฟออกพิกัด (ข้อมูลจริง)
  - [x] `output.frequency` (50.0 Hz) — ความถี่ไฟฟ้าขาออก (ข้อมูลจริง)
  - [x] `output.frequency.nominal` (50 Hz) — ความถี่ไฟออกพิกัด (ข้อมูลจริง)
  - [x] `output.current` (0.5 A) — กระแสไฟฟ้าขาออก (ข้อมูลจริง)
  - [x] `output.power` (100 W) — กำลังไฟฟ้าจริง Active Power (ข้อมูลจริง จากมิเตอร์ฮาร์ดแวร์)
  - [x] `output.power.apparent` (130 VA) — กำลังไฟฟ้าปรากฏ Apparent Power (ข้อมูลจริง จากมิเตอร์ฮาร์ดแวร์)
  - [x] `outlet.1.status` (`on` / `off`) — สถานะเต้ารับจ่ายไฟ (ข้อมูลจริง)
* **ระบบแบตเตอรี่ (Battery Subsystem):**
  - [x] `battery.charge` (100 %) — เปอร์เซ็นต์แบตเตอรี่ (ข้อมูลจริง)
  - [x] `battery.voltage` (41.2 V) — แรงดันไฟฟ้ากระแสตรงแบตเตอรี่ (ข้อมูลจริง)
  - [x] `battery.runtime` (~5435 วินาที) — เวลาสำรองไฟที่เหลือ (ข้อมูลจริง)
  - [x] `battery.runtime.low` (180 วินาที) — เกณฑ์เตือนเวลาสำรองไฟใกล้หมด (Fallback ตามมาตรฐาน NUT)
  - [x] `battery.charger.status` (`resting` / `floating` / `charging` / `discharging`) — สถานะการชาร์จ (ข้อมูลจริง ประเมินตามสภาวะการทำงาน)
  - [x] `battery.type` (`PbAc`) — ชนิดแบตเตอรี่ตะกั่ว-กรด (Fallback ตามมาตรฐาน NUT)
  - [x] `battery.test.status` (`passed` / `in progress` / `failed`) — ผลการทดสอบแบตเตอรี่ (ข้อมูลจริง จาก Report 0x24)
  - [x] `ups.test.result` (`Done and passed` / `In progress`) — ผลการทดสอบแบตเตอรี่ตามมาตรฐาน NUT
* **ข้อมูลตัวเครื่องและระบบ (Device & System Info):**
  - [x] `ups.load` (13 %) — ภาระโหลดเทียบกับพิกัด (ข้อมูลจริง)
  - [x] `ups.temperature` (31.9 °C) — อุณหภูมิภายในตัวเครื่อง (ข้อมูลจริง จากเซนเซอร์ฮาร์ดแวร์)
  - [x] `ups.power.nominal` (2700 VA) / `ups.realpower.nominal` (2700 W) — พิกัดกำลังไฟฟ้า (ข้อมูลจริง จาก Report 0x74)
  - [x] `ups.firmware` (4.3.18) — เวอร์ชันเฟิร์มแวร์ (ข้อมูลจริง)
  - [x] `device.mfr` (`PHOENIXTEC`) / `device.model` (`Innova Unity`) — ข้อมูลผู้ผลิตและรุ่น (ข้อมูลจริง จาก USB Descriptors)
  - [x] `device.serial` (`CP10T2354690002`) — หมายเลขซีเรียล (ข้อมูลจริง จาก USB Descriptors)
  - [x] `ups.beeper.status` (`enabled`) — สถานะเสียงเตือน (ข้อมูลจริง)

---

### 2. **InnovaBasicG2** (Line-Interactive / Basic G2 3kVA)
* **สถานะการทำงาน (Operating Status):**
  - [x] `ups.status: OL` — สถานะไฟหลวงปกติ จ่ายไฟตรง (ข้อมูลจริง)
  - [x] `ups.status: OL CAL` — สถานะเมื่อกำลังทดสอบแบตเตอรี่ Self-Test (ข้อมูลจริง จาก Report 0x24 [0x01] / [0x02])
  - [x] `ups.status: OB DISCHRG` — สถานะเมื่อถอดปลั๊กหรือไฟดับ (ข้อมูลจริง)
  - [x] `ups.status: OL BYPASS` — สถานะเมื่อเปิดใช้งานโหมดบายพาส (ข้อมูลจริง จาก Report 0x07)
  - [x] `ups.status: OB DISCHRG LB` — สถานะเตือนแบตเตอรี่เหลือน้อย (ข้อมูลจริง และ Fallback ตรวจสอบเกณฑ์แบตเตอรี่)
* **ระบบไฟฟ้าขาเข้า (Input Power):**
  - [x] `input.voltage` (~228.5 - 230.0 V) — แรงดันไฟฟ้าขาเข้าจริง (ข้อมูลจริง จาก USB Control Transfer Report 0x31)
  - [x] `input.voltage.nominal` (230 V) — แรงดันไฟเข้าพิกัด (ข้อมูลจริง)
  - [x] `input.frequency` (49.9 - 50.0 Hz) — ความถี่ไฟฟ้าขาเข้า (ข้อมูลจริง)
  - [x] `input.frequency.nominal` (50 Hz) — ความถี่ไฟเข้าพิกัด (ข้อมูลจริง)
* **ระบบไฟฟ้าขาออก (Output Power):**
  - [x] `output.voltage` (~228.0 - 230.5 V) — แรงดันไฟฟ้าขาออก (ข้อมูลจริง)
  - [x] `output.voltage.nominal` (220 V) — แรงดันไฟออกพิกัด (ข้อมูลจริง)
  - [x] `output.frequency` (49.9 - 50.0 Hz) — ความถี่ไฟฟ้าขาออก (ข้อมูลจริง)
  - [x] `output.frequency.nominal` (50 Hz) — ความถี่ไฟออกพิกัด (ข้อมูลจริง)
  - [x] `output.current` (~0.0 - 0.2 A) — กระแสไฟฟ้าขาออก (ข้อมูลจริง)
  - [x] `output.power` (0 - 20 W) — กำลังไฟฟ้าจริง (ข้อมูลจริง จากมิเตอร์ฮาร์ดแวร์)
  - [x] `output.power.apparent` (0 - 50 VA) — กำลังไฟฟ้าปรากฏ (ข้อมูลจริง จากมิเตอร์ฮาร์ดแวร์)
  - [x] `outlet.1.status` (`on` / `off`) — สถานะเต้ารับจ่ายไฟ (ข้อมูลจริง)
* **ระบบแบตเตอรี่ (Battery Subsystem):**
  - [x] `battery.charge` (99 - 100 %) — เปอร์เซ็นต์แบตเตอรี่ (ข้อมูลจริง)
  - [x] `battery.voltage` (~26.4 - 27.5 V) — แรงดันแบตเตอรี่ (ข้อมูลจริง ดึงโหลดจริงช่วงทดสอบเหลือ ~26.5V และประจุเต็ม ~27.1V)
  - [x] `battery.runtime` (~15146 - 59940 วินาที) — เวลาสำรองไฟที่เหลือ (ข้อมูลจริง)
  - [x] `battery.charger.status` (`resting` / `floating` / `charging` / `discharging`) — สถานะการชาร์จ (ข้อมูลจริง ประเมินตามสภาวะการทำงาน)
  - [x] `battery.type` (`PbAc`) — ชนิดแบตเตอรี่ (Fallback ตามมาตรฐาน NUT)
  - [x] `battery.test.status` (`passed` / `in progress` / `failed`) — ผลการทดสอบแบตเตอรี่ (ข้อมูลจริง จาก Report 0x24)
  - [x] `ups.test.result` (`Done and passed` / `In progress`) — ผลการทดสอบแบตเตอรี่ตามมาตรฐาน NUT
* **ข้อมูลตัวเครื่องและระบบ (Device & System Info):**
  - [x] `ups.load` (0 %) — ภาระโหลด (ข้อมูลจริง)
  - [x] `ups.temperature` (27.9 °C) — อุณหภูมิเครื่อง (ข้อมูลจริง จากเซนเซอร์ฮาร์ดแวร์)
  - [x] `ups.apparent.power.nominal` (900 VA) / `ups.power.nominal` (2700 VA) — พิกัดกำลังไฟฟ้า (ข้อมูลจริง จาก Report 0x74)
  - [x] `device.mfr` (`PHOENIXTEC`) / `device.model` (`InnovaBasicG2`) — ข้อมูลผู้ผลิตและรุ่น (ข้อมูลจริง จาก USB Descriptors)
  - [x] `device.serial` (`CPLUV1279190013`) — หมายเลขซีเรียล (ข้อมูลจริง จาก USB Descriptors)
  - [x] `ups.beeper.status` (`enabled`) — สถานะเสียงเตือน (ข้อมูลจริง)

---

### 3. **Offline UPS 2000D** (Offline / Line-Interactive 2000VA)
* **สถานะการทำงาน (Operating Status):**
  - [x] `ups.status: OFF` — ปิดสวิตช์ UPS (ข้อมูลจริง)
  - [x] `ups.status: OL` — สถานะไฟหลวงปกติ (ข้อมูลจริง)
  - [x] `ups.status: OL CAL` — สถานะเมื่อกำลังทดสอบแบตเตอรี่ Self-Test (ข้อมูลจริง จาก Report 0x24 [0x01] / [0x02])
  - [x] `ups.status: OB DISCHRG` — สถานะเมื่อไฟดับหรือสลับเข้าแบตเตอรี่ (ข้อมูลจริง)
  - [x] `ups.status: OB DISCHRG LB` — สถานะแบตเตอรี่เหลือน้อย (ข้อมูลจริง และ Fallback ตรวจสอบเกณฑ์แบตเตอรี่)
  - [-] `ups.status: BYPASS` — สถานะบายพาส (ไม่มีในฮาร์ดแวร์จริง เนื่องจากเครื่องประเภท Offline ไม่มีวงจรบายพาส)
* **ระบบไฟฟ้าขาเข้า (Input Power):**
  - [x] `input.voltage` (230.0 - 231.0 V) — แรงดันไฟฟ้าขาเข้า (ข้อมูลจริง จาก Report 0x31)
  - [x] `input.voltage.nominal` (220 V) — แรงดันไฟเข้าพิกัด (ข้อมูลจริง)
  - [x] `input.frequency` (50.0 Hz) — ความถี่ไฟฟ้าขาเข้า (Fallback จำลองจากความถี่พิกัด เนื่องจากฮาร์ดแวร์ไม่มีมิเตอร์วัดความถี่ขาเข้า)
  - [x] `input.frequency.nominal` (50 Hz) — ความถี่ไฟเข้าพิกัด (ข้อมูลจริง)
* **ระบบไฟฟ้าขาออก (Output Power):**
  - [x] `output.voltage` (215.0 V ขณะสลับอินเวอร์เตอร์ทดสอบแบตเตอรี่ / 231.0 V ไฟหลวงปกติ) — แรงดันไฟฟ้าขาออก (ข้อมูลจริง จาก Report 0x42)
  - [x] `output.voltage.nominal` (220 V) — แรงดันไฟออกพิกัด (ข้อมูลจริง)
  - [x] `output.frequency` (50.0 - 50.2 Hz) — ความถี่ไฟฟ้าขาออก (ข้อมูลจริง จาก Report 0x42)
  - [x] `output.frequency.nominal` (50 Hz) — ความถี่ไฟออกพิกัด (ข้อมูลจริง)
  - [x] `output.current` — กระแสไฟฟ้าขาออก (คำนวณตามมาตรฐาน NUT จากค่าภาระโหลดและแรงดันขาออก)
  - [x] `output.power` — กำลังไฟฟ้าจริง (คำนวณตามมาตรฐาน NUT จาก Load % x 1200 W)
  - [x] `output.power.apparent` — กำลังไฟฟ้าปรากฏ (คำนวณตามมาตรฐาน NUT จาก Load % x 2000 VA)
  - [x] `outlet.1.status` (`on` / `off`) — สถานะเต้ารับจ่ายไฟ (ข้อมูลจริง)
* **ระบบแบตเตอรี่ (Battery Subsystem):**
  - [x] `battery.charge` (100 %) — เปอร์เซ็นต์แบตเตอรี่ (ข้อมูลจริง จาก Report 0x06)
  - [x] `battery.voltage` (~26.3 - 27.8 V) — แรงดันไฟฟ้าแบตเตอรี่ (ข้อมูลจริง ดึงโหลดจริงช่วงทดสอบเหลือ 26.3 V และประจุเต็ม 27.8 V)
  - [x] `battery.runtime` (~3359 วินาที) — เวลาสำรองไฟที่เหลือ (ข้อมูลจริง จาก Report 0x06)
  - [x] `battery.charger.status` (`resting` / `floating` / `charging` / `discharging`) — สถานะการชาร์จ (ข้อมูลจริง ประเมินตามสภาวะการทำงาน)
  - [x] `battery.type` (`PbAc`) — ชนิดแบตเตอรี่ (Fallback ตามมาตรฐาน NUT)
  - [x] `battery.test.status` (`passed` / `in progress` / `failed`) — ผลการทดสอบแบตเตอรี่ (ข้อมูลจริง จาก Report 0x24)
  - [x] `ups.test.result` (`Done and passed` / `In progress`) — ผลการทดสอบแบตเตอรี่ตามมาตรฐาน NUT
* **ข้อมูลตัวเครื่องและระบบ (Device & System Info):**
  - [x] `ups.load` (0 % เมื่อไม่มีโหลด / แสดงค่าจริงเมื่อต่อโหลด) — ภาระโหลด (ข้อมูลจริง จาก Report 0x07)
  - [x] `ups.temperature` (25.0 °C) — อุณหภูมิเครื่อง (Fallback จำลองค่าคงที่ เนื่องจากฮาร์ดแวร์ไม่มีเซนเซอร์วัดอุณหภูมิ)
  - [x] `ups.power.nominal` (2000 VA) / `ups.realpower.nominal` (1200 W) — พิกัดกำลังไฟฟ้า (ข้อมูลจริง จาก Report 0x74 / meta.json)
  - [x] `device.mfr` (`PPC`) / `device.model` (`Offline UPS`) — ข้อมูลผู้ผลิตและรุ่น (ข้อมูลจริง จาก USB Descriptors)
  - [x] `device.serial` (`000000000`) — หมายเลขซีเรียล (ข้อมูลจริง จาก USB Descriptors)

---

### 4. **MEC0003** (Megatec Q1 Protocol 800VA)
* **สถานะการทำงาน (Operating Status):**
  - [x] `ups.status: OFF` — ปิดสวิตช์ UPS (ข้อมูลจริง ประเมินจากแรงดันขาออกและสวิตช์)
  - [x] `ups.status: OL` — สถานะไฟหลวงปกติ (ข้อมูลจริง จาก Megatec Q1 Index 3)
  - [x] `ups.status: OB` — สถานะเมื่อไฟดับหรือสลับเข้าแบตเตอรี่ (ข้อมูลจริง จาก Megatec Q1 Index 3)
  - [x] `ups.status: OB LB` — สถานะแบตเตอรี่เหลือน้อย (ข้อมูลจริง จาก Megatec Q1 Index 3 และ Fallback ตรวจสอบแรงดันแบตเตอรี่)
  - [x] `ups.status: CAL` / `OFF CAL` — สถานะเมื่อกำลังทดสอบแบตเตอรี่ Self-Test (ควบคุมผ่าน State Machine และ Bit 5 ของ Index 3)
  - [-] `ups.status: BYPASS` — สถานะบายพาส (ไม่มีในฮาร์ดแวร์จริง เนื่องจากเครื่องประเภท Offline ไม่มีวงจรบายพาส)
* **ระบบไฟฟ้าขาเข้า (Input Power):**
  - [x] `input.voltage` (230.8 V) — แรงดันไฟฟ้าขาเข้า (ข้อมูลจริง จาก Megatec Q1 Index 3)
  - [x] `input.voltage.nominal` (220.0 V) — แรงดันไฟเข้าพิกัด (ข้อมูลจริง จาก Megatec Q1 Index 13)
  - [x] `input.frequency` (50.1 Hz) — ความถี่ไฟฟ้าขาเข้า (ข้อมูลจริง จาก Megatec Q1 Index 3)
  - [x] `input.frequency.nominal` (50.0 Hz) — ความถี่ไฟเข้าพิกัด (ข้อมูลจริง จาก Megatec Q1 Index 13)
* **ระบบไฟฟ้าขาออก (Output Power):**
  - [x] `output.voltage` (230.9 V) — แรงดันไฟฟ้าขาออก (ข้อมูลจริง จาก Megatec Q1 Index 3)
  - [x] `output.voltage.nominal` (220 V) — แรงดันไฟออกพิกัด (ข้อมูลจริง จาก Megatec Q1 Index 13)
  - [x] `output.frequency` (50.1 Hz) — ความถี่ไฟฟ้าขาออก (ข้อมูลจริง จาก Megatec Q1 Index 3)
  - [x] `output.frequency.nominal` (50 Hz) — ความถี่ไฟออกพิกัด (ข้อมูลจริง จาก Megatec Q1 Index 13)
  - [x] `output.current` — กระแสไฟฟ้าขาออก (คำนวณตามมาตรฐาน NUT จากค่าภาระโหลดและแรงดันขาออก)
  - [x] `output.power` — กำลังไฟฟ้าจริง (คำนวณตามมาตรฐาน NUT จาก Load % x 528 W)
  - [x] `output.power.apparent` — กำลังไฟฟ้าปรากฏ (คำนวณตามมาตรฐาน NUT จาก Load % x 880 VA)
  - [x] `outlet.1.status` (`on` / `off`) — สถานะเต้ารับจ่ายไฟ (ข้อมูลจริง)
* **ระบบแบตเตอรี่ (Battery Subsystem):**
  - [x] `battery.charge` (100.0 %) — เปอร์เซ็นต์แบตเตอรี่ (คำนวณตามคุณสมบัติทางเคมี Lead-Acid SoC จากแรงดัน Vbat จริง)
  - [x] `battery.voltage` (13.8 V) — แรงดันไฟฟ้าแบตเตอรี่ (ข้อมูลจริง จาก Megatec Q1 Index 3)
  - [x] `battery.voltage.nominal` (12.0 V) — แรงดันแบตเตอรี่พิกัด (ข้อมูลจริง จาก Megatec Q1 Index 13)
  - [x] `battery.charger.status` (`resting` / `floating` / `charging` / `discharging`) — สถานะการชาร์จ (ข้อมูลจริง ประเมินตามสภาวะการทำงานและแรงดัน Vbat)
  - [x] `battery.type` (`PbAc`) — ชนิดแบตเตอรี่ (Fallback ตามมาตรฐาน NUT)
  - [-] `battery.runtime` — เวลาสำรองไฟที่เหลือ (ไม่มีในฮาร์ดแวร์จริง เนื่องจากโปรโตคอล Megatec Q1 ไม่มีฟังก์ชันคำนวณ Runtime)
  - [x] `battery.test.status` (`in progress` / `passed` / `failed` / `aborted`) — สถานะการทดสอบแบตเตอรี่ (ข้อมูลจริง และ State Machine)
  - [x] `ups.test.result` (`In progress` / `Done and passed` / `Done and error` / `Aborted`) — ผลการทดสอบแบตเตอรี่ตามมาตรฐาน NUT
  - [x] `ups.test.date` — วันและเวลาที่สั่งทดสอบแบตเตอรี่ล่าสุด
* **ข้อมูลตัวเครื่องและระบบ (Device & System Info):**
  - [x] `ups.load` (แสดงค่าโหลด % จาก Megatec Q1 Index 3) — ภาระโหลด (ข้อมูลจริง จาก Megatec Q1 Index 3)
  - [x] `ups.temperature` (25.0 °C) — อุณหภูมิเครื่อง (Fallback จำลองค่าคงที่ เนื่องจากฮาร์ดแวร์ไม่มีเซนเซอร์วัดอุณหภูมิ)
  - [x] `ups.power.nominal` (880 VA) / `ups.realpower.nominal` (528 W) — พิกัดกำลังไฟฟ้า (ข้อมูลจริง คำนวณจากแรงดันและกระแสพิกัด Index 13)
  - [x] `device.mfr` (`MEC`) / `device.model` (`MEC0003`) — ข้อมูลผู้ผลิตและรุ่น (ข้อมูลจริง จาก USB Descriptors)
  - [x] `device.serial` (`MEC0003`) — หมายเลขซีเรียล (ข้อมูลจริง จาก USB Descriptors)
