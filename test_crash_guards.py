"""Replay ERR dispatches using real x86 guard code and native DLL DrawControl."""
import struct
import unittest
from pathlib import Path
import pefile
from unicorn import UcError, UC_HOOK_CODE
from unicorn.x86_const import *
import viewport_patch
from test_viewport_ui import machine, SOURCE, OBJECT, STACK, PUTIMAGE

READ, CODE, VT, HEAD = 0x2000e200,0x2000e220,OBJECT+0x100,OBJECT+0x200

class CrashGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=viewport_patch.transform(SOURCE.read_bytes(),False)
        cls.patched=viewport_patch.transform(cls.original)

    def setup_vm(self, patched=True):
        vm=machine(self.patched if patched else self.original)
        dll=pefile.PE(str(SOURCE.parent/'GameCtrl.dll'))
        vm.mem_map(0x10000000,0x20000)
        for section in dll.sections:
            vm.mem_write(0x10000000+section.VirtualAddress,section.get_data())
        vm.mem_write(0x4ec2a0,struct.pack('<I',READ))
        vm.mem_write(0x4ec2a4,struct.pack('<I',CODE))
        vm.mem_write(READ,bytes.fromhex('c20800'))
        vm.mem_write(CODE,bytes.fromhex('c20400'))
        def api(uc,address,size,_):
            if address not in (READ,CODE):return
            sp=uc.reg_read(UC_X86_REG_ESP)
            pointer=struct.unpack('<I',uc.mem_read(sp+4,4))[0]
            n=struct.unpack('<I',uc.mem_read(sp+8,4))[0] if address==READ else 1
            good=(0x20000000<=pointer and pointer+n<=0x20010000)
            if address==CODE:good=pointer in (PUTIMAGE,0x10003400)
            uc.reg_write(UC_X86_REG_EAX,0 if good else 1)
            # Windows APIs may clobber volatile registers.
            uc.reg_write(UC_X86_REG_ECX,0xdeadbeef)
            uc.reg_write(UC_X86_REG_EDX,0xdeadbeef)
        vm.hook_add(UC_HOOK_CODE,api)
        vm.reg_write(UC_X86_REG_ESP,STACK)
        vm.reg_write(UC_X86_REG_EBP,STACK+0x100)
        vm.reg_write(UC_X86_REG_ECX,OBJECT)
        vm.reg_write(UC_X86_REG_EAX,OBJECT)
        vm.mem_write(STACK+0xf8,struct.pack('<I',OBJECT))
        vm.mem_write(OBJECT,struct.pack('<I',VT))
        vm.mem_write(OBJECT+0x3c,struct.pack('<I',HEAD))
        vm.mem_write(HEAD,struct.pack('<3I',HEAD,HEAD,0))
        return vm

    def test_hud_null_invalid_and_valid_dispatch(self):
        for target in (0,10,PUTIMAGE):
            vm=self.setup_vm()
            vm.mem_write(VT+0x2c,struct.pack('<I',target))
            vm.mem_write(PUTIMAGE,bytes.fromhex('b878563412c3'))
            vm.emu_start(0x463a94,0x463a9c,count=1000)
            self.assertEqual(vm.reg_read(UC_X86_REG_ESP),STACK)
            self.assertEqual(vm.reg_read(UC_X86_REG_ECX),OBJECT)
            if target==PUTIMAGE:self.assertEqual(vm.reg_read(UC_X86_REG_EAX),0x12345678)
        vm=self.setup_vm(False)
        with self.assertRaises(UcError):vm.emu_start(0x463a94,0x463a9c,count=1000)

    def test_err_form_sentinel_and_empty_valid_native_draw(self):
        for sentinel in (10,0,HEAD):
            vm=self.setup_vm()
            vm.mem_write(VT+0x20,struct.pack('<I',0x10003400))
            vm.mem_write(OBJECT+0x3c,struct.pack('<I',sentinel))
            vm.emu_start(0x42891e,0x428923,count=1000)
            self.assertEqual(vm.reg_read(UC_X86_REG_ESP),STACK)
        vm=self.setup_vm(False)
        vm.mem_write(VT+0x20,struct.pack('<I',0x10003400))
        vm.mem_write(OBJECT+0x3c,struct.pack('<I',10))
        with self.assertRaises(UcError):vm.emu_start(0x42891e,0x428923,count=1000)

    def test_process_skip_and_valid_stdcall_stack_cleanup(self):
        for sentinel in (10,HEAD):
            vm=self.setup_vm()
            vm.mem_write(VT+0x1c,struct.pack('<I',PUTIMAGE))
            vm.mem_write(PUTIMAGE,bytes.fromhex('b801000000c20c00'))
            vm.mem_write(OBJECT+0x3c,struct.pack('<I',sentinel))
            vm.mem_write(STACK,struct.pack('<3I',0x200,1,2))
            vm.emu_start(0x4289a1,0x4289a6,count=1000)
            self.assertEqual(vm.reg_read(UC_X86_REG_ESP),STACK+12)
            self.assertEqual(vm.reg_read(UC_X86_REG_EAX),int(sentinel==HEAD))

    def test_unreadable_object_vtable_and_first_node(self):
        for slot,value in ((OBJECT,10),(OBJECT+0x3c,10),(HEAD,10)):
            vm=self.setup_vm()
            vm.mem_write(VT+0x20,struct.pack('<I',0x10003400))
            vm.mem_write(slot,struct.pack('<I',value))
            vm.emu_start(0x42891e,0x428923,count=1000)
            self.assertEqual(vm.reg_read(UC_X86_REG_ESP),STACK)
        vm=self.setup_vm()
        vm.reg_write(UC_X86_REG_ECX,10)
        vm.reg_write(UC_X86_REG_EAX,10)
        vm.emu_start(0x42891e,0x428923,count=1000)
        self.assertEqual(vm.reg_read(UC_X86_REG_ESP),STACK)

if __name__=='__main__':unittest.main()
