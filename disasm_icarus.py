import sys, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
EXE = r"C:\Program Files (x86)\TriggerSoft\RhakMu\iCARUS.dll"
pe = pefile.PE(EXE); ib = pe.OPTIONAL_HEADER.ImageBase
data = open(EXE, "rb").read()
def va_to_off(va):
    rva = va - ib
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise ValueError("VA not in section")
md = Cs(CS_ARCH_X86, CS_MODE_32)
for arg in sys.argv[1:]:
    p = arg.split(":"); va = int(p[0],16); n = int(p[1]) if len(p)>1 else 160
    off = va_to_off(va); code = data[off:off+n]
    print(f"\n== VA 0x{va:08X} off 0x{off:X} ==")
    for ins in md.disasm(code, va):
        print(f"0x{ins.address:08X}(+0x{ins.address-va:X}): {ins.mnemonic} {ins.op_str}")
