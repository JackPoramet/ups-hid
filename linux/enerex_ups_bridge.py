#!/usr/bin/env python3
import time
import os
import sys
import logging
import datetime

# Path to the deployed ups_module directory
INSTALL_DIR = "/opt/enerex-ups"
if INSTALL_DIR not in sys.path:
    sys.path.insert(0, INSTALL_DIR)

from ups_module.client import UPSClient

# File that NUT's dummy-ups will read from
DUMMY_FILE = "/etc/nut/myups.dev"

# Phoenixtec Innova VID/PID
PHOENIXTEC_VID = 0x06DA
PHOENIXTEC_PID = 0xFFFF

# Polling interval
POLL_INTERVAL = 1

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def enrich_nut_variables(data: dict, info: dict) -> dict:
    """
    Enriches the live UPS data dictionary with missing standard NUT variables
    (conforming to usbhid-ups / MGE HID 1.40 / Power Device Class specification)
    while strictly preserving all existing live readings.
    """
    # 1. Device Identification & Serial
    mfr = info.get("manufacturer_string") or data.get("device.mfr") or data.get("ups.mfr") or "PHOENIXTEC"
    prod = info.get("product_string") or data.get("device.model") or data.get("ups.model") or "Innova Unity Tower 3K"
    serial = info.get("serial_number") or data.get("device.serial") or data.get("ups.serial") or "CPLUR4709040011"

    data.setdefault("device.mfr", mfr)
    data.setdefault("device.model", prod)
    data.setdefault("device.serial", serial)
    data.setdefault("device.type", "ups")
    data.setdefault("ups.mfr", mfr)
    data.setdefault("ups.model", prod)
    data.setdefault("ups.serial", serial)
    data.setdefault("ups.type", "online")

    # 2. Driver Metadata (MGE HID / usbhid-ups compatible)
    data.setdefault("driver.name", "usbhid-ups")
    data.setdefault("driver.version", "2.7.4")
    data.setdefault("driver.version.data", "MGE HID 1.40")
    data.setdefault("driver.version.internal", "0.41")
    data.setdefault("driver.parameter.pollfreq", "30")
    data.setdefault("driver.parameter.pollinterval", "15")
    data.setdefault("driver.parameter.port", "auto")
    data.setdefault("driver.parameter.synchronous", "no")

    # 3. Battery Subsystem
    data.setdefault("battery.capacity", "0.00")
    data.setdefault("battery.charge.restart", 0)
    data.setdefault("battery.protection", "yes")
    data.setdefault("battery.type", "PbAc")
    data.setdefault("battery.runtime.low", 180)

    # Dynamically determine battery charger status if not already set
    if "battery.charger.status" not in data:
        status = str(data.get("ups.status", "")).upper()
        try:
            charge = float(data.get("battery.charge", 100) or 100)
        except (ValueError, TypeError):
            charge = 100.0

        if "OB" in status or "DISCHRG" in status:
            data["battery.charger.status"] = "discharging"
        elif "CHRG" in status or charge < 90:
            data["battery.charger.status"] = "charging"
        elif "OL" in status and charge >= 90:
            data["battery.charger.status"] = "floating"
        else:
            data["battery.charger.status"] = "resting"

    # 4. Input & Output Power Nominals
    data.setdefault("input.voltage.nominal", 220)
    data.setdefault("input.frequency.nominal", 50)
    data.setdefault("output.voltage.nominal", 220)
    data.setdefault("output.frequency.nominal", 50)
    data.setdefault("outlet.1.status", "on")

    # 5. UPS Nominal Power & Real Power
    if "ups.power.nominal" in data and "ups.realpower.nominal" not in data:
        data["ups.realpower.nominal"] = data["ups.power.nominal"]
    elif "ups.realpower.nominal" in data and "ups.power.nominal" not in data:
        data["ups.power.nominal"] = data["ups.realpower.nominal"]
    else:
        data.setdefault("ups.power.nominal", 2700)
        data.setdefault("ups.realpower.nominal", 2700)

    # 6. System Timers, Control & Dates
    data.setdefault("ups.delay.shutdown", 20)
    data.setdefault("ups.delay.start", 30)
    data.setdefault("ups.timer.shutdown", -1)
    data.setdefault("ups.timer.start", -1)
    data.setdefault("ups.test.result", "Done and passed")
    data.setdefault("ups.beeper.status", "enabled")
    data.setdefault("ups.date", datetime.datetime.now().strftime("%Y/%m/%d"))

    return data


def main():
    while True:
        client = None
        try:
            logging.info("Scanning for Enerex/Phoenixtec/Megatec UPS...")
            client = UPSClient.auto_detect()
            client.connect()

            info = client.device_info
            mfr = info.get("manufacturer_string", "PHOENIXTEC")
            prod = info.get("product_string", "Innova Unity Tower 3K")
            logging.info(f"Connected to UPS: Manufacturer='{mfr}', Product='{prod}'")

            # Clear old data in dummy-ups memory and reconnect upsd
            logging.info("Restarting nut-driver and nut-server to clear stale variables...")
            os.system("systemctl restart nut-driver && systemctl restart nut-server")
            time.sleep(2)

            # Polling loop for the connected UPS
            while True:
                try:
                    # 1. Read live UPS variables (existing logic preserved 100%)
                    data = client.get_vars()

                    # 2. Enrich with missing usbhid-ups compatible variables (existing values untouched)
                    data = enrich_nut_variables(data, info)

                    # 3. Write to temp file first to prevent NUT from reading an incomplete file
                    temp_file = DUMMY_FILE + ".tmp"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        for key, value in sorted(data.items()):
                            f.write(f"{key}: {value}\n")

                    # 4. Atomic replace
                    os.rename(temp_file, DUMMY_FILE)
                    os.chmod(DUMMY_FILE, 0o666)

                except Exception as e:
                    logging.error(f"Error reading UPS data (Device disconnected?): {e}")
                    # Tell dummy-ups the device is disconnected
                    temp_file = DUMMY_FILE + ".tmp"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write("ups.status: OFF\n")
                    os.rename(temp_file, DUMMY_FILE)
                    os.chmod(DUMMY_FILE, 0o666)

                    # Break the inner loop to reconnect/auto-detect again
                    break

                time.sleep(POLL_INTERVAL)

        except Exception as e:
            logging.warning(f"No UPS found or connect failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)
        finally:
            if client and getattr(client, "is_connected", False):
                try:
                    client.disconnect()
                except Exception:
                    pass
    logging.info("Exiting...")


if __name__ == "__main__":
    main()
