"""
UPS Monitor GUI — Linux (Tailored Version)
Real-time display via PySide6, polls every 1 second.
"""

import datetime
import re
import sys
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
except ImportError:
    HID_AVAILABLE = False
    VID = 0x06DA
    PID = 0xFFFF
    DEFAULT_REPORT_SIZES = (64,)
    DEFAULT_DESCRIPTOR_BIN = "report_descriptor_live.bin"
    DEFAULT_DESCRIPTOR_TXT = "report_descriptor_live.txt"

POLL_INTERVAL_MS = 1000  # 1 วินาที

def _read_descriptor_from_sysfs(device_path: object) -> Optional[bytes]:
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

COLOR_STATUS_OK   = "#4ECA6E"   
COLOR_STATUS_WARN = "#F5A623"   
COLOR_STATUS_ERR  = "#E04A4A"   
COLOR_STATUS_INFO = "#56B0F5"   
COLOR_DIM         = "#606080"   

# ══════════════════════════════════════════════════════════════════════════════
# Worker Thread
# ══════════════════════════════════════════════════════════════════════════════
class UPSWorker(QThread):
    data_ready = Signal(dict, dict)
    error_occurred = Signal(str)
    descriptor_ready = Signal(str)
    command_result = Signal(str)

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
            try: self._h.close()
            except Exception: pass
            self._h = None

    def poll_once(self) -> None:
        if not HID_AVAILABLE:
            self.error_occurred.emit("ไม่พบ module hid_ups")
            return
        if self._h is None:
            self._connect()
            return
        try:
            raw, _ = read_all_feature_reports(
                self._h, report_ids=self._report_ids, sizes=(64,), retries=1, include_zero=False
            )
            ups = decode_feature_reports(raw)
            ups.update(infer_tentative_live_values(raw, ups))
            self.data_ready.emit(self._info, ups)
        except Exception as exc:
            try: self._h.close()
            except Exception: pass
            self._h = None
            self.error_occurred.emit(f"Poll error: {exc}")

    def _connect(self) -> None:
        try:
            h, info = open_ups_device(self.vid, self.pid)
            if h is None:
                self.error_occurred.emit(f"ไม่พบอุปกรณ์ VID=0x{self.vid:04X} PID=0x{self.pid:04X}")
                return
            self._h = h
            self._info = info or {}
            self._read_descriptor()
            self.error_occurred.emit("")
        except Exception as exc:
            self.error_occurred.emit(f"Connect error: {exc}")

    def _read_descriptor(self) -> None:
        raw_path = self._info.get("path")
        if not raw_path:
            self.descriptor_ready.emit("Profile: — (ไม่มี device path)")
            return
        descriptor_bytes = _read_descriptor_from_sysfs(raw_path)
        if not descriptor_bytes:
            self.descriptor_ready.emit("Profile: — (อ่าน sysfs ไม่ได้)")
            return
        bin_path = Path(DEFAULT_DESCRIPTOR_BIN)
        try:
            bin_path.write_bytes(descriptor_bytes)
            self._descriptor_profile = load_descriptor_profile(bin_path, Path(DEFAULT_DESCRIPTOR_TXT))
            ids = get_descriptor_feature_ids(self._descriptor_profile)
            if ids:
                self._report_ids = ids
                self.descriptor_ready.emit(f"Profile: {len(descriptor_bytes)}B → {len(ids)} report IDs")
            else:
                self.descriptor_ready.emit(f"Profile: {len(descriptor_bytes)}B (scan 0x01-0x7F)")
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
        if not self._h: return None
        try:
            data = self._h.get_feature_report(rid, size)
            return list(data) if data else None
        except Exception: return None

    def read_interrupt_data(self, size: int = 64, timeout_ms: int = 500) -> Optional[list]:
        if not self._h: return None
        try:
            data = self._h.read(size, timeout_ms)
            return data if data else None
        except Exception: return None

