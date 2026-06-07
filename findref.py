import sys, pefile, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

EXE = r"C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe"
pe = pefile.PE(EXE)
image_base = pe.OPTIONAL_HEADER.ImageBase
data = open(EXE, "rb").read()

# Find the .text section file range and its VA
text = None
for s in pe.sections:
    if s.Name.startswith(b".text"):
        text = s
text_start_off = text.PointerToRawData
text_end_off = text.PointerToRawData + text.SizeOfRawData
text_va = image_base + text.VirtualAddress

def off_to_va(off):
    return text_va + (off - text_start_off)

targets = [int(x, 16) for x in sys.argv[1:]]
tset = set(targets)

# Scan .text for 4-byte little-endian immediates matching targets
seg = data[text_start_off:text_end_off]
for i in range(len(seg) - 4):
    val = struct.unpack_from("<I", seg, i)[0]
    if val in tset:
        va = off_to_va(text_start_off + i)
        print(f"ref to 0x{val:08X} at VA~0x{va:08X} (operand bytes at file 0x{text_start_off+i:X})")
