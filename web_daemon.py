"""
UPS Daemon - Headless Linux Service with Web GUI
Polls UPS data in the background and serves a Web UI + REST API on port 5000.
"""

import logging
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, request

# --- UPS HID API Import ---
try:
    from core_hid_ups import (
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
except ImportError as e:
    print(f"Failed to import core_hid_ups: {e}")
    HID_AVAILABLE = False
    VID = 0x06DA
    PID = 0xFFFF
    DEFAULT_REPORT_SIZES = (64,)
    DEFAULT_DESCRIPTOR_BIN = "report_descriptor_live.bin"
    DEFAULT_DESCRIPTOR_TXT = "report_descriptor_live.txt"

# ══════════════════════════════════════════════════════════════════════════════
# Linux sysfs descriptor helper
# ══════════════════════════════════════════════════════════════════════════════

def _read_descriptor_from_sysfs(device_path: object) -> Optional[bytes]:
    """Read HID report descriptor from Linux sysfs."""
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
# Global Data Store
# ══════════════════════════════════════════════════════════════════════════════

_api_store: dict = {"device": {}, "ups": {}, "timestamp": None, "status_message": "Starting..."}
_api_lock = threading.Lock()
_device_handle = None
_device_handle_lock = threading.Lock()

def _sanitize_for_json(d: dict) -> dict:
    """Convert bytes to strings for JSON serialization."""
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

def _update_api_store(device_info: dict, ups: dict, status_message: str = "") -> None:
    with _api_lock:
        _api_store["device"] = _sanitize_for_json(device_info)
        _api_store["ups"] = _sanitize_for_json(ups)
        _api_store["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        if status_message:
            _api_store["status_message"] = status_message

def _set_api_error(status_message: str) -> None:
    with _api_lock:
        _api_store["status_message"] = status_message
        _api_store["timestamp"] = None # Indicate disconnected

# ══════════════════════════════════════════════════════════════════════════════
# Background Poller Thread
# ══════════════════════════════════════════════════════════════════════════════

class UPSPoller(threading.Thread):
    def __init__(self, vid: int = VID, pid: int = PID):
        super().__init__(daemon=True, name="UPSPoller")
        self.vid = vid
        self.pid = pid
        self._stop_event = threading.Event()
        self._info: dict = {}
        self._descriptor_profile: Optional[dict] = None
        self._report_ids: list = list(range(0x01, 0x80))

    def run(self):
        global _device_handle
        logging.info("UPSPoller started.")
        while not self._stop_event.is_set():
            if not HID_AVAILABLE:
                _set_api_error("Module core_hid_ups not found.")
                time.sleep(5)
                continue

            with _device_handle_lock:
                h = _device_handle
            
            if h is None:
                self._connect()
                if self._stop_event.is_set():
                    break
                if _device_handle is None:
                    # Retry connection every 5 seconds if not found
                    time.sleep(5)
                    continue
                else:
                    h = _device_handle

            try:
                raw, _ = read_all_feature_reports(
                    h,
                    report_ids=self._report_ids,
                    sizes=(64,),
                    retries=1,
                    include_zero=False,
                )
                ups = decode_feature_reports(raw)
                ups.update(infer_tentative_live_values(raw, ups))
                _update_api_store(self._info, ups, status_message="Connected")
            except Exception as exc:
                logging.error(f"Poll error: {exc}")
                _set_api_error(f"Poll error: {exc}")
                with _device_handle_lock:
                    if _device_handle:
                        try:
                            _device_handle.close()
                        except Exception:
                            pass
                        _device_handle = None
            
            time.sleep(1.0) # Poll every 1 second

    def _connect(self) -> None:
        try:
            h, info = open_ups_device(self.vid, self.pid)
            if h is None:
                _set_api_error(f"Device not found VID=0x{self.vid:04X} PID=0x{self.pid:04X}")
                return
            
            with _device_handle_lock:
                global _device_handle
                _device_handle = h
            
            self._info = info or {}
            self._read_descriptor()
            logging.info(f"Connected to UPS: {self._info.get('manufacturer_string')} {self._info.get('product_string')}")
        except Exception as exc:
            logging.error(f"Connect error: {exc}")
            _set_api_error(f"Connect error: {exc}")

    def _read_descriptor(self) -> None:
        raw_path = self._info.get("path")
        if not raw_path:
            return

        descriptor_bytes = _read_descriptor_from_sysfs(raw_path)
        if not descriptor_bytes:
            return

        bin_path = Path(DEFAULT_DESCRIPTOR_BIN)
        try:
            bin_path.write_bytes(descriptor_bytes)
            self._descriptor_profile = load_descriptor_profile(
                bin_path, Path(DEFAULT_DESCRIPTOR_TXT)
            )
            ids = get_descriptor_feature_ids(self._descriptor_profile)
            if ids:
                self._report_ids = ids
        except Exception as exc:
            logging.error(f"Profile load error: {exc}")

# ══════════════════════════════════════════════════════════════════════════════
# Flask Web & API Application
# ══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)

# --- UI Route ---
@app.route("/")
def index():
    return render_template("index.html")

# --- Original API Routes ---
@app.route("/api/health")
def api_health():
    with _api_lock:
        return jsonify({
            "status": "ok",
            "connected": _api_store["timestamp"] is not None,
            "timestamp": _api_store["timestamp"],
            "message": _api_store["status_message"],
        })

@app.route("/api/ups")
def api_ups():
    with _api_lock:
        return jsonify({
            "device": _api_store["device"],
            "ups": _api_store["ups"],
            "timestamp": _api_store["timestamp"],
            "message": _api_store["status_message"],
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

# --- Control Endpoints ---
def _send_feature(rid: int, payload: list) -> tuple[bool, str]:
    with _device_handle_lock:
        h = _device_handle
        if not h:
            return False, "Not connected to UPS"
        try:
            data = [rid] + list(payload)
            h.send_feature_report(data)
            hex_str = " ".join(f"{b:02X}" for b in payload)
            return True, f"RID=0x{rid:02X} sent payload: {hex_str}"
        except Exception as exc:
            return False, f"RID=0x{rid:02X} Error: {exc}"

def _send_u32(rid: int, value: int) -> tuple[bool, str]:
    payload = [(value >> (i * 8)) & 0xFF for i in range(4)]
    return _send_feature(rid, payload)

def _send_u16(rid: int, value: int) -> tuple[bool, str]:
    payload = [(value >> (i * 8)) & 0xFF for i in range(2)]
    return _send_feature(rid, payload)

@app.route("/api/control/test", methods=["POST"])
def api_control_test():
    req = request.json or {}
    action = req.get("action") # "run" or "abort"
    if action == "run":
        ok, msg = _send_feature(0x24, [0x01])
    elif action == "abort":
        ok, msg = _send_feature(0x24, [0x00])
    else:
        return jsonify({"success": False, "message": "Invalid action"}), 400
    return jsonify({"success": ok, "message": msg})

@app.route("/api/control/shutdown", methods=["POST"])
def api_control_shutdown():
    req = request.json or {}
    delay = req.get("delay")
    if delay is None or not isinstance(delay, int):
        return jsonify({"success": False, "message": "Invalid delay"}), 400
    ok, msg = _send_u32(0x09, delay)
    return jsonify({"success": ok, "message": msg})

@app.route("/api/control/startup", methods=["POST"])
def api_control_startup():
    req = request.json or {}
    delay = req.get("delay")
    if delay is None or not isinstance(delay, int):
        return jsonify({"success": False, "message": "Invalid delay"}), 400
    ok, msg = _send_u32(0x0A, delay)
    return jsonify({"success": ok, "message": msg})

@app.route("/api/control/cancel_shutdown", methods=["POST"])
def api_control_cancel_shutdown():
    ok, msg = _send_u32(0x09, 0xFFFFFFFF)
    return jsonify({"success": ok, "message": msg})

@app.route("/api/control/config", methods=["POST"])
def api_control_config():
    req = request.json or {}
    voltage = req.get("voltage")
    freq = req.get("frequency")
    runtime_limit = req.get("runtime_limit")

    results = []
    success = True
    if voltage is not None:
        ok, msg = _send_u16(0x72, int(voltage))
        results.append(msg)
        success = success and ok
    if freq is not None:
        ok, msg = _send_feature(0x0D, [int(freq)])
        results.append(msg)
        success = success and ok
    if runtime_limit is not None:
        ok, msg = _send_u16(0x17, int(runtime_limit))
        results.append(msg)
        success = success and ok
    
    return jsonify({"success": success, "message": " | ".join(results)})

@app.route("/api/control/time", methods=["POST"])
def api_control_time():
    # Sync time
    now = time.time()
    # Unix timestamp (seconds since 1970)
    ok, msg = _send_u32(0x29, int(now))
    return jsonify({"success": ok, "message": msg})


# ══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    
    # Start Poller Thread
    poller = UPSPoller()
    poller.start()
    
    # Run Flask App
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0") # Listen on all interfaces by default for daemon
    
    logging.info(f"Starting Web GUI and API on http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
