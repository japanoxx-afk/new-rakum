"""메뉴 해제 크래시 보호: CGameMenu::Free (0x424110) 를 그대로 실행해 확인."""
import struct
import unittest
from pathlib import Path

import menu_free_guard_patch as g
import minimap_patch

HERE = Path(__file__).resolve().parent
EXE = HERE / 'game_backup' / 'Rhakmu.exe'
STUB, RET, THIS = 0x3000000, 0x3000F00, 0x2300000


class MenuFreeGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXE.is_file():
            raise unittest.SkipTest('game_backup/Rhakmu.exe 없음')
        cls.original = EXE.read_bytes()
        cls.built = minimap_patch.build(cls.original, False, True, True, True)

    def test_state_roundtrip_and_code(self):
        self.assertFalse(g.state(self.original))
        on = g.transform(self.original, True)
        self.assertTrue(g.state(on))
        self.assertEqual(g.transform(on, False), self.original)
        try:
            self.assertEqual(g.assemble(), g.CODE)
        except ImportError as e:
            self.skipTest(str(e))

    def run_free(self, image, form, control_head=None):
        try:
            import pefile
            from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
            from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EAX
        except ImportError as e:
            self.skipTest(str(e))
        img = pefile.PE(data=image).get_memory_mapped_image()
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0x400000, (len(img) + 0xFFF) & ~0xFFF)
        mu.mem_write(0x400000, img)
        mu.mem_map(0x2000000, 0x400000)
        mu.mem_map(STUB, 0x1000)
        mu.mem_write(RET, b'\xf4')
        called = []
        # IsBadReadPtr(p, n): 1 if not mapped
        mu.mem_write(STUB, b'\xc2\x08\x00')
        mu.mem_write(0x4EC2A0, struct.pack('<I', STUB))
        mu.mem_write(STUB + 0x10, b'\xc3')                      # [0x4EC3F8] (this+0x654 정리)
        mu.mem_write(0x4EC3F8, struct.pack('<I', STUB + 0x10))
        for a in (0x42C3B0, 0x425990, 0x423FB0, 0x428780):     # 다른 정리 함수들
            mu.mem_write(a, b'\xc3')

        def bad_read_ptr(uc, addr, size, _):
            esp = uc.reg_read(UC_X86_REG_ESP)
            p, n = struct.unpack('<II', uc.mem_read(esp + 4, 8))
            try:
                uc.mem_read(p, n); bad = 0
            except Exception:
                bad = 1
            uc.reg_write(UC_X86_REG_EAX, bad)

        def note(uc, addr, size, _):
            called.append((addr, uc.reg_read(UC_X86_REG_ECX)))
        mu.hook_add(UC_HOOK_CODE, bad_read_ptr, begin=STUB, end=STUB)
        mu.hook_add(UC_HOOK_CODE, note, begin=0x428780, end=0x428780)
        mu.mem_write(THIS, struct.pack('<I', form))
        if control_head is not None:
            mu.mem_write(form + 0x3C, struct.pack('<I', control_head))
        esp = 0x2080000
        mu.mem_write(esp, struct.pack('<I', RET))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_ECX, THIS)
        mu.emu_start(0x424110, RET, count=100000)
        self.assertEqual(mu.reg_read(UC_X86_REG_ESP), esp + 4)
        return called

    def test_deleted_form_is_skipped(self):
        # control list head points into unmapped memory (what RhakMU.ERR shows)
        self.assertEqual(self.run_free(self.built, 0x2310000, control_head=0x5000_0000), [])
        self.assertEqual(self.run_free(self.built, 0x6000_0000), [])        # form itself unreadable

    def test_valid_form_is_still_freed(self):
        head = 0x2320000
        self.assertEqual(self.run_free(self.built, 0x2310000, control_head=head), [(0x428780, 0x2310000)])
        self.assertEqual(self.run_free(self.original, 0x2310000, control_head=head), [(0x428780, 0x2310000)])
        self.assertEqual(self.run_free(self.built, 0), [])                  # 폼 없음: 원래처럼 건너뜀


if __name__ == '__main__':
    unittest.main()
