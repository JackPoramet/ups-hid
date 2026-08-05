"""
UPS Monitor — UPS Data Poller Thread
======================================
อ่านข้อมูล UPS ผ่าน USB HID ทุก N วินาที (default: 1 วินาที)
ตรวจจับการเปลี่ยนสถานะ AC / แบตเตอรี่ และเรียก callback แจ้งเตือน

Architecture:
    - รันเป็น daemon thread (หยุดเมื่อ main process จบ)
    - ใช้ core_hid_ups.py (ที่มีอยู่เดิม) สำหรับการสื่อสาร HID
    - เก็บ state ล่าสุดไว้ใน thread-safe dict (protected by Lock)
    - แจ้ง callback เมื่อ:
        * AC fail (ac_present: True → False)
        * AC restore (ac_present: False → True)
        * Battery low (battery.charge ต่ำกว่า threshold เป็นครั้งแรก)
        * Battery critical (battery.charge ต่ำกว่า critical_threshold)

Dependencies:
    - core_hid_ups.py  (อยู่ใน parent directory UPS/)
    - win32_hid_wrapper.py  (อยู่ใน parent directory UPS/)

Usage:
    >>> from tray_service.poller import UPSPoller
    >>> def on_ac_fail(state): print("ไฟดับ!")
    >>> poller = UPSPoller(on_ac_fail=on_ac_fail)
    >>> poller.start()
    >>> # ... later ...
    >>> poller.stop()
    >>> state = poller.get_state()
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── ดึง core_hid_ups จาก parent directory ────────────────────────────────────
_UPS_DIR = Path(__file__).resolve().parent.parent.parent  # UPS/
if str(_UPS_DIR) not in sys.path:
    sys.path.insert(0, str(_UPS_DIR))

try:
    from core_hid_ups import (
        VID,
        PID,
        decode_feature_reports,
        infer_tentative_live_values,
        list_ups_devices,
        open_ups_device,
        read_all_feature_reports,
        load_descriptor_profile,
        get_descriptor_feature_ids,
        DEFAULT_DESCRIPTOR_BIN,
        DEFAULT_DESCRIPTOR_TXT,
    )
    HID_AVAILABLE = True
except ImportError as _e:
    logger.error(f"core_hid_ups not found: {_e}")
    HID_AVAILABLE = False
    VID = 0x06DA
    PID = 0xFFFF

try:
    from win32_hid_wrapper import WinHidApi, normalize_path
    WIN_HID_AVAILABLE = True
except ImportError:
    WIN_HID_AVAILABLE = False

# ── Type aliases ──────────────────────────────────────────────────────────────
StateDict = dict[str, Any]
Callback = Callable[[StateDict], None]

# ── Sentinel ──────────────────────────────────────────────────────────────────
_UNSET = object()


class UPSPoller(threading.Thread):
    """
    Background thread ที่อ่านข้อมูล UPS ผ่าน USB HID

    อ่านค่าทุก ``poll_interval_s`` วินาที แล้วตรวจว่ามีการเปลี่ยนสถานะ
    สำคัญหรือไม่ (AC fail / restore / battery low) ก่อน invoke callback

    Attributes:
        vid (int): USB Vendor ID (default 0x06DA Phoenixtec)
        pid (int): USB Product ID (default 0xFFFF)
        poll_interval_s (float): ระยะเวลาระหว่างการอ่าน (วินาที)
        battery_low_threshold (int): % แบตที่ถือว่า "ต่ำ" (ค่า default 20)
        battery_critical_threshold (int): % แบตวิกฤต (ค่า default 10)

    Callbacks (เรียกใน poller thread — ไม่ใช่ main thread):
        on_ac_fail:      เรียกเมื่อไฟดับ, arg: state dict
        on_ac_restore:   เรียกเมื่อไฟกลับมา, arg: state dict
        on_low_battery:  เรียกเมื่อแบตต่ำ, arg: state dict
        on_critical_battery: เรียกเมื่อแบตวิกฤต, arg: state dict
        on_connect:      เรียกเมื่อเชื่อมต่อ UPS สำเร็จ, arg: device_info dict
        on_disconnect:   เรียกเมื่อ UPS ถูกถอด, arg: error message str
        on_data:         เรียกทุกรอบ poll ที่สำเร็จ, arg: state dict

    Example:
        >>> poller = UPSPoller(
        ...     on_ac_fail=lambda s: print("ไฟดับ!"),
        ...     on_ac_restore=lambda s: print("ไฟกลับมา!"),
        ...     on_low_battery=lambda s: print(f"แบตต่ำ {s['battery.charge']}%"),
        ... )
        >>> poller.start()
    """

    def __init__(
        self,
        vid: int = VID,
        pid: int = PID,
        target_path: Optional[str] = None,
        target_serial: Optional[str] = None,
        poll_interval_s: float = 1.0,
        battery_low_threshold: int = 20,
        battery_critical_threshold: int = 10,
        on_ac_fail: Optional[Callback] = None,
        on_ac_restore: Optional[Callback] = None,
        on_low_battery: Optional[Callback] = None,
        on_critical_battery: Optional[Callback] = None,
        on_connect: Optional[Callable[[dict], None]] = None,
        on_disconnect: Optional[Callable[[str], None]] = None,
        on_data: Optional[Callback] = None,
        db: Optional[Any] = None,
        telemetry_interval_s: float = 10.0,
    ) -> None:
        super().__init__(daemon=True, name="UPSPoller")

        self.vid = vid
        self.pid = pid
        self.target_path = target_path
        self.target_serial = target_serial
        self.poll_interval_s = poll_interval_s
        self.battery_low_threshold = battery_low_threshold
        self.battery_critical_threshold = battery_critical_threshold
        self.db = db
        self.telemetry_interval_s = telemetry_interval_s

        # Callbacks
        self._on_ac_fail = on_ac_fail
        self._on_ac_restore = on_ac_restore
        self._on_low_battery = on_low_battery
        self._on_critical_battery = on_critical_battery
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._on_data = on_data

        # Internal state
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._state: StateDict = {}
        self._device_info: dict = {}
        self._handle: Any = None
        self._report_ids: list[int] = list(range(0x01, 0x80))
        self._descriptor_profile: Optional[dict] = None
        self._last_telemetry_time = 0.0
        self._last_target_check_time = 0.0

        # Previous values สำหรับตรวจ state change
        self._prev_ac_present: Any = _UNSET
        self._low_battery_notified = False
        self._critical_battery_notified = False

        # สถานะการเชื่อมต่อ
        self._connected = False
        self._monitoring = True  # flag เปิด/ปิด polling

    # ── Public API ────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """
        หยุด poller thread อย่างปลอดภัย

        หลังเรียก stop() thread จะหยุดที่รอบ poll ถัดไป
        """
        self._stop_event.set()
        self._close_device()
        logger.info("UPSPoller stopped")

    def pause(self) -> None:
        """หยุด polling ชั่วคราว (ไม่ disconnect)"""
        self._monitoring = False
        logger.info("UPSPoller paused")

    def resume(self) -> None:
        """เริ่ม polling ต่อหลัง pause()"""
        self._monitoring = True
        logger.info("UPSPoller resumed")

    def get_state(self) -> StateDict:
        with self._state_lock:
            return dict(self._state)

    def get_device_info(self) -> dict:
        return dict(self._device_info)

    def is_connected(self) -> bool:
        return self._connected

    def is_monitoring(self) -> bool:
        return self._monitoring

    def select_device(self, vid: int, pid: int, path: Optional[str] = None, serial: Optional[str] = None) -> None:
        """
        สลับอุปกรณ์เป้าหมายและเริ่มเชื่อมต่อใหม่ทันที
        """
        logger.info(f"Selecting new UPS target: VID=0x{vid:04X} PID=0x{pid:04X} serial={serial} path={path}")
        self.vid = vid
        self.pid = pid
        self.target_path = path
        self.target_serial = serial
        self._close_device()
        self._connected = False
        self._device_info = {}
        with self._state_lock:
            self._state = {}

    # ── Thread main loop ─────────────────────────────────────────────────────

    def run(self) -> None:
        """Main loop ของ poller thread"""
        logger.info(f"UPSPoller started — VID=0x{self.vid:04X} PID=0x{self.pid:04X} serial={self.target_serial} path={self.target_path}")

        while not self._stop_event.is_set():
            if not self._monitoring:
                time.sleep(0.5)
                continue

            if not HID_AVAILABLE:
                logger.error("core_hid_ups not available — polling disabled")
                time.sleep(5)
                continue

            # Check if preferred remembered device came online (every 5s)
            now = time.time()
            if (self.target_serial or self.target_path) and (now - self._last_target_check_time >= 5.0):
                self._last_target_check_time = now
                current_serial = self._device_info.get("serial_number")
                current_path = self._device_info.get("path_str") or str(self._device_info.get("path") or "")

                is_current_preferred = False
                if self.target_serial and current_serial and str(current_serial).strip() == str(self.target_serial).strip():
                    is_current_preferred = True
                elif self.target_path and current_path and current_path == self.target_path:
                    is_current_preferred = True

                if not is_current_preferred:
                    try:
                        devices = list_ups_devices(target_vid=self.vid)
                        target_online = False
                        for d in devices:
                            s = d.get("serial_number")
                            p = d.get("path_str")
                            if self.target_serial and s and str(s).strip() == str(self.target_serial).strip():
                                target_online = True
                                break
                            if self.target_path and p and p == self.target_path:
                                target_online = True
                                break
                        if target_online:
                            logger.info("Remembered preferred UPS device is now online! Reconnecting to preferred UPS...")
                            self._close_device()
                            self._connected = False
                            self._connect()
                    except Exception as ex:
                        logger.debug(f"Error checking preferred target: {ex}")

            if self._handle is None:
                self._connect()
                if self._handle is None:
                    time.sleep(5)
                    continue

            self._poll_once()
            self._stop_event.wait(self.poll_interval_s)

        logger.info("UPSPoller thread exiting")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        """เชื่อมต่อ UPS device"""
        import os
        os.environ["PYTHONIOENCODING"] = "utf-8"
        os.environ["PYTHONUTF8"] = "1"

        try:
            h, info = open_ups_device(self.vid, self.pid, target_path=self.target_path, target_serial=self.target_serial)
            if h is None:
                logger.debug(f"UPS not found (VID=0x{self.vid:04X} PID=0x{self.pid:04X} serial={self.target_serial} path={self.target_path})")
                self._connected = False
                self._device_info = {}
                with self._state_lock:
                    self._state = {}
                return

            # Sanitize info strings: decode bytes → str อย่างปลอดภัย
            if info:
                for key, val in info.items():
                    if isinstance(val, (bytes, bytearray)):
                        info[key] = val.decode("utf-8", errors="ignore")
                    elif isinstance(val, str):
                        # ป้องกัน surrogate characters จาก Windows HID API
                        info[key] = val.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")

            self._handle = h
            self._device_info = info or {}
            self._connected = True

            # โหลด descriptor profile สำหรับ Windows
            self._load_descriptor()

            logger.info(
                f"UPS connected: {self._device_info.get('manufacturer_string', '')} "
                f"{self._device_info.get('product_string', '')}"
            )

            if self._on_connect:
                self._safe_call(self._on_connect, self._device_info)

        except UnicodeDecodeError as exc:
            logger.error(f"UPS encoding error (device string): {exc}")
            logger.info("Hint: ลอง set PYTHONIOENCODING=utf-8 ก่อนรัน")
        except Exception as exc:
            logger.error(f"UPS connect error: {exc}")


    def _load_descriptor(self) -> None:
        """โหลด HID Report Descriptor ผ่าน WinHidApi (Windows เท่านั้น)"""
        if not WIN_HID_AVAILABLE:
            return

        raw_path = self._device_info.get("path")
        if not raw_path:
            return

        # decode bytes → str อย่างปลอดภัย (ป้องกัน charmap error บน Windows)
        if isinstance(raw_path, (bytes, bytearray)):
            raw_path = raw_path.decode("utf-8", errors="ignore")

        try:
            dev_path = normalize_path(raw_path)
            api = WinHidApi()
            handle = api.create_file(dev_path)
            descriptor_bytes = None

            try:
                descriptor_bytes, _ = api.get_report_descriptor(
                    handle, sizes=(256, 512, 1024, 2048, 4096)
                )
            finally:
                try:
                    api.close_handle(handle)
                except Exception:
                    pass

            if descriptor_bytes:
                bin_path = Path(_UPS_DIR) / DEFAULT_DESCRIPTOR_BIN
                bin_path.write_bytes(descriptor_bytes)
                self._descriptor_profile = load_descriptor_profile(
                    bin_path, Path(_UPS_DIR) / DEFAULT_DESCRIPTOR_TXT
                )
                ids = get_descriptor_feature_ids(self._descriptor_profile)
                if ids:
                    self._report_ids = ids
                    logger.debug(f"Descriptor loaded — {len(ids)} report IDs")

        except Exception as exc:
            logger.debug(f"Descriptor load failed (non-critical): {exc}")


    def _poll_once(self) -> None:
        """อ่านค่า UPS หนึ่งรอบ"""
        try:
            raw, _ = read_all_feature_reports(
                self._handle,
                report_ids=self._report_ids,
                sizes=(64,),
                retries=1,
                include_zero=False,
            )
            ups = decode_feature_reports(raw)
            ups.update(infer_tentative_live_values(raw, ups))
            self._fallback_read_input_voltage(ups)

            # อัปเดต state (thread-safe)
            with self._state_lock:
                self._state = ups

            # ตรวจ state change และเรียก callbacks
            self._check_state_changes(ups)

            # บันทึก Telemetry ลง DB ตามช่วงเวลาที่กำหนด
            now = time.time()
            if self.db and (now - self._last_telemetry_time >= self.telemetry_interval_s):
                self._last_telemetry_time = now
                self.db.log_telemetry(dict(ups))

            if self._on_data:
                self._safe_call(self._on_data, dict(ups))

        except Exception as exc:
            logger.warning(f"Poll error: {exc}")
            self._close_device()
            self._connected = False
            self._device_info = {}
            with self._state_lock:
                self._state = {}
            if self._on_disconnect:
                self._safe_call(self._on_disconnect, str(exc))

    def _fallback_read_input_voltage(self, ups: dict) -> None:
        """
        Fallback reading input.voltage via pyusb / libusb0 filter driver on Windows
        (เมื่อ Windows HID API บล็อก Report 0x31)
        """
        if "input.voltage" in ups and ups["input.voltage"] is not None:
            return

        try:
            import usb.core
            import platform
            import os

            system = platform.system().lower()
            backend = None

            if system == "windows":
                import usb.backend.libusb0
                local_dll = str(_UPS_DIR / "ups_module" / "drivers" / "windows" / "libusb0.dll")
                fallback_dll = r"C:\Program Files\WinpowerG2\libUSB_driver\amd64\libusb0.dll"

                if os.path.exists(local_dll):
                    backend = usb.backend.libusb0.get_backend(find_library=lambda x: local_dll)
                elif os.path.exists(fallback_dll):
                    backend = usb.backend.libusb0.get_backend(find_library=lambda x: fallback_dll)

            dev = usb.core.find(idVendor=self.vid, idProduct=self.pid, backend=backend)

            # Auto-Install Filter Driver on Windows if pyusb fails to find it or access it
            if not dev and system == "windows":
                try:
                    from ups_module import driver_installer
                    if driver_installer.install_filter(self.vid, self.pid):
                        dev = usb.core.find(idVendor=self.vid, idProduct=self.pid, backend=backend)
                except Exception as _e:
                    logger.debug(f"driver_installer error: {_e}")

            if not dev:
                return

            if system == "linux":
                try:
                    if dev.is_kernel_driver_active(0):
                        dev.detach_kernel_driver(0)
                except Exception:
                    pass

            # GET_REPORT: bmRequestType=0xA1, bRequest=0x01, wValue=0x0331, wIndex=0, length=5
            payload = dev.ctrl_transfer(0xA1, 0x01, 0x0331, 0, 5, timeout=1000)
            if payload and len(payload) >= 5:
                volt_raw = payload[3] | (payload[4] << 8)
                ups["input.voltage"] = volt_raw / 10.0
                logger.debug(f"Input voltage read via pyusb fallback: {ups['input.voltage']} V")

            if system == "linux":
                try:
                    dev.attach_kernel_driver(0)
                except Exception:
                    pass

        except Exception as exc:
            logger.debug(f"pyusb fallback read failed: {exc}")


    def _check_state_changes(self, ups: StateDict) -> None:
        """ตรวจและ invoke callbacks เมื่อสถานะเปลี่ยน"""
        ac_present = ups.get("ac_present")
        battery_charge = ups.get("battery.charge")

        # ── AC State Change ─────────────────────────────────────────────────
        if self._prev_ac_present is not _UNSET and ac_present is not None:
            if self._prev_ac_present is True and ac_present is False:
                # ไฟดับ!
                logger.warning("AC FAIL detected — power outage!")
                self._low_battery_notified = False    # reset เพื่อแจ้งใหม่ถ้าแบตลด
                self._critical_battery_notified = False
                if self.db:
                    self.db.log_event("AC_FAIL", "Power outage / ไฟฟ้าดับ", battery_level=battery_charge, ac_present=False)
                if self._on_ac_fail:
                    self._safe_call(self._on_ac_fail, dict(ups))

            elif self._prev_ac_present is False and ac_present is True:
                # ไฟกลับมา!
                logger.info("AC RESTORE detected — power restored!")
                self._low_battery_notified = False
                self._critical_battery_notified = False
                if self.db:
                    self.db.log_event("AC_RESTORE", "Power restored / ไฟฟ้ากลับมาเป็นปกติ", battery_level=battery_charge, ac_present=True)
                if self._on_ac_restore:
                    self._safe_call(self._on_ac_restore, dict(ups))

        if ac_present is not None:
            self._prev_ac_present = ac_present

        # ── Battery Level ────────────────────────────────────────────────────
        if battery_charge is not None and ac_present is False:
            charge = float(battery_charge)

            # Critical threshold (แจ้งก่อน low)
            if charge <= self.battery_critical_threshold and not self._critical_battery_notified:
                logger.warning(f"Battery CRITICAL: {charge:.0f}%")
                self._critical_battery_notified = True
                if self.db:
                    self.db.log_event("BATTERY_CRITICAL", f"Battery critical ({charge:.0f}%)", battery_level=int(charge), ac_present=ac_present)
                if self._on_critical_battery:
                    self._safe_call(self._on_critical_battery, dict(ups))

            # Low threshold
            elif charge <= self.battery_low_threshold and not self._low_battery_notified:
                logger.warning(f"Battery LOW: {charge:.0f}%")
                self._low_battery_notified = True
                if self.db:
                    self.db.log_event("BATTERY_LOW", f"Battery low ({charge:.0f}%)", battery_level=int(charge), ac_present=ac_present)
                if self._on_low_battery:
                    self._safe_call(self._on_low_battery, dict(ups))

    def _close_device(self) -> None:
        """ปิด HID device handle"""
        if self._handle:
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None

    @staticmethod
    def _safe_call(fn: Callable, *args: Any) -> None:
        """เรียก callback อย่างปลอดภัย — จับ exception ไม่ให้ crash poller"""
        try:
            fn(*args)
        except Exception as exc:
            logger.error(f"Callback error in {fn.__name__}: {exc}")
