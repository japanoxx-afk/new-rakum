"""ESC 예약 취소 패치: 게임의 ESC 경로(0x42F048)를 그대로 실행해 어떤 취소 명령을 보내는지 확인."""
import struct
import unittest
from pathlib import Path

import minimap_patch
import queue_cancel_patch as q

HERE = Path(__file__).resolve().parent
EXE = HERE / 'game_backup' / 'Rhakmu.exe'
SELECTION = 0x80083E            # 선택 목록 (word 12칸)
MENU = 0x801E80                 # [MENU+0x2C] 가 0 이면 메뉴 없음 -> ESC 가 취소로 쓰임


class QueueCancelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXE.is_file():
            raise unittest.SkipTest('game_backup/Rhakmu.exe 없음')
        cls.original = EXE.read_bytes()

    def test_state_roundtrip_and_code(self):
        self.assertFalse(q.state(self.original))
        on = q.transform(self.original, True)
        self.assertTrue(q.state(on))
        self.assertEqual(q.transform(on, False), self.original)
        try:
            self.assertEqual(q.assemble(), q.CODE)
        except ImportError as e:
            self.skipTest(str(e))

    def test_every_build_has_it_and_validation_strips_it(self):
        for args in ((False, True, True, True), (False, False, False, False, True)):
            built = minimap_patch.build(self.original, *args)
            self.assertTrue(q.state(built))
            self.assertEqual(minimap_patch.build(built, *args), built)     # 다시 실행해도 같은 결과

    def press_esc(self, image, units):
        """units: {유닛 번호: 예약 개수}. 보낸 취소 명령 목록 [(명령, 유닛, 칸)]."""
        try:
            import pefile
            from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
            from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EBP, UC_X86_REG_EIP
        except ImportError as e:
            self.skipTest(str(e))
        img = pefile.PE(data=image).get_memory_mapped_image()
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        size = max(len(img), 0x1100000 - 0x400000)
        mu.mem_map(0x400000, (size + 0xFFF) & ~0xFFF)
        mu.mem_write(0x400000, img)
        mu.mem_map(0x2000000, 0x100000)
        mu.mem_write(MENU + 0x2C, struct.pack('<I', 0))
        sel = list(units) + [0] * (12 - len(units))
        mu.mem_write(SELECTION, struct.pack('<12h', *sel))
        for u, n in units.items():
            base = q.UNITS + u * q.UNIT_SIZE
            mu.mem_write(base + 8, struct.pack('<h', 100))           # 체력
            mu.mem_write(base + q.QUEUE_COUNT, bytes([n]))
        sent = []

        def stub(uc, addr, size, _):
            esp = uc.reg_read(UC_X86_REG_ESP)
            ret, unit = struct.unpack('<Ih', bytes(uc.mem_read(esp, 6)))
            slot = uc.mem_read(esp + 8, 1)[0]
            sent.append((0x400A, unit, None) if addr == q.CANCEL_CURRENT else (0x400B, unit, slot))
            uc.reg_write(UC_X86_REG_ESP, esp + 4)
            uc.reg_write(UC_X86_REG_EIP, ret)
        for a in (q.CANCEL_CURRENT, q.CANCEL_SLOT):
            mu.hook_add(UC_HOOK_CODE, stub, begin=a, end=a)
        # 0x42EF90 프레임 흉내: [ebp-4] 반복 변수, ESC 경로 뒤 0x42F0F8 에서 멈춤
        frame = 0x2080000
        mu.reg_write(UC_X86_REG_EBP, frame)
        mu.reg_write(UC_X86_REG_ESP, frame - 0x40)
        mu.emu_start(0x42F048, 0x42F0F8, count=100000)
        return sent

    def test_esc_cancels_last_reserved_slot(self):
        built = q.transform(self.original, True)
        self.assertEqual(self.press_esc(built, {5: 3}), [(0x400B, 5, 2)])
        self.assertEqual(self.press_esc(built, {5: 1}), [(0x400B, 5, 0)])

    def test_esc_without_queue_cancels_current(self):
        built = q.transform(self.original, True)
        self.assertEqual(self.press_esc(built, {5: 0, 7: 2}), [(0x400A, 5, None), (0x400B, 7, 1)])

    def test_original_always_cancels_current(self):
        self.assertEqual(self.press_esc(self.original, {5: 3}), [(0x400A, 5, None)])


if __name__ == '__main__':
    unittest.main()
