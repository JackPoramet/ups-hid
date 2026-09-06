import sys
import os
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "linux"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "windows"))

from ups_module.client import UPSClient
from core_hid_ups import read_winpower_libusb_report_31

print("=== TESTING INNOVA UNITY BATTERY TEST (Report 0x24) ===")

client = UPSClient.auto_detect().connect()
info = client.get_device_info()
print(f"Device: {info.get('manufacturer')} {info.get('model')} (SN: {info.get('serial')})")

# 1. Read Vin via libusb0.dll (Mandatory rule for Phoenixtec in Windows)
vin, freq = read_winpower_libusb_report_31()
print(f"Initial Vin (Report 0x31 via libusb0.dll): {vin} V, Freq: {freq} Hz")

# 2. Read initial vars
v_init = client.get_vars()
print(f"Initial Status: {v_init.get('ups.status')}, Vbat: {v_init.get('battery.voltage')}V, Charge: {v_init.get('battery.charge')}%")

# 3. Trigger Battery Test via client.test_battery_quick() (Report 0x24 [0x01])
print("\nTriggering client.test_battery_quick()...")
success, msg = client.test_battery_quick()
print(f"Trigger result: success={success}, msg='{msg}'")

# 4. Monitor next 15 seconds
print("\nMonitoring status for 15 seconds:")
for i in range(1, 16):
    time.sleep(1)
    v = client.get_vars()
    print(f"  Sec +{i:2d}: Status={v.get('ups.status'):<15} | Vbat={v.get('battery.voltage')}V | Vout={v.get('output.voltage')}V | TestStatus={v.get('battery.test.status')}")

client.disconnect()
print("\nTest finished.")
