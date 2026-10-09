"""Execute patched terrain/fog with an unmapped page immediately after pixels."""
import struct
import unittest
import pefile
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import *
from test_viewport_ui import machine, call, SOURCE, STACK, STOP
from viewport_probe import transform
import viewport_patch
import viewport_terrain as terrain

SURFACE = 0x3003e000
SURFACE_SIZE = 1280*720*2  # ends exactly at unmapped 0x30200000
RESOURCE = 0x40000000
ROWS_TABLE = RESOURCE+0x10000
TAG = RESOURCE+0x12000
FILL_STUB, COPY_STUB = 0x2000e200, 0x2000e300


class TerrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.exists():
            raise unittest.SkipTest('Reference game not installed')
        cls.patched = transform(viewport_patch.transform(SOURCE.read_bytes(),False))[0]

    def scene(self, camera=(0,0), dimensions=(100,100)):
        vm = machine(self.patched)
        vm.mem_map(SURFACE,SURFACE_SIZE)
        vm.mem_write(SURFACE,b'\xab'*SURFACE_SIZE)
        vm.mem_map(RESOURCE,0x20000)
        vm.mem_write(0x106a5e0,struct.pack('<hh',1280,720))
        vm.mem_write(0xb412d4,struct.pack('<hh',*dimensions))
        vm.mem_write(0xb412d8,struct.pack('<hh',*camera))
        vm.mem_write(0x4ec438,struct.pack('<I',TAG))
        vm.mem_write(TAG+0x6c,struct.pack('<III',1280,SURFACE,ROWS_TABLE))
        vm.mem_write(ROWS_TABLE,struct.pack('<720I',*(y*2560 for y in range(720))))
        return vm

    def test_rows_and_columns_map_limits_and_original_modes(self):
        vm = self.scene()
        for address, size, offset in ((terrain.ROWS,720,2),(terrain.COLUMNS,1280,0)):
            for remaining,expected in ((100,23 if offset else 40),(1,1),(0,0),(-1,0)):
                vm.mem_write(0xb412d4+offset,struct.pack('<h',50))
                vm.mem_write(0xb412d8+offset,struct.pack('<h',50-remaining))
                vm.reg_write(UC_X86_REG_EAX,size)
                call(vm,address)
                self.assertEqual(vm.reg_read(UC_X86_REG_EAX),expected)
        for w,h in ((800,600),(1024,768)):
            vm.mem_write(0x106a5e0,struct.pack('<hh',w,h))
            vm.reg_write(UC_X86_REG_EAX,h)
            call(vm,terrain.ROWS)
            self.assertEqual(vm.reg_read(UC_X86_REG_EAX),(h-152)//32)

    def test_actual_tile_loop_refreshes_last_pixel_and_map_edges(self):
        for dimensions in ((100,100),(2,1)):
            vm = self.scene(dimensions=dimensions)
            vm.mem_write(0x6e0938,struct.pack('<I',RESOURCE))
            vm.mem_write(RESOURCE+0x9084,struct.pack('<I',RESOURCE+0x13000))
            vm.mem_write(RESOURCE+0x13010,struct.pack('<I',RESOURCE+0x14000))
            vm.mem_write(RESOURCE+0x14000,b'\x34\x12'*(32*32))
            template = struct.pack('<hh',0,32)+b''.join(
                struct.pack('<hhh',y*32,0,32) for y in range(32))
            vm.mem_write(RESOURCE+0x3002,template)
            vm.mem_write(0x4ca410,b'\xc3')  # decoration list is independently tested
            vm.mem_write(0x4ddf20,b'\xc3')
            vm.mem_write(0x4ec480,struct.pack('<I',FILL_STUB))
            vm.mem_write(FILL_STUB,bytes.fromhex('c21400'))
            copied = []
            def intercept(uc,address,size,_):
                sp = uc.reg_read(UC_X86_REG_ESP)
                if address == FILL_STUB:
                    args=struct.unpack('<5I',uc.mem_read(sp+4,20))
                    self.assertEqual(args,(0,0,1280,720,0))
                    uc.mem_write(SURFACE,bytes(SURFACE_SIZE))
                elif address == 0x4ddf20:
                    dst,src,count=struct.unpack('<3I',uc.mem_read(sp+4,12))
                    self.assertGreaterEqual(dst,SURFACE)
                    self.assertLessEqual(dst+count,SURFACE+SURFACE_SIZE)
                    uc.mem_write(dst,bytes(uc.mem_read(src,count)))
                    copied.append(dst)
            vm.hook_add(UC_HOOK_CODE,intercept)
            vm.reg_write(UC_X86_REG_ESP,STACK)
            vm.mem_write(STACK,struct.pack('<I',STOP))
            vm.emu_start(0x4ca690,STOP,count=10000000)
            self.assertEqual(vm.reg_read(UC_X86_REG_EIP),STOP)
            self.assertTrue(copied)
            self.assertEqual(bytes(vm.mem_read(SURFACE,2)),b'\x34\x12')
            expected=b'\x34\x12' if dimensions==(100,100) else b'\x00\x00'
            self.assertEqual(bytes(vm.mem_read(SURFACE+SURFACE_SIZE-2,2)),expected)
            if dimensions==(2,1):
                self.assertEqual(bytes(vm.mem_read(SURFACE+64*2,2)),b'\x00\x00')

    def test_actual_fog_loop_covers_bottom_without_crossing_surface(self):
        vm=self.scene()
        vm.mem_write(0x915d50,b'\x0f'*(0x208*24))
        vm.mem_write(0x4ec480,struct.pack('<I',FILL_STUB))
        vm.mem_write(FILL_STUB,bytes.fromhex('c21400'))
        calls=[]
        def fill(uc,address,size,_):
            if address!=FILL_STUB:
                return
            sp=uc.reg_read(UC_X86_REG_ESP)
            x,y,w,h,color=struct.unpack('<5I',uc.mem_read(sp+4,20))
            self.assertLessEqual(y+h,720)
            self.assertLessEqual(x+w,1280)
            for row in range(y,y+h):
                uc.mem_write(SURFACE+row*2560+x*2,bytes(w*2))
            calls.append((x,y,w,h))
        vm.hook_add(UC_HOOK_CODE,fill)
        vm.reg_write(UC_X86_REG_ESP,STACK)
        vm.mem_write(STACK,struct.pack('<I',STOP))
        vm.emu_start(0x4caf40,STOP,count=1000000)
        self.assertEqual(vm.reg_read(UC_X86_REG_EIP),STOP)
        self.assertEqual(len(calls),40*23)
        self.assertEqual(calls[-1],(1248,704,32,16))
        self.assertEqual(bytes(vm.mem_read(SURFACE,SURFACE_SIZE)),bytes(SURFACE_SIZE))

    def test_real_dll_fog_calls_clip_final_partial_row(self):
        dll = pefile.PE(str(SOURCE.with_name('iCARUS.dll')))
        exports={s.name:s.address+0x10000000 for s in dll.DIRECTORY_ENTRY_EXPORT.symbols}
        for helper,iat,name in (
            (terrain.FILL,0x4ec480,b'_iCARUS16_FillScr@20'),
            (terrain.REDUCE,0x4ec484,b'_iCARUS16_ReduceColorWithRleTable@20'),
            (terrain.HALF,0x4ec538,b'_iCARUS16_ChangeColor50WithRectangle@20')):
            vm=self.scene()
            vm.mem_map(0x10000000,(dll.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
            for section in dll.sections:
                vm.mem_write(0x10000000+section.VirtualAddress,section.get_data())
            vm.mem_write(0x100b406c,struct.pack('<III',1280,SURFACE,ROWS_TABLE))
            vm.mem_write(iat,struct.pack('<I',exports[name]))
            # Synthetic valid 32px RLE rows: zero skip, 32 pixels, row terminator.
            rle=RESOURCE+0x14000
            vm.mem_write(rle,(bytes([0,32])+bytes(32)+bytes([0,0]))*32)
            value=rle if helper==terrain.REDUCE else 0
            vm.reg_write(UC_X86_REG_ESP,STACK)
            vm.mem_write(STACK,struct.pack('<6I',STOP,1248,704,32,32,value))
            vm.emu_start(helper,STOP,count=1000000)
            self.assertEqual(vm.reg_read(UC_X86_REG_EIP),STOP)
            self.assertEqual(vm.reg_read(UC_X86_REG_ESP),STACK+24)
            self.assertEqual(struct.unpack('<I',vm.mem_read(STACK+16,4))[0],16)
            self.assertEqual(bytes(vm.mem_read(SURFACE,2)),b'\xab\xab')


if __name__=='__main__':
    unittest.main()
