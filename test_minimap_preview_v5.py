import struct
import unittest
from unicorn.x86_const import UC_X86_REG_EBP
from test_minimap_preview_v2 import TrialTests, SOURCE
import viewport_patch
import minimap_preview_v5 as p
import minimap_preview_v4 as v4

class WorldResourceTests(unittest.TestCase):
    def test_restore_supported_resolutions(self):
        for high in (False,True):
            source=viewport_patch.transform(SOURCE.read_bytes(),high)
            self.assertEqual(p.restore(p.build(source)),source)

    def test_only_live_gold_and_water_forced_and_no_duplicate(self):
        for kind,amount,expected in [(0x53,100,True),(0x53,0,False),(0x63,0,True),(0x43,500,False),(0x11,500,False)]:
            data=p.build(SOURCE.read_bytes());vm=TrialTests().vm(data)
            vm.mem_write(v4.CODE,data[v4.RAW:v4.RAW+0x2000])
            ebp=0x30007000;vm.reg_write(UC_X86_REG_EBP,ebp)
            vm.mem_write(ebp-8,struct.pack('<hh',20,0))
            vm.mem_write(ebp-4,struct.pack('<h',20))
            vm.mem_write(0xfe5e0a+20*0x410+40,struct.pack('<H',1))
            vm.mem_write(0x915d50+20*520+20,b'\x0f')
            record=bytearray(32);record[0x12]=kind
            struct.pack_into('<i',record,0x1c,amount)
            addr=0x766970+32;vm.mem_write(addr,bytes(record))
            # Head 0 specifically tests duplicate prevention for the first resource.
            vm.emu_start(p.ENTRY,0x43e61b,count=1000)
            head=struct.unpack('<H',vm.mem_read(0xb41168,2))[0]
            self.assertEqual(head,1 if expected else 0)
            self.assertEqual(bytes(vm.mem_read(addr+0x10,16)),bytes(record[0x10:]))
            vm.emu_start(p.ENTRY,0x43e61b,count=1000)
            self.assertEqual(struct.unpack('<H',vm.mem_read(addr+0xe,2))[0],0)
            self.assertEqual(bytes(vm.mem_read(0x999dd0,520*520)),b'\0'*(520*520))

if __name__=='__main__':unittest.main()
