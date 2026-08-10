import sys
from pathlib import Path
import pefile
from capstone import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

# Search for references to "Mega(USB)" string
rva_str = 0x241dfe  # VA 0x641dfe
va_str = rva_str + image_base

print(f"Searching references to VA {hex(va_str)} ('Mega(USB)')...")

md = Cs(CS_ARCH_X86, CS_MODE_32)

text_sec = pe.sections[0]
text_start_rva = text_sec.VirtualAddress
text_start_va = text_start_rva + image_base
text_bytes = data[text_sec.PointerToRawData : text_sec.PointerToRawData + text_sec.SizeOfRawData]

va_bytes = va_str.to_bytes(4, 'little')
idx = 0
while True:
    pos = text_bytes.find(va_bytes, idx)
    if pos == -1:
        break
    code_va = text_start_va + pos
    print(f"  Reference at VA {hex(code_va)}")
    # Disassemble 30 bytes before and 40 bytes after
    start_p = max(0, pos - 30)
    end_p = min(len(text_bytes), pos + 40)
    snippet = text_bytes[start_p:end_p]
    base_addr = text_start_va + start_p
    for insn in md.disasm(snippet, base_addr):
        marker = "===> " if insn.address <= code_va <= insn.address + insn.size else "     "
        print(f"{marker}0x{insn.address:x}: {insn.mnemonic}\t{insn.op_str}")
    idx = pos + 1

