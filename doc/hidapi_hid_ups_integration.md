# HID UPS Integration: hidapi.py + hid_ups.py

## สรุปสั้น
สองไฟล์นี้ทำงานร่วมกันได้ และถูกออกแบบให้ต่อกันแบบ file-based workflow (ไม่ import กันโดยตรง)

- hidapi.py: ดึง descriptor/caps จากอุปกรณ์ HID แล้ว export เป็นไฟล์
- hid_ups.py: โหลดไฟล์ descriptor ที่ export มา เพื่อเลือก Report ID แบบ dynamic ก่อนสแกนค่า UPS

## บทบาทของแต่ละไฟล์

### 1) hidapi.py
หน้าที่หลัก
- ค้นหาอุปกรณ์ HID จาก VID/PID และ usage
- อ่าน raw HID report descriptor ผ่าน DeviceIoControl
- ถ้าอ่าน descriptor ไม่ได้ จะ fallback ไป collection descriptor/caps
- เขียนผลลัพธ์ลงไฟล์

ไฟล์ผลลัพธ์ default
- report_descriptor_live.bin
- report_descriptor_live.txt
- report_descriptor_meta.json

จุดอ้างอิงในโค้ด
- default output names: hidapi.py บรรทัด 31-33
- อ่าน descriptor หลัก: hidapi.py บรรทัด 504
- เขียนไฟล์ output: hidapi.py บรรทัด 391 และ 590

### 2) hid_ups.py
หน้าที่หลัก
- เปิด UPS แล้วสแกน Feature Reports หลายขนาด/หลายรอบ
- โหลด descriptor profile เพื่อช่วยเลือก Report IDs ที่น่าจะเกี่ยวข้อง
- decode ค่าที่ยืนยันได้ + tentative values สำหรับ reverse mapping
- export JSON ผลลัพธ์สแกน

จุดอ้างอิงในโค้ด
- input descriptor defaults: hid_ups.py บรรทัด 28-29
- รับอาร์กิวเมนต์ descriptor: hid_ups.py บรรทัด 1076-1077
- โหลด descriptor profile: hid_ups.py บรรทัด 247 และ 1128
- เลือก base/request report ids: hid_ups.py บรรทัด 1133 และ 1161
- export JSON payload: hid_ups.py บรรทัด 1028

## การเชื่อมกันของสองไฟล์

### สัญญาการเชื่อม (Integration Contract)
- hidapi.py สร้างไฟล์ descriptor
- hid_ups.py อ่านไฟล์ descriptor ผ่าน --descriptor-bin และ --descriptor-txt

### จุดที่ต้องระวัง
ค่า default ปัจจุบันตรงกันแล้ว
- hidapi.py default txt = report_descriptor_live.txt
- hid_ups.py default txt = report_descriptor_live.txt

คำแนะนำ
- ถ้าใช้ไฟล์ชื่ออื่น ให้ระบุ --descriptor-bin/--descriptor-txt ให้ตรงกับไฟล์ที่ export จริง

## ลำดับการใช้งานที่แนะนำ

ขั้นที่ 1: ดึง descriptor จากอุปกรณ์

.venv\Scripts\python.exe hidapi.py --vid 0x06DA --pid 0xFFFF --usage-page 0x84 --usage 0x04

ขั้นที่ 2: สแกน UPS โดยใช้ descriptor ที่เพิ่ง export

.venv\Scripts\python.exe hid_ups.py --descriptor-bin report_descriptor_live.bin --descriptor-txt report_descriptor_live.txt --passes 8 --retries 2 --include-zero --input-sec 30 --json ups_scan_dynamic.json

## วิธีเช็กว่าเชื่อมกันสำเร็จ
1. ใน output ของ hid_ups.py ต้องเห็น Descriptor profile และ source
2. ถ้า source เป็น hid_parser หรือ caps_text แปลว่าโหลด profile ได้
3. scan.requested_ids และ scan.captured_ids ใน JSON ควรมีความสอดคล้องกับ descriptor profile

