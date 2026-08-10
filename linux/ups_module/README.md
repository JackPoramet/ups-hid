# ups_module — Pure Python HID-UPS Client & Driver Library

ไลบรารี Python สำหรับสื่อสารกับอุปกรณ์ UPS ผ่านโปรโตคอล USB HID บนระบบปฏิบัติการ Linux

---

## 1. คุณสมบัติและขอบเขตการทำงาน (Module Scope & Features)

* **Direct USB HID Communication**: อ่านและเขียนข้อมูลกับอุปกรณ์ UPS ผ่าน `hidapi` (`/dev/hidraw*`)
* **Multi-Model Device Registry**: ควบคุมการเชื่อมต่ออุปกรณ์ผ่านไฟล์ลงทะเบียน `meta.json` และโมดูล `DeviceRegistry` รองรับการระบุ Vendor ID (VID) และ Product ID (PID) หลายรุ่น
* **NUT Protocol Compatibility**: แปลงค่าสถานะและข้อมูลวัดไฟฟ้าเข้าสู่ฟิลด์มาตรฐาน NUT (Network UPS Tools) dot-notation
* **Synchronous & Asynchronous Operations**:
  * อ่านข้อมูลครั้งเดียวแบบ Synchronous ผ่าน `UPSClient`
  * อ่านข้อมูลต่อเนื่องผ่าน Background Polling Thread (`UPSPoller`)
* **Event Detection & Dispatching**: ตรวจจับการเปลี่ยนแปลงสถานะไฟฟ้า (`ONBATT`, `ONLINE`, `LOWBATT`) และส่งเหตุการณ์ผ่าน `EventBus` แบบ Asynchronous Queue
* **Hardware Control Commands**: สั่งงานอุปกรณ์ด้วย HID Feature Report Writes (Self-test, Schedule Shutdown, Cancel Shutdown, Sync Time, Set Nominal Voltage/Frequency)
* **Deployment Automation**: สคริปต์ตรวจสอบ Dependencies, สร้าง udev rules อัตโนมัติ (`install.sh`), และสคริปต์ถอนการติดตั้ง (`uninstall.sh`)

---

## 2. ข้อกำหนดระบบและ Dependencies (System Dependencies)

### System Libraries (Debian/Ubuntu)
* `pkg-config`
* `build-essential`
* `python3-dev`
* `libudev-dev`
* `libhidapi-hidraw0`
* `libhidapi-dev`
* `libusb-1.0-0-dev`

### Python Packages (Python 3.8+)
* `hidapi>=0.14.0`
* `pyusb>=1.2.1`

---

## 3. การติดตั้งและการถอนการติดตั้ง (Installation & Uninstallation)

### 3.1 การติดตั้งแบบอัตโนมัติ (Automated Installation)

```bash
cd linux/ups_module
chmod +x install.sh
sudo ./install.sh
```

ขั้นตอนที่ `install.sh` ดำเนินการ:
1. ติดตั้ง System Shared Libraries ผ่าน `apt-get`
2. ติดตั้ง Python Packages ตาม `requirements.txt`
3. สร้าง udev rule ใน `/etc/udev/rules.d/99-ups-hid.rules` สำหรับทุกอุปกรณ์ใน `meta.json`
4. สั่ง Reload และ Trigger `udevadm`
5. ตรวจสอบสถานะความพร้อมของระบบผ่าน `linux_setup.py`

### 3.2 การติดตั้งแบบกำหนดเอง (Manual Installation)

```bash
sudo apt-get update
sudo apt-get install -y pkg-config build-essential python3-dev libudev-dev libhidapi-hidraw0 libhidapi-dev libusb-1.0-0-dev
pip install -r requirements.txt
sudo python3 linux_setup.py
```

### 3.3 การถอนการติดตั้ง (Uninstallation)

```bash
sudo bash uninstall.sh          # ถอนการติดตั้งแบบถามยืนยันแต่ละขั้นตอน
sudo bash uninstall.sh --yes    # ถอนการติดตั้งแบบอัตโนมัติทั้งหมดโดยไม่ถาม
```

ขั้นตอนที่ `uninstall.sh` ดำเนินการ:
1. ถอนการติดตั้ง Python Packages (`hidapi`, `pyusb`)
2. ลบไฟล์ udev rule `/etc/udev/rules.d/99-ups-hid.rules`
3. สั่ง Reload `udevadm control --reload-rules` และ `udevadm trigger`

