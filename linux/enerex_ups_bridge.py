#!/usr/bin/env python3
import time
import os
import sys
import logging

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

def main():
    while True:
        client = None
        try:
            logging.info("Scanning for Enerex/Phoenixtec/Megatec UPS...")
            client = UPSClient.auto_detect()
            client.connect()
            
            info = client.device_info
            mfr = info.get("manufacturer_string", "Enerex")
            prod = info.get("product_string", "UPS")
            logging.info(f"Connected to UPS: Manufacturer='{mfr}', Product='{prod}'")
            
            # Clear old data in dummy-ups memory and reconnect upsd
            logging.info("Restarting nut-driver and nut-server to clear stale variables...")
            os.system("systemctl restart nut-driver && systemctl restart nut-server")
            time.sleep(2)
            
            # Polling loop for the connected UPS
            while True:
                try:
                    # Read all UPS variables
                    data = client.get_vars()
                    
                    # Inject manufacturer and model from USB device info
                    data["device.mfr"] = mfr
                    data["device.model"] = prod
                    data["ups.mfr"] = mfr
                    data["ups.model"] = prod
                    
                    # Write to temp file first to prevent NUT from reading an incomplete file
                    temp_file = DUMMY_FILE + ".tmp"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        for key, value in data.items():
                            f.write(f"{key}: {value}\n")
                    
                    # Atomic replace
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
