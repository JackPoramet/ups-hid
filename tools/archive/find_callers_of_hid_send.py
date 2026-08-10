import sys
from pathlib import Path
import pefile
from capstone import *
from capstone.x86 import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

text_sec = None
for s in pe.sections:
    if s.Name.decode('utf-8', errors='ignore').rstrip('\x00') == '.text':
        text_sec = s
        break

text_start_rva = text_sec.VirtualAddress
text_start_va = text_start_rva + image_base
text_bytes = data[text_sec.PointerToRawData : text_sec.PointerToRawData + text_sec.SizeOfRawData]

targets = [0x4043cc, 0x40486c, 0x404a0c, 0x404b80]

print("=== SEARCHING FOR CALLS TO HID WRAPPER FUNCTIONS ===")
for target_va in targets:
    print(f"\nSearching calls to 0x{target_va:x}:")
    for insn in md.disasm(text_bytes, text_start_va):
        if insn.mnemonic == 'call':
            for op in insn.operands:
                if op.type == X86_OP_IMM and op.imm == target_va:
                    print(f"  Call from 0x{insn.address:x}")

