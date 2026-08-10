import re
import sys
from pathlib import Path

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
if not exe_path.exists():
    print(f"File not found: {exe_path}")
    sys.exit(1)

data = exe_path.read_bytes()
print(f"Loaded {len(data)} bytes from {exe_path}")

# Extract strings
ascii_strs = [s.decode("latin1") for s in re.findall(b"[\x20-\x7e]{4,}", data)]
unicode_strs = [s.decode("utf-16le", errors="ignore") for s in re.findall(b"(?:[\x20-\x7e]\x00){4,}", data)]

all_strs = ascii_strs + unicode_strs

print(f"Total ASCII strings: {len(ascii_strs)}")
print(f"Total Unicode strings: {len(unicode_strs)}")

# Search for interesting terms
search_terms = [
    "0001", "0000", "vid", "pid", "MEC", "Mega", "USB", "hid", "Q1",
    "hid.dll", "setupapi", "CreateFile", "WriteFile", "ReadFile",
    "SetFeature", "GetInputReport", "DeviceIoControl", "com", "tty",
    "serial", "baud", "Megatec", "Voltronic", "Phoenix"
]

for term in search_terms:
    matches = [s for s in all_strs if term.lower() in s.lower()]
    print(f"\n=== Keyword '{term}' ({len(matches)} matches) ===")
    # filter duplicates
    unique_matches = list(dict.fromkeys(matches))
    for m in unique_matches[:20]:
        print(f"  {m}")

