import struct
import unittest
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.x86_const import UC_X86_REG_ESP
from test_minimap_preview_v2 import SOURCE, TrialTests
import viewport_patch
import minimap_preview_v4 as p

class ContinuousFogTests(unittest.TestCase):
    def test_original_highres_restore_and_tampering(self):
        for high in (False,True):
            source=viewport_patch.transform(SOURCE.read_bytes(),high)
            data=p.build(source)
            self.assertEqual(p.restore(data),source)
            bad=bytearray(data);bad[p.RAW+15]^=1
            with self.assertRaises(ValueError):p.restore(bad)

    def test_continuous_edges_and_render_only_writes(self):
        for high in (False,True):
            for mask in (0xf7def7de,0x7bde7bde):
                data=p.build(viewport_patch.transform(SOURCE.read_bytes(),high))
                vm=TrialTests().vm(data)
                vm.mem_write(p.CODE,data[p.RAW:p.RAW+0x2000])
                context=0x20000000;frame=0x20010000;rows=0x20001000
                width,height=160,64
                vm.mem_write(0x4ec438,struct.pack('<I',context))
                vm.mem_write(context+0x38,struct.pack('<I',mask))
                vm.mem_write(context+0x70,struct.pack('<II',frame,rows))
                vm.mem_write(rows,struct.pack('<64I',*(y*width*2 for y in range(height))))
                vm.mem_write(0x106a5e0,struct.pack('<HH',width,height if high else height+152))
                vm.mem_write(0xb412cd,b'\0')
                vm.mem_write(0xb412d8,struct.pack('<hh',32,32))
                white=0xffff if mask==0xf7def7de else 0x7fff
                vm.mem_write(frame,struct.pack('<H',white)*(width*height))
                # Native current-fog mask: visible left, fully hidden right.
                for y in range(30,37):
                    for x in range(30,40):
                        vm.mem_write(0x957d90+y*520+x,bytes([0 if x<34 else 255]))
                before=bytes(vm.mem_read(0x957d90,520*520))
                writes=[]
                def check_write(emu,access,address,size,value,_):
                    if not (frame<=address<frame+width*height*2 or p.GRID<=address<p.GRID+0x4000 or 0x30000000<=address<0x30010000):
                        writes.append(hex(address))
                vm.hook_add(UC_HOOK_MEM_WRITE,check_write)
                stack=0x30008000;stop=0x30000000
                vm.mem_write(stack,struct.pack('<I',stop))
                vm.emu_start(p.CODE,stop,count=2000000)
                colors=struct.unpack('<160H',vm.mem_read(frame+width*2*32,width*2))
                blue=[color&31 for color in colors]
                self.assertEqual(blue[0],31)
                self.assertEqual(blue[-1],15)
                self.assertLessEqual(max(abs(a-b) for a,b in zip(blue,blue[1:])),1)
                self.assertGreater(len(set(blue)),12)
                self.assertEqual(writes,[])
                self.assertEqual(bytes(vm.mem_read(0x957d90,520*520)),before)
                self.assertEqual(vm.reg_read(UC_X86_REG_ESP),stack+4)

if __name__=='__main__':unittest.main()
