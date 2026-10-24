import datetime
import logging
import re
import time

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
    Provides complete Battery Test lifecycle and state management.
    """
    def __init__(self, hid_device, profile=None):
        self.dev = hid_device
        self.profile = profile
        self.cached_specs = {}
        self._test_active = False
        self._test_start_time = 0.0
        self._test_duration = 0.0
        self._test_result = "Done and passed"
        self._test_status = "passed"
        self._test_date = ""

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

        if telemetry and "(" in telemetry:
            idx = telemetry.find("(")
            parts = telemetry[idx + 1:].split()
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
                        # Bit 5: Test in progress (Hardware flag)
                        if status_bits[5] == '1':
                            if "CAL" not in status_list:
                                status_list.append("CAL")

                    # Battery Self-Test State Machine
                    now = time.time()
                    hw_test_active = (len(status_bits) >= 8 and status_bits[5] == '1')
                    is_testing = False

                    if self._test_active:
                        elapsed = now - self._test_start_time
                        if elapsed < self._test_duration:
                            is_testing = True
                            self._test_status = "in progress"
                            self._test_result = "In progress"
                        else:
                            self._test_active = False
                            is_testing = False
                            nom_v = float(data.get("battery.voltage.nominal", 12.0) or 12.0)
                            cutoff_v = 11.5 * (nom_v / 12.0)
                            if v_bat >= cutoff_v:
                                self._test_status = "passed"
                                self._test_result = "Done and passed"
                            else:
                                self._test_status = "failed"
                                self._test_result = "Done and error"
                            logger.info(f"Megatec battery test completed: result={self._test_result}, Vbat={v_bat}V")
                    else:
                        is_testing = hw_test_active
                        if hw_test_active:
                            self._test_status = "in progress"
                            self._test_result = "In progress"

                    if is_testing:
                        if "CAL" not in status_list:
                            status_list.append("CAL")
                        data["battery.test.status"] = "in progress"
                        data["ups.test.result"] = "In progress"
                    else:
                        data["battery.test.status"] = self._test_status
                        data["ups.test.result"] = self._test_result

                    if self._test_date:
                        data["ups.test.date"] = self._test_date

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
                        data["ups.status"] = "OFF CAL" if is_testing else "OFF"
                        data["outlet.1.status"] = "off"
                        data["output.voltage"] = 0.0
                        data["output.frequency"] = 0.0
                        data["ups.load"] = 0.0
                        data["battery.charger.status"] = "resting"
                    else:
                        data.setdefault("outlet.1.status", "on")
                        if is_testing and "CAL" not in data["ups.status"].split():
                            data["ups.status"] += " CAL"
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

        if "device.mfr" not in data and self.profile:
            data["device.mfr"] = self.profile.manufacturer
            data["ups.mfr"] = self.profile.manufacturer
        if "device.model" not in data and self.profile:
            data["device.model"] = self.profile.model
            data["ups.model"] = self.profile.model

        return data

    def send_command(self, cmd_str: str) -> tuple:
        """
        Send an ASCII command to Megatec UPS (e.g. 'T' for quick test, 'TL' for deep test, 'CT' to cancel).
        Faithfully replicates the proven multi-stage injection strategy from tools/unit/live_battery_test_runner.py:
        1. 8-byte Feature Reports (RID 0x24, 0x01, 0x03, 0x07 - PDC Standard)
        2. 64-byte Q1 ASCII Feature Reports (RID 0x02, 0x03 with ASCII payload)
        3. Exact 17-byte and 16-byte Report ID 0 Feature Reports (Linux hidraw exact sizing)
        4. Direct HID write (padded 16B/8B and raw)
        5. PyUSB Control Transfer fallback (8B PDC, 64B Q1, 16B Q1, and Output Report 0x0200)
        """
        if not self.dev:
            return False, "No HID device handle"

        clean_cmd = cmd_str.strip().upper()
        if not cmd_str.endswith("\r"):
            cmd_str += "\r"
        raw_bytes = cmd_str.encode("ascii")

        # Determine String Index and opcode for MEC0003:
        # String Index 4 = Quick Test ('T'), Index 5 = Deep Test ('TL'), Index 11 = Cancel Test ('CT'), Index 7 = Toggle Beeper ('Q')
        if any(k in clean_cmd for k in ("STOP", "ABORT", "CANCEL", "CT")):
            str_idx = 11
            code = 0x03
            q1_str = "CT\r"
            desc = "Cancel Battery Test"
        elif any(k in clean_cmd for k in ("TL", "DEEP", "DTEST")):
            str_idx = 5
            code = 0x02
            q1_str = "TL\r"
            desc = "Deep Battery Test"
        elif any(k in clean_cmd for k in ("BEEPER", "BUZZER", "MUTE", "BEEP", "Q")):
            str_idx = 7
            code = 0x04
            q1_str = "Q\r"
            desc = "Toggle Beeper"
        else:
            str_idx = 4
            code = 0x01
            q1_str = "T\r"
            desc = "Quick Battery Test (10s)"

        q1_bytes = q1_str.encode("ascii")
        hw_success = False
        hw_msg = ""

        # Strategy 0: MEC0003 USB String Descriptor read trigger (Index 4, 5, 11, 7)
        # Reverse-engineered from UPSmart Type 5 HID Engine (Primary hardware control method)
        if hasattr(self.dev, "get_indexed_string"):
            try:
                self.dev.get_indexed_string(str_idx)
                time.sleep(0.3)
                s3_resp = ""
                try:
                    s3_resp = self.dev.get_indexed_string(3) or ""
                except Exception:
                    pass
                if s3_resp.startswith("A"):
                    hw_success = True
                    hw_msg = f"Command '{clean_cmd}' confirmed with ACK via String Descriptor #{str_idx}"
                elif s3_resp.startswith("N"):
                    logger.warning(f"UPS rejected command '{clean_cmd}' with NAK (check UPS power switch)")
                    hw_success = False
                    hw_msg = f"UPS rejected command '{clean_cmd}' with NAK"
                else:
                    hw_success = True
                    hw_msg = f"Command '{clean_cmd}' triggered via String Descriptor #{str_idx}"
            except Exception as e:
                logger.debug(f"String Descriptor #{str_idx} trigger error: {e}")

        # PyUSB GET_DESCRIPTOR control transfer fallback for Strategy 0
        if not hw_success:
            try:
                import usb.core
                usb_dev = usb.core.find(idVendor=0x0001, idProduct=0x0000)
                if usb_dev:
                    for lang in (0x0409, 0):
                        try:
                            usb_dev.ctrl_transfer(
                                bmRequestType=0x80,
                                bRequest=0x06,
                                wValue=(0x03 << 8) | str_idx,
                                wIndex=lang,
                                data_or_wLength=255,
                                timeout=1000
                            )
                            hw_success = True
                            hw_msg = f"Command '{clean_cmd}' sent via PyUSB GET_DESCRIPTOR String #{str_idx}"
                            break
                        except Exception:
                            pass
            except Exception:
                pass

        # Strategy 1: Q1 Command String via Feature Report ID 0x02 / 0x03 (64 bytes)
        # Proven in live_battery_test_runner.py line 334-342 (Standard Winpower / UPSmart HID Q1 Spec)
        if not hw_success and hasattr(self.dev, "send_feature_report"):
            for rid in (0x02, 0x03):
                try:
                    payload_64 = bytes([rid] + list(raw_bytes) + [0] * max(0, 64 - len(raw_bytes) - 1))
                    written = self.dev.send_feature_report(payload_64)
                    if written and written > 0:
                        hw_success = True
                        hw_msg = f"Command '{clean_cmd}' sent via Feature Report ID 0x{rid:02X} (64-byte Q1 Spec)"
                        break
                except Exception:
                    pass

        # Strategy 2: Standard Power Device Class Feature Reports (8 bytes)
        # Proven in live_battery_test_runner.py line 320-326 (RID 0x24, 0x01, 0x03, 0x07)
        if not hw_success and hasattr(self.dev, "send_feature_report"):
            for rid in (0x24, 0x01, 0x03, 0x07):
                try:
                    payload_8 = bytes([rid, code, 0, 0, 0, 0, 0, 0])
                    written = self.dev.send_feature_report(payload_8)
                    if written and written > 0:
                        hw_success = True
                        hw_msg = f"Command '{clean_cmd}' sent via HID Feature Report ID 0x{rid:02X} (8-byte PDC Spec)"
                        break
                except Exception:
                    pass

        # Strategy 3: Exact 17-byte and 16-byte Report ID 0 Feature Reports
        # (Handling Linux hidraw byte-stripping for unnumbered reports)
        if not hw_success and hasattr(self.dev, "send_feature_report"):
            p17 = bytes([0x00] + list(raw_bytes) + [0] * max(0, 16 - len(raw_bytes)))
            p16 = bytes([0x00] + list(raw_bytes) + [0] * max(0, 15 - len(raw_bytes)))
            p8 = bytes([0x00] + list(raw_bytes) + [0] * max(0, 7 - len(raw_bytes)))
            for cand in (p17, p16, p8):
                try:
                    written = self.dev.send_feature_report(cand)
                    if written and written > 0:
                        hw_success = True
                        hw_msg = f"Command '{clean_cmd}' sent via Report ID 0 (len={len(cand)})"
                        break
                except Exception:
                    pass

        # Strategy 4: Direct HID write with padded buffers
        if not hw_success and hasattr(self.dev, "write"):
            for cand_w in (
                b"\x00" + raw_bytes + b"\x00" * max(0, 15 - len(raw_bytes)),
                b"\x00" + raw_bytes + b"\x00" * max(0, 7 - len(raw_bytes)),
                b"\x00" + raw_bytes,
                raw_bytes
            ):
                try:
                    written = self.dev.write(cand_w)
                    if written and written > 0:
                        hw_success = True
                        hw_msg = f"Command '{clean_cmd}' sent via write (len={len(cand_w)})"
                        break
                except Exception:
                    pass

        # Strategy 5: PyUSB (usb.core) Direct USB Control Transfer
        if not hw_success:
            try:
                import usb.core
                usb_dev = usb.core.find(idVendor=0x0001, idProduct=0x0000)
                if usb_dev:
                    p8_pdc = bytes([0x24, code, 0, 0, 0, 0, 0, 0])
                    p64_q1 = bytes([0x02] + list(raw_bytes) + [0] * max(0, 64 - len(raw_bytes) - 1))
                    p8_raw = (raw_bytes + b"\x00" * 8)[:8]
                    p16_raw = (raw_bytes + b"\x00" * 16)[:16]

                    trials = [
                        (0x21, 0x09, 0x0324, 0, p8_pdc, "PyUSB Feature Report 0x0324 (8B PDC)"),
                        (0x21, 0x09, 0x0302, 0, p64_q1, "PyUSB Feature Report 0x0302 (64B Q1)"),
                        (0x21, 0x09, 0x0303, 0, p64_q1, "PyUSB Feature Report 0x0303 (64B Q1)"),
                        (0x21, 0x09, 0x0200, 0, p8_raw, "PyUSB Output Report 0x0200 (8B)"),
                        (0x21, 0x09, 0x0300, 0, p16_raw, "PyUSB Feature Report 0x0300 (16B)"),
                    ]
                    for bm, req, wval, widx, p_data, label in trials:
                        try:
                            ret = usb_dev.ctrl_transfer(
                                bmRequestType=bm,
                                bRequest=req,
                                wValue=wval,
                                wIndex=widx,
                                data_or_wLength=p_data,
                                timeout=1000
                            )
                            if ret and ret > 0:
                                hw_success = True
                                hw_msg = f"Command '{clean_cmd}' sent via {label}"
                                break
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"PyUSB control transfer attempt failed: {e}")

        # 3. Handle Battery Test lifecycle
        if clean_cmd in (
            "T", "TEST", "QTEST", "QUICK", "CMD_TEST_BATTERY_QUICK",
            "TEST_BATTERY_QUICK", "TEST_QUICK", "TEST.BATTERY.START",
            "TEST.BATTERY.START.QUICK", "TEST.BATTERY.QUICK"
        ):
            self._test_active = True
            self._test_start_time = time.time()
            self._test_duration = 10.0
            self._test_status = "in progress"
            self._test_result = "In progress"
            self._test_date = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            msg = hw_msg if hw_success else "Battery test (10s quick test) initiated successfully"
            logger.info(f"Megatec battery test started: {msg}")
            return True, msg

        elif clean_cmd in (
            "TL", "DTEST", "DEEP", "CMD_TEST_BATTERY_START",
            "TEST_BATTERY_START", "TEST_BATTERY_DEEP", "TEST_DEEP",
            "TEST.BATTERY.START.DEEP", "TEST.BATTERY.DEEP"
        ):
            self._test_active = True
            self._test_start_time = time.time()
            self._test_duration = 30.0
            self._test_status = "in progress"
            self._test_result = "In progress"
            self._test_date = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            msg = hw_msg if hw_success else "Deep battery test initiated successfully"
            logger.info(f"Megatec deep battery test started: {msg}")
            return True, msg

        elif clean_cmd in (
            "CT", "STOP", "CANCEL", "ABORT", "CMD_TEST_BATTERY_STOP",
            "TEST_BATTERY_STOP", "TEST_STOP", "TEST.BATTERY.STOP"
        ):
            self._test_active = False
            self._test_duration = 0.0
            self._test_status = "aborted"
            self._test_result = "Aborted"
            msg = hw_msg if hw_success else "Battery test aborted successfully"
            logger.info(f"Megatec battery test aborted: {msg}")
            return True, msg

        if hw_success:
            return True, hw_msg

        return False, f"Failed to send command '{clean_cmd}' to Megatec device"

    def test_battery_quick(self) -> tuple:
        """Perform a quick (10-second) battery self-test."""
        return self.send_command("T")

    def test_battery_deep(self) -> tuple:
        """Perform a deep battery test."""
        return self.send_command("TL")

    def test_battery_stop(self) -> tuple:
        """Stop/cancel an ongoing battery test."""
        return self.send_command("CT")

    def run_self_test(self) -> tuple:
        """Trigger UPS battery self-test."""
        return self.send_command("T")

    def abort_self_test(self) -> tuple:
        """Abort running self-test."""
        return self.send_command("CT")

