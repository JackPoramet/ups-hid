"""
UPS Monitor GUI — Linux
Real-time display via PySide6, polls every 1 second.

Linux-specific changes vs. the Windows version:
- HID report descriptor is read directly from sysfs
  (/sys/class/hidraw/hidrawN/device/report_descriptor)
- No dependency on hidapi.py (Windows-only DeviceIoControl wrapper)
"""

import datetime
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# ── ดึงฟังก์ชันหลักจาก hid_ups.py ───────────────────────────────────────────
try:
    from hid_ups import (
        DEFAULT_DESCRIPTOR_BIN,
        DEFAULT_DESCRIPTOR_TXT,
        DEFAULT_REPORT_SIZES,
        VID,
        PID,
        decode_feature_reports,
        get_descriptor_feature_ids,
        infer_tentative_live_values,
        load_descriptor_profile,
        open_ups_device,
        read_all_feature_reports,
    )
    HID_AVAILABLE = True
except ImportError as _hid_import_err:
    HID_AVAILABLE = False
    VID = 0x06DA
    PID = 0xFFFF
    DEFAULT_REPORT_SIZES = (64,)
    DEFAULT_DESCRIPTOR_BIN = "report_descriptor_live.bin"
    DEFAULT_DESCRIPTOR_TXT = "report_descriptor_live.txt"

POLL_INTERVAL_MS = 1000  # 1 วินาที


# ══════════════════════════════════════════════════════════════════════════════
# Linux sysfs descriptor helper
# ══════════════════════════════════════════════════════════════════════════════

def _read_descriptor_from_sysfs(device_path: object) -> Optional[bytes]:
    """
    อ่าน HID report descriptor จาก sysfs ของ Linux

    device_path: bytes หรือ str ที่ได้จาก hid.enumerate() เช่น b'/dev/hidraw0'
    คืนค่า bytes ของ descriptor หรือ None ถ้าอ่านไม่ได้
    """
    if isinstance(device_path, (bytes, bytearray)):
        path_str = device_path.decode("utf-8", errors="ignore")
    else:
        path_str = str(device_path)

    m = re.search(r"hidraw(\d+)", path_str)
    if not m:
        return None

    sysfs = Path(f"/sys/class/hidraw/hidraw{m.group(1)}/device/report_descriptor")
    try:
        return sysfs.read_bytes()
    except OSError:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# ค่าสี
# ══════════════════════════════════════════════════════════════════════════════

COLOR_BG_WINDOW   = "#1E1E2E"
COLOR_BG_SECTION  = "#2A2A3E"
COLOR_BG_ROW_ALT  = "#25253A"
COLOR_TEXT_LABEL  = "#9A9AB0"
COLOR_TEXT_VALUE  = "#E0E0F0"
COLOR_TEXT_TITLE  = "#C0C0E0"
COLOR_BORDER      = "#44446A"

COLOR_STATUS_OK   = "#4ECA6E"   # เขียว: ไฟปกติ / charged
COLOR_STATUS_WARN = "#F5A623"   # ส้ม: กำลังชาร์จ / fallback
COLOR_STATUS_ERR  = "#E04A4A"   # แดง: ไฟดับ / fault
COLOR_STATUS_INFO = "#56B0F5"   # ฟ้า: ข้อมูลทั่วไป
COLOR_DIM         = "#606080"   # เทา: ปิดอยู่ / False


# ══════════════════════════════════════════════════════════════════════════════
# Worker Thread
# ══════════════════════════════════════════════════════════════════════════════

class UPSWorker(QThread):
    """อ่านข้อมูล UPS ใน background thread แล้ว emit signal กลับมาที่ UI"""

    data_ready = Signal(dict, dict)    # (device_info, ups_values)
    error_occurred = Signal(str)
    descriptor_ready = Signal(str)     # descriptor status message
    command_result = Signal(str)       # SetFeatureReport result

    def __init__(self, vid: int = VID, pid: int = PID, parent=None):
        super().__init__(parent)
        self.vid = vid
        self.pid = pid
        self._stop = False
        self._h = None
        self._info: dict = {}
        self._descriptor_profile: Optional[dict] = None
        self._report_ids: list = list(range(0x01, 0x80))

    def stop(self) -> None:
        self._stop = True
        if self._h:
            try:
                self._h.close()
            except Exception:
                pass
            self._h = None

    def poll_once(self) -> None:
        if not HID_AVAILABLE:
            self.error_occurred.emit("ไม่พบ module hid_ups (import ไม่สำเร็จ)")
            return

        if self._h is None:
            self._connect()
            return

        try:
            raw, _ = read_all_feature_reports(
                self._h,
                report_ids=self._report_ids,
                sizes=(64,),
                retries=1,
                include_zero=False,
            )
            ups = decode_feature_reports(raw)
            ups.update(infer_tentative_live_values(raw, ups))
            self.data_ready.emit(self._info, ups)
        except Exception as exc:
            try:
                self._h.close()
            except Exception:
                pass
            self._h = None
            self.error_occurred.emit(f"Poll error: {exc}")

    def _connect(self) -> None:
        try:
            h, info = open_ups_device(self.vid, self.pid)
            if h is None:
                self.error_occurred.emit(
                    f"ไม่พบอุปกรณ์ VID=0x{self.vid:04X} PID=0x{self.pid:04X}"
                )
                return
            self._h = h
            self._info = info or {}
            self._read_descriptor()
            self.error_occurred.emit("")
        except Exception as exc:
            self.error_occurred.emit(f"Connect error: {exc}")

    def _read_descriptor(self) -> None:
        """อ่าน report descriptor จาก sysfs ของ Linux"""
        raw_path = self._info.get("path")
        if not raw_path:
            self.descriptor_ready.emit("Profile: — (ไม่มี device path)")
            return

        descriptor_bytes = _read_descriptor_from_sysfs(raw_path)

        if not descriptor_bytes:
            self.descriptor_ready.emit(
                "Profile: — (อ่าน sysfs ไม่ได้ → scan 0x01-0x7F)"
            )
            return

        bin_path = Path(DEFAULT_DESCRIPTOR_BIN)
        try:
            bin_path.write_bytes(descriptor_bytes)
        except OSError as exc:
            self.descriptor_ready.emit(f"Profile: บันทึกไม่ได้ ({exc})")
            return

        try:
            self._descriptor_profile = load_descriptor_profile(
                bin_path, Path(DEFAULT_DESCRIPTOR_TXT)
            )
            ids = get_descriptor_feature_ids(self._descriptor_profile)
            if ids:
                self._report_ids = ids
                self.descriptor_ready.emit(
                    f"Profile: {len(descriptor_bytes)}B → {len(ids)} report IDs"
                )
            else:
                self.descriptor_ready.emit(
                    f"Profile: {len(descriptor_bytes)}B (ไม่พบ structured IDs → scan 0x01-0x7F)"
                )
        except Exception as exc:
            self.descriptor_ready.emit(f"Profile load error: {exc}")

    def send_feature_report(self, rid: int, payload: list) -> None:
        if not self._h:
            self.command_result.emit("\u2717 ยังไม่ได้เชื่อมต่ออุปกรณ์")
            return
        try:
            data = [rid] + list(payload)
            self._h.send_feature_report(data)
            hex_str = " ".join(f"{b:02X}" for b in payload)
            self.command_result.emit(f"\u2713 RID=0x{rid:02X} \u2190 {hex_str}")
        except Exception as exc:
            self.command_result.emit(f"\u2717 RID=0x{rid:02X}: {exc}")

    def read_feature_report(self, rid: int, size: int = 8) -> Optional[list]:
        if not self._h:
            return None
        try:
            data = self._h.get_feature_report(rid, size)
            return list(data) if data else None
        except Exception:
            return None

    def read_interrupt_data(self, size: int = 64, timeout_ms: int = 500) -> Optional[list]:
        if not self._h:
            return None
        try:
            data = self._h.read(size, timeout_ms)
            return data if data else None
        except Exception:
            return None


