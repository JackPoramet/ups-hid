# AI Agent Development Guide: NUT C Subdriver Port

## [System Instruction / Objective]

You are an expert C developer specializing in Linux system programming and the Network UPS Tools (NUT) driver framework. Your task is to port an existing Python HID UPS parser into a native C subdriver for the `usbhid-ups` driver.

## [Workspace & Directory Context]

- **Reference Code:** The existing Python source files are located in the `linux/ups_module` folder. You must refer to the logic in these files (specifically `core.py`, `models.py`, and `store.py`) to understand the HID report IDs, byte offsets, and decoding logic.
- **Development Workspace:** The NUT source code and your active development environment are located in the `nut` folder. All new C files (e.g., `phoenixtec-hid.c`, `phoenixtec-hid.h`) and modifications to existing files (e.g., adding the subdriver to `Makefile.am` or `usbhid-ups.c`) must be implemented within this folder.

## [Strict Documentation Requirement]

- **Document Every Step:** For every single file you create, modify, or logic you implement, you MUST write clear documentation (a changelog or implementation note) explaining exactly what was done, why it was done, and how it correlates to the original Python code.
- Do not write code silently. Always explain your thought process and the modifications made to the `nut` folder workspace.

## [Target Hardware & Collision Handling]

- **Target:** PHOENIXTEC Innova Unity IOT Tower (VID: `0x06DA`, PID: `0xFFFF`).
- **Collision Prevention:** In the subdriver's `claim` hook, do not rely solely on VID and PID. You must also retrieve the USB Product String. The subdriver should only claim the device if the Product String explicitly contains or matches "Innova Unity IOT Tower" to prevent VID/PID collisions with other models from the same manufacturer.

## [Implementation Steps]

1. **Subdriver Creation:** Create `phoenixtec-hid.c` and `phoenixtec-hid.h` in the appropriate `nut` driver directory. Include standard NUT HID headers.
2. **Device Match Table:** Define a `usb_device_id_t` array for VID `0x06DA` and PID `0xFFFF`.
3. **Variable Mapping (`hid_info_t`):** Translate the Python report decoding logic (from `linux/ups_module`) into the NUT `hid_info_t` lookup tables. Handle the scaling (e.g., dividing voltage and frequency by 10) appropriately.
   - _Reference:_ Battery Charge (Report `0x06`), Input Frequency (Report `0x31`), Input Voltage (Report `0x31`), Output Voltage (Report `0x42`), Percent Load (Report `0x07`).
4. **Custom Status Formatter:** Implement a custom status formatter function (e.g., `phoenixtec_format_status`) to decode Report ID `0x01` and update the `ups.status` variable ("OL", "OB", "LB", "BYPASS", "OFF") based on the boolean flags mapped in the Python code.
5. **Subdriver Hooks:** Implement the `subdriver_t` struct with the necessary hooks (`claim`, `format_status`, `initinfo`).

---

_Please begin by analyzing the requirements, outputting your first documentation note on how you plan to structure the files in the `nut` folder, and then proceed with the implementation step by step._

พบปัญหาในการทำตอนนี้คือไม่สามารถอ่านinput ของupsได้ น่าจะเพราะเกิดจากการใช้ usb-hid ของ nut
จึงใช้ dummy-ups ในการอ่านแทน

sudo nano /etc/nut/ups.conf
[myups]
driver = dummy-ups
port = /etc/nut/dummy.dev
desc = "Innova Unity IOT Tower (via Python Bridge)"

sudo nano /etc/systemd/system/ups-python-bridge.service
[Unit]
Description=UPS Python to Dummy-UPS Bridge
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /home/pi/nut/ups_dummy_bridge.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

🛠️ คู่มือฉบับสมบูรณ์: การสร้าง Python Bridge เชื่อมต่อ UPS สู่ Network UPS Tools (NUT) ผ่าน Dummy-ups
🎯 แนวคิดหลัก (Architecture)
เนื่องจากไดร์เวอร์ดั้งเดิมของ NUT (usbhid-ups) มักมีปัญหาแย่งชิงสิทธิ์การเข้าถึงพอร์ต USB กับไลบรารีของ Python ทำให้ดึงค่าแรงดันไฟฟ้าขาเข้า (input.voltage) ไม่สำเร็จ เราจึงแก้ปัญหาด้วยการสร้าง "สะพานเชื่อมข้อมูล (Bridge)" ดังนี้:

