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
import re
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import: bundled core.py first, then legacy fallbacks
try:
    from .core import (
        DEFAULT_DESCRIPTOR_BIN,
        DEFAULT_DESCRIPTOR_TXT,
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
    try:
        from .core_hid_ups import (
            DEFAULT_DESCRIPTOR_BIN,
            DEFAULT_DESCRIPTOR_TXT,
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
        try:
            from core_hid_ups import (
                DEFAULT_DESCRIPTOR_BIN,
                DEFAULT_DESCRIPTOR_TXT,
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
        except ImportError as _e:
            logger.warning("core protocol engine not available: %s", _e)
            HID_AVAILABLE = False
            VID = 0x06DA
            PID = 0xFFFF
            DEFAULT_DESCRIPTOR_BIN = "report_descriptor_live.bin"
            DEFAULT_DESCRIPTOR_TXT = "report_descriptor_live.txt"


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
    vid:
        USB Vendor ID (default: 0x06DA Phoenixtec).
    pid:
        USB Product ID (default: 0xFFFF Innova Unity).
    poll_interval:
        Seconds between polls (default: 1.0 s).
    """

    def __init__(
        self,
        store,
        detector=None,
        vid: int = VID,
        pid: int = PID,
        poll_interval: float = 1.0,
    ) -> None:
        super().__init__(daemon=True, name="UPSPoller")
        self.store = store
        self.detector = detector
        self.vid = vid
        self.pid = pid
        self.poll_interval = poll_interval

        self._stop_event = threading.Event()
        self._device_lock = threading.Lock()
        self._device_handle = None
        self._device_info: dict = {}
        self._descriptor_profile: Optional[dict] = None
        self._report_ids: list = list(range(0x01, 0x80))

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
                time.sleep(5)
                continue

            if self.device_handle is None:
                self._connect()
                if self.device_handle is None:
                    time.sleep(5)
                    continue

            self._poll_once()
            time.sleep(self.poll_interval)

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
        self._load_descriptor()

        mfr = self._device_info.get("manufacturer_string", "?")
        prod = self._device_info.get("product_string", "?")
        logger.info("Connected to UPS: %s %s", mfr, prod)

    def _load_descriptor(self) -> None:
        """Try to read the HID descriptor from sysfs and build report ID list."""
        raw_path = self._device_info.get("path")
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
                logger.info("Descriptor loaded: %d feature report IDs.", len(ids))
        except Exception as exc:
            logger.error("Profile load error: %s", exc)

    def _poll_once(self) -> None:
        """Perform a single HID read cycle and update the store."""
        h = self.device_handle
        if h is None:
            return

        try:
            raw, _ = read_all_feature_reports(
                h,
                report_ids=self._report_ids,
                sizes=(8, 16, 32),
                retries=1,
                include_zero=False,
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
            import platform
            import os

            system = platform.system().lower()
            backend = None

            if system == "windows":
                import usb.backend.libusb0
                
                # 1. Check if WinpowerG2 is installed in the default path
                dll_path = r"C:\Program Files\WinpowerG2\libUSB_driver\amd64\libusb0.dll"
                
                # 2. Check if the user placed libusb0.dll inside the ups_module folder
                local_dll = os.path.join(os.path.dirname(__file__), "libusb0.dll")
                # Prioritize our bundled driver
                local_dll = os.path.join(os.path.dirname(__file__), "drivers", "windows", "libusb0.dll")
                fallback_dll = r"C:\Program Files\WinpowerG2\libUSB_driver\amd64\libusb0.dll"
                
                if os.path.exists(local_dll):
                    backend = usb.backend.libusb0.get_backend(find_library=lambda x: local_dll)
                elif os.path.exists(fallback_dll):
                    backend = usb.backend.libusb0.get_backend(find_library=lambda x: fallback_dll)

            dev = usb.core.find(idVendor=self.vid, idProduct=self.pid, backend=backend)
            
            # Auto-Install Filter Driver on Windows if pyusb fails to find it or access it
            if not dev and system == "windows":
                from . import windows_setup
                if windows_setup.install_filter(self.vid, self.pid):
                    # Retry finding device after installation
                    dev = usb.core.find(idVendor=self.vid, idProduct=self.pid, backend=backend)
            
            if not dev:
                return

            if system == "linux":
                try:
                    if dev.is_kernel_driver_active(0):
                        dev.detach_kernel_driver(0)
                except Exception as e:
                    logger.debug("detach_kernel_driver failed: %s", e)

            # GET_REPORT: bmRequestType=0xA1, bRequest=0x01, wValue=0x0331, wIndex=0, length=5
            payload = dev.ctrl_transfer(0xA1, 0x01, 0x0331, 0, 5, timeout=1000)
            if payload and len(payload) >= 5:
                volt_raw = payload[3] | (payload[4] << 8)
                ups["input.voltage"] = volt_raw / 10.0

            if system == "linux":
                try:
                    dev.attach_kernel_driver(0)
                except Exception as e:
                    logger.debug("attach_kernel_driver failed: %s", e)
                    
        except usb.core.USBError as e:
            logger.debug("pyusb fallback access denied: %s", e)
            if platform.system().lower() == "windows":
                # The device might be present but locked (filter driver not fully active)
                from . import windows_setup
                windows_setup.install_filter(self.vid, self.pid)
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
