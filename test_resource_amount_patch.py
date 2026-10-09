from pathlib import Path
import struct
import unittest
import resource_amount_patch as patch


class ResourcePatchTests(unittest.TestCase):
    def test_guard_and_reversibility(self):
        source=Path(r'C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe').read_bytes()
        patched=patch.transform(source)
        self.assertEqual(patch.transform(patched),patched)
        self.assertEqual(patch.transform(patched,False),source)
        self.assertEqual(patched[:patch.OFFSET],source[:patch.OFFSET])
        self.assertEqual(patched[patch.OFFSET+len(patch.OLD):],source[patch.OFFSET+len(patch.OLD):])
        with self.assertRaises(ValueError):patch.transform(b'MZ'+bytes(len(source)))

    def test_actual_instructions_push_map_amount(self):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
        from unicorn.x86_const import UC_X86_REG_EBP,UC_X86_REG_ESP
        for amount in (1,3000,5000,12345,1000000):
            vm=Uc(UC_ARCH_X86,UC_MODE_32);vm.mem_map(0x1000,0x5000)
            vm.mem_write(0x1000,patch.NEW)
            vm.reg_write(UC_X86_REG_EBP,0x3000);vm.reg_write(UC_X86_REG_ESP,0x4000)
            vm.mem_write(0x3008,struct.pack('<I',0x2000))
            vm.mem_write(0x2010,struct.pack('<I',amount))
            vm.emu_start(0x1000,0x1000+len(patch.NEW))
            self.assertEqual(struct.unpack('<I',vm.mem_read(0x3ffc,4))[0],amount)


if __name__=='__main__':unittest.main()
