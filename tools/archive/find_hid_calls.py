import sys
from pathlib import Path
import pefile
from capstone import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

md = Cs(CS_ARCH_X86, CS_MODE_32)

text_sec = None
for s in pe.sections:
    if s.Name.decode('utf-8', errors='ignore').rstrip('\x00') == '.text':
        text_sec = s
        break

text_start_rva = text_sec.VirtualAddress
text_start_va = text_start_rva + image_base
text_bytes = data[text_sec.PointerToRawData : text_sec.PointerToRawData + text_sec.SizeOfRawData]

fp_table = {
    0x886540: "HidD_GetAttributes",
    0x886560: "HidD_SetFeature",
    0x886590: "HidD_GetFeature",
    0x8865b0: "HidD_GetPreparsedData",
    0x8865d0: "HidP_GetCaps"
}

print("=== SEARCHING FOR HID API CALLS IN CODE ===")
for addr, name in fp_table.items():
    addr_bytes = addr.to_bytes(4, 'little')
    print(f"\nSearching calls/references to {name} (0x{addr:x}):")
    idx = 0
    while True:
        pos = text_bytes.find(addr_bytes, idx)
        if pos == -1:
            break
        code_va = text_start_va + pos
        print(f"  Reference at VA {hex(code_va)}")
        # Disassemble around this address
        start_p = max(0, pos - 25)
        end_p = min(len(text_bytes), pos + 35)
        snippet = text_bytes[start_p:end_p]
        base_addr = text_start_va + start_p
        for insn in md.disasm(snippet, base_addr):
            marker = "===> " if insn.address <= code_va <= insn.address + insn.size else "     "
            print(f"{marker}0x{insn.address:x}: {insn.mnemonic}\t{insn.op_str}")
        idx = pos + 1

