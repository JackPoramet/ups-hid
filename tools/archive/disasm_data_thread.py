import sys
from pathlib import Path
import pefile
from capstone import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

md = Cs(CS_ARCH_X86, CS_MODE_32)

# Search for virtual table / vtable or string references to "data_thread"
# Let's search for string "11data_thread" or "data_thread"
pos = data.find(b"11data_thread")
if pos != -1:
    rva = pe.get_rva_from_offset(pos)
    va = rva + image_base
    print(f"Found '11data_thread' at VA {hex(va)}")

# Search for references to RVA 0x24fe68 ("data_thread")
str_va = 0x64fe68
print(f"Searching references to 0x{str_va:x} ('data_thread')...")

idx = 0
while True:
    pos = data.find(str_va.to_bytes(4, 'little'), idx)
    if pos == -1:
        break
    rva = pe.get_rva_from_offset(pos)
    va = rva + image_base
    print(f"  Ref at VA {hex(va)} (RVA {hex(rva)})")
    idx = pos + 1