---

## 4. ระบบการลงทะเบียนอุปกรณ์ (Multi-Model Device Registry)

### โครงสร้างไฟล์ `meta.json`

```json
{
  "version": "1.0",
  "description": "UPS device registry — supported models and their USB identifiers",
  "devices": [
    {
      "id": "phoenixtec_innova_unity",
      "manufacturer": "PHOENIXTEC",
      "model": "Innova Unity IOT Tower",
      "vid": "0x06DA",
      "pid": "0xFFFF",
      "protocol": "phoenixtec_hid",
      "report_ids": [
        "0x01", "0x02", "0x03", "0x05", "0x06", "0x07", "0x08",
        "0x0C", "0x0D", "0x10", "0x14", "0x17", "0x24", "0x25",
        "0x26", "0x27", "0x29", "0x31", "0x42", "0x4A", "0x74"
      ],
      "notes": "Tested on UP-Connex-Box (Ubuntu 22.04, kernel 5.15+)"
    }
  ]
}
```

### การเพิ่ม UPS รุ่นใหม่เข้าสู่ระบบ

เพิ่ม Object ใหม่ลงในอาร์เรย์ `devices` ของไฟล์ `meta.json` โดยระบุฟิลด์บังคับดังนี้:
* `id`: รหัสระบุรุ่นอุปกรณ์ (string)
* `manufacturer`: ชื่อผู้ผลิต (string)
* `model`: ชื่อรุ่นอุปกรณ์ (string)
* `vid`: รหัส USB Vendor ID ในรูปแบบ 16-bit Hex String (ฟอร์แมต `"0x06DA"`)
* `pid`: รหัส USB Product ID ในรูปแบบ 16-bit Hex String (ฟอร์แมต `"0xFFFF"`)
* `protocol`: รหัสโปรโตคอลการถอดรหัส (string)
* `report_ids`: อาร์เรย์ของ Report ID Hex Strings ที่อุปกรณ์รองรับ

---

## 5. การใช้งาน Python API Reference

### 5.1 การอ่านค่าแบบ One-shot Read (เทียบเท่าคำสั่ง `upsc`)

```python
from ups_module import UPSClient

# ใช้งานผ่าน Context Manager (เปิดและปิดอุปกรณ์อัตโนมัติ)
with UPSClient() as client:
    status = client.get_status()             # คืนค่าสตริงสถานะ "OL"
    voltage = client.get_var("input.voltage") # คืนค่าตัวเลขแรงดันไฟเข้า 220.5
    all_vars = client.get_vars()             # คืนค่า dict รูปแบบ NUT Key-Value
    data_obj = client.get_data()             # คืนค่าวัตถุ UPSData (Typed Dataclass)
    info = client.get_device_info()          # คืนค่า dict ข้อมูลอุปกรณ์
```

### 5.2 การเลือกใช้งานอุปกรณ์ตามโมเดล หรือ VID/PID

```python
from ups_module import UPSClient

# 1. ระบุด้วย model id จาก meta.json
client = UPSClient(model="phoenixtec_innova_unity")

# 2. ระบุ VID / PID โดยตรง
client = UPSClient(vid=0x06DA, pid=0xFFFF)

# 3. ไม่ระบุพารามิเตอร์ (ใช้ค่า default จากอุปกรณ์แรกใน meta.json)
client = UPSClient()
```

### 5.3 การดักจับเหตุการณ์ (Event Monitoring)

```python
from ups_module import UPSClient, NotifyType

client = UPSClient()
client.connect()

@client.on(NotifyType.ONBATT)
def on_power_failure(event):
    print(f"เกิดเหตุการณ์ไฟดับ: {event.message} เวลา: {event.timestamp}")

@client.on(NotifyType.ONLINE)
def on_power_restored(event):
    print(f"ระบบไฟฟ้ากลับสู่ภาวะปกติ: {event.message}")

@client.on(NotifyType.LOWBATT)
def on_low_battery(event):
    print(f"เตือนแบตเตอรี่ต่ำ: {event.message}")

# เริ่มต้น Thread ตรวจจับเหตุการณ์เบื้องหลัง
client.start_monitor(interval=1.0)

# ... การทำงานของโปรแกรม ...

# หยุด Thread ตรวจจับเหตุการณ์และปิดการเชื่อมต่อ
client.stop_monitor()
client.disconnect()
```

### 5.4 การส่งคำสั่งควบคุมอุปกรณ์ (Hardware Control Commands)

