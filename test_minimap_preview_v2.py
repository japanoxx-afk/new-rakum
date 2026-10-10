import struct
import unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP
import minimap_preview_v2 as p
import viewport_patch

SOURCE=Path(__file__).parent/'research/runtime/viewport-1280-ui-v5/Rhakmu.exe.original'

@unittest.skipUnless(SOURCE.exists(),'Reference unavailable')
class TrialTests(unittest.TestCase):
    def vm(self,data):
        vm=Uc(UC_ARCH_X86,UC_MODE_32)
        vm.mem_map(0x400000,0xd00000)
        vm.mem_map(0x20000000,0x40000)
        vm.mem_map(0x30000000,0x10000)
        vm.mem_write(p.CODE,data[p.RAW:p.RAW+0x1000])
        vm.reg_write(UC_X86_REG_ESP,0x30008000)
        return vm

    def test_both_resolutions_restore_and_unknown_rejection(self):
        for high in (False,True):
            source=viewport_patch.transform(SOURCE.read_bytes(),high)
            data=p.build(source)
            self.assertEqual(p.restore(data),source)
            damaged=bytearray(data);damaged[p.RAW+0x110]^=1
            with self.assertRaises(ValueError):p.restore(damaged)
            damaged=bytearray(source);damaged[0x1000]^=1
            with self.assertRaises(ValueError):p.build(damaged)

    def test_resources_classification_depletion_and_private_cache(self):
        data=p.build(SOURCE.read_bytes());vm=self.vm(data)
        obj=0x20000000;context=0x20030000
        vm.mem_write(0x4ec438,struct.pack('<I',context))
        vm.mem_write(context+0x38,struct.pack('<I',0xf7def7de))
        vm.reg_write(UC_X86_REG_ECX,obj)
        for i,(kind,amount,x,y) in enumerate([(0x53,10,20,20),(0x63,0,30,30),(0x53,0,40,40),(0x43,100,50,50),(0x11,100,60,60)],1):
            rec=bytearray(32);struct.pack_into('<H',rec,6,17);rec[0x12]=kind
            struct.pack_into('<hh',rec,0x14,x,y);struct.pack_into('<i',rec,0x1c,amount)
            vm.mem_write(0x766970+i*32,bytes(rec))
            vm.mem_write(obj+0x20254+x*2,struct.pack('<h',x))
            vm.mem_write(obj+0x20664+y*2,struct.pack('<h',y))
        before=bytes(vm.mem_read(0x766970,0x5dc*32))
        vm.emu_start(p.CODE+0x100,0x4690a2,count=80000)
        self.assertEqual(bytes(vm.mem_read(0x766970,len(before))),before)
        def pixel(n):return struct.unpack('<H',vm.mem_read(obj+0x1002c+n*256+n*2,2))[0]
        self.assertEqual(pixel(20),0xffe0);self.assertEqual(pixel(30),0x1f)
        self.assertEqual(pixel(40),0);self.assertEqual(pixel(50),0);self.assertEqual(pixel(60),0)
        self.assertEqual(struct.unpack('<I',vm.mem_read(p.STATE+4,4))[0],3)
        vm.mem_write(obj+0x1002c,b'\0'*0x8000)
        vm.mem_write(0x766970+32+0x1c,struct.pack('<i',0))
        vm.emu_start(p.CODE+0x100,0x4690a2,count=2000)
        self.assertEqual(pixel(20),0);self.assertEqual(pixel(30),0x1f)

    def test_fog_changes_framebuffer_only_and_clips(self):
        data=p.build(SOURCE.read_bytes());vm=self.vm(data)
        context=0x20000000;frame=0x20010000;rows=0x20001000
        vm.mem_write(0x4ec438,struct.pack('<I',context))
        vm.mem_write(context+0x38,struct.pack('<I',0xf7def7de))
        vm.mem_write(context+0x70,struct.pack('<II',frame,rows))
        vm.mem_write(rows,struct.pack('<4I',0,16,32,48))
        vm.mem_write(0x106a5e0,struct.pack('<HH',8,4))
        vm.mem_write(frame,b'\xff'*64)
        stop=0x30000000;stack=0x30008000
        vm.mem_write(stack,struct.pack('<6I',stop,6,2,32,32,0))
        vm.emu_start(p.CODE+0x400,stop,count=1000)
        out=bytes(vm.mem_read(frame,64))
        expected=bytearray(b'\xff'*64)
        for y in (2,3):
            for x in (6,7):struct.pack_into('<H',expected,y*16+x*2,0x7bef)
        self.assertEqual(out,bytes(expected))
        self.assertEqual(vm.reg_read(UC_X86_REG_ESP),stack+24)
        self.assertEqual(bytes(vm.mem_read(0x915d50,0x42040)),b'\0'*0x42040)
        self.assertEqual(bytes(vm.mem_read(0x999dd0,0x42040)),b'\0'*0x42040)

if __name__=='__main__':unittest.main()
