import sys
from pathlib import Path
import pefile
from capstone import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))

print(f"Machine: {hex(pe.FILE_HEADER.Machine)}")
print(f"ImageBase: {hex(pe.OPTIONAL_HEADER.ImageBase)}")
print(f"Entrypoint: {hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint)}")

# Find sections
code_section = None
for section in pe.sections:
    name = section.Name.decode('utf-8', errors='ignore').rstrip('\x00')
    print(f"Section {name}: VirtualAddress={hex(section.VirtualAddress)}, Size={hex(section.SizeOfRawData)}")
    if name == '.text':
        code_section = section

image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

# Function to search byte patterns or string references
def find_string_rvas(string_bytes):
    rvas = []
    idx = 0
    while True:
        pos = data.find(string_bytes, idx)
        if pos == -1:
            break
        # Convert offset to VA
        va = pe.get_rva_from_offset(pos) + image_base
        rvas.append((pos, va))
        idx = pos + 1
    return rvas

# Let's search for "hid_get_megatec_string" or other strings
target_strs = [
    b"hid_get_megatec_string",
    b"Mega(USB)",
    b"Single-phase UPS(USB)",
    b"Communication protocols",
    b"Q1\r",
    b"Q1",
    b"Q",
    b"I\r",
    b"F\r",
    b"M\r"
]

for ts in target_strs:
    matches = find_string_rvas(ts)
    print(f"\nString {ts} found at:")
    for offset, va in matches:
        print(f"  File offset: {hex(offset)}, VA: {hex(va)}")

