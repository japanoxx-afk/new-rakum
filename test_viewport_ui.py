"""Execute the actual x86 UI paths, not just a model of their coordinates."""
from pathlib import Path
import struct
import unittest
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
import viewport_probe
from viewport_helpers import helpers, CURSOR_RETURN, LEFT_DECORATION

SOURCE = Path(r'C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe')
STOP, SETRECT, PUTIMAGE = 0x2000f000, 0x2000e000, 0x2000e100
OBJECT, STACK = 0x20002000, 0x2000c000


def machine(data):
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, 0xd00000)
    vm.mem_map(0x20000000, 0x10000)
    pe = pefile.PE(data=data)
    for section in pe.sections:
        vm.mem_write(0x400000+section.VirtualAddress, section.get_data())
    vm.mem_write(0x4ec338, struct.pack('<I', SETRECT))
    vm.mem_write(SETRECT, bytes.fromhex('c21400'))
    def setrect(uc, address, size, _):
        if address == SETRECT:
            sp = uc.reg_read(UC_X86_REG_ESP)
            pointer, *rectangle = struct.unpack('<5I', uc.mem_read(sp+4, 20))
            uc.mem_write(pointer, struct.pack('<4I', *rectangle))
    vm.hook_add(UC_HOOK_CODE, setrect)
    return vm


def call(vm, address, this=OBJECT):
    vm.reg_write(UC_X86_REG_ESP, STACK)
    vm.reg_write(UC_X86_REG_ECX, this)
    vm.mem_write(STACK, struct.pack('<I', STOP))
    vm.emu_start(address, STOP, count=100000)
    if vm.reg_read(UC_X86_REG_EIP) != STOP:
        raise AssertionError('Function did not return')


class ViewportUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.exists():
            raise unittest.SkipTest('Reference executable unavailable')
        cls.original = SOURCE.read_bytes()
        cls.patched = viewport_probe.transform(cls.original)[0]

    def test_reproduce_old_crash_coordinate_and_fix_actual_initializer(self):
        for data, expected_y in ((self.original, 688), (self.patched, 640)):
            vm = machine(data)
            vm.mem_write(0x501ea0, struct.pack('<hh', 112, 168))
            call(vm, 0x45b7c0)  # original process-startup coordinate construction
            vm.mem_write(0x501ea0, struct.pack('<hh', 240, 120))
            call(vm, 0x45bad0)  # actual command object initialization
            rectangle = struct.unpack('<4i', vm.mem_read(OBJECT+0xd8+5*16, 16))
            self.assertEqual(rectangle[1], expected_y)
            # The crashing DrawCtrl instruction adds 45 before drawing its bar.
            self.assertEqual(rectangle[1]+45, 733 if data is self.original else 685)

    def test_resolution_change_updates_all_hitboxes_without_resetting_commands(self):
        vm = machine(self.patched)
        vm.mem_write(OBJECT+0x178, b'\x55'*0x90)
        for x, y in ((240, 120), (112, 168), (240, 120)):
            vm.mem_write(0x501ea0, struct.pack('<hh', x, y))
            call(vm, 0x45bab0)
            for index in range(10):
                left = 13+(index % 5)*46+x
                top = 474+(index // 5)*46+y
                self.assertEqual(struct.unpack('<4i', vm.mem_read(OBJECT+0xd8+index*16,16)),
                                 (left, top, left+40, top+40))
            self.assertEqual(bytes(vm.mem_read(OBJECT+0x178,0x90)), b'\x55'*0x90)

    def test_left_decoration_attaches_to_panel(self):
        vm = machine(self.patched)
        vm.reg_write(UC_X86_REG_ECX, OBJECT)
        vm.reg_write(UC_X86_REG_EAX, 0)
        vm.reg_write(UC_X86_REG_ESP, STACK)
        vm.mem_write(OBJECT+2, struct.pack('<h', 0))
        for origin, expected in ((112,0),(240,128)):
            vm.mem_write(0x106a690, struct.pack('<i', origin))
            vm.reg_write(UC_X86_REG_ESP, STACK)
            vm.emu_start(LEFT_DECORATION, 0x464778, count=100)
            self.assertEqual(struct.unpack('<i', vm.mem_read(STACK-4,4))[0], expected)

    def test_cursor_restore_arguments_and_bounds(self):
        for rect, expected in (((1200,650,32,32), True), ((1279,719,1,1), True),
                               ((1280,650,32,32), False), ((20,710,32,32),False),
                               ((-1,20,32,32),False), ((20,20,0,32),False),
                               ((20,20,512,32),False)):
            vm = machine(self.patched)
            vm.mem_write(0x7668ec, struct.pack('<I', 1))
            vm.mem_write(0x106a5e0, struct.pack('<hh',1280,720))
            vm.mem_write(0x6e68c4, struct.pack('<4h',*rect))
            vm.mem_write(0x4ec588, struct.pack('<I', PUTIMAGE))
            vm.mem_write(PUTIMAGE, bytes.fromhex('c21800'))
            seen = []
            def capture(uc,address,size,_):
                if address == PUTIMAGE:
                    seen.append(struct.unpack('<6I',uc.mem_read(uc.reg_read(UC_X86_REG_ESP)+4,24)))
            vm.hook_add(UC_HOOK_CODE,capture)
            # Reproduce saved registers and frame at Game_DrawMouseNFlip epilogue.
            vm.reg_write(UC_X86_REG_EBP, STACK+16)
            vm.reg_write(UC_X86_REG_ESP, STACK)
            vm.mem_write(STACK,struct.pack('<6I',11,22,33,0,44,STOP))
            vm.emu_start(CURSOR_RETURN, STOP, count=1000)
            self.assertEqual(bool(seen),expected)
            if expected:
                x,y,w,h=rect
                self.assertEqual(seen,[(x,y,0x6e68cc,w,h,w)])
            self.assertEqual(vm.reg_read(UC_X86_REG_ESP),STACK+24)
            self.assertEqual(vm.reg_read(UC_X86_REG_EDI),11)
            self.assertEqual(vm.reg_read(UC_X86_REG_ESI),22)
            self.assertEqual(vm.reg_read(UC_X86_REG_EBX),33)
            self.assertEqual(vm.reg_read(UC_X86_REG_EBP),44)


if __name__ == '__main__':
    unittest.main()
