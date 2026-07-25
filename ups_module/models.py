"""
ups_module/models.py
~~~~~~~~~~~~~~~~~~~~
NUT-compatible data model for UPS state.

Key naming follows the NUT (Network UPS Tools) variable naming convention:
  https://networkupstools.org/docs/developer-guide.chunked/apas01.html

Usage::

    data: UPSData = client.get_data()
    print(data.ups_status)            # "OL", "OB", "OB LB", etc.
    print(data.to_nut_dict())         # NUT-style key/value dict
    print(data.to_json())             # JSON string
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# NUT notification event types  (mirrors upsmon NOTIFYTYPE)
# ---------------------------------------------------------------------------

class NotifyType:
    """NUT-compatible notification type constants."""

    ONLINE = "ONLINE"          # UPS is back on line power
    ONBATT = "ONBATT"          # UPS is on battery power
    LOWBATT = "LOWBATT"        # Battery charge is low
    FSD = "FSD"                # Forced shutdown in progress
    COMMOK = "COMMOK"          # Communication established
    COMMBAD = "COMMBAD"        # Communication lost
    SHUTDOWN = "SHUTDOWN"      # System is being shut down
    REPLBATT = "REPLBATT"      # Battery needs to be replaced
    NOCOMM = "NOCOMM"          # UPS unreachable
    NOPARENT = "NOPARENT"      # upsmon parent process died

    # Extension: specific to this HID driver
    CHARGING = "CHARGING"      # Battery is charging
    OVERLOAD = "OVERLOAD"      # UPS is overloaded
    OVER_TEMP = "OVER_TEMP"    # Over temperature


@dataclass
class UPSEvent:
    """A notification event, analogous to NUT's NOTIFYMSG."""

    notify_type: str                     # One of NotifyType constants
    message: str                         # Human-readable message
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    data: Optional["UPSData"] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.notify_type,
            "message": self.message,
            "timestamp": self.timestamp,
        }

    def __str__(self) -> str:
        return f"[{self.timestamp}] {self.notify_type}: {self.message}"


# ---------------------------------------------------------------------------
# Core data model
# ---------------------------------------------------------------------------

