"""
ups_module/client.py
~~~~~~~~~~~~~~~~~~~~
Pure Python HID-UPS client library — ใช้งานแบบ PyNUT.

ไม่มี daemon, ไม่มี HTTP server, ไม่มี background thread โดย default.
เปิด device → อ่านข้อมูล → ปิด (หรือค้างการเชื่อมต่อไว้แล้ว poll เอง)

Quick start::

    from ups_module import UPSClient

    with UPSClient() as client:
        print(client.get_status())          # "OL"
        print(client.get_var("battery.charge"))  # 95
        print(client.get_vars())            # {"ups.status": "OL", ...}
        print(client.get_data().to_json())  # NUT-style JSON

Event monitoring (optional)::

    from ups_module import UPSClient
    from ups_module.events import NotifyType

    client = UPSClient()
    client.connect()

    @client.on(NotifyType.ONBATT)
    def power_failed(event):
        print("Power failure!", event.message)

    client.start_monitor(interval=1.0)  # background thread
    ...
    client.stop_monitor()
    client.disconnect()
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .events import EventBus, EventDetector, EventHandler
from .models import NotifyType, UPSData, UPSEvent, ups_data_from_raw
from .serializer import sanitize_for_json
from .device_registry import DeviceRegistry, DeviceProfile

logger = logging.getLogger(__name__)

_registry = DeviceRegistry()

# ---------------------------------------------------------------------------
# Lazy-import core (bundled core.py, or legacy core_hid_ups)
# ---------------------------------------------------------------------------
try:
    from .core import (
        VID,
        PID,
        decode_feature_reports,
        get_descriptor_feature_ids,
        infer_tentative_live_values,
        load_descriptor_profile,
        open_ups_device,
        read_all_feature_reports,
        DEFAULT_DESCRIPTOR_BIN,
        DEFAULT_DESCRIPTOR_TXT,
    )
    HID_AVAILABLE = True
except ImportError:
    try:
        from .core_hid_ups import (
            VID,
            PID,
            decode_feature_reports,
            get_descriptor_feature_ids,
            infer_tentative_live_values,
            load_descriptor_profile,
            open_ups_device,
            read_all_feature_reports,
            DEFAULT_DESCRIPTOR_BIN,
            DEFAULT_DESCRIPTOR_TXT,
        )
        HID_AVAILABLE = True
    except ImportError:
        try:
            from core_hid_ups import (
                VID,
                PID,
                decode_feature_reports,
                get_descriptor_feature_ids,
                infer_tentative_live_values,
                load_descriptor_profile,
                open_ups_device,
                read_all_feature_reports,
                DEFAULT_DESCRIPTOR_BIN,
                DEFAULT_DESCRIPTOR_TXT,
            )
            HID_AVAILABLE = True
        except ImportError as _e:
            logger.warning("core protocol engine not available: %s", _e)
            HID_AVAILABLE = False
            _fallback = _registry.get_default()
            VID = _fallback.vid
            PID = _fallback.pid
            DEFAULT_DESCRIPTOR_BIN = "report_descriptor_live.bin"
            DEFAULT_DESCRIPTOR_TXT = "report_descriptor_live.txt"


_default_profile = _registry.get_default()
DEFAULT_REPORT_IDS = list(_default_profile.report_ids) if _default_profile.report_ids else [
    0x01, 0x02, 0x03, 0x05, 0x06, 0x07, 0x08, 0x0C, 0x0D, 0x10,
    0x14, 0x17, 0x24, 0x25, 0x26, 0x27, 0x29, 0x31, 0x42, 0x4A, 0x74
]


class UPSClient:
    """
    Pure Python HID-UPS client — ใช้งานเหมือน PyNUT library.

    Design
    ------
    * **Synchronous by default** — :meth:`get_vars` / :meth:`get_data` /
      :meth:`get_status` อ่านจาก HID device โดยตรงทุกครั้งที่เรียก
    * **No HTTP / no daemon required** — ไม่ต้องรัน upsd หรือ Flask
    * **Optional background monitor** — ถ้าต้องการ event (ONBATT, LOWBATT ฯลฯ)
      ให้เรียก :meth:`start_monitor` เพื่อเปิด polling thread

    Parameters
    ----------
    model : str | None
        Registered model id from meta.json (e.g. ``"phoenixtec_innova_unity"``).
        If provided, VID/PID/report_ids are loaded from the registry.
    vid : int | None
        USB Vendor ID. Overrides the registry value if provided.
    pid : int | None
        USB Product ID. Overrides the registry value if provided.
    name : str
        Logical UPS name (เหมือน ``<upsname>`` ใน NUT config).
    report_ids : list[int] | None
        Report IDs ที่จะ poll (None = ใช้ registry defaults).
    """

    def __init__(
        self,
        model: Optional[str] = None,
        vid: Optional[int] = None,
        pid: Optional[int] = None,
        name: str = "ups@local",
        report_ids: Optional[List[int]] = None,
    ) -> None:
        self.name = name

        # Resolve device profile
        if model:
            profile = _registry.get_by_id(model)
            if not profile:
                raise ValueError(f"Unknown model: {model!r}. Available: {[d.id for d in _registry.devices]}")
        else:
            profile = _default_profile

        self._vid = vid if vid is not None else profile.vid
        self._pid = pid if pid is not None else profile.pid
        self._profile = profile
        self._report_ids: List[int] = report_ids or list(profile.report_ids) or list(DEFAULT_REPORT_IDS)

        self._handle = None                        # hid.device handle
        self._device_info: Dict[str, Any] = {}    # raw device metadata
        self._handle_lock = threading.Lock()

        # Optional monitor components (created lazily)
        self._bus: Optional[EventBus] = None
        self._detector: Optional[EventDetector] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()
        self._monitor_interval: float = 1.0

    # =========================================================================
    # Connection management
    # =========================================================================

    def connect(self) -> "UPSClient":
        """
        Open the HID device.

        Raises
        ------
        RuntimeError
            If ``core_hid_ups`` is not installed or the device is not found.

        Returns
        -------
        UPSClient
            *self* — enables chaining: ``client = UPSClient().connect()``
        """
        if not HID_AVAILABLE:
            raise RuntimeError("core_hid_ups / hidapi not installed.")

        h, info = open_ups_device(self._vid, self._pid)
        if h is None:
            raise RuntimeError(
                f"UPS device not found (VID=0x{self._vid:04X} PID=0x{self._pid:04X})"
            )

        with self._handle_lock:
            self._handle = h
        self._device_info = info or {}

        mfr = self._device_info.get("manufacturer_string", "?")
        prod = self._device_info.get("product_string", "?")
        logger.info("Connected to UPS: %s %s", mfr, prod)
        return self

    def disconnect(self) -> None:
        """Close the HID device and stop the monitor if running."""
        self.stop_monitor()
        with self._handle_lock:
            if self._handle:
                try:
                    self._handle.close()
                except Exception:
                    pass
                self._handle = None
        logger.info("Disconnected from UPS '%s'.", self.name)

    @property
    def is_connected(self) -> bool:
        """True when a HID device handle is open."""
        with self._handle_lock:
            return self._handle is not None

    @property
    def device_info(self) -> Dict[str, Any]:
        """Raw device metadata dict (manufacturer, product, serial, …)."""
        return dict(self._device_info)

    # =========================================================================
    # Context manager support  (with UPSClient() as client: ...)
    # =========================================================================

    def __enter__(self) -> "UPSClient":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()

    # =========================================================================
    # Data read API  (synchronous — same style as PyNUT)
    # =========================================================================

    def _read_raw(self) -> Dict[str, Any]:
        """
        Perform a single HID read cycle.

        Returns the merged decoded + inferred dict from
        ``core_hid_ups.decode_feature_reports``.

        Raises
        ------
        RuntimeError
            If not connected.
        """
        with self._handle_lock:
            h = self._handle
        if h is None:
            raise RuntimeError("Not connected. Call connect() first.")

        from .core import DEFAULT_REPORT_SIZES as _SIZES  # noqa: PLC0415
        raw_reports, _ = read_all_feature_reports(
            h,
            report_ids=self._report_ids,
            sizes=_SIZES,
            retries=1,
            include_zero=False,
        )
        decoded = decode_feature_reports(raw_reports)
        decoded.update(infer_tentative_live_values(raw_reports, decoded))
        return decoded


    def get_data(self) -> UPSData:
        """
        Read UPS state and return a typed :class:`~ups_module.models.UPSData`.

        Each call performs a live HID read.

        Analogous to PyNUT's ``GetUPSVars()`` but returns a typed object.

        Example::

            data = client.get_data()
            print(data.ups_status)        # "OL"
            print(data.battery_charge)    # 95
            print(data.is_on_battery())   # False
        """
        return ups_data_from_raw(self._read_raw())

    def get_vars(self) -> Dict[str, Any]:
        """
        Read and return all UPS variables as a NUT-style dict.

        Equivalent to PyNUT's ``GetUPSVars(upsname)`` and to running
        ``upsc <upsname>`` on the command line::

            {
              "ups.status": "OL",
              "battery.charge": 95,
              "battery.runtime": 3600,
              "input.voltage": 220.5,
              ...
            }

        Each call performs a live HID read.
        """
        return ups_data_from_raw(self._read_raw()).to_nut_dict()

    def get_var(self, varname: str) -> Optional[Any]:
        """
        Read a single NUT variable.

        Equivalent to PyNUT's ``GetVar(upsname, varname)``::

            client.get_var("battery.charge")   # -> 95
            client.get_var("ups.status")       # -> "OL"
            client.get_var("input.voltage")    # -> 220.5

        Each call performs a live HID read.
        """
        return self.get_vars().get(varname)

    def get_status(self) -> str:
        """
        Read and return the NUT status string.

        Equivalent to PyNUT's ``GetUPSStatus(upsname)``::

            "OL"        # On line power, normal
            "OB"        # On battery
            "OB LB"     # On battery, low battery
            "OL CHRG"   # On line, charging
            "NOCOMM"    # Not connected

        Each call performs a live HID read.
        """
        if not self.is_connected:
            return NotifyType.NOCOMM
        data = ups_data_from_raw(self._read_raw())
        return data.ups_status or NotifyType.NOCOMM

    def get_device_info(self) -> Dict[str, Any]:
        info = self._device_info
        mfr = info.get("manufacturer_string") or info.get("manufacturer") or ""
        model = info.get("product_string") or info.get("model") or ""
        serial = info.get("serial_number") or info.get("serial") or ""
        return {
            "manufacturer": mfr,
            "model":        model,
            "serial":       serial,
            "type":         "ups",
        }

    # =========================================================================
    # Control commands
    # =========================================================================

    def _send_feature(self, rid: int, payload: list) -> tuple[bool, str]:
        """Send a raw HID feature report. Returns (success, message)."""
        with self._handle_lock:
            h = self._handle
        if not h:
            return False, "Not connected to UPS"
        try:
            h.send_feature_report([rid] + list(payload))
            hex_str = " ".join(f"{b:02X}" for b in payload)
            return True, f"RID=0x{rid:02X} sent: {hex_str}"
        except Exception as exc:
            return False, f"RID=0x{rid:02X} error: {exc}"

    def _send_u32(self, rid: int, value: int) -> tuple[bool, str]:
        return self._send_feature(rid, [(value >> (i * 8)) & 0xFF for i in range(4)])

    def _send_u16(self, rid: int, value: int) -> tuple[bool, str]:
        return self._send_feature(rid, [(value >> (i * 8)) & 0xFF for i in range(2)])

    def run_self_test(self) -> tuple[bool, str]:
        """Trigger UPS battery self-test."""
        return self._send_feature(0x24, [0x01])

    def abort_self_test(self) -> tuple[bool, str]:
        """Abort a running self-test."""
        return self._send_feature(0x24, [0x00])

    def schedule_shutdown(self, delay_seconds: int) -> tuple[bool, str]:
        """Schedule UPS output shutdown after *delay_seconds*."""
        return self._send_u32(0x09, delay_seconds)

    def cancel_shutdown(self) -> tuple[bool, str]:
        """Cancel a previously scheduled shutdown."""
        return self._send_u32(0x09, 0xFFFFFFFF)

    def schedule_startup(self, delay_seconds: int) -> tuple[bool, str]:
        """Schedule UPS output to come back on after *delay_seconds*."""
        return self._send_u32(0x0A, delay_seconds)

    def sync_time(self) -> tuple[bool, str]:
        """Sync the UPS internal clock to the current system time."""
        return self._send_u32(0x29, int(time.time()))

    def set_voltage(self, voltage: int) -> tuple[bool, str]:
        """Set nominal output voltage."""
        return self._send_u16(0x72, voltage)

    def set_frequency(self, freq_hz: int) -> tuple[bool, str]:
        """Set output frequency (50 or 60 Hz)."""
        return self._send_feature(0x0D, [int(freq_hz)])

    def set_runtime_limit(self, minutes: int) -> tuple[bool, str]:
        """Set minimum runtime threshold (minutes)."""
        return self._send_u16(0x17, minutes)

    # =========================================================================
    # Optional background monitor  (NUT upsmon-style)
    # =========================================================================

    def on(self, notify_type: str) -> Callable[[EventHandler], EventHandler]:
        """
        Decorator to register a NUT-style event handler.

        Requires :meth:`start_monitor` to be called for events to fire::

            @client.on(NotifyType.ONBATT)
            def power_failed(event: UPSEvent) -> None:
                send_alert(event.message)
                run_shutdown_script()

            client.start_monitor()
        """
        bus = self._ensure_bus()
        return bus.on(notify_type)

    def subscribe(
        self,
        handler: EventHandler,
        notify_type: Optional[str] = None,
    ) -> None:
        """
        Register *handler* to receive monitor events.

        If *notify_type* is ``None``, handler receives all events.
        Requires :meth:`start_monitor` to be active.
        """
        self._ensure_bus().subscribe(handler, notify_type=notify_type)

    def unsubscribe(
        self,
        handler: EventHandler,
        notify_type: Optional[str] = None,
    ) -> None:
        """Remove a previously registered event handler."""
        if self._bus:
            self._bus.unsubscribe(handler, notify_type=notify_type)

    def start_monitor(self, interval: float = 1.0) -> "UPSClient":
        """
        Start background UPS monitoring with NUT-style events.

        Launches a daemon thread that polls the device every *interval*
        seconds and fires registered event handlers on state transitions
        (ONLINE → ONBATT, ONBATT → ONLINE, LOWBATT, etc.)

        Must call :meth:`connect` before :meth:`start_monitor`.

        Parameters
        ----------
        interval : float
            Polling interval in seconds (default: 1.0).

        Returns
        -------
        UPSClient
            *self* — enables chaining.

        Example::

            client = UPSClient().connect()

            @client.on(NotifyType.ONBATT)
            def on_batt(event):
                print("Power failure!")

            client.start_monitor(interval=2.0)
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Monitor already running.")
            return self

        if not self.is_connected:
            raise RuntimeError("Must connect() before start_monitor().")

        self._monitor_interval = interval
        self._monitor_stop.clear()
        bus = self._ensure_bus()
        self._detector = EventDetector(bus)

        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name=f"UPSMonitor-{self.name}",
        )
        self._monitor_thread.start()
        logger.info("Monitor started for '%s' (interval=%.1fs).", self.name, interval)
        return self

    def stop_monitor(self) -> None:
        """Stop the background monitor thread."""
        self._monitor_stop.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
            self._monitor_thread = None
        if self._bus:
            self._bus.stop()
            self._bus = None
        self._detector = None
        logger.info("Monitor stopped for '%s'.", self.name)

    def _monitor_loop(self) -> None:
        """Internal: background polling + event detection loop."""
        while not self._monitor_stop.is_set():
            try:
                raw = self._read_raw()
                data = ups_data_from_raw(raw)
                if self._detector:
                    self._detector.process(data, connected=True)
            except Exception as exc:
                logger.error("Monitor poll error: %s", exc)
                if self._detector:
                    self._detector.process(None, connected=False)

            self._monitor_stop.wait(timeout=self._monitor_interval)

    def _ensure_bus(self) -> EventBus:
        if self._bus is None:
            self._bus = EventBus()
        return self._bus

    # =========================================================================
    # Repr
    # =========================================================================

    def __repr__(self) -> str:
        conn = "connected" if self.is_connected else "disconnected"
        monitoring = ", monitoring" if (self._monitor_thread and self._monitor_thread.is_alive()) else ""
        return f"UPSClient(name={self.name!r}, vid=0x{self._vid:04X}, {conn}{monitoring})"
