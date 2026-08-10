import sys
from pathlib import Path
import pefile
from capstone import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

# Search for sscanf, atof, QString::toDouble, QString::split, or string parsing routines
# Let's search for strings like "%f", "(%f", "%d", "%s" or parsing patterns
import re
ascii_strs = [m.group(0) for m in re.finditer(b"[\x20-\x7e]{3,}", data)]

print("=== PARSING & FORMATTING STRINGS IN UPSMART.EXE ===")
for s in ascii_strs:
    s_str = s.decode('latin1', errors='ignore')
    if any(k in s_str for k in ['%f', '%d', '232', '50.', '13.', 'Q1', '(', 'Hz', 'V', '%']):
        if len(s_str) < 80:
            print(f"  {s_str}")

