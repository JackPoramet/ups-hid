import sys
import os
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "linux"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "windows"))

from ups_module.client import UPSClient

client = UPSClient.auto_detect()
client.connect()
print(f"Connected: {client.get_device_info()}")
res = client.test_battery_quick()
print(f"Trigger Quick Test: {res}")

for i in range(1, 15):
    time.sleep(1)
    v = client.get_vars()
    st = v.get("ups.status")
    tst = v.get("battery.test.status")
    tres = v.get("ups.test.result")
    vout = v.get("output.voltage")
    vbat = v.get("battery.voltage")
    print(f"+{i:2d}s | status: {st:<10} | test: {tst:<12} | result: {tres:<16} | Vout: {vout}V | Vbat: {vbat}V")

client.disconnect()
