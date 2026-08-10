import sys
from pathlib import Path
import pefile
from capstone import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

# Function to search strings in entire file and find pointers or instructions
def search_all_str(s_bytes):
    matches = []
    idx = 0
    while True:
        pos = data.find(s_bytes, idx)
        if pos == -1:
            break
        try:
            rva = pe.get_rva_from_offset(pos)
            va = rva + image_base
            matches.append((pos, rva, va))
        except Exception:
            pass
        idx = pos + 1
    return matches

print("=== STRINGS OF INTEREST ===")
terms = [
    b"hid_get_megatec_string",
    b"hid.dll",
    b"HidD_SetFeature",
    b"HidD_GetFeature",
    b"HidD_GetAttributes",
    b"HidD_GetPreparsedData",
    b"Mega(USB)",
    b"Single-phase UPS(USB)",
    b"Port:Mega(USB)",
    b"Q1\r",
    b"Q1",
    b"^P005MEC",
    b"MEC",
    b"0001",
    b"0000",
    b"VID_",
    b"PID_"
]

for t in terms:
    res = search_all_str(t)
    print(f"Term '{t.decode('latin1', errors='ignore')}': {len(res)} matches")
    for pos, rva, va in res[:5]:
        print(f"  File Pos: {hex(pos)}, RVA: {hex(rva)}, VA: {hex(va)}")