# ══════════════════════════════════════════════════════════════════════════════
# UI Components
# ══════════════════════════════════════════════════════════════════════════════
class ValueRow(QWidget):
    def __init__(self, label: str, unit: str = "", parent: Optional[QWidget] = None, alt_bg: bool = False):
        super().__init__(parent)
        self._unit = unit
        self.setAutoFillBackground(True)
        bg = COLOR_BG_ROW_ALT if alt_bg else COLOR_BG_SECTION
        self.setStyleSheet(f"background-color: {bg};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        self._label_w = QLabel(label)
        self._label_w.setFixedWidth(220)
        self._label_w.setStyleSheet(f"color: {COLOR_TEXT_LABEL}; font-size: 12px;")
        self._value_w = QLabel("—")
        self._value_w.setStyleSheet(f"color: {COLOR_TEXT_VALUE}; font-size: 13px; font-weight: bold;")
        self._value_w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._label_w)
        layout.addStretch()
        layout.addWidget(self._value_w)

    def set_value(self, value: object, color: Optional[str] = None, suffix: Optional[str] = None) -> None:
        if value is None or value == "": text = "—"
        elif isinstance(value, float): text = f"{value:.1f}"
        else: text = str(value)
        unit = suffix if suffix is not None else self._unit
        self._value_w.setText(f"{text}  {unit}".strip() if unit else text)
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
            QGroupBox {{ background-color: {COLOR_BG_SECTION}; border: 1px solid {COLOR_BORDER}; border-radius: 6px; margin-top: 10px; padding: 4px; }}
            QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 2px 10px; color: {COLOR_TEXT_TITLE}; font-size: 12px; font-weight: bold; }}
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
        if key in self._rows:
            if value is None: self._rows[key].set_na()
            else: self._rows[key].set_value(value, color=color, suffix=suffix)

class StatusBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {COLOR_BG_SECTION}; border-top: 1px solid {COLOR_BORDER};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
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
        self._desc_label.setStyleSheet(f"color: {COLOR_STATUS_OK if 'IDs' in message else COLOR_DIM}; font-size: 11px;")

    def set_connected(self, ok: bool, message: str = "") -> None:
        if ok:
            self._conn_label.setText("เชื่อมต่อแล้ว")
            self._conn_label.setStyleSheet(f"color: {COLOR_STATUS_OK}; font-size: 12px;")
        else:
            self._conn_label.setText(f"ผิดพลาด: {message}" if message else "ไม่ได้เชื่อมต่อ")
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
        self.setMinimumWidth(520)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {COLOR_BG_WINDOW}; }}
            QGroupBox {{ background-color: {COLOR_BG_SECTION}; border: 1px solid {COLOR_BORDER}; border-radius: 5px; margin-top: 10px; color: {COLOR_TEXT_TITLE}; font-weight: bold; }}
            QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 2px 8px; }}
            QLabel {{ color: {COLOR_TEXT_LABEL}; font-size: 12px; }}
            QSpinBox {{ background-color: {COLOR_BG_ROW_ALT}; color: {COLOR_TEXT_VALUE}; border: 1px solid {COLOR_BORDER}; padding: 3px 6px; }}
            QPushButton {{ background-color: {COLOR_BG_SECTION}; color: {COLOR_TEXT_VALUE}; border: 1px solid {COLOR_BORDER}; border-radius: 4px; padding: 5px 12px; }}
            QPushButton:hover {{ background-color: {COLOR_BORDER}; }}
        """)
        root = QVBoxLayout(self)
        root.addWidget(self._build_test_section())
        
        self._test_poll_timer = QTimer(self)
        self._test_poll_timer.setInterval(1000)
        self._test_poll_timer.timeout.connect(self._poll_test_status)
        self._test_countdown = 0

        self._result_label = QLabel("พร้อมรับคำสั่ง")
        self._result_label.setStyleSheet(f"color: {COLOR_STATUS_INFO}; padding: 6px; background-color: {COLOR_BG_SECTION};")
        root.addWidget(self._result_label)
        self._worker.command_result.connect(self._on_result)

    def _build_test_section(self) -> QGroupBox:
        grp = QGroupBox("Self Test  (RID 0x24)")
        lay = QVBoxLayout(grp)
        btn_row = QHBoxLayout()
        btn_run = QPushButton("Run Self-Test")
        btn_run.clicked.connect(self._run_test)
        btn_abort = QPushButton("Abort Test")
        btn_abort.clicked.connect(self._abort_test)
        btn_row.addWidget(btn_run)
        btn_row.addWidget(btn_abort)
        btn_row.addStretch()
        self._test_status_label = QLabel("\u2500")
        self._test_status_label.setStyleSheet(f"color: {COLOR_TEXT_VALUE}; background-color: {COLOR_BG_ROW_ALT}; padding: 5px;")
        warn = QLabel("\u26a0 สังเกตผลลัพธ์ที่หมวด 'การแจ้งเตือน' ในหน้าจอหลัก")
        warn.setStyleSheet(f"color: {COLOR_STATUS_WARN}; font-size: 11px;")
        lay.addLayout(btn_row)
        lay.addWidget(self._test_status_label)
        lay.addWidget(warn)
        return grp

    def _send(self, rid: int, payload: list) -> None:
        self._worker.send_feature_report(rid, payload)

    def _run_test(self) -> None:
        self._send(0x24, [0x01])
        self._test_countdown = 12
        self._test_status_label.setText(f"กำลังทดสอบ... สลับใช้ไฟจากแบตเตอรี่ (เหลือ {self._test_countdown} วิ)")
        self._test_status_label.setStyleSheet(f"color: {COLOR_STATUS_WARN}; background-color: {COLOR_BG_ROW_ALT}; padding: 5px;")
        self._test_poll_timer.start()

    def _abort_test(self) -> None:
        self._test_poll_timer.stop()
        self._send(0x24, [0x00])
        self._test_status_label.setText("ยกเลิกการทดสอบแล้ว")
        self._test_status_label.setStyleSheet(f"color: {COLOR_DIM}; background-color: {COLOR_BG_ROW_ALT}; padding: 5px;")

    def _poll_test_status(self) -> None:
        self._test_countdown -= 1
        if self._test_countdown > 0:
            self._test_status_label.setText(f"กำลังทดสอบ... สลับใช้ไฟจากแบตเตอรี่ (เหลือ {self._test_countdown} วิ)")
        else:
            self._test_poll_timer.stop()
            self._test_status_label.setText("✅ ทดสอบเสร็จสิ้น! (ดูผลลัพธ์ที่หมวด 'การแจ้งเตือน' ในหน้าจอหลัก)")
            self._test_status_label.setStyleSheet(f"color: {COLOR_STATUS_OK}; background-color: {COLOR_BG_ROW_ALT}; padding: 5px;")

    @Slot(str)
    def _on_result(self, message: str) -> None:
        color = COLOR_STATUS_OK if message.startswith("\u2713") else COLOR_STATUS_ERR
        self._result_label.setText(message)
        self._result_label.setStyleSheet(f"color: {color}; background-color: {COLOR_BG_SECTION}; padding: 6px;")

# ══════════════════════════════════════════════════════════════════════════════
# Main Window
# ══════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UPS Monitor")
        self.resize(900, 780)
        self.setStyleSheet(f"background-color: {COLOR_BG_WINDOW}; color: {COLOR_TEXT_VALUE};")
        self._build_ui()
        self._control_dialog = None
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
        
        # Header
        header = QWidget()
        header.setStyleSheet(f"background-color: {COLOR_BG_SECTION}; border-bottom: 1px solid {COLOR_BORDER};")
        lay_h = QHBoxLayout(header)
        title = QLabel("UPS Monitor (Innova Unity)")
        title.setStyleSheet(f"color: {COLOR_STATUS_INFO}; font-size: 16px; font-weight: bold; border: none;")
        self._header_subtitle = QLabel("Real-time polling 1s")
        self._header_subtitle.setStyleSheet(f"color: {COLOR_TEXT_LABEL}; font-size: 11px; border: none;")
        btn_control = QPushButton("Control Panel")
        btn_control.setStyleSheet(f"background-color: {COLOR_BG_SECTION}; color: {COLOR_STATUS_INFO}; border: 1px solid {COLOR_BORDER}; padding: 4px 14px;")
        btn_control.clicked.connect(self._open_control_panel)
        lay_h.addWidget(title)
        lay_h.addStretch()
        lay_h.addWidget(self._header_subtitle)
        lay_h.addWidget(btn_control)
        root.addWidget(header)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: {COLOR_BG_WINDOW}; border: none; }}")
        scroll_content = QWidget()
        grid = QGridLayout(scroll_content)

        # ── 1. ข้อมูลระบบ ──
        self._sec_device = Section("อุปกรณ์ (Device Info)", [
            ("manufacturer_string", "Manufacturer",  ""),
            ("product_string",      "Product",       ""),
            ("serial_number",       "Serial",        ""),
            ("ups.firmware",        "Firmware",      ""),
        ])

        # ── 2. สถานะการทำงาน ──
        self._sec_status = Section("สถานะปัจจุบัน (Status)", [
            ("ups.status",            "UPS Status",            ""),
            ("ups_mode",              "UPS Mode",              ""),
            ("ac_present",            "AC Present (ไฟบ้าน)",     ""),
            ("charging",              "Charging (กำลังชาร์จ)",    ""),
            ("discharging",           "Discharging (ใช้ไฟแบต)",  ""),
        ])

        # ── 3. แบตเตอรี่ ──
        self._sec_battery = Section("แบตเตอรี่ (Battery)", [
            ("battery.charge",                "Battery Charge",     "%"),
            ("battery_voltage_v",             "Battery Voltage",    "V"),
            ("battery.runtime.hr",            "Runtime Remaining",  "hr"),
            ("battery.charge.low",            "Low Batt Threshold", "%"),
        ])

        # ── 4. ไฟเข้าและไฟออก ──
        self._sec_power = Section("กระแสไฟฟ้า (Power IO)", [
            ("output_voltage_v",          "Output Voltage (ไฟออก)",  "V"),
            ("input.frequency",           "Input Frequency (ความถี่)", "Hz"),
            ("output_active_power_w",     "Active Power (โหลด)",    "W"),
            ("percent_load",              "Percent Load",           "%"),
            ("temperature_c",             "System Temperature",     "°C"),
        ])

        # ── 5. การแจ้งเตือน (แทนที่ Fault เดิม) ──
        self._sec_alert = Section("การแจ้งเตือน (Alerts)", [
            ("alert_system_fault",  "System Fault (ระบบมีปัญหา)", ""),
            ("alert_low_batt",      "Low Battery (แบตเตอรี่ต่ำ)",   ""),
        ])

        # ── 6. ค่าที่ตั้งไว้ (Config) ──
        self._sec_config = Section("ค่าคอนฟิก (Configuration)", [
            ("config_nominal_voltage_v",    "Config Nominal Voltage",    "V"),
            ("config_nominal_frequency_hz", "Config Nominal Frequency",  "Hz"),
            ("input.transfer.low",          "Low Transfer Voltage",      "V"),
            ("last_event_date",             "Last Event Date",           ""),
        ])

        # จัดวาง Grid
        grid.addWidget(self._sec_device,  0, 0)
        grid.addWidget(self._sec_status,  1, 0)
        grid.addWidget(self._sec_alert,   2, 0)

        grid.addWidget(self._sec_power,   0, 1)
        grid.addWidget(self._sec_battery, 1, 1)
        grid.addWidget(self._sec_config,  2, 1)

        scroll.setWidget(scroll_content)
        root.addWidget(scroll)

        self._status_bar = StatusBarWidget()
        root.addWidget(self._status_bar)

    @Slot(dict, dict)
    def _on_data(self, device_info: dict, ups: dict) -> None:
        self._status_bar.set_connected(True)
        self._status_bar.set_time(time.strftime("%H:%M:%S"))

        # 1. ข้อมูลระบบ
        self._sec_device.update_row("manufacturer_string", device_info.get("manufacturer_string"))
        self._sec_device.update_row("product_string",      device_info.get("product_string"))
        self._sec_device.update_row("serial_number",       device_info.get("serial_number"))
        self._sec_device.update_row("ups.firmware",        ups.get("ups.firmware"))

        # 2. สถานะปัจจุบัน
        nut = ups.get("ups.status", "")
        self._sec_status.update_row("ups.status", nut or None, color=COLOR_STATUS_OK if "OL" in str(nut) else COLOR_STATUS_WARN)
        self._sec_status.update_row("ups_mode", ups.get("ups_mode"), color=COLOR_STATUS_INFO)
        
        for key in ("ac_present", "charging", "discharging"):
            val = ups.get(key)
            if val is not None:
                b = bool(val)
                c = COLOR_STATUS_OK if (b and key != "discharging") else (COLOR_STATUS_WARN if b else COLOR_DIM)
                self._sec_status.update_row(key, "True" if b else "False", color=c)

        # 3. แบตเตอรี่
        self._sec_battery.update_row("battery.charge",     ups.get("battery.charge"), color=COLOR_STATUS_OK if ups.get("battery.charge", 0) > 20 else COLOR_STATUS_ERR)
        self._sec_battery.update_row("battery_voltage_v",  ups.get("battery_voltage_v"))
        self._sec_battery.update_row("battery.runtime.hr", ups.get("battery.runtime.hr"))
        self._sec_battery.update_row("battery.charge.low", ups.get("battery.charge.low"))

        # 4. กระแสไฟฟ้า (Power IO)
        self._sec_power.update_row("output_voltage_v",      ups.get("output_voltage_v"))
        self._sec_power.update_row("input.frequency",       ups.get("input.frequency"))
        self._sec_power.update_row("output_active_power_w", ups.get("output_active_power_w"))
        self._sec_power.update_row("percent_load",          ups.get("percent_load"))
        self._sec_power.update_row("temperature_c",         ups.get("temperature_c"))

        # 5. การแจ้งเตือน (แปลงจาก Status_Good และ Below_Capacity)
        status_good = ups.get("status_good")
        if status_good is not None:
            sys_fault = not bool(status_good)
            self._sec_alert.update_row("alert_system_fault", "True" if sys_fault else "False", color=COLOR_STATUS_ERR if sys_fault else COLOR_STATUS_OK)
        
        low_batt = ups.get("below_capacity_limit")
        if low_batt is not None:
            self._sec_alert.update_row("alert_low_batt", "True" if bool(low_batt) else "False", color=COLOR_STATUS_ERR if bool(low_batt) else COLOR_STATUS_OK)

        # 6. ค่าที่ตั้งไว้
        self._sec_config.update_row("config_nominal_voltage_v",    ups.get("config_nominal_voltage_v"))
        self._sec_config.update_row("config_nominal_frequency_hz", ups.get("config_nominal_frequency_hz"))
        self._sec_config.update_row("input.transfer.low",          ups.get("input.transfer.low"))
        self._sec_config.update_row("last_event_date",             ups.get("last_event_date"))

    @Slot(str)
    def _on_error(self, message: str) -> None:
        if message: self._status_bar.set_connected(False, message)

    @Slot(str)
    def _on_descriptor_status(self, message: str) -> None:
        self._status_bar.set_descriptor_status(message)

    def _open_control_panel(self) -> None:
        if self._control_dialog is None:
            self._control_dialog = ControlDialog(self._worker, self)
        self._control_dialog.show()
        self._control_dialog.raise_()
        self._control_dialog.activateWindow()

def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("UPS Monitor")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLOR_BG_WINDOW))
    palette.setColor(QPalette.WindowText, QColor(COLOR_TEXT_VALUE))
    app.setPalette(palette)
    window = MainWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())