## โหมด fallback
หากยังไม่มี descriptor files หรือไม่ต้องใช้ profile
- ใช้ --no-descriptor-profile
- hid_ups.py จะ fallback ไปสแกนตามช่วง RID ที่กำหนด

## หมายเหตุ
- สองไฟล์นี้สามารถรันแยกได้
- แต่เมื่อใช้ร่วมกันตามลำดับ จะได้ dynamic report selection ที่แม่นกว่าการไล่ RID แบบกว้างเพียงอย่างเดียว
- ups_monitor_gui.py รวม hidapi.py ไว้ภายในแล้ว — ไม่ต้องรัน hidapi.py แยกก่อน

## คำสั่งควบคุม UPS (Writable Feature Reports)

Feature Reports ที่มี Bit0=Data + Volatile สามารถเขียนได้ผ่าน `SetFeatureReport`:

### คำสั่งมาตรฐาน (HID Power Device / Battery System)

| RID    | Usage                      | ความหมาย                              | ขนาด        | ค่าพิเศษ                   |
|--------|----------------------------|---------------------------------------|-------------|---------------------------|
| `0x24` | `0x0058` Test              | สั่งรัน Self-Test แบตเตอรี่           | 8-bit       | `0x01`=start, `0x00`=abort |
| `0x09` | `0x0057` Delay Before Shutdown | หน่วงเวลา (วินาที) ก่อนปิด output | 32-bit LE   | `0xFFFFFFFF`=cancel        |
| `0x0A` | `0x0056` Delay Before Startup  | หน่วงเวลา (วินาที) ก่อนเปิด output หลังไฟกลับ | 32-bit LE | —         |
| `0x05` | `0x006C` Switchable        | เปิด/ปิด outlet                       | 8-bit       | `0x01`=on, `0x00`=off      |
| `0x0D` | `0x0042` Config Frequency  | ตั้งค่าความถี่ nominal                | 8-bit       | Hz                         |
| `0x72` | `0x0040` Config Voltage    | ตั้งค่าแรงดัน nominal                 | 16-bit LE   | V                          |
| `0x17` | `0x002A` Remaining Time Limit | ตั้ง alarm เวลาแบตคงเหลือ          | 16-bit LE   | วินาที                     |

### Vendor-defined (ยังไม่ทราบความหมาย)

| RID              | Collection    |
|------------------|---------------|
| `0x2A`           | Battery       |
| `0x25`           | Battery       |
| `0x22`           | Charger       |
| `0x12`, `0x0E`, `0x11`, `0x29` | Vendor |
| `0xFE`, `0xFF`   | Vendor (อาจเป็น config พิเศษ/firmware) |

### ตัวอย่างการส่งคำสั่งใน Python

```python
# Self-Test
h.send_feature_report([0x24, 0x01])

# Shutdown หลังจาก 60 วินาที
delay = 60
h.send_feature_report([0x09, delay & 0xFF, (delay>>8)&0xFF, (delay>>16)&0xFF, (delay>>24)&0xFF])

# Cancel Shutdown
h.send_feature_report([0x09, 0xFF, 0xFF, 0xFF, 0xFF])

# Startup delay 10 วินาที (UPS จะเปิดอีกครั้งหลังไฟกลับ)
startup = 10
h.send_feature_report([0x0A, startup & 0xFF, (startup>>8)&0xFF, (startup>>16)&0xFF, (startup>>24)&0xFF])

# Config Voltage 220V
h.send_feature_report([0x72, 220 & 0xFF, (220>>8)&0xFF])

# Config Frequency 50Hz
h.send_feature_report([0x0D, 50])
```

### ข้อควรระวัง

- `OutputReportByteLength = 0` — ไม่มี Output Report, ใช้ `SetFeatureReport` เท่านั้น
- `Delay Before Shutdown = 0` จะปิด output **ทันที**
- ควรตั้ง `Delay Before Startup > 0` ก่อนเสมอ เพื่อให้ UPS รีสตาร์ทเองหลังไฟกลับ
- `ups_monitor_gui.py` มี **Control Panel** (ปุ่ม ⚙ Control) รองรับคำสั่งเหล่านี้แบบ GUI พร้อม confirmation dialog
