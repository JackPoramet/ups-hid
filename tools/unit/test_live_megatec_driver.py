import sys
import os
import time
import datetime

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add linux path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "linux"))

from ups_module.drivers.megatec import MegatecQ1Driver
from ups_module.core import open_ups_device

print("=== LIVE TEST OF MEGATEC DRIVER WITH MEC0003 HARDWARE ===")

# Open live hardware MEC0003 (VID 0x0001, PID 0x0000)
h, info = open_ups_device(0x0001, 0x0000)
if not h:
    print("❌ Failed to open MEC0003 device!")
    sys.exit(1)

print(f"✅ Device opened successfully: {info}")

driver = MegatecQ1Driver(h)

# 1. Read initial vars
print("\n--- 1. Reading Initial Live Telemetry ---")
vars_init = driver.get_vars()
for k, v in sorted(vars_init.items()):
    print(f"  {k}: {v}")

h.close()
print("\nDevice closed successfully.")
