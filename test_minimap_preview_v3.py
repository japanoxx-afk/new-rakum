import struct
import unittest
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP
import minimap_preview_v3 as p
import minimap_preview_v2 as v2
from test_minimap_preview_v2 import TrialTests, SOURCE
import viewport_patch

class SmoothFogTests(unittest.TestCase):
    def test_restore_both_resolutions(self):
        for high in (False,True):
            source=viewport_patch.transform(SOURCE.read_bytes(),high)
            self.assertEqual(p.restore(p.build(source)),source)

    def test_native_gradient_is_retained_and_opacity_halved(self):
        for high in (False,True):
            data=p.build(viewport_patch.transform(SOURCE.read_bytes(),high))
            vm=TrialTests().vm(data)
            context=0x20000000;frame=0x20010000;rows=0x20001000
            vm.mem_write(0x4ec438,struct.pack('<I',context))
            vm.mem_write(context+0x38,struct.pack('<I',0xf7def7de))
            vm.mem_write(context+0x70,struct.pack('<II',frame,rows))
            vm.mem_write(rows,struct.pack('<4I',0,16,32,48))
            vm.mem_write(0x106a5e0,struct.pack('<HH',8,4))
            vm.mem_write(frame,b'\xff'*64)
            native=0x4ebf10 if high else 0x400100
            vm.mem_write(0x4ec484,struct.pack('<I',native))
            calls=[]
            def fake_native(emu,pc,size,_):
                if pc!=native:return
                sp=emu.reg_read(UC_X86_REG_ESP)
                ret,x,y,w,h,table=struct.unpack('<6I',emu.mem_read(sp,24))
                calls.append((x,y,w,h,table))
                # Mock smooth native RLE output: black -> gray -> white.
                for yy in range(h):
                    for xx,color in enumerate((0,0x39e7,0x7bef,0xffff)):
                        emu.mem_write(frame+(y+yy)*16+(x+xx)*2,struct.pack('<H',color))
                emu.reg_write(UC_X86_REG_ESP,sp+24)
                emu.reg_write(UC_X86_REG_EIP,ret)
            vm.hook_add(UC_HOOK_CODE,fake_native)
            stack=0x30008000;stop=0x30000000
            vm.mem_write(stack,struct.pack('<6I',stop,2,1,4,2,0x12345678))
            vm.emu_start(v2.CODE+0x500,stop,count=3000)
            self.assertEqual(calls,[(2,1,4,2,0x12345678)])
            values=struct.unpack('<4H',vm.mem_read(frame+16+4,8))
            self.assertTrue(all(a<b for a,b in zip(values,values[1:])))
            self.assertEqual(values[0],0x7bef)
            self.assertEqual(values[-1],0xffff)
            self.assertEqual(bytes(vm.mem_read(frame,16)),b'\xff'*16)
            self.assertEqual(vm.reg_read(UC_X86_REG_ESP),stack+24)
            self.assertEqual(bytes(vm.mem_read(0x915d50,0x42040)),b'\0'*0x42040)

if __name__=='__main__':unittest.main()
