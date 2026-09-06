import sys
import os
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "linux"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "windows"))

from ups_module.client import UPSClient

client = UPSClient.auto_detect().connect()
print("Connected.")

print("\nTriggering quick test...")
client.test_battery_quick()
time.sleep(1)
v = client.get_vars()
print(f"Status during test: {v.get('ups.status')}, TestStatus: {v.get('battery.test.status')}")

print("\nSending abort command...")
success, msg = client.test_battery_stop()
print(f"Abort command: success={success}, msg='{msg}'")

for i in range(1, 6):
    time.sleep(1)
    v = client.get_vars()
    print(f"  +{i}s after abort: Status={v.get('ups.status'):<12} | TestStatus={v.get('battery.test.status'):<12} | Result={v.get('ups.test.result')}")

client.disconnect()
