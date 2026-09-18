# ============================================================================

# Universal UPS Bridge for Linux (NUT Integration)

# ============================================================================

ระบบบริดจ์สำหรับเชื่อมต่อ UPS แบรนด์ Enerex / Phoenixtec / MEC
เข้ากับ NUT (Network UPS Tools) บนระบบปฏิบัติการ Linux

---

## Supported Hardware

---

| Hardware Model         | USB VID:PID   | Protocol       | Rating         |
| ---------------------- | ------------- | -------------- | -------------- |
| Innova Unity IOT Tower | 0x06DA:0xFFFF | phoenixtec_hid | 3000VA / 2700W |
| Innova Basic G2        | 0x06DA:0xFFFF | phoenixtec_hid | 2700VA / 2700W |
| Offline UPS 2000D      | 0x06DA:0xFFFF | phoenixtec_hid | 2000VA / 1200W |
| MEC0003 (800E)         | 0x0001:0x0000 | megatec_q1     | 880VA / 528W   |

---

## Installation & Management

---

```bash
chmod +x install.sh update.sh uninstall.sh
sudo ./install.sh       # ติดตั้งระบบและ service ทั้งหมด
sudo ./update.sh        # อัพเดทโค้ดและ reload service ทันที
sudo ./uninstall.sh     # ถอนการติดตั้ง
```

---

## Architecture

---

```text
+---------------+
|  UPS Device   | (Innova Unity / Basic G2 / 2000D / MEC0003)
+-------+-------+
        | (USB HID / Direct Control Transfer)
        v
+-------+---------------+
| enerex_ups_bridge.py  | (Driver poller + IPC listener)
+-------+---------------+
        | (Atomic write via os.rename)
        v
+-------+---------------+
|  /etc/nut/myups.dev   | (State file)
+-------+---------------+
        |
        v
+-------+---------------+
|  NUT (dummy-ups)      | ---> [upsd :3493] ---> [upsc / Web clients]
+-----------------------+
```

บริการระบบ 3 services:

| Service           | หน้าที่                                       |
| ----------------- | --------------------------------------------- |
| enerex-ups-bridge | อ่าน USB HID -> บันทึก telemetry ลง myups.dev |
| nut-driver        | dummy-ups driver อ่าน telemetry file ของ NUT  |
| nut-server        | upsd daemon ให้บริการ TCP port 3493           |

---

## System Paths

---

| File / Path                                   | หน้าที่ / คำอธิบาย       |
| --------------------------------------------- | ------------------------ |
| /etc/systemd/system/enerex-ups-bridge.service | Systemd service file     |
| /opt/enerex-ups/                              | โฟลเดอร์โปรแกรมหลัก      |
| /lib/nut/enerex                               | Symlink -> dummy-ups     |
| /usr/local/bin/upscmd                         | Wrapper ดักจับคำสั่ง NUT |
| /usr/local/bin/enerex-test                    | CLI สั่งทดสอบแบตเตอรี่   |
| /etc/nut/myups.dev                            | State pipe file          |
| /run/enerex_ups_bridge.lock                   | Lock file ป้องกันซ้ำซ้อน |
| /run/enerex_ups_cmd                           | Command IPC queue (0660) |

---

## Monitoring

---

```bash
upsc myups                              # ดู telemetry ทั้งหมด
upsc myups ups.status                   # ดูสถานะ (OL / OB / OFF)
upsc myups battery.test.status          # ดูผลทดสอบแบตเตอรี่
sudo systemctl status enerex-ups-bridge # ดูสถานะ service
sudo journalctl -u enerex-ups-bridge -f # ดู live log แบบ real-time
```

---

## Key Features

---

- Atomic Write : os.rename() ป้องกัน NUT อ่านข้อมูลไม่สมบูรณ์
- Auto-Recovery : ตรวจจับสายหลุด -> เคลียร์ค่า OFF/0 -> reconnect ทันที
- Smart NUT Reload : ตรวจสอบ is-active ก่อน reload/restart ลด downtime
- Single Instance : fcntl.flock ป้องกัน process ซ้อนทับ
- Multi-Model : แยก profile ตาม VID:PID + model string อัตโนมัติ
- Battery Bridge : รับคำสั่งจาก CLI / Web / Signal ส่งตรงไปยังฮาร์ดแวร์

---

## Battery Self-Test

---

### Trigger Methods

```bash
# 1) CLI (แนะนำ)
enerex-test quick                       # Quick test (10 วินาที)
enerex-test deep                        # Deep discharge test
enerex-test stop                        # ยกเลิกการทดสอบ

# 2) NUT upscmd
upscmd myups test.battery.start.quick
upscmd myups test.battery.start.deep
upscmd myups test.battery.stop

# 3) Linux Signal
pkill -SIGUSR1 -f enerex_ups_bridge.py  # Quick test
pkill -SIGUSR2 -f enerex_ups_bridge.py  # Abort test
```

### Status Lifecycle

| State   | ups.status | battery.test.status | ups.test.result |
| ------- | ---------- | ------------------- | --------------- |
| Idle    | OL         | passed              | Done and passed |
| Testing | OL CAL     | in progress         | In progress     |
| Passed  | OL         | passed              | Done and passed |
| Aborted | OL         | abort               | Aborted         |

### Hardware Command Matrix

| Model            | Quick Test  | Deep Test   | Abort       |
| ---------------- | ----------- | ----------- | ----------- |
| Unity / Basic G2 | 0x24 [0x01] | 0x24 [0x02] | 0x24 [0x00] |
| Offline 2000D    | 0x24 [0x01] | 0x24 [0x02] | 0x24 [0x03] |
| MEC0003 (800E)   | ASCII "T"   | ASCII "TL"  | ASCII "CT"  |

---

## Driver Switching (Enerex <-> usbhid-ups)

---

ระบบรองรับการสลับระหว่าง `driver = enerex` และ `driver = usbhid-ups` ใน `/etc/nut/ups.conf` ได้โดยตรง:

- **เมื่อตั้งเป็น `driver = enerex`**:
  `enerex_ups_bridge` จะทำงานเต็มรูปแบบ ดึงค่า $V_{in}$ จริงผ่าน Direct USB Control Transfer (Report 0x31) และส่งคำสั่ง Battery Test ผ่าน IPC
- **เมื่อตั้งเป็น `driver = usbhid-ups`**:
  `enerex_ups_bridge` จะเข้าโหมด Standby และปล่อยพอร์ต USB ให้ `usbhid-ups` ทันที คำสั่ง `upscmd` และระบบเดิมจะถูกส่งต่อเข้า Native NUT โดยอัตโนมัติ

**วิธีสลับ Driver**:
1. แก้ไข `/etc/nut/ups.conf`:
   ```text
   [myups]
       driver = usbhid-ups   # หรือ enerex
       port = auto           # หรือ /etc/nut/myups.dev
   ```
2. รีสตาร์ท service:
   ```bash
   sudo systemctl restart nut-driver nut-server
   ```