# ══════════════════════════════════════════════════════════════════════════════
# ValueRow / Section
# ══════════════════════════════════════════════════════════════════════════════

class ValueRow(QWidget):
    def __init__(self, label: str, unit: str = "", parent: Optional[QWidget] = None, alt_bg: bool = False):
        super().__init__(parent)
        self._unit = unit
        self._alt_bg = alt_bg

        self.setAutoFillBackground(True)
        bg = COLOR_BG_ROW_ALT if alt_bg else COLOR_BG_SECTION
        self.setStyleSheet(f"background-color: {bg};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        self._label_w = QLabel(label)
        self._label_w.setFixedWidth(220)
        self._label_w.setStyleSheet(f"color: {COLOR_TEXT_LABEL}; font-size: 12px;")

        self._value_w = QLabel("—")
        self._value_w.setStyleSheet(f"color: {COLOR_TEXT_VALUE}; font-size: 13px; font-weight: bold;")
        self._value_w.setMinimumWidth(140)
        self._value_w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(self._label_w)
        layout.addStretch()
        layout.addWidget(self._value_w)

    def set_value(self, value: object, color: Optional[str] = None, suffix: Optional[str] = None) -> None:
        if value is None or value == "":
            text = "—"
        elif isinstance(value, float):
            text = f"{value:.1f}"
        elif isinstance(value, list):
            text = ", ".join(str(v) for v in value)
        else:
            text = str(value)

        unit = suffix if suffix is not None else self._unit
        display = f"{text}  {unit}".strip() if unit else text
        self._value_w.setText(display)
        c = color or COLOR_TEXT_VALUE
        self._value_w.setStyleSheet(f"color: {c}; font-size: 13px; font-weight: bold;")

    def set_na(self) -> None:
        self._value_w.setText("N/A")
        self._value_w.setStyleSheet(f"color: {COLOR_DIM}; font-size: 13px; font-weight: bold;")


class Section(QGroupBox):
    def __init__(self, title: str, fields: list, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setTitle(title)
        self.setStyleSheet(f"""
            QGroupBox {{
                background-color: {COLOR_BG_SECTION};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                margin-top: 10px;
                padding: 4px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 10px;
                color: {COLOR_TEXT_TITLE};
                font-size: 12px;
                font-weight: bold;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 12, 4, 6)
        layout.setSpacing(1)

        self._rows: dict[str, ValueRow] = {}
        for idx, (key, label, unit) in enumerate(fields):
            row = ValueRow(label, unit, alt_bg=(idx % 2 == 1))
            layout.addWidget(row)
            self._rows[key] = row

    def update_row(self, key: str, value: object, color: Optional[str] = None, suffix: Optional[str] = None) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        if value is None:
            row.set_na()
        else:
            row.set_value(value, color=color, suffix=suffix)

    def clear_all(self) -> None:
        for row in self._rows.values():
            row.set_na()


class StatusBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {COLOR_BG_SECTION}; border-top: 1px solid {COLOR_BORDER};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(20)

        self._conn_label = QLabel("ไม่ได้เชื่อมต่อ")
        self._conn_label.setStyleSheet(f"color: {COLOR_TEXT_LABEL}; font-size: 12px;")

        self._desc_label = QLabel("")
        self._desc_label.setStyleSheet(f"color: {COLOR_DIM}; font-size: 11px;")

        self._time_label = QLabel("")
        self._time_label.setStyleSheet(f"color: {COLOR_TEXT_LABEL}; font-size: 12px;")
        self._time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(self._conn_label)
        layout.addStretch()
        layout.addWidget(self._desc_label)
        layout.addWidget(self._time_label)

    def set_descriptor_status(self, message: str) -> None:
        self._desc_label.setText(message)
        ok = "report IDs" in message and "→" in message
        color = COLOR_STATUS_OK if ok else COLOR_DIM
        self._desc_label.setStyleSheet(f"color: {color}; font-size: 11px;")

    def set_connected(self, ok: bool, message: str = "") -> None:
        if ok:
            self._conn_label.setText("เชื่อมต่อแล้ว")
            self._conn_label.setStyleSheet(f"color: {COLOR_STATUS_OK}; font-size: 12px;")
        else:
            msg = f"ผิดพลาด: {message}" if message else "ไม่ได้เชื่อมต่อ"
            self._conn_label.setText(msg)
            self._conn_label.setStyleSheet(f"color: {COLOR_STATUS_ERR}; font-size: 12px;")

    def set_time(self, ts: str) -> None:
        self._time_label.setText(f"อัปเดต: {ts}")


# ══════════════════════════════════════════════════════════════════════════════
# ControlDialog: หน้าต่างควบคุม UPS
# ══════════════════════════════════════════════════════════════════════════════

class ControlDialog(QDialog):
    def __init__(self, worker: "UPSWorker", parent=None):
        super().__init__(parent)
        self._worker = worker
        self.setWindowTitle("UPS Control Panel")
        self.setModal(False)
        self.setMinimumWidth(520)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {COLOR_BG_WINDOW}; }}
            QGroupBox {{
                background-color: {COLOR_BG_SECTION};
                border: 1px solid {COLOR_BORDER};
                border-radius: 5px;
                margin-top: 10px;
                padding: 4px;
                color: {COLOR_TEXT_TITLE};
                font-size: 12px;
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
            }}
            QLabel {{ color: {COLOR_TEXT_LABEL}; font-size: 12px; background: transparent; }}
            QSpinBox {{
                background-color: {COLOR_BG_ROW_ALT};
                color: {COLOR_TEXT_VALUE};
                border: 1px solid {COLOR_BORDER};
                border-radius: 3px;
                padding: 3px 6px;
                min-width: 110px;
            }}
            QPushButton {{
                background-color: {COLOR_BG_SECTION};
                color: {COLOR_TEXT_VALUE};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 5px 12px;
                min-width: 80px;
            }}
            QPushButton:hover {{ background-color: {COLOR_BORDER}; }}
            QPushButton:pressed {{ background-color: #303050; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        root.addWidget(self._build_test_section())
        root.addWidget(self._build_shutdown_section())
        root.addWidget(self._build_config_section())
        root.addWidget(self._build_time_section())

        self._test_poll_timer = QTimer(self)
        self._test_poll_timer.setInterval(1000)
        self._test_poll_timer.timeout.connect(self._poll_test_status)
        self._test_countdown = 0

        self._result_label = QLabel("พร้อมรับคำสั่ง")
        self._result_label.setStyleSheet(
            f"color: {COLOR_STATUS_INFO}; font-size: 12px; "
            f"background-color: {COLOR_BG_SECTION}; padding: 6px; border-radius: 4px;"
        )
        root.addWidget(self._result_label)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(btn_close)
        root.addLayout(close_row)

        self._worker.command_result.connect(self._on_result)

    def _build_test_section(self) -> QGroupBox:
        grp = QGroupBox("Self Test  (RID 0x24)")
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(8, 18, 8, 8)
        lay.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_run   = QPushButton("Run Self-Test")
        btn_abort = QPushButton("Abort Test")
        btn_run.clicked.connect(self._run_test)
        btn_abort.clicked.connect(self._abort_test)
        btn_row.addWidget(btn_run)
        btn_row.addWidget(btn_abort)
        btn_row.addStretch()

        self._test_status_label = QLabel("\u2500")
        self._test_status_label.setStyleSheet(
            f"color: {COLOR_TEXT_VALUE}; font-size: 12px; "
            f"background-color: {COLOR_BG_ROW_ALT}; padding: 5px; border-radius: 3px;"
        )
        warn = QLabel("")
        warn.setStyleSheet(f"color: {COLOR_STATUS_WARN}; font-size: 11px;")

        lay.addLayout(btn_row)
        lay.addWidget(self._test_status_label)
        lay.addWidget(warn)
        return grp

    def _build_shutdown_section(self) -> QGroupBox:
        grp = QGroupBox("Shutdown Schedule")
        lay = QGridLayout(grp)
        lay.setContentsMargins(8, 18, 8, 8)
        lay.setSpacing(8)
        lay.setColumnStretch(1, 1)

        self._spin_shutdown = QSpinBox()
        self._spin_shutdown.setRange(0, 86400)
        self._spin_shutdown.setValue(60)
        self._spin_shutdown.setSuffix("  วินาที")

        self._spin_startup = QSpinBox()
        self._spin_startup.setRange(0, 86400)
        self._spin_startup.setValue(0)
        self._spin_startup.setSuffix("  วินาที")

        btn_sched  = QPushButton("Schedule  (RID 0x09)")
        btn_sched.setStyleSheet(
            f"background-color: #4A1A1A; color: {COLOR_TEXT_VALUE}; "
            f"border: 1px solid #8A3A3A; border-radius: 4px; padding: 5px 12px;"
        )
        btn_cancel = QPushButton("Cancel Shutdown")
        btn_set_su = QPushButton("Set  (RID 0x0A)")
        btn_sched.clicked.connect(self._do_shutdown)
        btn_cancel.clicked.connect(self._do_cancel_shutdown)
        btn_set_su.clicked.connect(self._do_startup)

        warn = QLabel(
            "\u26a0 Delay=0 ปิด output ทันที  |  ตั้ง Startup Delay ก่อนเสมอ เพื่อให้ UPS รีสตาร์ทอัตโนมัติ"
        )
        warn.setStyleSheet(f"color: {COLOR_STATUS_WARN}; font-size: 11px;")

        lay.addWidget(QLabel("Delay Before Shutdown:"), 0, 0)
        lay.addWidget(self._spin_shutdown,              0, 1)
        lay.addWidget(btn_sched,                        0, 2)
        lay.addWidget(btn_cancel,                       0, 3)
        lay.addWidget(QLabel("Delay Before Startup:"),  1, 0)
        lay.addWidget(self._spin_startup,               1, 1)
        lay.addWidget(btn_set_su,                       1, 2)
        lay.addWidget(warn,                             2, 0, 1, 4)
        return grp

    def _build_config_section(self) -> QGroupBox:
        grp = QGroupBox("Configuration")
        lay = QGridLayout(grp)
        lay.setContentsMargins(8, 18, 8, 8)
        lay.setSpacing(8)
        lay.setColumnStretch(1, 1)

        self._spin_voltage = QSpinBox()
        self._spin_voltage.setRange(100, 300)
        self._spin_voltage.setValue(220)
        self._spin_voltage.setSuffix("  V")

        self._spin_freq = QSpinBox()
        self._spin_freq.setRange(45, 65)
        self._spin_freq.setValue(50)
        self._spin_freq.setSuffix("  Hz")

        self._spin_runtime_lim = QSpinBox()
        self._spin_runtime_lim.setRange(0, 65535)
        self._spin_runtime_lim.setValue(120)
        self._spin_runtime_lim.setSuffix("  วินาที")

        btn_v  = QPushButton("Set  (RID 0x72)")
        btn_f  = QPushButton("Set  (RID 0x0D)")
        btn_rt = QPushButton("Set  (RID 0x17)")
        btn_v.clicked.connect(self._do_config_voltage)
        btn_f.clicked.connect(self._do_config_freq)
        btn_rt.clicked.connect(self._do_runtime_limit)

        lay.addWidget(QLabel("Config Voltage:"),           0, 0)
        lay.addWidget(self._spin_voltage,                  0, 1)
        lay.addWidget(btn_v,                               0, 2)
        lay.addWidget(QLabel("Config Frequency:"),         1, 0)
        lay.addWidget(self._spin_freq,                     1, 1)
        lay.addWidget(btn_f,                               1, 2)
        lay.addWidget(QLabel("Low Batt Runtime Limit:"),   2, 0)
        lay.addWidget(self._spin_runtime_lim,              2, 1)
        lay.addWidget(btn_rt,                              2, 2)
        return grp

    def _build_time_section(self) -> QGroupBox:
        grp = QGroupBox("นาฬิกา UPS  (RID 0x29 — Vendor Defined / ทดลองใช้)")
        lay = QGridLayout(grp)
        lay.setContentsMargins(8, 18, 8, 8)
        lay.setSpacing(8)
        lay.setColumnStretch(1, 1)

        self._time_status = QLabel("(ยังไม่ได้อ่าน)")
        self._time_status.setStyleSheet(f"color: {COLOR_TEXT_VALUE}; font-size: 12px;")

        btn_read = QPushButton("Read UPS Time")
        btn_set  = QPushButton("Set Time = PC Time")
        btn_set.setStyleSheet(
            f"background-color: #3A3A1A; color: {COLOR_TEXT_VALUE}; "
            f"border: 1px solid #7A7A3A; border-radius: 4px; padding: 5px 12px;"
        )
        btn_read.clicked.connect(self._do_read_time)
        btn_set.clicked.connect(self._do_set_time)

        warn = QLabel(
            "Warning: Vendor-defined field (Usage 0x0097) — experimental, "
            "may have no effect or may change another field"
        )
        warn.setStyleSheet(f"color: {COLOR_STATUS_WARN}; font-size: 11px;")

        lay.addWidget(QLabel("UPS time:"),  0, 0)
        lay.addWidget(self._time_status,    0, 1)
        lay.addWidget(btn_read,             0, 2)
        lay.addWidget(btn_set,              1, 2)
        lay.addWidget(warn,                 2, 0, 1, 3)
        return grp

    # ── helpers ─────────────────────────────────────────────────────────────

    def _send(self, rid: int, payload: list) -> None:
        self._worker.send_feature_report(rid, payload)

    def _send_u32(self, rid: int, value: int) -> None:
        self._send(rid, [(value >> (i * 8)) & 0xFF for i in range(4)])

    def _send_u16(self, rid: int, value: int) -> None:
        self._send(rid, [(value >> (i * 8)) & 0xFF for i in range(2)])

    def _do_shutdown(self) -> None:
        delay = self._spin_shutdown.value()
        reply = QMessageBox.warning(
            self,
            "ยืนยัน Shutdown",
            f"ต้องการสั่ง Shutdown UPS หลังจาก {delay} วินาทีใช่หรือไม่?\n\n"
            "\u26a0 UPS จะหยุดจ่ายไฟไปยังอุปกรณ์ที่ต่ออยู่",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply == QMessageBox.Yes:
            self._send_u32(0x09, delay)

    def _do_cancel_shutdown(self) -> None:
        self._send_u32(0x09, 0xFFFFFFFF)

    def _do_startup(self) -> None:
        self._send_u32(0x0A, self._spin_startup.value())

    def _do_config_voltage(self) -> None:
        self._send_u16(0x72, self._spin_voltage.value())

    def _do_config_freq(self) -> None:
        self._send(0x0D, [self._spin_freq.value()])

    def _do_runtime_limit(self) -> None:
        self._send_u16(0x17, self._spin_runtime_lim.value())

    # ── Self-Test ────────────────────────────────────────────────────────────

    def _run_test(self) -> None:
        self._send(0x24, [0x01])
        self._test_countdown = 12
        self._test_status_label.setText(
            f"กำลังทดสอบ... UPS สลับใช้ไฟจากแบตเตอรี่ (เหลือ {self._test_countdown} วิ)"
        )
        self._test_status_label.setStyleSheet(
            f"color: {COLOR_STATUS_WARN}; font-size: 12px; "
            f"background-color: {COLOR_BG_ROW_ALT}; padding: 5px; border-radius: 3px;"
        )
        self._test_poll_timer.start()

    def _abort_test(self) -> None:
        self._test_poll_timer.stop()
        self._send(0x24, [0x00])
        self._test_status_label.setText("ยกเลิกการทดสอบแล้ว")
        self._test_status_label.setStyleSheet(
            f"color: {COLOR_DIM}; font-size: 12px; "
            f"background-color: {COLOR_BG_ROW_ALT}; padding: 5px; border-radius: 3px;"
        )

    # RID 0x24 result values (ยืนยันจาก usbmon + การทดสอบจริง)
    _TEST_STATUS = {
        0x01: ("✅ ผ่าน / Idle",         COLOR_STATUS_OK),
        0x02: ("⚠️ Warning",              COLOR_STATUS_WARN),
        0x03: ("⏸ Abort",                COLOR_DIM),
        0x04: ("❌ ล้มเหลว / Failed",    COLOR_STATUS_ERR),
        0x05: ("🔄 กำลังทดสอบ...",        COLOR_STATUS_WARN),
    }

    def _poll_test_status(self) -> None:
        self._test_countdown -= 1

        # อ่านผลจริงจาก RID 0x24
        data = self._worker.read_feature_report(0x24, 4)
        if data and len(data) >= 2:
            val = data[1]
            label, color = self._TEST_STATUS.get(
                val, (f"สถานะ: 0x{val:02X}", COLOR_TEXT_VALUE)
            )
            running = (val == 0x05)

            if running:
                label = f"{label} (เหลือ ~{max(self._test_countdown, 0)} วิ)"
            else:
                self._test_poll_timer.stop()

            self._test_status_label.setText(label)
            self._test_status_label.setStyleSheet(
                f"color: {color}; font-size: 12px; "
                f"background-color: {COLOR_BG_ROW_ALT}; padding: 5px; border-radius: 3px;"
            )
            return

        # fallback: countdown เฉยๆ ถ้าอ่านไม่ได้
        if self._test_countdown > 0:
            self._test_status_label.setText(
                f"กำลังทดสอบ... (เหลือ {self._test_countdown} วิ)"
            )
        else:
            self._test_poll_timer.stop()
            self._test_status_label.setText("ทดสอบเสร็จสิ้น (ไม่สามารถอ่านผลได้)")
            self._test_status_label.setStyleSheet(
                f"color: {COLOR_DIM}; font-size: 12px; "
                f"background-color: {COLOR_BG_ROW_ALT}; padding: 5px; border-radius: 3px;"
            )

    # ── UPS time ─────────────────────────────────────────────────────────────

    _LOCAL_EPOCH = datetime.datetime(1970, 1, 1)

    def _do_read_time(self) -> None:
        data = self._worker.read_feature_report(0x29, 8)
        if data and len(data) >= 5:
            ts = data[1] | (data[2] << 8) | (data[3] << 16) | (data[4] << 24)
            if ts > 0:
                try:
                    dt = self._LOCAL_EPOCH + datetime.timedelta(seconds=ts)
                    self._time_status.setText(dt.strftime("%Y-%m-%d  %H:%M:%S"))
                    return
                except Exception:
                    pass
            self._time_status.setText(f"Raw: 0x{ts:08X}")
        else:
            self._time_status.setText("อ่านไม่ได้")

    def _do_set_time(self) -> None:
        now = datetime.datetime.now()
        ts  = int((now - self._LOCAL_EPOCH).total_seconds())
        reply = QMessageBox.question(
            self, "ยืนยันตั้งเวลา",
            f"Write PC time ({now.strftime('%Y-%m-%d %H:%M:%S')}) to the UPS?\n\n"
            "Warning: RID 0x29 is a Vendor-defined field\n"
            "It may have no effect or may change a different field instead",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply == QMessageBox.Yes:
            self._send_u32(0x29, ts)

    @Slot(str)
    def _on_result(self, message: str) -> None:
        ok = message.startswith("\u2713")
        color = COLOR_STATUS_OK if ok else COLOR_STATUS_ERR
        self._result_label.setText(message)
        self._result_label.setStyleSheet(
            f"color: {color}; font-size: 12px; "
            f"background-color: {COLOR_BG_SECTION}; padding: 6px; border-radius: 4px;"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Main Window
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UPS Monitor")
        self.resize(900, 780)
        self.setMinimumWidth(700)
        self.setStyleSheet(f"background-color: {COLOR_BG_WINDOW}; color: {COLOR_TEXT_VALUE};")

        self._build_ui()
        self._control_dialog: Optional[ControlDialog] = None
        self._worker = UPSWorker()
        self._worker.data_ready.connect(self._on_data)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.descriptor_ready.connect(self._on_descriptor_status)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._worker.poll_once)
        self._timer.start()

        QTimer.singleShot(100, self._worker.poll_once)

    def closeEvent(self, event):
        self._timer.stop()
        self._worker.stop()
        super().closeEvent(event)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {COLOR_BG_WINDOW}; border: none; }}"
        )
        scroll_content = QWidget()
        scroll_content.setStyleSheet(f"background-color: {COLOR_BG_WINDOW};")
        scroll.setWidget(scroll_content)

        grid = QGridLayout(scroll_content)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setSpacing(10)

        self._sec_device = Section("อุปกรณ์ (Device Info)", [
            ("manufacturer_string", "Manufacturer",  ""),
            ("product_string",      "Product",       ""),
            ("serial_number",       "Serial",        ""),
            ("release_number",      "Release",       ""),
            ("usage_page",          "Usage Page",    ""),
            ("usage",               "Usage",         ""),
        ])

        self._sec_status = Section("สถานะ (Status)", [
            ("ups.status",            "UPS Status",            ""),
            ("ups_mode",              "UPS Mode",              ""),
            ("ac_present",            "AC Present",            ""),
            ("charging",              "Charging",              ""),
            ("discharging",           "Discharging",           ""),
            ("below_capacity_limit",  "Below Capacity Limit",  ""),
            ("status_good",           "Status Good",           ""),
            ("battery_test_status",   "Battery Test",          ""),
        ])

        self._sec_fault = Section("ความผิดปกติ (Fault)", [
            ("internal_failure",  "Internal Failure",   ""),
            ("need_replacement",  "Need Replacement",   ""),
            ("overload",          "Overload",           ""),
            ("shutdown_imminent", "Shutdown Imminent",  ""),
            ("over_temperature",  "Over Temperature",   ""),
        ])

        self._sec_battery = Section("แบตเตอรี่ (Battery)", [
            ("battery.charge",                "Battery Charge",     "%"),
            ("battery_capacity_percent",      "Battery Capacity",   "%"),
            ("low_batt_alert_limit_percent",  "Low Batt Alert",     "%"),
            ("battery.charge.low",            "Low Batt Threshold", "% (config)"),
            ("battery.runtime",               "Runtime Remaining",  "s"),
            ("battery.runtime.hr",            "Runtime Remaining",  "hr"),
            ("battery_voltage_v",             "Battery Voltage",    "V"),
        ])

        self._sec_thermal = Section("ความร้อน / โหลด (Thermal & Load)", [
            ("temperature_c",  "Temperature",    "°C"),
            ("percent_load",   "Percent Load",   "%"),
        ])

        self._sec_output = Section("ไฟออก (Output)", [
            ("output_voltage_v",          "Output Voltage",        "V"),
            ("output_current_a",          "Output Current",        "A"),
            ("output_frequency_hz",       "Output Frequency",      "Hz"),
            ("output_active_power_w",     "Output Active Power",   "W"),
            ("output_apparent_power_va",  "Output Apparent Power", "VA"),
        ])

        self._sec_input = Section("ไฟเข้า / ค่าตั้ง (Input & Config)", [
            ("input.voltage",               "Input Voltage",         "V"),
            ("input.frequency",             "Input Frequency",       "Hz"),
            ("input.voltage.nominal",       "Nominal Voltage",       "V (config)"),
            ("input.frequency.nominal",     "Nominal Frequency",     "Hz (config)"),
            ("config_nominal_voltage_v",    "Config Nominal Voltage",    "V"),
            ("config_nominal_frequency_hz", "Config Nominal Frequency",  "Hz"),
            ("input.transfer.low",          "Low Transfer Voltage",  "V"),
        ])

        self._sec_info = Section("ข้อมูลอื่น (Info)", [
            ("ups.firmware",   "Firmware Version", ""),
            ("last_event_date","Last Event Date",  ""),
        ])

        for row_idx, sec in enumerate([
            self._sec_device,
            self._sec_status,
            self._sec_fault,
            self._sec_info,
        ]):
            grid.addWidget(sec, row_idx, 0)

        for row_idx, sec in enumerate([
            self._sec_battery,
            self._sec_thermal,
            self._sec_output,
            self._sec_input,
        ]):
            grid.addWidget(sec, row_idx, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        root.addWidget(scroll)
        self._status_bar = StatusBarWidget()
        root.addWidget(self._status_bar)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setStyleSheet(
            f"background-color: {COLOR_BG_SECTION}; border-bottom: 1px solid {COLOR_BORDER};"
        )
        header.setFixedHeight(54)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 8, 16, 8)

        title = QLabel("UPS Monitor")
        title.setStyleSheet(
            f"color: {COLOR_STATUS_INFO}; font-size: 16px; font-weight: bold; border: none;"
        )

        self._header_subtitle = QLabel("Real-time polling 1s")
        self._header_subtitle.setStyleSheet(
            f"color: {COLOR_TEXT_LABEL}; font-size: 11px; border: none;"
        )
        self._header_subtitle.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        btn_control = QPushButton("Control")
        btn_control.setStyleSheet(
            f"background-color: {COLOR_BG_SECTION}; color: {COLOR_STATUS_INFO}; "
            f"border: 1px solid {COLOR_BORDER}; border-radius: 4px; "
            f"padding: 4px 14px; font-size: 12px;"
        )
        btn_control.setCursor(Qt.PointingHandCursor)
        btn_control.clicked.connect(self._open_control_panel)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(self._header_subtitle)
        layout.addWidget(btn_control)
        return header

    @Slot(dict, dict)
    def _on_data(self, device_info: dict, ups: dict) -> None:
        self._status_bar.set_connected(True)
        self._status_bar.set_time(time.strftime("%H:%M:%S"))
        _update_api_store(device_info, ups)

        print("\n--- รายชื่อตัวแปรและค่าที่ UPS ส่งมา ---")
        for key, value in ups.items():
            print(f"Key: {key:<30} | Value: {value}")
        print("------------------------------------------")

        mfr  = device_info.get("manufacturer_string") or ""
        prod = device_info.get("product_string") or ""
        device_label = " / ".join(filter(None, [mfr, prod])) or "UPS"
        self._header_subtitle.setText(f"{device_label}  |  Real-time polling 1s")
        self.setWindowTitle(f"UPS Monitor — {device_label}")

        self._sec_device.update_row("manufacturer_string", device_info.get("manufacturer_string"))
        self._sec_device.update_row("product_string",      device_info.get("product_string"))
        self._sec_device.update_row("serial_number",       device_info.get("serial_number"))
        self._sec_device.update_row("release_number",      device_info.get("release_number"))
        up = device_info.get("usage_page")
        self._sec_device.update_row("usage_page", f"0x{up:04X}" if up is not None else None)
        u = device_info.get("usage")
        self._sec_device.update_row("usage", f"0x{u:04X}" if u is not None else None)

        nut = ups.get("ups.status", "")
        nut_color = (
            COLOR_STATUS_OK  if "OL" in str(nut) and "OB" not in str(nut) else
            COLOR_STATUS_ERR if "OB" in str(nut) else
            COLOR_STATUS_WARN
        )
        self._sec_status.update_row("ups.status", nut or None, color=nut_color)
        self._sec_status.update_row("ups_mode", ups.get("ups_mode"), color=COLOR_STATUS_INFO)

        for key in ("ac_present", "charging", "discharging", "below_capacity_limit", "status_good"):
            val = ups.get(key)
            if val is None:
                self._sec_status.update_row(key, None)
            else:
                b = bool(val)
                self._sec_status.update_row(key, "True" if b else "False", color=_bool_color(key, b))

        test_st = ups.get("battery_test_status")
        _test_color = {
            "idle":    COLOR_STATUS_OK,
            "running": COLOR_STATUS_WARN,
            "failed":  COLOR_STATUS_ERR,
            "warning": COLOR_STATUS_WARN,
            "abort":   COLOR_DIM,
        }
        self._sec_status.update_row(
            "battery_test_status",
            test_st,
            color=_test_color.get(str(test_st), COLOR_TEXT_VALUE),
        )

        for key in ("internal_failure", "need_replacement", "overload", "shutdown_imminent", "over_temperature"):
            val = ups.get(key)
            if val is None:
                self._sec_fault.update_row(key, None)
            else:
                b = bool(val)
                self._sec_fault.update_row(key, "True" if b else "False",
                                           color=COLOR_STATUS_ERR if b else COLOR_STATUS_OK)

        charge = ups.get("battery.charge")
        charge_color = (
            COLOR_STATUS_ERR  if isinstance(charge, (int, float)) and charge < 20  else
            COLOR_STATUS_WARN if isinstance(charge, (int, float)) and charge < 50  else
            COLOR_STATUS_OK
        )
        self._sec_battery.update_row("battery.charge",               charge, color=charge_color)
        self._sec_battery.update_row("battery_capacity_percent",     ups.get("battery_capacity_percent"))
        self._sec_battery.update_row("low_batt_alert_limit_percent", ups.get("low_batt_alert_limit_percent"))
        self._sec_battery.update_row("battery.charge.low",           ups.get("battery.charge.low"))
        self._sec_battery.update_row("battery.runtime",              ups.get("battery.runtime"))
        self._sec_battery.update_row("battery.runtime.hr",           ups.get("battery.runtime.hr"))
        self._sec_battery.update_row("battery_voltage_v",            ups.get("battery_voltage_v"))

        temp = ups.get("temperature_c") or ups.get("ups.temperature")
        temp_color = (
            COLOR_STATUS_ERR  if isinstance(temp, (int, float)) and temp > 55 else
            COLOR_STATUS_WARN if isinstance(temp, (int, float)) and temp > 45 else
            COLOR_TEXT_VALUE
        )
        self._sec_thermal.update_row("temperature_c", temp, color=temp_color)
        self._sec_thermal.update_row("percent_load",  ups.get("percent_load"))

        self._sec_output.update_row("output_voltage_v",         ups.get("output_voltage_v") or ups.get("output.voltage"))
        self._sec_output.update_row("output_current_a",         ups.get("output_current_a"))
        self._sec_output.update_row("output_frequency_hz",      ups.get("output_frequency_hz"))
        self._sec_output.update_row("output_active_power_w",    ups.get("output_active_power_w"))
        self._sec_output.update_row("output_apparent_power_va", ups.get("output_apparent_power_va"))

        self._sec_input.update_row("input.voltage",               ups.get("input.voltage"))
        self._sec_input.update_row("input.frequency",             ups.get("input.frequency"))
        self._sec_input.update_row("input.voltage.nominal",       ups.get("input.voltage.nominal"))
        self._sec_input.update_row("input.frequency.nominal",     ups.get("input.frequency.nominal"))
        self._sec_input.update_row("config_nominal_voltage_v",    ups.get("config_nominal_voltage_v"))
        self._sec_input.update_row("config_nominal_frequency_hz", ups.get("config_nominal_frequency_hz"))
        self._sec_input.update_row("input.transfer.low",          ups.get("input.transfer.low"))

        self._sec_info.update_row("ups.firmware",    ups.get("ups.firmware"))
        self._sec_info.update_row("last_event_date", ups.get("last_event_date"))

    @Slot(str)
    def _on_error(self, message: str) -> None:
        if message:
            self._status_bar.set_connected(False, message)

    @Slot(str)
    def _on_descriptor_status(self, message: str) -> None:
        self._status_bar.set_descriptor_status(message)

    def _open_control_panel(self) -> None:
        if self._control_dialog is None:
            self._control_dialog = ControlDialog(self._worker, self)
        self._control_dialog.show()
        self._control_dialog.raise_()
        self._control_dialog.activateWindow()


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _bool_color(key: str, value: bool) -> str:
    good_when_true = {"ac_present", "charging", "status_good"}
    bad_when_true  = {"discharging", "below_capacity_limit"}
    if key in good_when_true:
        return COLOR_STATUS_OK   if value else COLOR_DIM
    if key in bad_when_true:
        return COLOR_STATUS_WARN if value else COLOR_STATUS_OK
    return COLOR_TEXT_VALUE


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# Linux permission setup
# ══════════════════════════════════════════════════════════════════════════════

UDEV_RULE_PATH = "/etc/udev/rules.d/99-ups-hid.rules"
UDEV_RULE_CONTENT = (
    'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="06da", '
    'ATTRS{idProduct}=="ffff", MODE="0660", GROUP="plugdev"\n'
    'SUBSYSTEM=="usb", ATTRS{idVendor}=="06da", '
    'ATTRS{idProduct}=="ffff", MODE="0660", GROUP="plugdev"\n'
)


def _check_hid_permission() -> bool:
    """ตรวจสอบว่าสามารถ enumerate HID device ได้ไหม"""
    try:
        import hid as _hid
        devices = _hid.enumerate(VID, PID)
        if not devices:
            return True   # ไม่มีอุปกรณ์ แต่ไม่ใช่ปัญหาสิทธิ์
        # ลอง open จริง
        h = _hid.device()
        h.open_path(devices[0]["path"])
        h.close()
        return True
    except OSError:
        return False
    except Exception:
        return True


def _try_setup_permissions() -> None:
    """แสดงคำแนะนำหรือสร้าง udev rule อัตโนมัติถ้าเป็น root"""
    import os, subprocess

    is_root = (os.geteuid() == 0)

    if is_root:
        # สร้าง udev rule โดยตรง
        try:
            with open(UDEV_RULE_PATH, "w") as f:
                f.write(UDEV_RULE_CONTENT)
            subprocess.run(["udevadm", "control", "--reload-rules"], check=False)
            subprocess.run(["udevadm", "trigger", "--subsystem-match=hidraw",
                            "--subsystem-match=usb"], check=False)
            print(f"[setup] สร้าง udev rule ที่ {UDEV_RULE_PATH} แล้ว")
            print("[setup] กรุณา logout/login ใหม่ถ้า user ยังเข้าไม่ได้")
            return
        except OSError as e:
            print(f"[setup] สร้าง udev rule ไม่ได้: {e}")

    # ไม่ใช่ root — แสดงคำแนะนำ (ใช้ sys.executable เพื่อให้ชี้ไปที่ venv)
    python = sys.executable
    username = os.environ.get("USER", os.environ.get("LOGNAME", "$USER"))
    print("\n" + "=" * 60)
    print("⚠️  ไม่มีสิทธิ์เข้าถึง USB HID device")
    print("=" * 60)
    print("รันคำสั่งต่อไปนี้ครั้งเดียวเพื่อแก้ปัญหาถาวร:\n")
    print(f"  sudo tee {UDEV_RULE_PATH} <<'EOF'")
    print(UDEV_RULE_CONTENT.strip())
    print("EOF")
    print("  sudo udevadm control --reload-rules")
    print("  sudo udevadm trigger")
    print(f"  sudo usermod -aG plugdev {username}")
    print("  # แล้ว logout + login ใหม่")
    print("=" * 60 + "\n")
    print("หรือรัน script นี้ด้วย sudo ครั้งเดียวเพื่อให้ setup อัตโนมัติ:")
    print(f"  sudo {python} {sys.argv[0]}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# REST API Server  (Flask — optional,  pip install flask)
# ══════════════════════════════════════════════════════════════════════════════

_api_store: dict = {"device": {}, "ups": {}, "timestamp": None}
_api_lock = threading.Lock()


def _sanitize_for_json(d: dict) -> dict:
    """แปลง bytes / ประเภทที่ JSON ไม่รองรับให้เป็น str"""
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, (bytes, bytearray)):
            out[k] = v.decode("utf-8", errors="ignore")
        elif isinstance(v, (int, float, str, bool, type(None))):
            out[k] = v
        elif isinstance(v, list):
            out[k] = [
                x.decode("utf-8", errors="ignore")
                if isinstance(x, (bytes, bytearray))
                else (x if isinstance(x, (int, float, str, bool, type(None))) else str(x))
                for x in v
            ]
        else:
            out[k] = str(v)
    return out


def _update_api_store(device_info: dict, ups: dict) -> None:
    with _api_lock:
        _api_store["device"] = _sanitize_for_json(device_info)
        _api_store["ups"] = _sanitize_for_json(ups)
        _api_store["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")


def _create_flask_app():
    try:
        from flask import Flask, jsonify
    except ImportError:
        return None

    import logging
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    app = Flask(__name__)

    @app.route("/api/health")
    def api_health():
        with _api_lock:
            return jsonify({
                "status": "ok",
                "connected": _api_store["timestamp"] is not None,
                "timestamp": _api_store["timestamp"],
            })

    @app.route("/api/ups")
    def api_ups():
        with _api_lock:
            return jsonify({
                "device": _api_store["device"],
                "ups": _api_store["ups"],
                "timestamp": _api_store["timestamp"],
            })

    @app.route("/api/ups/status")
    def api_status():
        with _api_lock:
            ups = _api_store["ups"]
            return jsonify({
                "ups.status":           ups.get("ups.status"),
                "ac_present":           ups.get("ac_present"),
                "charging":             ups.get("charging"),
                "discharging":          ups.get("discharging"),
                "below_capacity_limit": ups.get("below_capacity_limit"),
                "status_good":          ups.get("status_good"),
                "timestamp":            _api_store["timestamp"],
            })

    @app.route("/api/ups/battery")
    def api_battery():
        with _api_lock:
            ups = _api_store["ups"]
            return jsonify({
                "battery.charge":     ups.get("battery.charge"),
                "battery.runtime":    ups.get("battery.runtime"),
                "battery.runtime.hr": ups.get("battery.runtime.hr"),
                "battery_voltage_v":  ups.get("battery_voltage_v"),
                "timestamp":          _api_store["timestamp"],
            })

    return app


def _start_api_server(host: str = "127.0.0.1", port: int = 5000) -> None:
    app = _create_flask_app()
    if app is None:
        print("[API] ไม่พบ flask — ข้าม REST API (pip install flask)")
        return
    print(f"[API] REST API พร้อมใช้งานที่  http://{host}:{port}/api/ups")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


def start_api_thread(host: str = "127.0.0.1", port: int = 5000) -> None:
    t = threading.Thread(
        target=_start_api_server, args=(host, port), daemon=True, name="ups-rest-api"
    )
    t.start()


def main() -> int:
    # ── ตรวจสอบและแก้สิทธิ์ ─────────────────────────────────────────────────
    if not _check_hid_permission():
        _try_setup_permissions()
        # ถ้า root ทำ setup แล้ว ให้รันต่อ; ถ้าไม่ใช่ root ให้ exit
        import os
        if os.geteuid() != 0:
            sys.exit(1)

    start_api_thread()
    app = QApplication(sys.argv)
    app.setApplicationName("UPS Monitor")
    app.setApplicationVersion("1.0")

    palette = QPalette()
    palette.setColor(QPalette.Window,        QColor(COLOR_BG_WINDOW))
    palette.setColor(QPalette.WindowText,    QColor(COLOR_TEXT_VALUE))
    palette.setColor(QPalette.Base,          QColor(COLOR_BG_SECTION))
    palette.setColor(QPalette.AlternateBase, QColor(COLOR_BG_ROW_ALT))
    palette.setColor(QPalette.Text,          QColor(COLOR_TEXT_VALUE))
    palette.setColor(QPalette.ButtonText,    QColor(COLOR_TEXT_VALUE))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