Python Script ผูกขาดการคุยกับ USB ของ UPS แต่เพียงผู้เดียว (ไม่มีใครแย่ง)

Python ดึงค่าตัวแปรต่างๆ แปลงเป็นรูปแบบ NUT แล้วเขียนลง Text File กลาง (/etc/nut/dummy.dev)

NUT ถูกปรับให้ใช้ไดร์เวอร์ dummy-ups ทำหน้าที่แค่นั่งอ่านข้อมูลจากไฟล์ Text กลางนั้น นำไปให้บริการต่อผ่านคำสั่งมาตรฐาน (upsc)

📂 ขั้นตอนที่ 1: จัดระเบียบโครงสร้างไฟล์โปรเจกต์
เพื่อให้ Python สามารถเรียกใช้งานไลบรารีภายในได้อย่างถูกต้อง จำเป็นต้องรวมไฟล์โมดูลทั้งหมดไว้ในโฟลเดอร์แพ็กเกจเดียวกัน

สร้างโฟลเดอร์แพ็กเกจสำหรับเก็บโมดูล:

Bash
sudo mkdir -p /home/pi/nut/ups_module
ย้ายหรือก๊อปปี้ไฟล์โมดูลทั้งหมด (.py และ meta.json) มาไว้ที่ /home/pi/nut/ups_module/ ให้ครบถ้วน:

**init**.py (ไฟล์ว่างสำหรับประกาศแพ็กเกจ)

client.py (จัดการการเชื่อมต่อหลัก)

core.py (แกนกลางประมวลผลคำสั่ง)

events.py (จัดการระบบ Event)

models.py (โครงสร้างข้อมูล)

device_registry.py, poller.py, serializer.py, store.py, meta.json

🐍 ขั้นตอนที่ 2: เขียนสคริปต์ Python Bridge (ups_dummy_bridge.py)
สร้างสคริปต์หลักสำหรับดึงข้อมูลจาก UPS และอัปเดตลงไฟล์จำลองของ NUT แบบอัตโนมัติ

สร้างและเปิดไฟล์:

Bash
nano /home/pi/nut/ups_dummy_bridge.py
ใส่โค้ดฉบับสมบูรณ์นี้ลงไป:

Python
#!/usr/bin/env python3
import time
import os
import sys

# กำหนด Path และบังคับให้ค้นหาโมดูลในโฟลเดอร์โปรเจกต์

script_dir = "/home/pi/nut"
if script_dir not in sys.path:
sys.path.insert(0, script_dir)

from ups_module.client import UPSClient

# ไฟล์เป้าหมายที่ NUT จะเข้ามาอ่านข้อมูล

DUMMY_FILE = "/etc/nut/dummy.dev"

def main():
client = UPSClient()

    # วนลูปพยายามเชื่อมต่อกับ UPS จนกว่าจะสำเร็จ
    while True:
        try:
            client.connect()
            print("Connected to UPS. Writing to dummy file...")
            break
        except Exception as e:
            print(f"Waiting for UPS... {e}")
            time.sleep(5)

    try:
        while True:
            try:
                # ดึงค่าตัวแปรทั้งหมดในรูปแบบ NUT-style dict จากไลบรารี
                data = client.get_vars()

                # เขียนลงไฟล์ชั่วคราวก่อน (ป้องกันปัญหา NUT อ่านจังหวะเขียนยังไม่เสร็จ)
                temp_file = DUMMY_FILE + ".tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    for key, value in data.items():
                        f.write(f"{key}: {value}\n")

                # สลับไฟล์แบบ Atomic ทันที (รวดเร็วและปลอดภัย)
                os.rename(temp_file, DUMMY_FILE)

            except Exception as e:
                print(f"Read error: {e}")
                client.disconnect()
                time.sleep(2)
                try:
                    client.connect()
                except Exception:
                    pass

            # กำหนดความถี่ในการอัปเดตข้อมูลทุกๆ 2 วินาที
            time.sleep(2)

    except KeyboardInterrupt:
        client.disconnect()
        print("\nExiting...")

