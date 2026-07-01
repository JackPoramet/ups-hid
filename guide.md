# 📖 คู่มือการพัฒนาระบบ Auto-Discovery สำหรับ USB HID UPS (Report Descriptor Parsing)

การทำ Auto-Discovery หรือ Dynamic Mapping คือการเขียนโปรแกรมให้เข้าไปอ่าน **"คู่มือที่ฝังอยู่ในอุปกรณ์" (HID Report Descriptor)** เพื่อค้นหาว่าค่าต่างๆ (เช่น สถานะไฟดับ, แบตเตอรี่, แรงดันไฟ) ถูกเก็บไว้ที่ Report ID หมายเลขใดแบบอัตโนมัติ

วิธีนี้ช่วยให้ซอฟต์แวร์ Agent มีความยืดหยุ่นสูง สามารถนำไปใช้กับ UPS ยี่ห้อใด หรือรุ่นใดก็ได้ที่รองรับมาตรฐาน USB HID Power Device (0x0084) โดยไม่ต้องกลับมาแก้ไขโค้ด (Hardcode) ใหม่ทุกครั้งที่มีการเปลี่ยนฮาร์ดแวร์

---

## 🧠 1. ทำความเข้าใจโครงสร้างข้อมูล (The Concept)

มาตรฐาน USB HID จะจัดเก็บข้อมูลในรูปแบบลำดับชั้น (Hierarchical) การจะหาข้อมูลที่ต้องการ โปรแกรมจะต้องทำการค้นหาคีย์เวิร์ด (Usage) ภายใต้หมวดหมู่ (Usage Page) ที่ถูกต้อง:

* **Usage Page:** หมวดหมู่หลัก เช่น `0x0084` หมายถึง Power Device Page
* **Usage:** ตัวระบุข้อมูล (Data Point) เช่น:
    * `0x00D0` = AC Present (สถานะไฟบ้าน)
    * `0x0045` = Discharging (สถานะการใช้แบตเตอรี่)
    * `0x0066` = Remaining Capacity (ความจุแบตเตอรี่ %)
    * `0x0030` = Voltage (แรงดันไฟฟ้า)
* **Report ID:** หมายเลขหน้าต่างข้อมูล (ตัวแปรที่เราจะใช้คำสั่ง `get_feature_report(ID)` เพื่อดึงค่าออกมา)

---

## 🛠️ 2. เครื่องมือและไลบรารีที่แนะนำ (Environment Setup)
การเขียน Parser เพื่อถอดรหัส Raw Bytes ของ Descriptor ด้วยตัวเองจากศูนย์มีความซับซ้อน แนะนำให้ใช้ Python ร่วมกับไลบรารีจัดการ USB HID:
1.  **`hidapi` (ไลบรารี `hid`):** สำหรับการเปิดพอร์ตและดึง Raw Descriptor ออกมาจากฮาร์ดแวร์
2.  **`hid-parser` หรือ `pyusb`:** สำหรับการนำ Raw Descriptor มาถอดรหัส (Parse) เป็นโครงสร้าง Object ที่อ่านง่ายด้วยโค้ด

---

## 🔄 3. ขั้นตอนการดำเนินการ (Workflow)

### Step 1: เชื่อมต่อและดึง Raw Descriptor
เริ่มต้นด้วยการเปิดการเชื่อมต่อไปยังอุปกรณ์ผ่าน `Vendor ID` และ `Product ID` จากนั้นใช้คำสั่งเพื่อขอดึงโครงสร้างคู่มือออกมาทั้งหมด
* **Output ที่ได้:** จะเป็น Array ของ Raw Bytes (เช่น `[0x06, 0x84, 0x00, 0x09, 0x04, ...]`)

### Step 2: ถอดรหัสและสร้างตาราง Mapping (Parse & Map)
ส่ง Raw Bytes ไปให้ Parser ค้นหาคีย์เวิร์ด (Usage) ที่เราต้องการ และเก็บค่า `Report ID`, `Bit Size` และ `Data Index` ลงใน Dictionary เพื่อเตรียมใช้งาน

