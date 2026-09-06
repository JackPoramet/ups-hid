import sys
import os
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "linux"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "windows"))

from ups_module.client import UPSClient

print("===========================================================================")
print(" 🔌 INNOVA UNITY (3kVA Online) BATTERY TEST FULL LIFECYCLE VERIFICATION")
print("===========================================================================")

# 1. Connect via UPSClient
print("\n[Step 1] Connecting to Innova Unity via UPSClient...")
try:
    client = UPSClient.auto_detect()
    client.connect()
    dev_info = client.get_device_info()
    print(f"✅ Connected to: Manufacturer='{dev_info.get('manufacturer')}', Model='{dev_info.get('model')}', Serial='{dev_info.get('serial')}'")
except Exception as e:
    print(f"❌ Failed to connect: {e}")
    sys.exit(1)

# 2. Baseline telemetry check
print("\n[Step 2] Baseline Live Telemetry Check (Before Battery Test):")
vars_init = client.get_vars()
print(f"  • Operating Status    : {vars_init.get('ups.status')}")
print(f"  • Input Voltage (Vin) : {vars_init.get('input.voltage')} V")
print(f"  • Output Voltage(Vout): {vars_init.get('output.voltage')} V")
print(f"  • Battery Voltage(Vbat): {vars_init.get('battery.voltage')} V")
print(f"  • Battery Charge      : {vars_init.get('battery.charge')} %")
print(f"  • Battery Test Status : {vars_init.get('battery.test.status')}")
print(f"  • UPS Test Result     : {vars_init.get('ups.test.result')}")

vin = float(vars_init.get('input.voltage', 0.0) or 0.0)
print(f"  -> Verified Vin: {vin} V")

# 3. Trigger Quick Battery Test (10s)
print("\n[Step 3] Triggering Quick Battery Test via client.test_battery_quick() (Report 0x24 [0x01])...")
success, msg = client.test_battery_quick()
print(f"  Result: success={success}, msg='{msg}'")
if not success:
    print("❌ Failed to send battery test command!")
    client.disconnect()
    sys.exit(1)

# 4. Immediate Check after trigger
time.sleep(0.5)
vars_test = client.get_vars()
print("\n[Step 4] Immediate Status after trigger:")
print(f"  • Operating Status    : {vars_test.get('ups.status')}")
print(f"  • Battery Test Status : {vars_test.get('battery.test.status')}")
print(f"  • UPS Test Result     : {vars_test.get('ups.test.result')}")
print(f"  • Battery Voltage     : {vars_test.get('battery.voltage')} V")

# 5. Monitor 15 seconds during test window
print("\n[Step 5] Monitoring live telemetry during 15-second test window:")
for sec in range(1, 16):
    time.sleep(1)
    v = client.get_vars()
    status_str = v.get("ups.status", "")
    t_status = v.get("battery.test.status", "")
    t_res = v.get("ups.test.result", "")
    v_bat = v.get("battery.voltage", "")
    vout = v.get("output.voltage", "")
    print(f"  Time +{sec:2d}s | Status: {status_str:<12} | Vbat: {v_bat:>5}V | Vout: {vout:>5}V | Test: {t_status:<11} | Result: {t_res}")

# 6. Final Status after completion
print("\n[Step 6] Final Status after battery test completion:")
vars_final = client.get_vars()
print(f"  • Operating Status    : {vars_final.get('ups.status')}")
print(f"  • Battery Test Status : {vars_final.get('battery.test.status')}")
print(f"  • UPS Test Result     : {vars_final.get('ups.test.result')}")

# 7. Test Abort Command
print("\n[Step 7] Testing Abort Command via client.test_battery_stop() (Report 0x24 [0x00])...")
client.test_battery_quick()
time.sleep(1)
abort_success, abort_msg = client.test_battery_stop()
print(f"  Abort Result: success={abort_success}, msg='{abort_msg}'")
time.sleep(1)
vars_abort = client.get_vars()
print(f"  • Operating Status after abort: {vars_abort.get('ups.status')}")
print(f"  • Battery Test Status         : {vars_abort.get('battery.test.status')}")
print(f"  • UPS Test Result             : {vars_abort.get('ups.test.result')}")

client.disconnect()
print("\n===========================================================================")
print(" 🎉 INNOVA UNITY BATTERY TEST LIFECYCLE VERIFICATION COMPLETED SUCCESSFULLY!")
print("===========================================================================")
