import logging
import re

logger = logging.getLogger(__name__)

def calc_lead_acid_charge(v_bat: float, v_nom: float = 12.0, is_on_battery: bool = False) -> float:
    """
    Calculate State of Charge (SoC) % for Lead-Acid (PbAc) battery based on voltage.
    Handles 12V, 24V, 36V, 48V systems dynamically by scaling to a 12V base (6 cells).
    """
    if v_bat <= 0:
        return 0.0

    if v_nom >= 40.0 or v_bat >= 40.0:
        n_packs = 4
    elif v_nom >= 30.0 or v_bat >= 30.0:
        n_packs = 3
    elif v_nom >= 20.0 or v_bat >= 20.0:
        n_packs = 2
    else:
        n_packs = 1

    v_cell_12 = v_bat / n_packs  # Normalized 12V battery pack voltage

    if not is_on_battery:
        # On AC power (Charging / Float mode)
        if v_cell_12 >= 13.4:
            return 100.0
        elif v_cell_12 >= 12.7:
            # 12.7V - 13.4V -> 90% - 100%
            return round(90.0 + ((v_cell_12 - 12.7) / (13.4 - 12.7)) * 10.0, 1)
        elif v_cell_12 >= 12.2:
            # 12.2V - 12.7V -> 60% - 90%
            return round(60.0 + ((v_cell_12 - 12.2) / (12.7 - 12.2)) * 30.0, 1)
        elif v_cell_12 >= 11.5:
            # 11.5V - 12.2V -> 20% - 60%
            return round(20.0 + ((v_cell_12 - 11.5) / (12.2 - 11.5)) * 40.0, 1)
        elif v_cell_12 >= 10.5:
            # 10.5V - 11.5V -> 0% - 20%
            return round(((v_cell_12 - 10.5) / (11.5 - 10.5)) * 20.0, 1)
        else:
            return 0.0
    else:
        # On Battery (Discharge under load - lower voltage curve due to IR drop)
        if v_cell_12 >= 12.5:
            return 100.0
        elif v_cell_12 >= 12.0:
            # 12.0V - 12.5V -> 75% - 100%
            return round(75.0 + ((v_cell_12 - 12.0) / (12.5 - 12.0)) * 25.0, 1)
        elif v_cell_12 >= 11.5:
            # 11.5V - 12.0V -> 45% - 75%
            return round(45.0 + ((v_cell_12 - 11.5) / (12.0 - 11.5)) * 30.0, 1)
        elif v_cell_12 >= 11.0:
            # 11.0V - 11.5V -> 20% - 45%
            return round(20.0 + ((v_cell_12 - 11.0) / (11.5 - 11.0)) * 25.0, 1)
        elif v_cell_12 >= 10.5:
            # 10.5V - 11.0V -> 0% - 20%
            return round(((v_cell_12 - 10.5) / (11.0 - 10.5)) * 20.0, 1)
        else:
            return 0.0


