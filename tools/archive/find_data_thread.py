import sys
from pathlib import Path
import pefile

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

# Search for "data_thread" or related Qt slot/signal signatures
import re
matches = re.finditer(b"data_thread[^\x00]*", data)
for m in matches:
    pos = m.start()
    rva = pe.get_rva_from_offset(pos)
    va = rva + image_base
    print(f"VA {hex(va)} (RVA {hex(rva)}): {m.group(0).decode('latin1', errors='ignore')}")

