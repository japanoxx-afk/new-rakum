import struct
import unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_EIP
import minimap_preview_patch as patch
import viewport_patch

SOURCE = Path(__file__).parent/'research/runtime/viewport-1280-ui-v5/Rhakmu.exe.original'


@unittest.skipUnless(SOURCE.exists(), 'Verified local reference unavailable')
class MinimapTests(unittest.TestCase):
    def test_whole_image_guard_and_restore(self):
        original=SOURCE.read_bytes()
        for highres in (False, True):
            source=viewport_patch.transform(original, highres)
            result=patch.transform(source)
            self.assertEqual(patch.transform(result,False),source)
            self.assertEqual(patch.transform(result),result)
            self.assertEqual([i for i,(a,b) in enumerate(zip(source,result)) if a!=b],[patch.OFFSET+2])
            broken=bytearray(result);broken[0x1000]^=1
            with self.assertRaises(ValueError):patch.transform(broken)

    def test_native_copy_changes_only_minimap_working_pixels(self):
        for enabled in (False,True):
            vm=Uc(UC_ARCH_X86,UC_MODE_32)
            vm.mem_map(0x400000,0x100000)
            vm.mem_map(0x20000000,0x40000)
            vm.mem_map(0x30000000,0x10000)
            data=patch.transform(SOURCE.read_bytes(),enabled)
            vm.mem_write(0x467740,data[0x67740:0x67773])
            obj=0x20000000;stack=0x30008000;stop=0x30000000
            vm.mem_write(obj,b'\x5a'*0x30000)
            terrain=bytes((i*17)&255 for i in range(0x8000))
            explored=b'\0'*0x8000
            vm.mem_write(obj+0x2c,terrain)
            vm.mem_write(obj+0x802c,explored)
            before=bytes(vm.mem_read(obj,0x30000))
            def copy(emu,pc,size,_):
                if pc!=0x4ddf20:return
                sp=emu.reg_read(UC_X86_REG_ESP)
                ret,dest,src,n=struct.unpack('<4I',emu.mem_read(sp,16))
                self.assertEqual(dest,obj+0x1002c)
                self.assertEqual(n,0x8000)
                emu.mem_write(dest,bytes(emu.mem_read(src,n)))
                emu.reg_write(UC_X86_REG_ESP,sp+4)
                emu.reg_write(UC_X86_REG_EIP,ret)
            vm.hook_add(UC_HOOK_CODE,copy)
            vm.reg_write(UC_X86_REG_ECX,obj)
            vm.reg_write(UC_X86_REG_ESP,stack)
            vm.mem_write(stack,struct.pack('<I',stop))
            vm.emu_start(0x467740,stop,count=100)
            after=bytes(vm.mem_read(obj,0x30000))
            self.assertEqual(after[0x1002c:0x1802c],terrain if enabled else explored)
            self.assertEqual(after[:0x1002c],before[:0x1002c])
            self.assertEqual(after[0x1802c:],before[0x1802c:])
            self.assertEqual(vm.reg_read(UC_X86_REG_ESP),stack+4)


if __name__=='__main__':unittest.main()