**ตารางเป้าหมายที่โปรแกรมต้องค้นหา:**
| ข้อมูลที่ต้องการ | Usage Page | Usage | ตัวแปรที่จะบันทึกไว้ในระบบ |
| :--- | :--- | :--- | :--- |
| **ไฟดับ (AC Fail)** | `0x0084` | `0x00D0` | `map_ac_present_id` |
| **ความจุแบตเตอรี่ (%)** | `0x0085` | `0x0066` | `map_battery_id` |
| **แรงดันไฟ (Voltage)** | `0x0084` | `0x0030` | `map_voltage_id` |

### Step 3: เริ่มต้นลูปอ่านข้อมูล (Data Acquisition Loop)
เมื่อได้ Dictionary ที่จับคู่ Report ID ไว้เรียบร้อยแล้ว ซอฟต์แวร์ Agent จะเริ่มเข้าสู่ลูปการทำงานหลัก (Main Loop) เพื่ออ่านข้อมูลจริงตาม ID ที่สแกนเจอ

---

## 💻 4. ตัวอย่างการวางโครงสร้างโค้ด (Python Pseudo-Code)

นี่คือแนวทางการเขียนคลาสสำหรับจัดการ Auto-Discovery ใน Python เพื่อนำไปเป็นพื้นฐานของระบบ Agent:

```python
import hid

class UPSAutoDiscoveryAgent:
    def __init__(self, vid, pid):
        self.vid = vid
        self.pid = pid
        self.device = hid.device()
        self.data_map = {} # เก็บ Mapping Table

    def connect_and_discover(self):
        """เชื่อมต่อและสร้าง Data Mapping อัตโนมัติ"""
        self.device.open(self.vid, self.pid)
        
        # 1. ดึง Raw Descriptor (สมุดคู่มือ)
        raw_descriptor = self.device.get_report_descriptor()
        
        # 2. ส่งให้ Parser ถอดรหัส (ใช้ไลบรารี หรือเขียน Logic สแกน Hex)
        # ตัวอย่างนี้เป็นการจำลองผลลัพธ์จาก Parser
        parsed_data = self._parse_descriptor(raw_descriptor)
        
        # 3. จับคู่ค่า (Mapping)
        self.data_map['AC_PRESENT_ID'] = self._find_report_id(parsed_data, usage=0x00D0)
        self.data_map['BATTERY_PERCENT_ID'] = self._find_report_id(parsed_data, usage=0x0066)
        
        print("✅ Auto-Discovery สำเร็จ:", self.data_map)

    def _parse_descriptor(self, raw_bytes):
        """ลอจิกจำลองสำหรับการถอดรหัส Descriptor"""
        # (ในสเต็ปนี้ควรเรียกใช้ไลบรารี hid-parser หรือเขียน Regex เพื่อสแกนโครงสร้าง)
        pass 

    def _find_report_id(self, parsed_data, usage):
        """ลอจิกค้นหาหมายเลข Report ID จากโครงสร้างที่ถูกแกะแล้ว"""
        pass

    def run_monitor(self):
        """ลูปอ่านข้อมูลและประมวลผลเพื่อส่งต่อให้ RUTS Energy Management System"""
        ac_id = self.data_map.get('AC_PRESENT_ID')
        batt_id = self.data_map.get('BATTERY_PERCENT_ID')

        while True:
            # ดึงสถานะไฟตกไฟดับ
            if ac_id:
                ac_status = self.device.get_feature_report(ac_id, 8)
                is_ac_fail = (ac_status[1] == 0) # ตัวอย่างเช็ค Bit ที่ 1
                
            # ดึงสถานะแบตเตอรี่
            if batt_id:
                batt_status = self.device.get_feature_report(batt_id, 8)
                batt_percent = batt_status[1]
                
            # TODO: แปลงข้อมูลเป็น JSON แล้วยิงผ่าน MQTT / REST API เข้าสู่ Backend ต่อไป
            print(f"สเตตัสไฟ: {'ไฟดับ' if is_ac_fail else 'ปกติ'} | แบตเตอรี่: {batt_percent}%")
            time.sleep(2)

# การเรียกใช้งาน
if __name__ == "__main__":
    agent = UPSAutoDiscoveryAgent(0x06DA, 0xFFFF)
    agent.connect_and_discover()
    agent.run_monitor()