@dataclass
class UPSData:
    """
    UPS state snapshot using NUT-compatible variable names.

    All fields map 1-to-1 with NUT variable naming convention.
    Fields are ``None`` when not available from the device.
    """

    # -- Status --------------------------------------------------------------
    ups_status: Optional[str] = None
    """NUT status string: "OL", "OB", "OB LB", "OL CHRG", etc."""

    ups_alarm: Optional[str] = None
    """Alarm string from UPS."""

    ups_mode: Optional[str] = None
    """Human-readable operating mode (extension, not standard NUT)."""

    # -- Battery -------------------------------------------------------------
    battery_charge: Optional[float] = None
    """Battery charge level (0-100 %)."""

    battery_charge_low: Optional[float] = None
    """Threshold for low-battery warning (%)."""

    battery_charge_high: Optional[float] = None
    """Threshold for fully-charged (%)."""

    battery_runtime: Optional[int] = None
    """Estimated runtime on battery (seconds)."""

    battery_runtime_low: Optional[int] = None
    """Threshold for low runtime warning (seconds)."""

    battery_voltage: Optional[float] = None
    """Battery voltage (V)."""

    battery_temperature: Optional[float] = None
    """Battery temperature (degrees C)."""

    battery_type: Optional[str] = None
    """Battery chemistry type."""

    # -- Input ---------------------------------------------------------------
    input_voltage: Optional[float] = None
    """Input (mains) voltage (V)."""

    input_voltage_nominal: Optional[float] = None
    """Nominal input voltage (V)."""

    input_frequency: Optional[float] = None
    """Input AC frequency (Hz)."""

    input_frequency_nominal: Optional[float] = None
    """Nominal input frequency (Hz)."""

    input_transfer_low: Optional[float] = None
    """Low voltage transfer point (V)."""

    input_transfer_high: Optional[float] = None
    """High voltage transfer point (V)."""

    # -- Output --------------------------------------------------------------
    output_voltage: Optional[float] = None
    """Output voltage (V)."""

    output_voltage_nominal: Optional[float] = None
    """Nominal output voltage (V)."""

    output_frequency: Optional[float] = None
    """Output AC frequency (Hz)."""

    output_current: Optional[float] = None
    """Output current (A)."""

    output_power: Optional[int] = None
    """Output active power (W)."""

    output_power_apparent: Optional[int] = None
    """Output apparent power (VA)."""

    # -- UPS Configuration ---------------------------------------------------
    ups_load: Optional[float] = None
    """Load on UPS output (%)."""

    ups_temperature: Optional[float] = None
    """UPS internal temperature (degrees C)."""

    ups_firmware: Optional[str] = None
    """UPS firmware version string."""

    ups_power_nominal: Optional[int] = None
    """Nominal UPS power (W)."""

    ups_apparent_power_nominal: Optional[int] = None
    """Nominal UPS apparent power (VA)."""

    # -- Flags (internal - not standard NUT keys) ----------------------------
    ac_present: Optional[bool] = None
    charging: Optional[bool] = None
    discharging: Optional[bool] = None
    status_good: Optional[bool] = None
    below_capacity_limit: Optional[bool] = None
    overload: Optional[bool] = None
    internal_failure: Optional[bool] = None
    need_replacement: Optional[bool] = None
    over_temperature: Optional[bool] = None
    shutdown_imminent: Optional[bool] = None
    test_discharge_active: Optional[bool] = None

    # -- Self-test -----------------------------------------------------------
    battery_test_status: Optional[str] = None
    """Self-test result: "idle", "running", "passed", "failed", etc."""

    # -- Scan metadata -------------------------------------------------------
    scan_report_count: Optional[int] = None
    scan_report_ids: List[str] = field(default_factory=list)

    # -- Tentative/inferred values -------------------------------------------
    tentative_input_voltage: Optional[float] = None
    tentative_output_voltage: Optional[float] = None
    tentative_battery_voltage: Optional[float] = None
    tentative_input_frequency: Optional[float] = None
    tentative_runtime_min: Optional[int] = None

    # -- Last event date -----------------------------------------------------
    last_event_date: Optional[str] = None

    # -------------------------------------------------------------------------
    # Conversion helpers
    # -------------------------------------------------------------------------

    def to_nut_dict(self) -> Dict[str, Any]:
        """
        Return a NUT-style variable dictionary.

        Keys use dot-notation as in the NUT variable naming convention
        (e.g. ``"battery.charge"``, ``"ups.status"``).

        Only fields with non-None values are included.
        """
        mapping: Dict[str, Any] = {
            "ups.status":                   self.ups_status,
            "ups.alarm":                    self.ups_alarm,
            "ups.load":                     self.ups_load,
            "ups.temperature":              self.ups_temperature,
            "ups.firmware":                 self.ups_firmware,
            "battery.charge":               self.battery_charge,
            "battery.charge.low":           self.battery_charge_low,
            "battery.charge.high":          self.battery_charge_high,
            "battery.runtime":              self.battery_runtime,
            "battery.runtime.low":          self.battery_runtime_low,
            "battery.voltage":              self.battery_voltage,
            "battery.temperature":          self.battery_temperature,
            "battery.type":                 self.battery_type,
            "battery.test.status":          self.battery_test_status,
            "input.voltage":                self.input_voltage,
            "input.voltage.nominal":        self.input_voltage_nominal,
            "input.frequency":              self.input_frequency,
            "input.frequency.nominal":      self.input_frequency_nominal,
            "input.transfer.low":           self.input_transfer_low,
            "input.transfer.high":          self.input_transfer_high,
            "output.voltage":               self.output_voltage,
            "output.voltage.nominal":       self.output_voltage_nominal,
            "output.frequency":             self.output_frequency,
            "output.current":               self.output_current,
            "output.power":                 self.output_power,
            "output.power.apparent":        self.output_power_apparent,
            "ups.power.nominal":            self.ups_power_nominal,
            "ups.apparent.power.nominal":   self.ups_apparent_power_nominal,
        }
        return {k: v for k, v in mapping.items() if v is not None}

    def to_full_dict(self) -> Dict[str, Any]:
        """Return all fields as a dict (including None values and raw flags)."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Return NUT-style dict as a JSON string."""
        return json.dumps(self.to_nut_dict(), ensure_ascii=False, indent=indent)

    def is_on_battery(self) -> bool:
        """True when UPS is running on battery power."""
        status = self.ups_status or ""
        return "OB" in status or (self.ac_present is False)

    def is_low_battery(self) -> bool:
        """True when battery is below the low threshold."""
        status = self.ups_status or ""
        return "LB" in status or (self.below_capacity_limit is True)

    def is_charging(self) -> bool:
        """True when battery is actively charging."""
        return bool(self.charging)

    def is_online(self) -> bool:
        """True when UPS is on line power."""
        status = self.ups_status or ""
        return "OL" in status or (self.ac_present is True)

    def __repr__(self) -> str:
        charge = f"{self.battery_charge}%" if self.battery_charge is not None else "?"
        return (
            f"UPSData(status={self.ups_status!r}, "
            f"battery={charge}, "
            f"runtime={self.battery_runtime}s)"
        )


