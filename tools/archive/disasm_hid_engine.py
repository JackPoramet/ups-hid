import sys
from pathlib import Path
import pefile
from capstone import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

# Disassembler
md = Cs(CS_ARCH_X86, CS_MODE_32)

# Print printable ASCII strings in range RVA 0x240000 to 0x250000
start_rva = 0x238000
end_rva = 0x250000

start_offset = pe.get_offset_from_rva(start_rva)
end_offset = pe.get_offset_from_rva(end_rva)

print(f"Scanning RVA {hex(start_rva)} to {hex(end_rva)} (Offset {hex(start_offset)} to {hex(end_offset)})...")

sub_data = data[start_offset:end_offset]

import re
matches = re.finditer(b"[\x20-\x7e]{3,}", sub_data)
for m in matches:
    off = start_offset + m.start()
    rva = pe.get_rva_from_offset(off)
    va = rva + image_base
    print(f"VA {hex(va)} (RVA {hex(rva)} / Offset {hex(off)}): {m.group(0).decode('latin1')}")