```python
with UPSClient() as client:
    # เริ่มทดสอบแบตเตอรี่ (Self-Test)
    client.run_self_test()

    # ยกเลิกการทดสอบแบตเตอรี่
    client.abort_self_test()

    # ตั้งเวลาปิดการจ่ายไฟล่วงหน้า 60 วินาที
    client.schedule_shutdown(delay_seconds=60)

    # ยกเลิกการตั้งเวลาปิดการจ่ายไฟ
    client.cancel_shutdown()

    # ซิงค์เวลาภายใน UPS กับเวลาปัจจุบันของระบบ
    client.sync_time()

    # ตั้งค่า Nominal Output Voltage 220V
    client.set_nominal_voltage(220)

    # ตั้งค่า Nominal Output Frequency 50Hz
    client.set_nominal_frequency(50)
```

---

## 6. ตารางถอดรหัส HID Feature Reports (HID Report Decode Matrix)

โมดูลถอดรหัสข้อมูลจาก HID Feature Reports แต่ละ Report ID ดังตารางต่อไปนี้:

| Report ID | ความยาว (Bytes) | ตำแหน่งข้อมูล (Byte Offsets) | การตีความข้อมูล (Decoding Logic) | ฟิลด์ข้อมูลที่ได้ |
|---|---|---|---|---|
| `0x01` | 6 | Byte 0<br>Byte 1<br>Byte 2<br>Byte 3<br>Byte 4<br>Byte 5 | Boolean<br>Boolean<br>Boolean<br>Boolean<br>Boolean<br>Boolean | `ac_present`<br>`below_capacity_limit`<br>`charging`<br>`bypass`<br>`discharging`<br>`status_good` |
| `0x02` | 4 | Byte 0<br>Byte 1<br>Byte 2<br>Byte 3 | Boolean<br>Boolean<br>Boolean<br>Boolean | `internal_failure`<br>`need_replacement`<br>`overload`<br>`shutdown_imminent` |
| `0x03` | 1 | Byte 0 | Boolean | `over_temperature` |
| `0x05` | 1 | Byte 0 | Boolean | `switchable` |
| `0x06` | 5 | Byte 0<br>Byte 1–4 | Unsigned Int 8-bit<br>Unsigned Int 32-bit (Little-Endian) | `battery.charge` / `battery_capacity_percent`<br>`runtime_remaining_sec` / `battery.runtime` |
| `0x07` | 11 | Byte 0<br>Byte 1<br>Byte 3–4<br>Byte 9–10 | Enum (1=Standby, 2=Bypass, 3=Line, 4=OnBattery, 5=Test)<br>Unsigned Int 8-bit (% Load)<br>Unsigned Int 16-bit (Little-Endian, Kelvin) - 273.15<br>Unsigned Int 16-bit (Little-Endian) / 10.0 | `work_mode_code`<br>`percent_load`<br>`temperature_c` / `ups.temperature`<br>`battery_voltage_v` |
| `0x08` | 1 | Byte 0 | Unsigned Int 8-bit (%) | `low_batt_alert_limit_percent` |
| `0x0C` | 4 | Byte 2<br>Byte 3 | Unsigned Int 8-bit<br>Unsigned Int 8-bit | `battery.charge.low`<br>`battery.charge.high` |
| `0x0D` | 1 | Byte 0 | Unsigned Int 8-bit (Hz) | `input.frequency` |
| `0x10` | 64 | Byte 0–N | List of non-zero Report ID bytes | `supported_reports` |
| `0x14` | 2 | Byte 0<br>Byte 1 | Unsigned Int 8-bit (Hz)<br>Unsigned Int 8-bit (V) | `input.frequency.nominal`<br>`input.voltage.nominal` |
| `0x17` | 2 | Byte 0–1 | Unsigned Int 16-bit (Little-Endian) (V) | `input.transfer.low` |
| `0x24` | 1 | Byte 0 | Enum (1=idle, 2=warning, 3=abort, 4=failed, 5=running) | `battery_test_status_raw`<br>`battery_test_status` |
| `0x25` | 3 | Byte 1–2 | Unsigned Int 16-bit (Little-Endian) (วินาที) | `runtime_alt_sec` |
| `0x26` | 3 | Byte 0, Byte 1, Byte 2 | String: `"{Byte0}.{Byte1}.{Byte2}"` | `ups.firmware` |
| `0x27` | 4 | Byte 3 | Boolean | `test_discharge_active` |
| `0x29` | 4 | Byte 0–3 | Unsigned Int 32-bit (Unix Timestamp) | `last_event_date` |
| `0x31` | 4 | Byte 0–1<br>Byte 2–3 | Unsigned Int 16-bit (Little-Endian) / 10.0 (Hz)<br>Unsigned Int 16-bit (Little-Endian) / 10.0 (V) | `input.frequency`<br>`input.voltage` |
| `0x42` | 14 | Byte 4–5<br>Byte 6–7<br>Byte 8–9<br>Byte 10–11<br>Byte 12–13 | Unsigned Int 16-bit (Little-Endian) (W)<br>Unsigned Int 16-bit (Little-Endian) (VA)<br>Unsigned Int 16-bit (Little-Endian) / 10.0 (A)<br>Unsigned Int 16-bit (Little-Endian) / 10.0 (Hz)<br>Unsigned Int 16-bit (Little-Endian) / 10.0 (V) | `output_active_power_w`<br>`output_apparent_power_va`<br>`output_current_a`<br>`output_frequency_hz`<br>`output_voltage_v` / `output.voltage` |
| `0x4A` | 1 | Byte 0 | Unsigned Int 8-bit Enum | `converter_mode` |
| `0x74` | 5 | Byte 1–2<br>Byte 3–4 | Unsigned Int 16-bit (Little-Endian) (W)<br>Unsigned Int 16-bit (Little-Endian) (VA) | `config_max_active_power_w`<br>`config_max_apparent_power_va` |