# ---------------------------------------------------------------------------
# Factory: build UPSData from raw decoded dict
# ---------------------------------------------------------------------------

def ups_data_from_raw(raw: Dict[str, Any]) -> UPSData:
    """
    Convert the raw dict returned by ``core_hid_ups.decode_feature_reports``
    (and ``infer_tentative_live_values``) into a typed ``UPSData`` instance.
    """

    def _get(key: str, default: Any = None) -> Any:
        return raw.get(key, default)

    return UPSData(
        # Status
        ups_status=_get("ups.status"),
        ups_mode=_get("ups_mode"),

        # Battery
        battery_charge=_get("battery.charge"),
        battery_charge_low=_get("battery.charge.low"),
        battery_charge_high=_get("battery.charge.high"),
        battery_runtime=_get("battery.runtime"),
        battery_voltage=_get("battery_voltage_v"),
        battery_test_status=_get("battery_test_status"),

        # Input
        input_voltage=_get("input.voltage") or _get("tentative.input.voltage"),
        input_voltage_nominal=_get("input.voltage.nominal") or _get("config_nominal_voltage_v"),
        input_frequency=_get("input.frequency") or _get("tentative.input.frequency"),
        input_frequency_nominal=_get("input.frequency.nominal") or _get("config_nominal_frequency_hz"),
        input_transfer_low=_get("input.transfer.low"),

        # Output
        output_voltage=_get("output.voltage") or _get("output_voltage_v") or _get("tentative.output.voltage"),
        output_frequency=_get("output_frequency_hz"),
        output_current=_get("output_current_a"),
        output_power=_get("output_active_power_w"),
        output_power_apparent=_get("output_apparent_power_va"),

        # UPS
        ups_load=_get("percent_load"),
        ups_temperature=_get("ups.temperature") or _get("temperature_c"),
        ups_firmware=_get("ups.firmware"),
        ups_power_nominal=_get("config_max_active_power_w"),
        ups_apparent_power_nominal=_get("config_max_apparent_power_va"),

        # Flags
        ac_present=_get("ac_present"),
        charging=_get("charging"),
        discharging=_get("discharging"),
        status_good=_get("status_good"),
        below_capacity_limit=_get("below_capacity_limit"),
        overload=_get("overload"),
        internal_failure=_get("internal_failure"),
        need_replacement=_get("need_replacement"),
        over_temperature=_get("over_temperature"),
        shutdown_imminent=_get("shutdown_imminent"),
        test_discharge_active=_get("test_discharge_active"),

        # Tentative (inferred)
        tentative_input_voltage=_get("tentative.input.voltage"),
        tentative_output_voltage=_get("tentative.output.voltage"),
        tentative_battery_voltage=_get("tentative.battery.voltage"),
        tentative_input_frequency=_get("tentative.input.frequency"),
        tentative_runtime_min=_get("tentative.runtime.min"),

        # Scan metadata
        scan_report_count=_get("scan.report_count"),
        scan_report_ids=_get("scan.report_ids", []),

        # Event date
        last_event_date=_get("last_event_date"),
    )
