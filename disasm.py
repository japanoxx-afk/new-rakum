import sys, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

EXE = r"C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe"
pe = pefile.PE(EXE)
image_base = pe.OPTIONAL_HEADER.ImageBase
data = open(EXE, "rb").read()

def va_to_off(va):
    rva = va - image_base
    for s in pe.sections:
        start = s.VirtualAddress
        size = max(s.Misc_VirtualSize, s.SizeOfRawData)
        if start <= rva < start + size:
            return s.PointerToRawData + (rva - start)
    raise ValueError("VA not in section")

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = False

def disasm(va, length=160, label=""):
    off = va_to_off(va)
    code = data[off:off+length]
    print(f"\n===== {label} VA=0x{va:08X} off=0x{off:X} =====")
    for ins in md.disasm(code, va):
        print(f"0x{ins.address:08X}: {ins.mnemonic:8s} {ins.op_str}")

if __name__ == "__main__":
    for arg in sys.argv[1:]:
        parts = arg.split(":")
        va = int(parts[0], 16)
        length = int(parts[1]) if len(parts) > 1 else 160
        label = parts[2] if len(parts) > 2 else ""
        disasm(va, length, label)