---

## 7. ตารางการแปลงฟิลด์ข้อมูล NUT (NUT Variable Mapping Table)

| ฟิลด์ใน `UPSData` | NUT Key Name | ชนิดข้อมูล | คำอธิบายและช่วงค่า |
|---|---|---|---|
| `ups_status` | `ups.status` | `str` | สตริงสถานะ NUT ประกอบจากสถานะธง (`OL`, `OB`, `OFF`, `BYPASS`, `DISCHRG`, `LB`, `OVER`) |
| `ups_mode` | `ups.mode` | `str` | โหมดการทำงานภาษาไทย (`"Line Mode (ไฟปกติ)"`, `"Battery Mode (ไฟดับ!)"`, `"Bypass Mode (โหมดบายพาส)"`) |
| `battery_charge` | `battery.charge` | `int` | ความจุแบตเตอรี่คงเหลือ (0–100 %) |
| `battery_runtime` | `battery.runtime` | `int` | เวลาสำรองไฟคงเหลือ (วินาที) |
| `battery_voltage` | `battery.voltage` | `float` | แรงดันไฟฟ้าแบตเตอรี่ (โวลต์) |
| `battery_charge_low` | `battery.charge.low` | `int` | ขีดจำกัดความจุแบตเตอรี่ระดับต่ำ (%) |
| `battery_charge_high` | `battery.charge.high` | `int` | ขีดจำกัดความจุแบตเตอรี่ระดับสูง (%) |
| `input_voltage` | `input.voltage` | `float` | แรงดันไฟฟ้าไฟเข้า (โวลต์) |
| `input_frequency` | `input_frequency` / `input.frequency` | `float` | ความถี่ไฟฟ้าไฟเข้า (เฮิรตซ์) |
| `input_voltage_nominal` | `input.voltage.nominal` | `int` | แรงดันไฟฟ้าไฟเข้าพิกัด (โวลต์) |
| `input_frequency_nominal` | `input.frequency.nominal` | `int` | ความถี่ไฟฟ้าไฟเข้าพิกัด (เฮิรตซ์) |
| `input_transfer_low` | `input.transfer.low` | `int` | ขีดจำกัดแรงดันต่ำสุดที่สลับไปใช้แบตเตอรี่ (โวลต์) |
| `output_voltage` | `output.voltage` | `float` | แรงดันไฟฟ้าไฟออก (โวลต์) |
| `output_frequency` | `output.frequency` | `float` | ความถี่ไฟฟ้าไฟออก (เฮิรตซ์) |
| `output_current` | `output.current` | `float` | กระแสไฟฟ้าไฟออก (แอมแปร์) |
| `output_power` | `output.power` | `int` | กำลังไฟฟ้าไฟออกจริง Active Power (วัตต์) |
| `output_power_apparent` | `output.power.apparent` | `int` | กำลังไฟฟ้าไฟออกปรากฏ Apparent Power (โวลต์-แอมแปร์) |
| `ups_load` | `ups.load` | `int` | ภาระโหลดไฟออก (%) |
| `ups_temperature` | `ups.temperature` | `float` | อุณหภูมิภายในอุปกรณ์ (องศาเซลเซียส) |
| `ups_firmware` | `ups.firmware` | `str` | เวอร์ชันเฟิร์มแวร์อุปกรณ์ (สตริงเวอร์ชัน `"1.2.3"`) |

