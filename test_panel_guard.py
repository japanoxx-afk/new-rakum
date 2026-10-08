import pathlib
import struct
import tempfile
import unittest
from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_ESP
import panel_guard_patch as panel
import peer_address_patch as peer
from build_panel_guard import assemble

class PanelTests(unittest.TestCase):
    def machine(self, guarded, target):
        u=Uc(UC_ARCH_X86, UC_MODE_32)
        u.mem_map(0x400000,0xd00000)
        u.mem_map(0x1800000,0x10000)
        u.mem_map(0x2000000,0x10000)
        u.mem_write(0x463502,panel.JUMP if guarded else panel.ORIGINAL)
        u.mem_write(0x4eb600,panel.CODE)
        u.mem_write(0x1805000,struct.pack('<I',0x1805100))
        u.mem_write(0x1805100,struct.pack('<I',0x1010501))
        u.mem_write(0x1010531,struct.pack('<I',target))
        u.mem_write(0x4ec2a0,struct.pack('<I',0x1809000))
        u.mem_write(0x1809000,bytes.fromhex('31c0c20800'))
        u.mem_write(0x4ec2a4,struct.pack('<I',0x1809010))
        u.mem_write(0x1809010,bytes.fromhex('31c0c20400'))
        u.mem_write(0x1805500,bytes.fromhex('b800568001c20800'))
        u.mem_write(0x1805600,struct.pack('<I',0x3c))
        u.mem_write(0x2007ff8,b'\xff'*4)
        u.reg_write(UC_X86_REG_EAX,0x1805000)
        u.reg_write(UC_X86_REG_EBP,0x2008000)
        u.reg_write(UC_X86_REG_ESP,0x2007000)
        return u

    def test_original_null_call_and_guard(self):
        u=self.machine(False,0)
        with self.assertRaises(UcError): u.emu_start(0x463502,0x463517,count=1000)
        u=self.machine(True,0)
        u.emu_start(0x463502,0x463517,count=1000)
        self.assertEqual(u.reg_read(UC_X86_REG_ESP),0x2007008)
        self.assertEqual(bytes(u.mem_read(0x2007ff8,4)),b'\xff'*4)

    def test_valid_menu_keeps_original_result(self):
        for guarded in (False,True):
            u=self.machine(guarded,0x1805500)
            u.emu_start(0x463502,0x463517,count=1000)
            self.assertEqual(u.reg_read(UC_X86_REG_ESP),0x2007008)
            self.assertEqual(bytes(u.mem_read(0x2007ff8,4)),struct.pack('<I',0x3c))

    def test_assembly_and_restore(self):
        self.assertEqual(panel.CODE,assemble())
        source=pathlib.Path(r'C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe').read_bytes()
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root,'Rhakmu.exe')
            path.write_bytes(peer.transform(source,True))
            panel.apply(path,False)
            original=path.read_bytes()
            panel.apply(path)
            self.assertTrue(panel.state(path.read_bytes()))
            panel.apply(path,False)
            self.assertEqual(path.read_bytes(),original)

if __name__=='__main__': unittest.main()
