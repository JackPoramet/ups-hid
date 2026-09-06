import sys
import os
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "linux"))

from ups_module.drivers.megatec import MegatecQ1Driver
from ups_module.core import open_ups_device

print("===========================================================================")
print(" 🔋 MEC0003 BATTERY TEST FULL LIFECYCLE TEST ON LIVE HARDWARE")
print("===========================================================================")

h, info = open_ups_device(0x0001, 0x0000)
if not h:
    print("❌ Failed to open MEC0003 device!")
    sys.exit(1)

driver = MegatecQ1Driver(h)

# 1. Baseline status
print("\n[Step 1] Baseline status before battery test:")
v = driver.get_vars()
print(f"  ups.status          : {v.get('ups.status')}")
print(f"  battery.test.status : {v.get('battery.test.status')}")
print(f"  ups.test.result     : {v.get('ups.test.result')}")
print(f"  battery.voltage     : {v.get('battery.voltage')} V")

# 2. Trigger quick battery test (Command 'T')
print("\n[Step 2] Triggering Quick Battery Test (Command 'T')...")
success, msg = driver.send_command("T")
print(f"  send_command('T') result: success={success}, msg='{msg}'")
if not success:
    print("❌ Battery test trigger failed!")
    h.close()
    sys.exit(1)

# 3. Verify immediately after trigger (Should be IN PROGRESS with CAL)
v = driver.get_vars()
print("\n[Step 3] Status immediately after trigger:")
print(f"  ups.status          : {v.get('ups.status')}")
print(f"  battery.test.status : {v.get('battery.test.status')}")
print(f"  ups.test.result     : {v.get('ups.test.result')}")
print(f"  ups.test.date       : {v.get('ups.test.date')}")
assert "CAL" in v.get("ups.status", "").split(), "Expected CAL in ups.status!"
assert v.get("battery.test.status") == "in progress", "Expected battery.test.status == 'in progress'!"

# 4. Monitor during test window (10 seconds)
print("\n[Step 4] Monitoring during 10-second test window:")
for sec in range(1, 12):
    time.sleep(1)
    v = driver.get_vars()
    print(f"  Time +{sec:2d}s -> Status: {v.get('ups.status'):<12} | Test: {v.get('battery.test.status'):<12} | Result: {v.get('ups.test.result')}")

# 5. Verify final status after completion
print("\n[Step 5] Final status after test completion:")
v = driver.get_vars()
print(f"  ups.status          : {v.get('ups.status')}")
print(f"  battery.test.status : {v.get('battery.test.status')}")
print(f"  ups.test.result     : {v.get('ups.test.result')}")
print(f"  ups.test.date       : {v.get('ups.test.date')}")
assert "CAL" not in v.get("ups.status", "").split(), "CAL should be cleared after test!"
assert v.get("battery.test.status") == "passed", "Expected battery.test.status == 'passed'!"
assert v.get("ups.test.result") == "Done and passed", "Expected ups.test.result == 'Done and passed'!"

# 6. Test Abort command (Command 'CT')
print("\n[Step 6] Testing Abort Command (Command 'CT')...")
driver.send_command("T")
time.sleep(1)
abort_success, abort_msg = driver.send_command("CT")
print(f"  send_command('CT') result: success={abort_success}, msg='{abort_msg}'")
v = driver.get_vars()
print(f"  ups.status          : {v.get('ups.status')}")
print(f"  battery.test.status : {v.get('battery.test.status')}")
print(f"  ups.test.result     : {v.get('ups.test.result')}")
assert v.get("battery.test.status") == "aborted", "Expected battery.test.status == 'aborted'!"

h.close()
print("\n===========================================================================")
print(" 🎉 ALL MEC0003 BATTERY TEST LIFECYCLE CHECKS PASSED SUCCESSFULLY!")
print("===========================================================================")
