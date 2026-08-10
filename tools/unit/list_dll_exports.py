#!/usr/bin/env python3
"""
tools/unit/list_dll_exports.py
Lists all exported C symbols from Winpower DLLs
"""
import struct
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def get_exports(dll_path):
    data = dll_path.read_bytes()
    # Parse PE header
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    optional_header_offset = pe_offset + 4 + 20
    magic = struct.unpack_from("<H", data, optional_header_offset)[0]
    
    if magic == 0x20B: # PE32+ (64-bit)
        export_rva_offset = optional_header_offset + 112
    else:
        export_rva_offset = optional_header_offset + 96
        
    export_rva, export_size = struct.unpack_from("<II", data, export_rva_offset)
    if export_rva == 0:
        return []
        
    # Translate RVA to File Offset
    num_sections = struct.unpack_from("<H", data, pe_offset + 6)[0]
    section_table_offset = optional_header_offset + (240 if magic == 0x20B else 224)
    
    def rva_to_offset(rva):
        for i in range(num_sections):
            sec = section_table_offset + i * 40
            v_addr, v_size, raw_ptr = struct.unpack_from("<III", data, sec + 12)
            if v_addr <= rva < v_addr + v_size:
                return raw_ptr + (rva - v_addr)
        return None

    exp_offset = rva_to_offset(export_rva)
    if not exp_offset:
        return []
        
    num_names = struct.unpack_from("<I", data, exp_offset + 24)[0]
    names_rva = struct.unpack_from("<I", data, exp_offset + 32)[0]
    names_offset = rva_to_offset(names_rva)
    
    exports = []
    for i in range(num_names):
        name_rva = struct.unpack_from("<I", data, names_offset + i * 4)[0]
        n_off = rva_to_offset(name_rva)
        if n_off:
            end = data.find(b'\x00', n_off)
            name = data[n_off:end].decode('ascii', errors='ignore')
            exports.append(name)
    return exports

for dll_file in [
    Path(r"C:\Program Files\WinpowerG2\jusb.dll"),
    Path(r"C:\Program Files\WinpowerG2\libUSB_Win.dll"),
    Path(r"C:\Program Files\WinpowerG2\libUSB_driver\amd64\libusb0.dll")
]:
    print(f"==============================================================================")
    print(f" 📦 PE Exports from {dll_file.name}")
    print("==============================================================================")
    if dll_file.exists():
        exps = get_exports(dll_file)
        for e in exps:
            print("  -", e)
