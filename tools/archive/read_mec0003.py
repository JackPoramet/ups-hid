#!/usr/bin/env python3
"""
tools/read_mec0003.py
~~~~~~~~~~~~~~~~~~~~~
MEC MEC0003 (VID=0x0001, PID=0x0000) USB HID UPS Data Reader.
Reverse-engineered from UPSmart-II (Mega(USB) driver).

Usage:
    python tools/read_mec0003.py
"""

import sys
import time
import pywinusb.hid as pyhid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def read_mec_ups():
    print("=" * 70)
    print(" 🔌 MEC MEC0003 (VID=0x0001 PID=0x0000) UPS Reader")
    print(" Reverse-engineered from UPSmart (IDBK Mega(USB) Engine)")
    print("=" * 70)

    devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
    if not devices:
        print("\n❌ Device MEC0003 (VID=0x0001, PID=0x0000) not found.")
        print("   Make sure UPSmart is closed and UPS USB cable is connected.")
        return

    dev = devices[0]
    dev.open()

    print(f"\n✅ Device Connected: {dev.product_name}")
    print(f"   Path: {dev.device_path}")

    # Inspect Report Items
    print("\n--- Current UPS Telemetry Data ---")
    
    metrics = {}
    
    for r in dev.find_feature_reports() + dev.find_input_reports():
        try:
            r.get() # refresh report data
        except Exception:
            pass
        
        for key, item in r.items():
            val = item.get_value()
            page_id = item.page_id
            usage_id = item.usage_id
            
            # Map Power Device Usages (Page 0x84)
            if page_id == 0x84:
                if usage_id == 0x0030: # Voltage
                    metrics["Voltage"] = val
                elif usage_id == 0x0032: # Frequency
                    metrics["Frequency"] = val
                elif usage_id == 0x0035: # Percent Load
                    metrics["Load_Percent"] = val
                elif usage_id == 0x0017: # Config Voltage / Battery Voltage
                    metrics["Battery_Voltage"] = val
                elif usage_id == 0x0061: # Good / Normal
                    metrics["UPS_Normal"] = bool(val)
                elif usage_id == 0x006E: # Utility Normal
                    metrics["Utility_Normal"] = bool(val)
                elif usage_id == 0x0065: # Shutdown Active
                    metrics["Shutdown_Active"] = bool(val)
                elif usage_id == 0x006F: # Overload
                    metrics["Overload"] = bool(val)
                elif usage_id == 0x0058: # Battery Low
                    metrics["Battery_Low"] = bool(val)

    print(f"  Input Voltage     : {metrics.get('Voltage', 'N/A')} V")
    print(f"  Output Voltage    : {metrics.get('Voltage', 'N/A')} V")
    print(f"  Line Frequency    : {metrics.get('Frequency', 'N/A')} Hz")
    print(f"  Battery Voltage   : {metrics.get('Battery_Voltage', 'N/A')} V")
    print(f"  Load Level        : {metrics.get('Load_Percent', 'N/A')} %")
    print(f"  Utility Normal    : {'Yes' if metrics.get('Utility_Normal') else 'No'}")
    print(f"  UPS Status Normal : {'Yes' if metrics.get('UPS_Normal') else 'No'}")
    print(f"  Battery Low       : {'Yes' if metrics.get('Battery_Low') else 'No'}")
    print(f"  Overload Alarm    : {'Yes' if metrics.get('Overload') else 'No'}")
    print(f"  Shutdown Active   : {'Yes' if metrics.get('Shutdown_Active') else 'No'}")
    print("=" * 70)

    dev.close()

if __name__ == "__main__":
    read_mec_ups()

