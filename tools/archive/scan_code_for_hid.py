import sys
from pathlib import Path
import pefile
from capstone import *
from capstone.x86 import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

# Get IAT addresses for key functions
imports = {}
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    dll_name = entry.dll.decode('utf-8', errors='ignore').lower()
    for imp in entry.imports:
        if imp.name:
            name = imp.name.decode('utf-8', errors='ignore')
            imports[imp.address] = f"{dll_name}!{name}"

# Setup Capstone
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

# Find text section
text_sec = None
for s in pe.sections:
    if s.Name.decode('utf-8', errors='ignore').rstrip('\x00') == '.text':
        text_sec = s
        break

text_start_rva = text_sec.VirtualAddress
text_start_va = text_start_rva + image_base
text_bytes = data[text_sec.PointerToRawData : text_sec.PointerToRawData + text_sec.SizeOfRawData]

print(f"Scanning .text section ({hex(text_start_va)} to {hex(text_start_va + len(text_bytes))})...")

# Scan for calls to IAT entries (call dword ptr [addr])
interesting_calls = []
for insn in md.disasm(text_bytes, text_start_va):
    if insn.mnemonic == 'call':
        for op in insn.operands:
            if op.type == X86_OP_MEM and op.mem.disp in imports:
                func_name = imports[op.mem.disp]
                if any(k in func_name.lower() for k in ['createfile', 'deviceiocontrol', 'readfile', 'writefile', 'setupdi']):
                    interesting_calls.append((insn.address, func_name))

print(f"Found {len(interesting_calls)} interesting API calls in code:")
for addr, fname in interesting_calls:
    print(f"  {hex(addr)}: call {fname}")