---

## 8. คำสั่งควบคุมอุปกรณ์และโครงสร้าง Payload (Hardware Commands)

| คำสั่ง (Method) | Report ID | ชนิด Report | โครงสร้าง Payload (Bytes Hex) | ผลการทำงาน |
|---|---|---|---|---|
| `run_self_test()` | `0x24` | Feature | `[0x24, 0x05]` | เริ่มทดสอบแบตเตอรี่ (สถานะ Report 0x24 เปลี่ยนเป็น `0x05` running เป็นเวลา 10 วินาที) |
| `abort_self_test()` | `0x24` | Feature | `[0x24, 0x03]` | ยกเลิกการทดสอบแบตเตอรี่ทันที |
| `schedule_shutdown(delay_seconds)` | `0x09` | Feature | `[0x09, d0, d1, d2, d3]` (u32 LE) | ตั้งเวลาปิดการจ่ายไฟไฟออกของ UPS ตามจำนวนวินาทีที่กำหนด |
| `cancel_shutdown()` | `0x09` | Feature | `[0x09, 0xFF, 0xFF, 0xFF, 0xFF]` | ยกเลิกการตั้งเวลาปิดการจ่ายไฟ |
| `sync_time(timestamp)` | `0x29` | Feature | `[0x29, t0, t1, t2, t3]` (u32 LE) | เขียนค่า Unix Timestamp ลงในนาฬิกาภายในอุปกรณ์ |
| `set_nominal_voltage(voltage)` | `0x72` | Feature | `[0x72, 0x01, v_low, v_high]` (u16 LE) | กำหนดค่าแรงดันไฟฟ้าไฟออกพิกัด (Nominal Output Voltage) |
| `set_nominal_frequency(freq)` | `0x0D` | Feature | `[0x0D, freq]` | กำหนดค่าความถี่ไฟฟ้าไฟออกพิกัด (Nominal Output Frequency) |

---

## 9. สคริปต์เครื่องมือบรรทัดคำสั่ง (CLI Utilities)

### 9.1 `demo.py` — สคริปต์ทดสอบระบบและแสดงผล

```bash
# ตรวจสอบความพร้อมของระบบ (System Check)
python3 demo.py --check

# อ่านค่าครั้งเดียว (One-shot / upsc)
python3 demo.py --mode oneshot

# อ่านค่าแบบส่งออกฟอร์แมต JSON
python3 demo.py --mode oneshot --json

# อ่านค่าเฉพาะตัวแปรที่กำหนด
python3 demo.py --mode var --var battery.charge

# อ่านค่าแบบต่อเนื่องทุกๆ 2.0 วินาที
python3 demo.py --mode poll --interval 2.0

# ดักจับและแสดง Event ของ UPS
python3 demo.py --mode monitor

# ระบุโมเดลอุปกรณ์ที่ต้องการทดสอบ
python3 demo.py --model phoenixtec_innova_unity
```

### 9.2 `linux_setup.py` — สคริปต์ตั้งค่า udev และตรวจสอบ Dependencies

```bash
# ตรวจสอบความพร้อมโดยไม่แก้ไขระบบ (ไม่ต้องใช้ sudo)
python3 linux_setup.py --check

# สร้าง udev rules และ reload udevadm (ต้องใช้ sudo)
sudo python3 linux_setup.py

# เจาะจง VID และ PID แบบ manual
sudo python3 linux_setup.py --vid 0x06DA --pid 0xFFFF
```

### 9.3 `diagnose_linux.py` — สคริปต์วิเคราะห์ปัญหาแบบ Read-only

ใช้สำหรับวิเคราะห์ปัญหาบน Orange Pi หรือ Linux เครื่องอื่น โดยไม่แก้ไข udev,
ไม่ติดตั้ง package และไม่ส่งคำสั่งควบคุมไปยัง UPS:

