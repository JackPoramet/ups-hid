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
```

---

---

# 🔬 คู่มือ Reverse Engineering: แกะโปรแกรม WinpowerG2

## ภาพรวม

WinpowerG2 คือ UPS management software ของ Phoenixtec (Eaton) ที่ใช้งานได้บน Linux
แทนที่จะใช้ HID driver มาตรฐาน (hidraw + ioctl) โปรแกรมนี้สื่อสารกับ UPS ผ่าน **libusb โดยตรง** 
ด้วย `USBDEVFS_CONTROL` ioctl ไปยัง `/dev/bus/usb/BUS/DEV`

---

## เครื่องมือที่ใช้

### 1. usbmon — จับ USB traffic แบบ real-time

```bash
# ตรวจสอบและ enable
sudo modprobe usbmon
sudo ls /sys/kernel/debug/usb/usbmon/

# หา bus ของ UPS (ตัวอย่าง: Bus 001)
lsusb | grep "06da"

# จับ traffic 15 วินาที
sudo timeout 15 cat /sys/kernel/debug/usb/usbmon/1u > /tmp/usbmon.txt

# ดูเฉพาะ GET_REPORT (อ่านข้อมูลจาก UPS)
grep "S Ci.*s a1 01" /tmp/usbmon.txt

# ดูเฉพาะ SET_REPORT (เขียนคำสั่งไปยัง UPS)
grep "S Co.*s 21 09" /tmp/usbmon.txt
```

### 2. javap + unzip — แกะ JAR files

```bash
JAVAP=/opt/WinpowerG2/jre/bin/javap

# แตกไฟล์ jar
unzip -o /opt/WinpowerG2/lib/usbcomm-1.0.0.jar -d /tmp/usbcomm

# ดู string constants
strings /tmp/usbcomm/santak/hid/HidConstInt.class

# ดู integer values ของ constants
$JAVAP -verbose /tmp/usbcomm/santak/hid/HidConstInt.class | grep "ConstantValue: int"

# map constant name → integer value
$JAVAP -verbose /tmp/usbcomm/santak/hid/HidConstInt.class 2>&1 \
  | grep -B10 "ConstantValue: int" \
  | grep -E "Utf8 [A-Z_]+$|ConstantValue: int" | paste - -
```

### 3. strace — ดู system calls

```bash
# หา PID ของ WinpowerG2
pgrep -a java | grep winpower

