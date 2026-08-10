import sys
import time
import hid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== TESTING MEC MEC0003 (VID=0x0001 PID=0x0000) PROTOCOL ===")

# 1. Try HIDAPI open
try:
    h = hid.device()
    h.open(0x0001, 0x0000)
    print("SUCCESS: Successfully opened device via hidapi!")
    print(f"Manufacturer: {h.get_manufacturer_string()}")
    print(f"Product: {h.get_product_string()}")
    print(f"Serial: {h.get_serial_number_string()}")
    
    commands = [b"Q1\r", b"Q1", b"I\r", b"F\r"]
    
    # Test Feature Reports
    print("\n--- Testing Feature Reports (send_feature_report / get_feature_report) ---")
    for cmd in commands:
        for rep_id in [0, 1, 2]:
            buf = bytearray([rep_id]) + cmd
            buf_padded = buf.ljust(9, b'\x00')
            try:
                res = h.send_feature_report(bytes(buf_padded))
                print(f"  send_feature_report (rep_id={rep_id}, cmd={cmd}): sent {res} bytes")
                time.sleep(0.1)
                
                resp = h.get_feature_report(rep_id, 65)
                if resp:
                    resp_bytes = bytes(resp)
                    print(f"  get_feature_report (rep_id={rep_id}): hex={resp_bytes.hex()} str='{resp_bytes}'")
            except Exception as e:
                print(f"  send/get_feature_report (rep_id={rep_id}, cmd={cmd}) error: {e}")

    # Test hid.write / hid.read (Interrupt Reports)
    print("\n--- Testing Write / Read (hid.write / read) ---")
    for cmd in commands:
        for rep_id in [0, 1]:
            buf = bytearray([rep_id]) + cmd if rep_id != 0 else cmd
            buf_padded = buf.ljust(8, b'\x00')
            try:
                res = h.write(bytes(buf_padded))
                print(f"  hid.write (rep_id={rep_id}, cmd={cmd}): wrote {res} bytes")
                time.sleep(0.1)
                resp = h.read(64, timeout_ms=500)
                if resp:
                    resp_bytes = bytes(resp)
                    print(f"  hid.read: hex={resp_bytes.hex()} str='{resp_bytes}'")
            except Exception as e:
                print(f"  hid.write (rep_id={rep_id}, cmd={cmd}) error: {e}")

    h.close()

except Exception as e:
    print(f"ERROR: Failed to open via hidapi: {e}")

