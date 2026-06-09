import sys, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
F = r"C:\Program Files (x86)\TriggerSoft\RhakMu\handes.dll"
pe = pefile.PE(F); ib = pe.OPTIONAL_HEADER.ImageBase
data = open(F, "rb").read()
print("ENTRY RVA 0x%X" % pe.OPTIONAL_HEADER.AddressOfEntryPoint)
def v2o(va):
    rva = va - ib
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
md = Cs(CS_ARCH_X86, CS_MODE_32)
for arg in sys.argv[1:]:
    p=arg.split(":"); va=int(p[0],16); n=int(p[1]) if len(p)>1 else 120
    off=v2o(va); code=data[off:off+n]
    print(f"\n== VA 0x{va:08X} off 0x{off:X} ==")
    for ins in md.disasm(code, va):
        print(f"0x{ins.address:08X}(+0x{ins.address-va:X}): {ins.mnemonic} {ins.op_str}")
