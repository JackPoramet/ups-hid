"""
UPS Monitor — Flask Web Server
=================================
ให้บริการ Web UI (dashboard, settings, device info) ที่ localhost:<port>
และ REST API สำหรับดึงข้อมูล UPS และสั่งการต่างๆ

REST API Endpoints:
    GET  /api/health          — สถานะ server
    GET  /api/ups             — ข้อมูล UPS ทั้งหมด
    GET  /api/ups/status      — สถานะหลัก (AC, charging, discharging)
    GET  /api/ups/battery     — ข้อมูลแบตเตอรี่
    GET  /api/ups/device      — ข้อมูล device (Manufacturer, Serial ฯลฯ)
    GET  /api/config          — อ่าน config ปัจจุบัน
    POST /api/config          — อัปเดต config (body: JSON)
    POST /api/control/monitor/start   — เริ่ม monitoring
    POST /api/control/monitor/stop    — หยุด monitoring
    POST /api/control/shutdown/cancel — ยกเลิก PC auto-shutdown
    POST /api/ups/control/test        — สั่ง UPS self-test
    POST /api/ups/control/ups_shutdown — สั่ง UPS output shutdown

Design:
    - Flask run ใน daemon thread แยกต่างหากจาก pystray main thread
    - รับ reference ไปยัง poller, shutdown_mgr, config ผ่าน constructor
    - เปิดรับ connection จาก localhost เท่านั้น (host="127.0.0.1")

Usage:
    >>> from tray_service.web_server import WebServer
    >>> srv = WebServer(poller=poller, config=cfg, shutdown_mgr=shutdown_mgr)
    >>> srv.start()   # เริ่ม Flask ใน background thread
    >>> srv.stop()    # หยุด
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Optional

from flask import Flask, jsonify, render_template, request

from tray_service.startup_manager import is_startup_enabled, set_startup

logger = logging.getLogger(__name__)

# Template folder อยู่ใน tray_service/templates/
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


class WebServer:
    """
    Flask Web Server สำหรับ UPS Monitor

    รัน Flask ใน daemon thread แยกต่างหาก
    เปิดรับ connection เฉพาะ localhost (127.0.0.1) เพื่อความปลอดภัย

    Attributes:
        port (int): Port ที่ Flask จะ listen (default: 48655)
        host (str): Host (default: "127.0.0.1")

    Example:
        >>> srv = WebServer(poller=poller, config=cfg)
        >>> srv.start()
        >>> # เข้าถึงได้ที่ http://localhost:48655
        >>> srv.stop()
    """

    def __init__(
        self,
        poller: Any,                    # UPSPoller instance
        config: Any,                    # ConfigManager instance
        shutdown_mgr: Optional[Any] = None,  # AutoShutdownManager instance
        db: Optional[Any] = None,       # DatabaseManager instance
        host: str = "127.0.0.1",
        port: int = 48655,
    ) -> None:
        """
        สร้าง WebServer

        Args:
            poller:       UPSPoller instance สำหรับดึงข้อมูล UPS
            config:       ConfigManager instance สำหรับอ่าน/เขียน config
            shutdown_mgr: AutoShutdownManager instance (optional)
            db:           DatabaseManager instance (optional)
            host:         Host ที่ Flask จะ listen (ควรเป็น 127.0.0.1)
            port:         Port ที่ Flask จะ listen
        """
        self._poller = poller
        self._config = config
        self._shutdown_mgr = shutdown_mgr
        self._db = db
        self._host = host
        self._port = port
        self._thread: Optional[threading.Thread] = None

        self._app = Flask(
            __name__,
            template_folder=str(_TEMPLATE_DIR),
            static_folder=str(_STATIC_DIR),
        )
        self._app.config["JSON_AS_ASCII"] = False  # รองรับ Thai characters ใน JSON
        self._register_routes()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """เริ่ม Flask server ใน daemon background thread"""
        self._thread = threading.Thread(
            target=self._run_flask,
            daemon=True,
            name="FlaskWebServer",
        )
        self._thread.start()
        logger.info(f"Web UI started at http://{self._host}:{self._port}")

    def stop(self) -> None:
        """
        หยุด Flask server

        Note: Flask dev server ไม่มี clean shutdown — thread จะหยุดเมื่อ main process จบ
        (daemon thread)
        """
        logger.info("WebServer stopping (daemon thread will exit with main process)")

    def _run_flask(self) -> None:
        """รัน Flask ใน thread"""
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)  # ซ่อน Flask request logs (noisy)
        try:
            self._app.run(
                host=self._host,
                port=self._port,
                debug=False,
                use_reloader=False,
                threaded=True,
            )
        except Exception as exc:
            logger.error(f"Flask server error: {exc}")

    # ── Route Registration ────────────────────────────────────────────────────

    def _register_routes(self) -> None:
        """ลงทะเบียน URL routes ทั้งหมด"""
        app = self._app

        # ── Web UI ────────────────────────────────────────────────────────────
        @app.route("/")
        def index():
            """หน้า Dashboard หลัก"""
            return render_template("dashboard.html", port=self._port)

        # ── Health ────────────────────────────────────────────────────────────
        @app.route("/api/health")
        def api_health():
            """
            ตรวจสอบสถานะ server

            Returns:
                JSON: {"status": "ok", "connected": bool, "monitoring": bool}
            """
            return jsonify({
                "status": "ok",
                "connected": self._poller.is_connected(),
                "monitoring": self._poller.is_monitoring(),
                "port": self._port,
            })

        # ── UPS Data ──────────────────────────────────────────────────────────
        @app.route("/api/ups")
        def api_ups():
            """
            ข้อมูล UPS ทั้งหมด

            Returns:
                JSON: {"device": {...}, "ups": {...}}
            """
            state = self._poller.get_state()
            device = self._poller.get_device_info()
            pc_sd = self._shutdown_mgr.get_status() if self._shutdown_mgr else {}
            return jsonify({
                "device": _sanitize(device),
                "ups": _sanitize(state),
                "connected": self._poller.is_connected(),
                "pc_shutdown": pc_sd,
            })

        @app.route("/api/ups/status")
        def api_ups_status():
            """
            สถานะหลักของ UPS

            Returns:
                JSON: {"ac_present": bool, "charging": bool, "discharging": bool, ...}
            """
            s = self._poller.get_state()
            return jsonify({
                "ups_status":            s.get("ups.status"),
                "ac_present":            s.get("ac_present"),
                "charging":              s.get("charging"),
                "discharging":           s.get("discharging"),
                "below_capacity_limit":  s.get("below_capacity_limit"),
                "status_good":           s.get("status_good"),
                "shutdown_imminent":     s.get("shutdown_imminent"),
                "overload":              s.get("overload"),
                "connected":             self._poller.is_connected(),
            })

        @app.route("/api/ups/battery")
        def api_ups_battery():
            """
            ข้อมูลแบตเตอรี่

            Returns:
                JSON: {"battery_charge": float, "battery_runtime": int, ...}
            """
            s = self._poller.get_state()
            return jsonify({
                "battery_charge":        s.get("battery.charge"),
                "battery_runtime":       s.get("battery.runtime"),
                "battery_runtime_hr":    s.get("battery.runtime.hr"),
                "battery_voltage_v":     s.get("battery_voltage_v"),
                "battery_capacity_pct":  s.get("battery_capacity_percent"),
                "low_batt_threshold":    s.get("battery.charge.low"),
                "connected":             self._poller.is_connected(),
            })

        @app.route("/api/ups/device")
        def api_ups_device():
            """
            ข้อมูลรุ่น UPS

            Returns:
                JSON: {"manufacturer": str, "product": str, "serial": str, "firmware": str}
            """
            d = self._poller.get_device_info()
            s = self._poller.get_state()
            return jsonify({
                "manufacturer":  d.get("manufacturer_string"),
                "product":       d.get("product_string"),
                "serial":        d.get("serial_number"),
                "release":       d.get("release_number"),
                "firmware":      s.get("ups.firmware"),
                "usage_page":    f"0x{d['usage_page']:04X}" if d.get("usage_page") else None,
                "usage":         f"0x{d['usage']:04X}" if d.get("usage") else None,
                "connected":     self._poller.is_connected(),
            })

        @app.route("/api/ups/devices", methods=["GET"])
        def api_ups_devices():
            """
            รายการอุปกรณ์ UPS / HID ทั้งหมดที่เชื่อมต่อกับระบบ
            """
            try:
                from core_hid_ups import list_ups_devices
                devices = list_ups_devices()
            except Exception as exc:
                logger.error(f"Error listing HID devices: {exc}")
                devices = []

            current_info = self._poller.get_device_info() if self._poller else {}
            current_serial = current_info.get("serial_number")
            current_path = current_info.get("path_str") or str(current_info.get("path") or "")

            sel_serial = self._config.get("selected_device_serial")
            sel_path = self._config.get("selected_device_path")
            sel_vid = self._config.get("vid", 0x06DA)
            sel_pid = self._config.get("pid", 0xFFFF)
            is_connected = self._poller.is_connected() if self._poller else False

            formatted = []
            for dev in devices:
                dev_path = dev.get("path_str", "")
                dev_serial = dev.get("serial_number", "")

                is_act = False
                if is_connected:
                    if current_serial and dev_serial and str(dev_serial).strip() == str(current_serial).strip():
                        is_act = True
                    elif current_path and dev_path and dev_path == current_path:
                        is_act = True

                is_sel = False
                if sel_serial and dev_serial and str(dev_serial).strip() == str(sel_serial).strip():
                    is_sel = True
                elif sel_path and dev_path and dev_path == sel_path:
                    is_sel = True
                elif is_act:
                    is_sel = True

                d_copy = dict(dev)
                if "path" in d_copy:
                    d_copy["path"] = dev_path
                d_copy["is_selected"] = bool(is_sel)
                d_copy["is_active"] = bool(is_act)
                formatted.append(d_copy)

            return jsonify({
                "success": True,
                "count": len(formatted),
                "connected": is_connected,
                "selected_path": sel_path,
                "selected_serial": sel_serial,
                "selected_vid": f"0x{sel_vid:04X}" if sel_vid else None,
                "selected_pid": f"0x{sel_pid:04X}" if sel_pid else None,
                "devices": formatted,
            })

        @app.route("/api/ups/select_device", methods=["POST"])
        def api_ups_select_device():
            """
            สลับอุปกรณ์ UPS ที่ต้องการใช้งาน
            """
            data = request.get_json(silent=True) or {}
            path = data.get("path")
            serial = data.get("serial")
            vid_raw = data.get("vid")
            pid_raw = data.get("pid")

            vid = 0x06DA
            if vid_raw is not None:
                try:
                    vid = int(str(vid_raw), 16) if str(vid_raw).startswith("0x") else int(vid_raw)
                except ValueError:
                    vid = 0x06DA

            pid = 0xFFFF
            if pid_raw is not None:
                try:
                    pid = int(str(pid_raw), 16) if str(pid_raw).startswith("0x") else int(pid_raw)
                except ValueError:
                    pid = 0xFFFF

            self._config.set("selected_device_path", path)
            self._config.set("selected_device_serial", serial)
            self._config.set("vid", vid)
            self._config.set("pid", pid)
            self._config.save()

            if self._poller:
                self._poller.select_device(vid=vid, pid=pid, path=path, serial=serial)

            return jsonify({
                "success": True,
                "message": "เลือกอุปกรณ์ UPS เรียบร้อยแล้ว กำลังทำการเชื่อมต่อ...",
                "selected_path": path,
                "vid": vid,
                "pid": pid,
            })

        @app.route("/api/ups/power")
        def api_ups_power():
            """
            ข้อมูลไฟเข้า/ออก

            Returns:
                JSON: {"input_voltage_v": float, "output_voltage_v": float, ...}
            """
            s = self._poller.get_state()
            return jsonify({
                "input_voltage_v":        s.get("input.voltage"),
                "input_frequency_hz":     s.get("input.frequency"),
                "output_voltage_v":       s.get("output_voltage_v") or s.get("output.voltage"),
                "output_frequency_hz":    s.get("output_frequency_hz"),
                "output_current_a":       s.get("output_current_a"),
                "output_active_power_w":  s.get("output_active_power_w"),
                "output_apparent_power_va": s.get("output_apparent_power_va"),
                "percent_load":           s.get("percent_load"),
                "temperature_c":          s.get("temperature_c"),
                "connected":              self._poller.is_connected(),
            })

        # ── Config ────────────────────────────────────────────────────────────
        @app.route("/api/config", methods=["GET"])
        def api_config_get():
            """
            อ่าน config ปัจจุบัน
            """
            cfg_dict = self._config.as_dict()
            cfg_dict["startup_with_windows"] = is_startup_enabled()
            return jsonify(cfg_dict)

        @app.route("/api/config", methods=["POST"])
        def api_config_set():
            """
            อัปเดต config
            """
            data = request.get_json(silent=True) or {}
            allowed_keys = {
                "auto_shutdown_enabled", "shutdown_delay_minutes",
                "shutdown_battery_threshold", "shutdown_on_ac_fail",
                "shutdown_on_low_battery", "notifications_enabled",
                "notify_on_ac_fail", "notify_on_ac_restore", "notify_on_low_battery",
                "poll_interval_s", "startup_with_windows", "db_enabled",
                "db_telemetry_interval_s", "db_retention_days",
            }
            for key, val in data.items():
                if key in allowed_keys:
                    self._config.set(key, val)

            if "startup_with_windows" in data:
                set_startup(bool(data["startup_with_windows"]))

            saved = self._config.save()

            # Sync live settings to shutdown manager & poller
            if self._shutdown_mgr:
                self._shutdown_mgr.enabled = self._config.get("auto_shutdown_enabled", False)
                self._shutdown_mgr.shutdown_delay_minutes = int(self._config.get("shutdown_delay_minutes", 5))
                self._shutdown_mgr.battery_threshold_percent = int(self._config.get("shutdown_battery_threshold", 20))
                self._shutdown_mgr.shutdown_on_ac_fail = self._config.get("shutdown_on_ac_fail", True)
                self._shutdown_mgr.shutdown_on_low_battery = self._config.get("shutdown_on_low_battery", True)

            if self._poller:
                batt_thresh = float(self._config.get("shutdown_battery_threshold", 20))
                self._poller.battery_low_threshold = batt_thresh
                self._poller.battery_critical_threshold = max(batt_thresh - 10, 5)

            res_dict = self._config.as_dict()
            res_dict["startup_with_windows"] = is_startup_enabled()
            return jsonify({"success": saved, "config": res_dict})

        # ── Monitor Control ───────────────────────────────────────────────────
        @app.route("/api/control/monitor/start", methods=["POST"])
        def api_monitor_start():
            """เริ่ม UPS monitoring"""
            self._poller.resume()
            return jsonify({"success": True, "monitoring": True})

        @app.route("/api/control/monitor/stop", methods=["POST"])
        def api_monitor_stop():
            """หยุด UPS monitoring ชั่วคราว"""
            self._poller.pause()
            return jsonify({"success": True, "monitoring": False})

        # ── Shutdown Control ──────────────────────────────────────────────────
        @app.route("/api/control/shutdown/status", methods=["GET"])
        def api_shutdown_status():
            """ดึงสถานะ PC auto-shutdown ปัจจุบันพร้อม countdown"""
            if self._shutdown_mgr:
                return jsonify({"success": True, "status": self._shutdown_mgr.get_status()})
            return jsonify({"success": False, "message": "Shutdown manager not available"})

        @app.route("/api/control/shutdown/trigger", methods=["POST"])
        def api_shutdown_trigger():
            """
            สั่ง PC Shutdown ด้วยมือพร้อมเวลา countdown

            Body (JSON): {"delay_seconds": int, "reason": str}
            """
            if not self._shutdown_mgr:
                return jsonify({"success": False, "message": "Shutdown manager not available"})

            data = request.get_json(silent=True) or {}
            delay = int(data.get("delay_seconds", 60))
            reason = str(data.get("reason", "Manual PC Shutdown command via Web UI"))

            ok = self._shutdown_mgr.trigger_manual_pc_shutdown(delay_seconds=delay, reason=reason)
            return jsonify({
                "success": ok,
                "message": f"Scheduled PC shutdown in {delay}s" if ok else "Failed to schedule PC shutdown",
                "status": self._shutdown_mgr.get_status(),
            })

        @app.route("/api/control/shutdown/cancel", methods=["POST"])
        def api_shutdown_cancel():
            """ยกเลิก PC auto-shutdown ที่ scheduled ไว้"""
            if self._shutdown_mgr:
                self._shutdown_mgr.cancel()
                return jsonify({"success": True, "message": "Shutdown cancelled", "status": self._shutdown_mgr.get_status()})
            return jsonify({"success": False, "message": "Shutdown manager not available"})

        # ── UPS HID Control ───────────────────────────────────────────────────
        @app.route("/api/ups/control/test", methods=["POST"])
        def api_ups_test():
            """
            สั่ง UPS Self-Test (รองรับ quick, deep, cancel, run, abort ทั้งหมด)
            """
            data = request.get_json(silent=True) or {}
            action = (data.get("action") or "quick").lower()

            if action in ("run", "quick"):
                cmd_type = "quick"
            elif action == "deep":
                cmd_type = "deep"
            else:
                cmd_type = "cancel"

            h = getattr(self._poller, "_handle", None) if self._poller else None
            info = self._poller.get_device_info() if self._poller else {}

            if not h:
                return jsonify({"success": False, "message": "Not connected to UPS"})

            try:
                from tools.unit.live_battery_test_runner import send_universal_battery_test_command
                ok, msg = send_universal_battery_test_command(h, info, cmd_type)
                return jsonify({"success": ok, "message": msg})
            except Exception as exc:
                return jsonify({"success": False, "message": f"Battery test error: {exc}"})

        @app.route("/api/ups/control/shutdown", methods=["POST"])
        def api_ups_shutdown():
            """
            สั่ง UPS หยุดจ่ายไฟ (Output Shutdown)

            Body (JSON): {"delay_seconds": int}
            """
            data = request.get_json(silent=True) or {}
            delay = data.get("delay_seconds", 60)
            payload = [(delay >> (i * 8)) & 0xFF for i in range(4)]
            ok, msg = _send_hid_feature(self._poller, 0x09, payload)
            return jsonify({"success": ok, "message": msg})

        @app.route("/api/ups/control/cancel_shutdown", methods=["POST"])
        def api_ups_cancel_shutdown():
            """ยกเลิกคำสั่ง UPS Output Shutdown"""
            payload = [0xFF, 0xFF, 0xFF, 0xFF]
            ok, msg = _send_hid_feature(self._poller, 0x09, payload)
            return jsonify({"success": ok, "message": msg})

        # ── UPS Clock Control (RID 0x29) ──────────────────────────────────────
        @app.route("/api/ups/time", methods=["GET"])
        def api_ups_time_get():
            """อ่านเวลานาฬิกาของ UPS (RID 0x29)"""
            import datetime
            ok, data = _read_hid_feature(self._poller, 0x29, 8)
            if ok and len(data) >= 5:
                ts = data[1] | (data[2] << 8) | (data[3] << 16) | (data[4] << 24)
                if ts > 0:
                    try:
                        # แปลงวินาทีเป็นเวลาหน้าจอ UPS (Local Wall-clock Time)
                        dt = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=ts)
                        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                        return jsonify({"success": True, "timestamp": ts, "ups_time": time_str})
                    except Exception:
                        pass
                return jsonify({"success": True, "timestamp": ts, "ups_time": f"Raw: 0x{ts:08X}"})
            return jsonify({"success": False, "message": "ไม่สามารถอ่านเวลานาฬิกา UPS ได้ (RID 0x29)"})

        @app.route("/api/ups/time/sync", methods=["POST"])
        def api_ups_time_sync():
            """ซิงค์เวลานาฬิกา PC (Local Time) ไปยัง UPS (RID 0x29) เพื่อให้หน้าจอ UPS แสดงเวลาบ่ายตรงกับ PC"""
            import datetime
            now = datetime.datetime.now()
            # คำนวณจำนวนวินาทีจาก 1970-01-01 ถึงเวลาเครื่อง PC ปัจจุบัน (Local Epoch Seconds)
            # เพื่อให้หน้าจอ LCD ของ UPS แสดงเวลาท้องถิ่น (เช่น 13:00 น.) ตรงกับ PC
            local_epoch = datetime.datetime(1970, 1, 1)
            ts = int((now - local_epoch).total_seconds())

            payload = [(ts >> (i * 8)) & 0xFF for i in range(4)]
            ok, msg = _send_hid_feature(self._poller, 0x29, payload)
            time_str = now.strftime("%Y-%m-%d %H:%M:%S")
            return jsonify({
                "success": ok,
                "message": msg if ok else f"ตั้งเวลาไม่สำเร็จ: {msg}",
                "synced_time": time_str
            })

        # ── Database & History API ─────────────────────────────────────────────
        @app.route("/api/history", methods=["GET"])
        def api_history():
            """ดึงข้อมูลประวัติ Telemetry ย้อนหลัง ( default: 24 ชั่วโมง )"""
            if not self._db:
                return jsonify({"status": "disabled", "data": []})

            try:
                hours = float(request.args.get("hours", 24))
            except (ValueError, TypeError):
                hours = 24.0

            data = self._db.get_telemetry_history(hours=hours)
            return jsonify({"status": "ok", "count": len(data), "data": data})

        @app.route("/api/events", methods=["GET"])
        def api_events():
            """ดึงรายการ Event Logs ย้อนหลัง"""
            if not self._db:
                return jsonify({"status": "disabled", "events": []})

            try:
                limit = int(request.args.get("limit", 50))
                page = int(request.args.get("page", 1))
            except (ValueError, TypeError):
                limit = 50
                page = 1

            events = self._db.get_events_history(limit=limit, page=page)
            return jsonify({"status": "ok", "count": len(events), "events": events})

        # ── Winpower G2 Compatible API ───────────────────────────────────────
        @app.route("/api/v1/history/discharge/list", methods=["GET"])
        def api_v1_history_discharge_list():
            """
            ดึงข้อมูลประวัติ Battery Test / Discharge (โครงสร้างตรงกับ Winpower G2 API)
            """
            if not self._db:
                return jsonify({"total": 0, "pageSize": 100, "currentPage": 1, "data": [], "code": "000000", "msg": "OK"})

            device_id = request.args.get("deviceId")
            try:
                limit = int(request.args.get("pageSize", 100))
                page = int(request.args.get("currentPage", 1))
            except (ValueError, TypeError):
                limit = 100
                page = 1

            res = self._db.get_discharge_history(device_id=device_id, limit=limit, page=page)

            # Add deviceAlias mapping
            dev_info = self._poller.get_device_info() if self._poller else {}
            alias_id = device_id or dev_info.get("serial_number") or "80d6c1e4-e44d-4057-acfc-81c16b73ee54"
            prod_alias = f"HID-UPS-CP10T2354690002"
            res["deviceAlias"] = {alias_id: prod_alias}

            return jsonify(res)

        @app.route("/api/database/clear", methods=["POST"])
        def api_db_clear():
            """ล้างข้อมูลในฐานข้อมูล SQLite"""
            if not self._db:
                return jsonify({"status": "disabled", "message": "Database is disabled"})

            self._db.clear_all()
            return jsonify({"status": "ok", "message": "ล้างข้อมูลในฐานข้อมูลสำเร็จ"})


# ── Helper functions ──────────────────────────────────────────────────────────

def _sanitize(d: dict) -> dict:
    """แปลง bytes → str เพื่อให้ JSON serializable"""
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, (bytes, bytearray)):
            out[k] = v.decode("utf-8", errors="ignore")
        elif isinstance(v, (int, float, str, bool, type(None))):
            out[k] = v
        elif isinstance(v, list):
            out[k] = [
                x.decode("utf-8", errors="ignore") if isinstance(x, (bytes, bytearray)) else x
                for x in v
            ]
        else:
            out[k] = str(v)
    return out


def _send_hid_feature(poller: Any, rid: int, payload: list) -> tuple[bool, str]:
    """
    ส่ง HID Feature Report ผ่าน UPS device handle

    Args:
        poller:  UPSPoller instance
        rid:     Report ID (int)
        payload: list of bytes

    Returns:
        (success: bool, message: str)
    """
    h = getattr(poller, "_handle", None)
    if not h:
        return False, "Not connected to UPS"
    try:
        data = [rid] + list(payload)
        h.send_feature_report(data)
        hex_str = " ".join(f"{b:02X}" for b in payload)
        return True, f"RID=0x{rid:02X} sent: {hex_str}"
    except Exception as exc:
        return False, f"RID=0x{rid:02X} error: {exc}"


def _read_hid_feature(poller: Any, rid: int, size: int = 8) -> tuple[bool, bytes]:
    """
    อ่าน HID Feature Report จาก UPS device handle

    Args:
        poller: UPSPoller instance
        rid:    Report ID (int)
        size:   จำนวน bytes ที่ต้องการอ่าน (default: 8)

    Returns:
        (success: bool, raw_data: bytes)
    """
    h = getattr(poller, "_handle", None)
    if not h:
        return False, b""
    try:
        data = h.get_feature_report(rid, size)
        return True, bytes(data)
    except Exception as exc:
        logger.debug(f"get_feature_report(0x{rid:02X}) failed: {exc}")
        return False, b""


def _send_ups_feature(
    poller: Any,
    action: str,
    rid: int,
    action_map: dict,
) -> Any:
    """
    Helper สำหรับ endpoint ที่ต้องการ action key

    Args:
        poller:     UPSPoller instance
        action:     string action จาก request body
        rid:        Report ID
        action_map: {"action_name": [byte, ...]}
    """
    from flask import jsonify
    if action not in action_map:
        return jsonify({"success": False, "message": f"Invalid action: {action}"}), 400
    payload = action_map[action]
    ok, msg = _send_hid_feature(poller, rid, payload)
    return jsonify({"success": ok, "message": msg})
