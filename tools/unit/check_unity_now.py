import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "linux"))
from ups_module.client import UPSClient

c = UPSClient.auto_detect().connect()
v = c.get_vars()
print("Current Status:")
print(f"  • Operating Status    : {v.get('ups.status')}")
print(f"  • Battery Test Status : {v.get('battery.test.status')}")
print(f"  • UPS Test Result     : {v.get('ups.test.result')}")
print(f"  • Battery Voltage     : {v.get('battery.voltage')} V")
print(f"  • Input Voltage (Vin) : {v.get('input.voltage')} V")
print(f"  • Output Voltage(Vout): {v.get('output.voltage')} V")
c.disconnect()
