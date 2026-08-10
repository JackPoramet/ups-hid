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

# Find references to a given 32-bit address (e.g. 0x88b17c) in .text section
text_sec = None
for s in pe.sections:
    if s.Name.decode('utf-8', errors='ignore').rstrip('\x00') == '.text':
        text_sec = s
        break

text_start_rva = text_sec.VirtualAddress
text_start_va = text_start_rva + image_base
text_bytes = data[text_sec.PointerToRawData : text_sec.PointerToRawData + text_sec.SizeOfRawData]

print(f".text section: VA={hex(text_start_va)}, Size={hex(len(text_bytes))}")

def find_refs(target_va):
    # Target address as 4-byte little endian
    target_bytes = target_va.to_bytes(4, byteorder='little')
    refs = []
    idx = 0
    while True:
        pos = text_bytes.find(target_bytes, idx)
        if pos == -1:
            break
        code_rva = text_start_rva + pos
        code_va = code_rva + image_base
        refs.append((pos, code_rva, code_va))
        idx = pos + 1
    return refs

# Let's test searching for references to string 0x88b17c ("hid_get_megatec_string")
str_va = 0x88b17c
refs = find_refs(str_va)
print(f"References to {hex(str_va)} ('hid_get_megatec_string'): {len(refs)}")
for pos, rva, va in refs:
    print(f"  Ref at VA {hex(va)}")
    # Disassemble -20 bytes to +40 bytes
    start_pos = max(0, pos - 30)
    end_pos = min(len(text_bytes), pos + 40)
    snippet = text_bytes[start_pos:end_pos]
    base_addr = text_start_va + start_pos
    print("--- Disassembly ---")
    for insn in md.disasm(snippet, base_addr):
        marker = "===> " if insn.address <= va <= insn.address + insn.size else "     "
        print(f"{marker}{hex(insn.address)}: {insn.mnemonic} {insn.op_str}")