class MegatecQ1Driver:
    """
    Driver for Megatec Q1 protocol over USB HID.
    Used by Enerex MEC0003 (VID 0x0001, PID 0x0000).
    Reads data from Indexed String Descriptors instead of Feature Reports.
    """
    def __init__(self, hid_device, profile=None):
        self.dev = hid_device
        self.profile = profile
        self.cached_specs = {}

    def get_vars(self):
        data = {}

        # 1. Read Rating/Specs String (Index 13) once and cache
        if not self.cached_specs:
            try:
                specs = self.dev.get_indexed_string(13)
                if specs and specs.startswith("#"):
                    sp = specs[1:].split()
                    if len(sp) >= 4:
                        nom_v = float(sp[0])
                        nom_i = float(sp[1])
                        v_bat_nom = float(sp[2])
                        freq_nom = float(sp[3])

                        self.cached_specs["input.voltage.nominal"] = nom_v
                        self.cached_specs["output.voltage.nominal"] = nom_v
                        self.cached_specs["battery.voltage.nominal"] = v_bat_nom
                        self.cached_specs["input.frequency.nominal"] = freq_nom
                        self.cached_specs["output.frequency.nominal"] = freq_nom

                        # Compute nominal VA & Watt from rating string (e.g. 220V * 4A = 880 VA, 528W)
                        if nom_v > 0 and nom_i > 0:
                            nom_va = int(round(nom_v * nom_i))
                            self.cached_specs["ups.power.nominal"] = nom_va
                            self.cached_specs["ups.realpower.nominal"] = int(round(nom_va * 0.6))
                        else:
                            self.cached_specs["ups.power.nominal"] = 800
                            self.cached_specs["ups.realpower.nominal"] = 480
            except Exception as e:
                logger.debug(f"Failed to read Megatec Q1 specs (Index 13): {e}")

        data.update(self.cached_specs)

        # 2. Read Telemetry String (Index 3)
        # Format: (232.1 232.2 232.0 000 50.1 13.8 --.- 00001000
        try:
            telemetry = self.dev.get_indexed_string(3)
        except Exception as e:
            logger.error(f"Failed to read Megatec Q1 telemetry (Index 3): {e}")
            raise  # Raise exception to trigger device reconnect logic

        if telemetry and telemetry.startswith("("):
            parts = telemetry[1:].split()
            if len(parts) >= 8:
                try:
                    data["input.voltage"] = float(parts[0])
                    # parts[1] is fault voltage, usually ignored for standard NUT vars
                    data["output.voltage"] = float(parts[2])
                    data["ups.load"] = float(parts[3])
                    data["input.frequency"] = float(parts[4])
                    v_bat = float(parts[5])
                    data["battery.voltage"] = v_bat
                    
                    if parts[6] != "--.-":
                        data["ups.temperature"] = float(parts[6])

                    # Parse status bits
                    status_bits = parts[7]
                    status_list = []
                    is_on_batt = False
                    is_low_batt = False
                    if len(status_bits) >= 8:
                        if status_bits[0] == '1':
                            status_list.append("OB")
                            is_on_batt = True
                        else:
                            status_list.append("OL")

                        if status_bits[1] == '1':
                            status_list.append("LB")
                            is_low_batt = True

                        if status_bits[2] == '1':
                            status_list.append("BYPASS")

                        # Bit 3: UPS Failed
                        # Bit 4: UPS Type (0=Standby, 1=Online)
                        # Bit 5: Test in progress
                        if status_bits[5] == '1':
                            status_list.append("CAL")

                    # Calculate realistic battery charge % based on Lead-Acid voltage curve
                    nom_v_bat = float(data.get("battery.voltage.nominal", 12.0) or 12.0)
                    batt_pct = calc_lead_acid_charge(v_bat, nom_v_bat, is_on_battery=is_on_batt)
                    if is_low_batt and batt_pct > 20.0:
                        batt_pct = 15.0

                    data["battery.charge"] = batt_pct
                    data["ups.status"] = " ".join(status_list) if status_list else "WAIT"

                    # Determine charger status
                    v_cell_12 = v_bat / (2 if (v_bat >= 20.0 or nom_v_bat >= 20.0) else 1)
                    if is_on_batt:
                        data["battery.charger.status"] = "discharging"
                    elif v_cell_12 >= 13.4:
                        data["battery.charger.status"] = "floating"
                    else:
                        data["battery.charger.status"] = "charging"

                    # Explicitly zero out input measurements when on battery
                    if is_on_batt:
                        data["input.voltage"] = 0.0
                        data["input.frequency"] = 0.0

                    # If output voltage is 0/low (< 50V) and not on battery, the UPS power button is turned OFF
                    vout = data.get("output.voltage", 0.0)
                    if vout < 50.0 and not is_on_batt:
                        data["ups.status"] = "OFF"
                        data["outlet.1.status"] = "off"
                        data["output.voltage"] = 0.0
                        data["output.frequency"] = 0.0
                        data["ups.load"] = 0.0
                        data["battery.charger.status"] = "resting"
                    else:
                        data.setdefault("outlet.1.status", "on")
                except ValueError as ve:
                    logger.warning(f"Failed to parse telemetry parts: {ve}")

        # Also get device info for Manufacturer and Model if possible
        try:
            mfr = self.dev.get_manufacturer_string()
            if mfr:
                data["device.mfr"] = mfr
                data["ups.mfr"] = mfr
        except Exception:
            pass
            
        try:
            prod = self.dev.get_product_string()
            if prod:
                data["device.model"] = prod
                data["ups.model"] = prod
        except Exception:
            pass

        return data

    def send_command(self, cmd_str: str) -> tuple:
        """
        Send an ASCII command to Megatec UPS (e.g. 'T' for quick test, 'TL' for deep test, 'CT' to cancel).
        Appends '\r' if not already present.
        """
        if not self.dev:
            return False, "No HID device handle"
        if not cmd_str.endswith("\r"):
            cmd_str += "\r"
        raw_bytes = cmd_str.encode("ascii")
        try:
            # 1. Try standard HID write with Report ID 0
            if hasattr(self.dev, "write"):
                try:
                    written = self.dev.write(b"\x00" + raw_bytes)
                    if written and written > 0:
                        return True, f"Command '{cmd_str.strip()}' sent via write (RID 0)"
                except Exception:
                    pass
                # Try direct write without report ID prefix
                try:
                    written = self.dev.write(raw_bytes)
                    if written and written > 0:
                        return True, f"Command '{cmd_str.strip()}' sent via direct write"
                except Exception:
                    pass
            # 2. Try send_feature_report with Report ID 0
            if hasattr(self.dev, "send_feature_report"):
                try:
                    payload = [0x00] + list(raw_bytes)
                    written = self.dev.send_feature_report(payload)
                    if written and written > 0:
                        return True, f"Command '{cmd_str.strip()}' sent via feature report"
                except Exception:
                    pass
            return False, f"Failed to send command '{cmd_str.strip()}' to Megatec device"
        except Exception as e:
            return False, f"Error sending Megatec command: {e}"