# จับ ioctl calls (แต่ pointer-only, ไม่เห็น payload)
sudo timeout 10 strace -p <PID> -e trace=ioctl -f -o /tmp/strace.txt
grep "USBDEVFS_CONTROL" /tmp/strace.txt
```

---

## รูปแบบ usbmon packet

```
ffff... TIMESTAMP  S Ci:1:008:0  s a1 01  03RR 0000  LLLL  LLLL  <
ffff... TIMESTAMP  C Ci:1:008:0  0 N = HHHH HHHH...
```

| Field | ความหมาย |
|-------|---------|
| `S / C` | Submit (ส่ง) / Complete (รับกลับ) |
| `Ci / Co` | Control In (device→host) / Control Out (host→device) |
| `1:008:0` | bus:device:interface |
| `a1 01` | bmRequestType=0xA1, bRequest=0x01 → GET_REPORT |
| `21 09` | bmRequestType=0x21, bRequest=0x09 → SET_REPORT |
| `03RR` | wValue: 03=Feature report, RR=Report ID |
| `LLLL` | wLength (bytes) |
| `= HHHH` | ข้อมูลที่รับมา (hex) เมื่อ Complete |

**ตัวอย่าง decode:**
```
S Ci:1:008:0  s a1 01  0331 0000  0005  5 <     ← GET RID=0x31, max 5 bytes
C Ci:1:008:0  0 5 = 31f401a408                  ← response: 0x31,0xF4,0x01,0xA4,0x08
```
→ RID=0x31, payload=[0xF4, 0x01, 0xA4, 0x08]
→ u16 offset 0: 0x01F4 = 500 → /10 = **50.0 Hz** (Input Frequency)
→ u16 offset 2: 0x08A4 = 2212 → /10 = **221.2 V** (Input Voltage)

---

## ผล: Report IDs ทั้งหมดที่ WinpowerG2 อ่าน (Phoenixtec Innova Unity)

| RID | ขนาด | ข้อมูลที่พบ | หมายเหตุ |
|-----|------|------------|---------|
| `0x01` | 7B | Status flags | [AC, BelowCap, Charging, ?, Discharging, StatusGood] |
| `0x02` | 6B | Fault flags | [InternalFail, NeedReplace, Overload, ShutdownImminent, ?] |
| `0x03` | 6B | Temperature flag | [OverTemp, 0, 0, 0, 0] |
| `0x06` | 6B | Battery | [Charge%, Runtime(u32 LE, seconds)] |
| `0x07` | 12B | Sensors | d[1]=Load%, d[3-4]=TempK(u16), d[9-10]=BattV(u16/10) |
| `0x08` | — | Low battery alert % | d[0] = threshold% |
| `0x09` | 5B | Timer (countdown) | u32 LE, decrements 1/sec |
| `0x0C` | — | Battery thresholds | d[2]=LowBatt%, d[3]=HighBatt% |
| `0x0D` | 4B | Config | d[0]=NomFreq(Hz), d[1]=? |
| `0x10` | — | Supported report IDs | list of RIDs |
| `0x13` | 2B | Mode config | d[0]=2 |
| `0x14` | — | Nominal values | d[0]=NomFreq, d[1]=NomVoltage |
| `0x17` | — | Transfer voltage | u16 LE = low transfer voltage |
| `0x21` | 2B | Status | always 0 |
| `0x24` | 2B | **⭐ Self-test** | d[0]=**0x01**=idle/pass, **0x05**=running, **0x04**=failed(hypothesis) |
| `0x25` | — | Runtime alt | u16 at d[1-2] |
| `0x26` | 4B | Firmware version | [Major, Minor, Patch] → "4.3.18" |
| `0x27` | 8B | Flags | **d[3]=1 ระหว่าง self-test**, 0 หลัง |
| `0x30` | 9B | Collections/IDs | list |
| `0x31` | 5B | **⭐ Input** | u16/10 offset 0=InputFreq, **offset 2=InputVoltage** |
| `0x32` | 8B | Flags | d[2]=1 |
| `0x3F` | 2B | Status | always 0 |
| `0x41` | 8B | Flags | d[4]=1 |
| `0x42` | 17B | **⭐ Output** | d[4-5]=ActiveW, d[6-7]=ApparentVA, d[8-9]=CurrentA(/10), d[10-11]=OutFreq(/10), d[12-13]=OutVolt(/10) |
| `0x49` | 5B | — | zeros |
| `0x4A` | 3B | Mode | [2, 1] |
| `0x4B` | 2B | Status | 0 |
| `0x4E` | 8B | — | zeros |
| `0x72` | 3B | Config voltage | u16 LE = 230V |
| `0x73` | 2B | Status | 1 |
| `0x74` | — | Max power config | d[1-2]=MaxActivePower, d[3-4]=MaxApparentPower |
| `0x7F` | 2B | Status | 0 |
| `0x82` | 3B | Status | [1, 255] |
| `0x87` | 5B | Uptime? | u32 LE (seconds?) |
| `0x8A` | 5B | Flags | u32=3 |
| `0x8D` | 5B | Shutdown delay | **u32=0xFFFFFFFF = not scheduled** |

---

## คำสั่ง SET_REPORT (ควบคุม UPS)

WinpowerG2 ไม่ส่ง SET_REPORT ระหว่าง polling ปกติ — คำสั่งจะถูกส่งเมื่อผู้ใช้กดปุ่มใน UI
รูปแบบ SET_REPORT ผ่าน hidraw บน Linux:

```python
import hid

h = hid.device()
h.open_path(b'/dev/hidraw1')

