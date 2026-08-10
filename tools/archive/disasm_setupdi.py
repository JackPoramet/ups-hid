import sys
from pathlib import Path
import pefile
from capstone import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

md = Cs(CS_ARCH_X86, CS_MODE_32)

start_va = 0x404b80
end_va = 0x404df0

start_rva = start_va - image_base
end_rva = end_va - image_base

start_off = pe.get_offset_from_rva(start_rva)
end_off = pe.get_offset_from_rva(end_rva)

code_bytes = data[start_off:end_off]

print(f"=== Disassembling SetupDi Loop ({hex(start_va)} to {hex(end_va)}) ===")
for insn in md.disasm(code_bytes, start_va):
    print(f"0x{insn.address:x}:  {insn.mnemonic}\t{insn.op_str}")

