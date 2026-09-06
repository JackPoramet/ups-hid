"""
ups_module/poller.py
~~~~~~~~~~~~~~~~~~~~
Background polling thread for the UPS HID device.

Refactored from the ``UPSPoller`` class in ``web_daemon.py``.
Now takes explicit ``DataStore`` and ``EventDetector`` dependencies
instead of writing to module-level globals.

Usage::

    store = DataStore()
    bus = EventBus()
    detector = EventDetector(bus)

    poller = UPSPoller(store=store, detector=detector)
    poller.start()
    ...
    poller.stop()
    poller.join()
"""

from __future__ import annotations

import logging
import math
import os
import platform
import re
import threading
import time
from pathlib import Path
from typing import Optional

try:
    from .device_registry import DeviceRegistry
except ImportError:
    from device_registry import DeviceRegistry

logger = logging.getLogger(__name__)

_registry = DeviceRegistry()

# Lazy import: bundled core.py
try:
    from .core import (
        VID,
        PID,
        decode_feature_reports,
        infer_tentative_live_values,
        open_ups_device,
        read_all_feature_reports,
    )
    HID_AVAILABLE = True
except ImportError:
    try:
        from core import (
            VID,
            PID,
            decode_feature_reports,
            infer_tentative_live_values,
            open_ups_device,
            read_all_feature_reports,
        )
        HID_AVAILABLE = True
    except ImportError as _e:
        logger.warning("core protocol engine not available: %s", _e)
        HID_AVAILABLE = False
        _fallback = _registry.get_default()
        VID = _fallback.vid
        PID = _fallback.pid


def _read_descriptor_from_sysfs(device_path: object) -> Optional[bytes]:
    """Read HID report descriptor from Linux sysfs (Linux-only)."""
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


