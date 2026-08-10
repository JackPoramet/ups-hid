import sys
from pathlib import Path
import pefile
from capstone import *

exe_path = Path(r"C:\Program Files (x86)\IDBK\UPSmart\UPSmart.exe")
pe = pefile.PE(str(exe_path))
image_base = pe.OPTIONAL_HEADER.ImageBase
data = exe_path.read_bytes()

md = Cs(CS_ARCH_X86, CS_MODE_32)

start_off = pe.get_offset_from_rva(0x40a000 - image_base)
end_off = pe.get_offset_from_rva(0x40c500 - image_base)
sub = data[start_off:end_off]

prologues = []
idx = 0
while True:
    pos = sub.find(b"\x55\x89\xe5", idx)
    if pos == -1:
        break
    va = 0x40a000 + pos
    prologues.append(va)
    idx = pos + 1

target_fn_va = [v for v in prologues if v <= 0x40c2f4][-1]
print(f"Disassembling from function entry {hex(target_fn_va)} to 0x40c400:")

fn_off = pe.get_offset_from_rva(target_fn_va - image_base)
fn_bytes = data[fn_off : fn_off + (0x40c400 - target_fn_va)]

for insn in md.disasm(fn_bytes, target_fn_va):
    print(f"0x{insn.address:x}:  {insn.mnemonic}\t{insn.op_str}")

