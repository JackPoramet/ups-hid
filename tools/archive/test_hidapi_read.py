import sys
import time
import hid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== TESTING HIDAPI READ FOR MEC MEC0003 ===")

try:
    h = hid.device()
    h.open(0x0001, 0x0000)
    print("✅ Opened device via hidapi!")
    
    # Try non-blocking read
    h.set_nonblocking(1)
    
    print("\nReading packets via hid.read(64) for 3 seconds...")
    start = time.time()
    count = 0
    while time.time() - start < 3.0:
        data = h.read(64)
        if data:
            count += 1
            print(f"  [{count}] Packet: len={len(data)}, hex={bytes(data).hex()}, bytes={list(data)}")
        time.sleep(0.05)
        
    print(f"\nTotal packets read passively: {count}")
    
    # Now let's try sending Q1\r via hid.write or send_feature_report
    print("\n--- Sending 'Q1\\r' command via hid.write ---")
    for rep_id in [0, 1, 2, 3]:
        cmd_buf = bytes([rep_id]) + b"Q1\r" + b"\x00" * 12
        try:
            w_res = h.write(cmd_buf)
            print(f"  hid.write (rep_id={rep_id}): returned {w_res}")
            time.sleep(0.1)
            resp = h.read(64)
            if resp:
                print(f"  🎉 RESPONSE READ! len={len(resp)}, hex={bytes(resp).hex()}, str='{bytes(resp)}'")
        except Exception as e:
            print(f"  hid.write (rep_id={rep_id}) error: {e}")

    h.close()

except Exception as e:
    print(f"❌ Error: {e}")