if **name** == "**main**":
main()
บันทึกและออก (Ctrl+O, Enter, Ctrl+X)

⚙️ ขั้นตอนที่ 3: ติดตั้งไลบรารีฮาร์ดแวร์สำหรับสิทธิ์ Root
เนื่องจากตัว Bridge จะถูกรันเบื้องหลังด้วยสิทธิ์สูงสุด (root) จึงต้องติดตั้งไลบรารีติดต่อสื่อสาร USB ให้เรียบร้อย:

Bash
sudo apt update
sudo apt install -y python3-hid python3-usb
🔧 ขั้นตอนที่ 4: ตั้งค่า NUT ให้ใช้งาน Dummy Driver
เปิดไฟล์คอนฟิกไดร์เวอร์ของ NUT:

Bash
sudo nano /etc/nut/ups.conf
เพิ่มบล็อกตั้งค่าสำหรับ UPS ของคุณ (เช่น ตั้งชื่อว่า myups):

Ini, TOML
[myup]
driver = dummy-ups
port = /etc/nut/dummy.dev
desc = "UPS Bridge"
บันทึกไฟล์ให้เรียบร้อย

🚀 ขั้นตอนที่ 5: สร้าง Systemd Service ให้ Python Bridge ทำงาน 24 ชม.
เพื่อให้สคริปต์ Python รันเองอัตโนมัติเมื่อเปิดเครื่อง และช่วยรีสตาร์ทตัวเองหากเกิดข้อผิดพลาด

สร้างไฟล์ Service:

Bash
sudo nano /etc/systemd/system/ups-python-bridge.service
ใส่การตั้งค่าดังนี้:

Ini, TOML
[Unit]
Description=UPS Python to Dummy-UPS Bridge
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi/nut
ExecStart=/usr/bin/python3 /home/pi/nut/ups_dummy_bridge.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
บันทึกไฟล์แล้วสั่งเปิดใช้งาน Service:

Bash
sudo systemctl daemon-reload
sudo systemctl enable ups-python-bridge
sudo systemctl start ups-python-bridge
🧹 ขั้นตอนที่ 6: เคลียร์ไฟล์ Lock และสตาร์ทระบบ NUT
เคลียร์ไฟล์ PID ที่อาจค้างอยู่จากการรันครั้งก่อนๆ แล้วสั่งเปิดระบบ NUT ใหม่ทั้งหมด:

Bash

# 1. หยุดเซิร์ฟเวอร์และเคลียร์ไฟล์ Lock เดิม

sudo systemctl stop nut-server
sudo upsdrvctl stop 2>/dev/null || true
sudo rm -f /run/nut/dummy-ups-\*.pid

# 2. สร้างไฟล์ตั้งต้นเผื่อไว้ และกำหนดสิทธิ์

echo "ups.status: WAIT" | sudo tee /etc/nut/dummy.dev
sudo chmod 666 /etc/nut/dummy.dev

# 3. สตาร์ทไดร์เวอร์และ NUT Server ใหม่

sudo upsdrvctl start
sudo systemctl start nut-server
✅ ขั้นตอนที่ 7: ตรวจสอบผลลัพธ์และความสมบูรณ์
เช็คสถานะการทำงานของ Python Bridge:

Bash
sudo systemctl status ups-python-bridge
(ต้องขึ้นสถานะเขียว Active: active (running))

ดึงข้อมูลจาก NUT เพื่อดูตัวแปรทั้งหมด:

Bash
upsc myups
หากตั้งค่าถูกต้อง ข้อมูลพลังงานทั้งหมด เช่น แรงดันไฟฟ้า (input.voltage, output.voltage), เปอร์เซ็นต์แบตเตอรี่ (battery.charge), และสถานะระบบ (ups.status) จะแสดงผลออกมาครบถ้วน