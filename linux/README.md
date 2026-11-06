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
|  Native NUT adapter  | ---> [upsd :3493] ---> [upsc / Web clients]
+-----------------------+
```

บริการระบบ 3 services:

| Service           | หน้าที่                                       |
| ----------------- | --------------------------------------------- |
| enerex-ups-bridge | อ่าน USB HID -> บันทึก telemetry ลง myups.dev |
| nut-driver        | Native adapter อ่าน telemetry และรับคำสั่งจาก upsd |
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



## Command and state safety

- `enerex-test quick|deep|stop` and the matching `upscmd` battery commands write one command to the IPC mailbox. They do not also send SIGUSR1/2. `OK: command queued` confirms queuing, not hardware completion.
- Direct SIGUSR1 (quick) and SIGUSR2 (stop) remain supported as separate interfaces.
- Installer/updater install shared `enerex-test` and `upscmd` files. Copy those files and `enerex-ups.conf` together with the Python source when preparing an installation/update folder.
- `/etc/tmpfiles.d/enerex-ups.conf` creates the IPC files at boot as root:ups-hid 0660. An unavailable/unwritable queue returns a nonzero CLI exit code. The mailbox is for one writer; concurrent writers need a queued transport.
- Telemetry snapshots are published atomically as root:nut 0640. Missing readings remain unavailable; missing output voltage is not measured zero or evidence that output is off.
- NUT driver state is rechecked every 5 monotonic seconds while connected. Failed systemctl actions are retried, and updater health checks distinguish standby from a missing driver when telemetry exists.

### Device identity and power ratings

Phoenixtec variants share USB VID:PID `06da:ffff`. Generic `Innova Unity`
identifies the family only; the client refines it using captured identity strings
(indices 9 and 3). `Unity 1000 T` identifies Tower 1K. No serial-number rule is used.
MEC indexed strings are excluded from identity probing because some are controls.

`ups.power.nominal` and its compatibility alias `ups.apparent.power.nominal`
are VA; `ups.realpower.nominal` is W. Captured Report 0x74 contains two
little-endian u16 fields: W at bytes 0–1 and VA at bytes 2–3, after removing
the report ID. Incomplete reports provide no rating. Unknown ratings stay absent;
generic Unity no longer implies 3000VA/2700W. Output estimates require the
corresponding known rating. Actual 2000D/Basic G2 raw rating captures remain
necessary to resolve their earlier anomalous 9/900 readings.

### Native USB recovery in the bridge

The bridge supervises one spawned USB worker process. Startup and each request
have a 30-second response deadline; graceful close has a one-second deadline.
Shutdown can interrupt the wait. A native read/close hang causes worker teardown
(terminate, then kill if necessary), followed by the bridge's normal rescan.
The worker alone owns the USB handle. Timed-out commands have an unknown outcome
and are not replayed automatically; inspect hardware state before issuing another.
The ordinary synchronous `UPSClient` library API is unchanged.

MEC Q1 does not expose a definitive battery test pass result in these captured
telemetry strings. A healthy battery voltage after the local timer expires no
longer fabricates a pass; the reported result is unknown. The hardware test flag
still reports an active test. Live MEC reconnect validation after deployment is
pending; the exact native hidapi close deadlock has not been diagnosed to a stack.

The `upscmd` wrapper intercepts only a two-argument battery command targeting a
configured bridge UPS at the default local NUT endpoint. Other UPS names,
remote targets, nondefault ports and option forms pass to native `upscmd`.
A worker still alive after kill remains owned by the existing session; the
bridge retries its cleanup and cannot open a replacement until it exits.
The updater rejects a driver in systemd failed state even without a snapshot;
inactive service without telemetry means awaiting telemetry, not proof that
no UPS is physically connected.

### Maintenance rating capture (explicit operation)

Run `sudo bash update.sh --capture-ratings /absolute/path/new-capture.json`
from the source package only after coordinating the monitoring interruption.
This mode does not install files. It accepts one Enerex/dummy-ups configuration,
stops the active bridge and NUT adapter, then reads the Phoenixtec HID report
descriptor and Feature Report0x74 with one PyUSB owner. It refuses MEC, ambiguous
interfaces. When the kernel owns the interface, it uses the matching hidraw
node and GET-only ioctls, closing the unclaimed PyUSB metadata handle first.
It refuses missing/ambiguous nodes or wrong raw identity. The capture helper
never manually detaches/rebinds a driver, changes USB configuration or sends
UPS controls; normal bridge shutdown/startup retains its existing backend behavior.
The kernel API is documented at https://docs.kernel.org/hid/hidraw.html .

Install/update/capture share a nonblocking maintenance lock. Capture is bounded
by a15s deadline plus2s forced teardown. Its EXIT path restarts the bridge and,
when the driver was previously serving telemetry, waits up to30s (plus bounded
command overhead) for the driver and a snapshot newer than the capture marker,
and for NUT to serve identified telemetry again. A failed capture or failed
recovery returns nonzero. Partial raw evidence is retained with `complete:false`
and exit2; a missing descriptor is not proof of any W/VA layout. Existing output
files are never overwritten. No reboot or battery/output/beeper test is implied.


## Native NUT command adapter and notification-only monitor

The native adapter replaces the old /lib/nut/enerex symlink to dummy-ups. USB
ownership stays in one supervised bridge worker. The adapter exposes the standard
NUT driver socket, reads the same atomic telemetry file, and routes supported
battery-test commands through a bounded private Unix socket to the bridge.
`upsc myups` and native `upscmd -l myups` use the existing upsd. No new TCP
listener or LAN exposure is configured. Missing/stale snapshots become DATASTALE;
commands are revoked until fresh identified telemetry returns.

Supported instant commands, when the profile supports battery testing:
test.battery.start, test.battery.start.quick, test.battery.start.deep,
test.battery.stop. Writable variables and UPS output/kill-power operations are
unsupported; the driver rejects -k without touching hardware. NUT2.7.4 acknowledges
server acceptance, not actual USB completion or a passed battery test. The live
battery-test status and bridge log provide separate observations.

Existing local upscmd interception, enerex-test, OS signals and file IPC remain
legacy interfaces with OS-level permissions. Standard native upscmd forms using
NUT credentials now also reach the bridge through upsd/driver authentication.
When /etc/erx/.service/ups-command.py exists, the original web worker exclusively
owns system_command and its run_msg responses; the bridge no longer competes for
those DB rows. Keep upsboxcmd.service operational. Standalone deployments without
that worker retain the old DB ingress; legacy single-writer mailbox limits remain.

The installer/updater provisions a dedicated slave monitor with power value0,
MINSUPPLIES0 and SHUTDOWNCMD /bin/false because this Orange Pi uses an independent
adapter. This enables NUT monitoring without local automatic shutdown. No
powerdown flag is configured. Other machines powered by the UPS need their own
reviewed shutdown policy and network configuration. Existing independent MONITOR,
conflicting managed username or executable notification hooks cause a preflight
refusal before services stop. Credentials are generated once, stored root:nut0640,
and never printed; reruns preserve them. Uninstall removes only the managed
configuration and restores original overridden directives.

Install/update restart bridge, native driver, upsd and notification-only upsmon;
telemetry is interrupted during maintenance. Back up /opt/enerex-ups, /etc/nut,
/lib/nut/enerex, helper scripts and systemd/tmpfiles definitions before updating.
Rollback by restoring that release through its updater or the reviewed backup
procedure, never restoring stale command contents into a live queue.

Native migration requires one explicit driver=enerex section. A direct dummy-ups
section is refused in preflight instead of silently leaving the old emulator in
use. Original monitor enablement is recorded once and restored on uninstall.