# เขียน: [Report ID, byte1, byte2, ...]
h.send_feature_report([0x24, 0x01])        # เริ่ม Self-Test
h.send_feature_report([0x24, 0x00])        # ยกเลิก Self-Test
h.send_feature_report([0x8D, 0x3C, 0x00, 0x00, 0x00])  # Shutdown ใน 60 วิ (u32 LE)
h.send_feature_report([0x8D, 0xFF, 0xFF, 0xFF, 0xFF])  # Cancel Shutdown
h.send_feature_report([0x0A, 0x00, 0x00, 0x00, 0x00])  # Startup delay = 0
h.send_feature_report([0x72, 0xE6, 0x00])  # Config voltage = 230V (u16 LE)
h.send_feature_report([0x0D, 0x32, 0x00])  # Config freq = 50Hz
```

| RID | คำสั่ง | Payload | หมายเหตุ |
|-----|-------|---------|---------|
| `0x24` | Self-Test | `[0x01]`=start, `[0x00]`=abort | อ่านกลับ: 0x01=pass, 0x05=running, 0x04=failed |
| `0x8D` | Shutdown delay | u32 LE (seconds), `0xFFFFFFFF`=cancel | ยืนยันจากการอ่าน usbmon |
| `0x0A` | Startup delay | u32 LE (seconds) | — |
| `0x72` | Config voltage | u16 LE (volts) | 230 = 0xE6 0x00 |
| `0x0D` | Config frequency | `[Hz]` | 50 = 0x32 |
| `0x17` | Low batt runtime | u16 LE (seconds) | — |
| `0x29` | Timestamp | u32 LE (Unix seconds) | Vendor-defined, ทดลองใช้ |

> **หมายเหตุ:** RID `0x09` ที่ใช้ใน Windows version พบว่าบน Linux มีค่าเปลี่ยนทุกวินาที (อาจเป็น uptime หรือ clock)  
> ถ้า shutdown ไม่ทำงานผ่าน `0x09` ให้ลอง `0x8D` แทน

---

## JAR Files ที่เกี่ยวข้อง

| ไฟล์ | หน้าที่ |
|------|--------|
| `lib/usbcomm-1.0.0.jar` | HID communication layer, report decoding |
| `lib/winpower-comms-1.0.0.jar` | Polling loop, device search, data mapping |
| `lib/winpower-service-1.0.0.jar` | Business logic, battery test, shutdown |
| `winpower-api.jar` | Spring Boot REST API server |

## Classes ที่สำคัญ

| Class | หน้าที่ |
|-------|--------|
| `santak.hid.HidConstInt` | enum-like integer indices สำหรับ HID fields |
| `santak.hid.HidConst2XcpPath` | map HID index → XCP path string |
| `santak.shut.parser.ConstHidPath` | HID path string constants |
| `santak.shut.xcp.ConstXcpPath` | XCP path string constants |
| `santak.shut.imp.HidPortShut` | HID device open/close/send |
| `santak.hid.LinuxHidDevice` | Linux-specific HID device handler |
| `com.etn.wp.businessService.DeviceControlManager` | ส่งคำสั่ง control ผ่าน HID |

## REST API Endpoints (WinpowerG2)

WinpowerG2 มี REST API ที่ `https://localhost:8081`

| Endpoint | Method | หน้าที่ |
|----------|--------|--------|
| `/api/v1/auth` | POST | Login (token-based) |
| `/api/v1/deviceControl/test` | POST | Battery self-test |
| `/api/v1/deviceControl/setting/{deviceId}` | GET/POST | อ่าน/เขียน config |
| `/api/v1/scheduleShutdown` | POST | กำหนดเวลา shutdown |
| `/api/v1/shutdownNow` | POST | Shutdown ทันที |
| `/api/v1/scheduleTest` | POST | กำหนดเวลา battery test |
| `/api/v1/deviceData` | GET | ดูข้อมูล UPS ปัจจุบัน |

---

## 🧪 ผลการทดสอบ Self-Test (RID 0x24)

ยืนยันจากการทดสอบจริงบน Phoenixtec Innova Unity (VID=06DA) โดย Python + usbmon

### ค่าใน RID 0x24 (payload byte 0)

| ค่า | ความหมาย | สี |
|-----|---------|---|
| `0x01` | Idle / ผ่าน (ก่อนและหลัง test สำเร็จ) | เขียว |
| `0x05` | กำลังทดสอบ (ใช้เวลา ~10 วินาที) | ส้ม |
| `0x04` | ล้มเหลว (hypothesis — ยังไม่ได้ยืนยัน) | แดง |
| `0x02` | Warning | ส้ม |
| `0x03` | Abort | เทา |

### RID 0x27 (payload byte 3)
- `1` ระหว่าง self-test (UPS กำลัง discharge แบตเตอรี่)
- `0` หลังทดสอบเสร็จ

### ตัวอย่าง Python: ตรวจสอบผลทดสอบ

```python
import hid, time

TEST_STATUS = {
    0x01: "idle/pass",
    0x02: "warning",
    0x03: "abort",
    0x04: "failed",
    0x05: "running",
}

h = hid.device()
h.open_path(b'/dev/hidraw0')   # Linux
# h.open(0x06DA, 0xFFFF)       # Windows

# เริ่ม test
h.send_feature_report([0x24, 0x01])

# ตรวจสอบด้วย polling
for _ in range(30):
    data = h.get_feature_report(0x24, 4)
    status = TEST_STATUS.get(data[1], f"unknown(0x{data[1]:02X})")
    print(f"Status: {status}")
    if data[1] != 0x05:   # สิ้นสุดแล้ว
        break
    time.sleep(1)

h.close()
```

### Reports ที่เปลี่ยนระหว่าง self-test

| RID | ผลกระทบ |
|-----|-------|
| `0x24` d[1] | `0x01→0x05→0x01` (idle → running → complete) |
| `0x27` d[3] | `0→1→0` ระหว่าง discharge |
| `0x06` runtime | อัปเดตสูตรคาดเดา runtime หลัง test |
| `0x07` batt V | แรงดันแบตเตอรี่ลดลงชั่วคราว (normal) |
| `0x42` output | โหลดเปลี่ยนระหว่าง test |
    agent.run_monitor()