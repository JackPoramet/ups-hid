import sys
from pathlib import Path
import pefile
from capstone import *
from capstone.x86 import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

# Get IAT or function pointers in global data
# Let's inspect variables around 0x886500 where hid function pointers are stored
print("=== DYNAMIC FUNCTION POINTER TABLE AT 0x886500 ===")
# 0x886500 is RVA 0x486500 -> offset
rva_fp = 0x486500
off_fp = pe.get_offset_from_rva(rva_fp)

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

# Find function at 0x40486c (the HID init / DLL load function!)
print("\n=== DISASSEMBLING HID DLL LOAD FUNCTION 0x40486c ===")
start_va = 0x40486c
end_va = 0x404b00

start_rva = start_va - image_base
end_rva = end_va - image_base

start_off = pe.get_offset_from_rva(start_rva)
end_off = pe.get_offset_from_rva(end_rva)

code_bytes = data[start_off:end_off]

for insn in md.disasm(code_bytes, start_va):
    print(f"0x{insn.address:x}:  {insn.mnemonic}\t{insn.op_str}")

