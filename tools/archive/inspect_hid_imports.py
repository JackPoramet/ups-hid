import sys
from pathlib import Path
import pefile
from capstone import *
from capstone.x86 import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

# Setup Capstone for 32-bit x86
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

# Find import table entries or string references
def search_string(target):
    idx = 0
    results = []
    while True:
        pos = data.find(target, idx)
        if pos == -1:
            break
        rva = pe.get_rva_from_offset(pos)
        va = rva + image_base
        results.append((pos, rva, va))
        idx = pos + 1
    return results

print("=== SEARCH RESULTS FOR HID STRINGS AND FUNCTIONS ===")

# Search for hid_get_megatec_string
for pos, rva, va in search_string(b"hid_get_megatec_string"):
    print(f"hid_get_megatec_string string at VA {hex(va)}, RVA {hex(rva)}")

# Search for imports of hid.dll functions
print("\n=== IMPORTS ===")
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    dll_name = entry.dll.decode('utf-8', errors='ignore')
    if 'hid' in dll_name.lower() or 'setup' in dll_name.lower() or 'kernel' in dll_name.lower():
        print(f"DLL: {dll_name}")
        for imp in entry.imports:
            if imp.name:
                name = imp.name.decode('utf-8', errors='ignore')
                if any(k in name.lower() for k in ['hid', 'file', 'read', 'write', 'device']):
                    print(f"  {name} at IAT {hex(imp.address)}")

