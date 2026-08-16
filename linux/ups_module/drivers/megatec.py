import logging
import re

logger = logging.getLogger(__name__)

class MegatecQ1Driver:
    """
    Driver for Megatec Q1 protocol over USB HID.
    Used by Enerex MEC0003 (VID 0x0001, PID 0x0000).
    Reads data from Indexed String Descriptors instead of Feature Reports.
    """
    def __init__(self, hid_device, profile=None):
        self.dev = hid_device
        self.profile = profile

    def get_vars(self):
        data = {}
        
        # 1. Read Telemetry String (Index 3)
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
                    
                    # Estimate battery charge percentage via linear interpolation
                    batt_pct = round(max(0.0, min(100.0, (v_bat - 10.5) / (13.5 - 10.5) * 100.0)), 1)
                    if batt_pct >= 95.0:
                        batt_pct = 100.0
                    
                    if parts[6] != "--.-":
                        data["ups.temperature"] = float(parts[6])
                        
                    # Parse status bits
                    status_bits = parts[7]
                    status_list = []
                    if len(status_bits) >= 8:
                        if status_bits[0] == '1':
                            status_list.append("OB")
                        else:
                            status_list.append("OL")
                            
                        if status_bits[1] == '1':
                            status_list.append("LB")
                            if batt_pct > 20.0:
                                batt_pct = 15.0
                            
                        if status_bits[2] == '1':
                            status_list.append("BYPASS")
                            
                        # Bit 3: UPS Failed
                        # Bit 4: UPS Type (0=Standby, 1=Online)
                        # Bit 5: Test in progress
                        if status_bits[5] == '1':
                            status_list.append("CAL")
                            
                    data["battery.charge"] = batt_pct
                    data["ups.status"] = " ".join(status_list) if status_list else "WAIT"
                except ValueError as ve:
                    logger.warning(f"Failed to parse telemetry parts: {ve}")

        # 2. Read Rating/Specs String (Index 13)
        # Format: #220.0 004 12.00 50.0
        try:
            specs = self.dev.get_indexed_string(13)
        except Exception as e:
            logger.debug(f"Failed to read Megatec Q1 specs (Index 13): {e}")
            specs = ""
            
        if specs and specs.startswith("#"):
            sp = specs[1:].split()
            if len(sp) >= 4:
                try:
                    data["input.voltage.nominal"] = float(sp[0])
                    # sp[1] is max current
                    data["battery.voltage.nominal"] = float(sp[2])
                    data["input.frequency.nominal"] = float(sp[3])
                except ValueError:
                    pass

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