class UPSPoller(threading.Thread):
    """
    Background thread that continuously polls the UPS HID device.

    Results are written to *store* (a :class:`~ups_module.store.DataStore`)
    and state transitions are detected by *detector*
    (an :class:`~ups_module.events.EventDetector`).

    Parameters
    ----------
    store:
        Thread-safe data store where poll results are written.
    detector:
        Event detector that compares successive polls and fires notifications.
    model:
        Registered model id from meta.json. If provided, VID/PID are
        loaded from the registry.
    vid:
        USB Vendor ID. Overrides the registry value if provided.
    pid:
        USB Product ID. Overrides the registry value if provided.
    poll_interval:
        Seconds between polls (default: 1.0 s).
    """

    def __init__(
        self,
        store,
        detector=None,
        model: Optional[str] = None,
        vid: Optional[int] = None,
        pid: Optional[int] = None,
        poll_interval: float = 1.0,
    ) -> None:
        super().__init__(daemon=True, name="UPSPoller")
        self.store = store
        self.detector = detector

        # Resolve device profile
        if model:
            profile = _registry.get_by_id(model)
            if not profile:
                raise ValueError(f"Unknown model: {model!r}")
        else:
            profile = _registry.get_default()

        self.vid = vid if vid is not None else profile.vid
        self.pid = pid if pid is not None else profile.pid
        if not isinstance(poll_interval, (int, float)) or isinstance(poll_interval, bool) or not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("poll_interval must be a finite positive number of seconds")
        self.poll_interval = float(poll_interval)

        self._stop_event = threading.Event()
        self._device_lock = threading.Lock()
        self._device_handle = None
        self._device_info: dict = {}
        self._descriptor_profile: Optional[dict] = None
        self._report_ids: list = list(profile.report_ids) if profile.report_ids else list(range(0x01, 0x80))

    # -------------------------------------------------------------------------
    # Public control interface
    # -------------------------------------------------------------------------

    def stop(self) -> None:
        """Signal the poller to stop after the current poll cycle."""
        self._stop_event.set()

    @property
    def device_handle(self):
        """Thread-safe access to the current HID device handle."""
        with self._device_lock:
            return self._device_handle

    # -------------------------------------------------------------------------
    # Thread entry point
    # -------------------------------------------------------------------------

    def run(self) -> None:
        logger.info("UPSPoller started (VID=0x%04X PID=0x%04X, interval=%.1fs).",
                    self.vid, self.pid, self.poll_interval)

        while not self._stop_event.is_set():
            if not HID_AVAILABLE:
                self.store.set_error("Module core_hid_ups not found.")
                if self.detector:
                    self.detector.process(None, connected=False)
                self._stop_event.wait(5)
                continue

            if self.device_handle is None:
                self._connect()
                if self.device_handle is None:
                    self._stop_event.wait(5)
                    continue

            self._poll_once()
            self._stop_event.wait(self.poll_interval)

        self._close_device()
        logger.info("UPSPoller stopped.")

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _connect(self) -> None:
        """Open the HID device and load the descriptor profile."""
        try:
            h, info = open_ups_device(self.vid, self.pid)
        except Exception as exc:
            msg = f"Connect error: {exc}"
            logger.error(msg)
            self.store.set_error(msg)
            if self.detector:
                self.detector.process(None, connected=False)
            return

        if h is None:
            msg = f"Device not found VID=0x{self.vid:04X} PID=0x{self.pid:04X}"
            self.store.set_error(msg)
            if self.detector:
                self.detector.process(None, connected=False)
            return

        with self._device_lock:
            self._device_handle = h
        self._device_info = info or {}

        mfr = self._device_info.get("manufacturer_string", "?")
        prod = self._device_info.get("product_string", "?")
        logger.info("Connected to UPS: %s %s", mfr, prod)

    def _poll_once(self) -> None:
        """Perform a single HID read cycle and update the store."""
        h = self.device_handle
        if h is None:
            return

        try:
            raw, report_meta = read_all_feature_reports(
                h,
                report_ids=self._report_ids,
                sizes=(64,),
                retries=1,
                include_zero=False,
            )
            if 0x01 not in raw:
                errors = report_meta.get(0x01, {}).get("errors", 0)
                raise RuntimeError(
                    "Unable to read authoritative UPS status report 0x01"
                    + (f" ({errors} HID read error(s))" if errors else "")
                )
            ups = decode_feature_reports(raw)
            ups.update(infer_tentative_live_values(raw, ups))
            
            self._fallback_read_input_voltage(ups)
            
            self.store.update(self._device_info, ups, status_message="Connected")

            if self.detector:
                from .models import ups_data_from_raw
                self.detector.process(ups_data_from_raw(ups), connected=True)

        except Exception as exc:
            msg = f"Poll error: {exc}"
            logger.error(msg)
            self.store.set_error(msg)
            if self.detector:
                self.detector.process(None, connected=False)
            self._close_device()

    def _fallback_read_input_voltage(self, ups: dict) -> None:
        """Fallback to read Input Voltage (Report 0x31) using pyusb if missing."""
        if "input.voltage" in ups:
            return

        try:
            import usb.core

            system = platform.system().lower()
            # Never detach the kernel HID driver from a live UPS. The normal
            # hidapi report path is authoritative; absent input voltage stays
            # unavailable instead of risking the device interface.
            if system == "linux":
                return
            backend = None

            if system == "windows":
                import usb.backend.libusb0
                
                dll_path = r"C:\Program Files\WinpowerG2\libUSB_driver\amd64\libusb0.dll"
                local_dll = os.path.join(os.path.dirname(__file__), "drivers", "windows", "libusb0.dll")
                fallback_dll = r"C:\Program Files\WinpowerG2\libUSB_driver\amd64\libusb0.dll"
                
                if os.path.exists(local_dll):
                    backend = usb.backend.libusb0.get_backend(find_library=lambda x: local_dll)
                elif os.path.exists(fallback_dll):
                    backend = usb.backend.libusb0.get_backend(find_library=lambda x: fallback_dll)

            dev = usb.core.find(idVendor=self.vid, idProduct=self.pid, backend=backend)
            
            if not dev:
                return

            # GET_REPORT: bmRequestType=0xA1, bRequest=0x01, wValue=0x0331, wIndex=0, length=5
            payload = dev.ctrl_transfer(0xA1, 0x01, 0x0331, 0, 5, timeout=1000)
            if payload and len(payload) >= 5:
                volt_raw = payload[3] | (payload[4] << 8)
                ups["input.voltage"] = volt_raw / 10.0

        except usb.core.USBError as e:
            logger.debug("pyusb fallback access denied: %s", e)
        except ImportError:
            pass # pyusb not installed
        except Exception as e:
            logger.debug("pyusb fallback failed: %s", e)

    def _close_device(self) -> None:
        """Close the HID device handle."""
        with self._device_lock:
            h = self._device_handle
            if h:
                try:
                    h.close()
                except Exception:
                    pass
            self._device_handle = None
