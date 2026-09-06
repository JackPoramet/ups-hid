# Universal UPS Bridge for Linux (NUT Integration)

ระบบบริดจ์สำหรับเชื่อมต่อ UPS แบรนด์ Enerex / Phoenixtec / MEC เข้ากับ NUT (Network UPS Tools) บน Linux

## Supported Hardware

| รุ่น | USB VID:PID | Protocol | Rating |
|------|-------------|----------|--------|
| Innova Unity IOT Tower | `0x06DA:0xFFFF` | phoenixtec_hid | 3000VA / 2700W |
| Innova Basic G2 | `0x06DA:0xFFFF` | phoenixtec_hid | 2700VA / 2700W |
| Offline UPS 2000D | `0x06DA:0xFFFF` | phoenixtec_hid | 2000VA / 1200W |
| MEC0003 (800E) | `0x0001:0x0000` | megatec_q1 | 880VA / 528W |

## Installation

```bash
chmod +x install.sh uninstall.sh
sudo ./install.sh       # ติดตั้ง
sudo ./uninstall.sh     # ถอนการติดตั้ง
```

## Architecture

```
[UPS] <--(USB)--> [enerex_ups_bridge.py] --(atomic write)--> [/etc/nut/myups.dev] --> [NUT dummy-ups] --> [upsd :3493] --> [upsc / clients]
```

หลังติดตั้งจะมี 3 services ทำงาน:

| Service | หน้าที่ |
|---------|---------|
| `enerex-ups-bridge` | อ่าน USB HID → เขียน telemetry ลง `/etc/nut/myups.dev` |
| `nut-driver` | NUT driver (dummy-ups) อ่านไฟล์สถานะ |
| `nut-server` | NUT data server (upsd) ให้บริการ TCP :3493 |

## System Paths

| Path | หน้าที่ |
|------|---------|
| `/etc/systemd/system/enerex-ups-bridge.service` | Systemd service file |
| `/opt/enerex-ups/` | โปรแกรมหลัก (`enerex_ups_bridge.py` + `ups_module/`) |
| `/lib/nut/enerex` | Symlink → `/lib/nut/dummy-ups` |
| `/usr/local/bin/upscmd` | Wrapper ดักจับ instant commands |
| `/usr/local/bin/enerex-test` | CLI สั่งทดสอบแบตเตอรี่ |
| `/etc/nut/myups.dev` | State pipe file (telemetry data) |
| `/run/enerex_ups_bridge.lock` | Single-instance lock |
| `/run/enerex_ups_cmd` | Command IPC queue (group `ups-hid`, mode `0660`) |

## Monitoring

```bash
upsc myups                                      # ดูข้อมูล telemetry ทั้งหมด
upsc myups ups.status                           # ดูสถานะ (OL / OB / OFF)
upsc myups battery.test.status                  # ดูผลทดสอบแบตเตอรี่
sudo systemctl status enerex-ups-bridge         # ดูสถานะ service
sudo journalctl -u enerex-ups-bridge -f         # ดู log แบบ real-time
```

## Key Features

- **Atomic File Write** — `os.rename()` ป้องกัน NUT อ่านข้อมูลไม่สมบูรณ์
- **Auto-Recovery** — ตรวจจับ USB หลุด → เคลียร์ค่าเป็น OFF/0 → reconnect อัตโนมัติ
- **Smart NUT Reload** — ตรวจสอบ `systemctl is-active` ก่อน restart เพื่อลด downtime
- **Single Instance Lock** — `fcntl.flock` ป้องกันรันโปรเซสซ้อนทับ
- **Multi-Model** — แยก profile ตาม VID:PID + model string (Unity / Basic G2 / 2000D / MEC0003)
- **Battery Test Bridge** — รับคำสั่งจาก CLI / Web / MariaDB / Signal → ส่งฮาร์ดแวร์จริง

## Battery Self-Test

### Trigger Methods

```bash
# CLI (ง่ายที่สุด)
enerex-test quick               # Quick test (10s)
enerex-test deep                # Deep test
enerex-test stop                # ยกเลิก

# NUT upscmd
upscmd myups test.battery.start.quick
upscmd myups test.battery.start.deep
upscmd myups test.battery.stop

# Linux Signal
pkill -SIGUSR1 -f enerex_ups_bridge.py    # Quick test
pkill -SIGUSR2 -f enerex_ups_bridge.py    # Abort
```

### Status Lifecycle

| สถานะ | `ups.status` | `battery.test.status` | `ups.test.result` |
|--------|-------------|----------------------|-------------------|
| Idle | `OL` | `passed` | `Done and passed` |
| Testing | `OL CAL` | `in progress` | `In progress` |
| Passed | `OL` | `passed` | `Done and passed` |
| Aborted | `OL` | `abort` | `Aborted` |

### Hardware Command Matrix

| รุ่น | Quick Test | Deep Test | Abort |
|------|-----------|-----------|-------|
| **Unity / Basic G2** | `0x24 [0x01]` | `0x24 [0x02]` | `0x24 [0x00]` |
| **Offline 2000D** | `0x24 [0x01]` | `0x24 [0x02]` | `0x24 [0x03]` |
| **MEC0003** | ASCII `T` | ASCII `TL` | ASCII `CT` |