```bash
# แสดงผลการตรวจสอบแบบอ่านง่าย
python3 diagnose_linux.py

# รันด้วย root เพื่อแยกปัญหา permission ออกจากปัญหา driver/interface
sudo python3 diagnose_linux.py

# บันทึกผลแบบ JSON สำหรับส่งกลับมาวิเคราะห์
python3 diagnose_linux.py --json /tmp/ups-diagnostic.json

# ข้ามการอ่าน kernel log
python3 diagnose_linux.py --skip-kernel-log
```

สคริปต์จะตรวจสอบ OS/architecture, Python import path, source code version,
dependencies, udev rule, HID enumeration, `/dev/hidraw*` mode/owner/group,
process ที่จับ device, การเปิด HID interface และการอ่าน Feature Report `0x01`
กับ `0x06` รวมถึงข้อความผิดปกติจาก kernel log

> หมายเหตุสำหรับ Orange Pi/ARM: hidapi บาง build คืนค่า device path เป็น
> `str` แต่ `open_path()` ต้องการ `bytes`; `core.py`, `linux_setup.py` และ
> `diagnose_linux.py` จะแปลง path ให้อัตโนมัติแล้ว

### 9.4 `check_hid_users.py` — ตรวจว่า process ใดใช้ USB HID อยู่

ใช้ตรวจสอบว่า process ใดกำลังเปิด `/dev/hidrawN` ของ UPS อยู่ โดยสคริปต์จะ
ค้นหาจาก `fuser`, `lsof` และ `/proc/*/fd` พร้อมแสดง PID, user, command line,
permission ของ node และทดสอบ `open_path()` แบบ read-only

```bash
python3 check_hid_users.py
sudo python3 check_hid_users.py
python3 check_hid_users.py --json /tmp/hid-users.json
python3 check_hid_users.py --no-open
```

สคริปต์ไม่หยุด process, ไม่แก้ permission, ไม่ reload udev และไม่เขียนข้อมูล
ไปยัง UPS หากพบ process ในผลลัพธ์ ให้หยุดเฉพาะ process นั้นด้วยคำสั่งที่เหมาะสม
แล้วลอง `demo.py` ใหม่

---

## 10. โครงสร้างไฟล์ทั้งหมดในแพ็กเกจ `ups_module`

```
ups_module/
├── __init__.py         # Public API Exports (UPSClient, DeviceRegistry, DeviceProfile, UPSData, NotifyType, DataStore, EventBus, EventDetector)
├── client.py           # Class หลัก UPSClient สำหรับเชื่อมต่อ อ่านค่า และส่งคำสั่งควบคุม
├── core.py             # Engine หลักในอ่าน Feature Reports, ถอดรหัส Byte Offsets และจัดการ HID Connection
├── device_registry.py   # Class DeviceRegistry และ DeviceProfile สำหรับโหลดและค้นหาข้อมูลอุปกรณ์จาก meta.json
├── meta.json           # ไฟล์ JSON ลงทะเบียน Vendor ID, Product ID และ Report IDs ของอุปกรณ์ UPS ทุกรุ่น
├── models.py           # Dataclass มาตรฐาน NUT (UPSData, UPSEvent, NotifyType) และ helper functions
├── events.py           # Queue-based EventBus และ EventDetector สำหรับประมวลผล State Transitions
├── store.py            # Thread-safe In-Memory DataStore (Lock-protected snapshot storage)
├── serializer.py       # Functions สำหรับแปลงชนิดข้อมูล Python เป็น JSON-compatible formats
├── poller.py           # Background Thread UPSPoller สำหรับอ่านข้อมูลต่อเนื่องและ Reconnect อัตโนมัติ
├── linux_setup.py      # สคริปต์ตรวจเช็ค Dependencies ของ Linux และสร้าง udev rule
├── diagnose_linux.py    # Read-only diagnostic สำหรับวิเคราะห์ Linux/Orange Pi
├── check_hid_users.py   # ตรวจ process ที่เปิด /dev/hidrawN ของ UPS
├── install.sh          # Bash Script สำหรับติดตั้ง Dependencies ทั้งหมด และตั้งค่าระบบในคำสั่งเดียว
├── uninstall.sh        # Bash Script สำหรับถอนการติดตั้ง Python Packages และลบ udev rule
├── demo.py             # CLI Tool สำหรับทดสอบระบบทุกโหมดการทำงาน
└── requirements.txt    # รายการ Python dependencies (hidapi>=0.14.0, pyusb>=1.2.1)
```
