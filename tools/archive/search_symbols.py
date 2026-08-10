import sys
from pathlib import Path
import re

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
data = exe_path.read_bytes()

# MinGW symbol pattern: _Z...
symbols = re.findall(b"_Z[A-Za-z0-9_]+", data)
print(f"Total MinGW mangled symbols found: {len(symbols)}")

interesting = []
for s in set(symbols):
    s_str = s.decode('latin1', errors='ignore')
    if any(k in s_str.lower() for k in ['thread', 'hid', 'usb', 'serial', 'read', 'write', 'open', 'close', 'send', 'recv', 'mega', 'poll', 'data']):
        interesting.append(s_str)

print(f"Interesting symbols ({len(interesting)}):")
for s in sorted(interesting)[:50]:
    print(f"  {s}")

