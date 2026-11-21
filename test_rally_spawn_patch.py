"""집결지 패치 두 가지 (Rhakmu.exe 1.000d) 를 게임 코드 그대로 Unicorn 으로 실행해 확인.

  rally_construct_patch: 건설 중(상태 0x1004) 건물에서도 우클릭 집결지 명령 0x400E 를 보낸다.
  rally_spawn_patch:     생산 완료 때 유닛이 집결지 쪽 건물 가장자리에서 나온다.
"""
import itertools
import struct
import unittest
from pathlib import Path

import minimap_patch
import rally_construct_patch as rc
import rally_spawn_patch as rs

HERE = Path(__file__).resolve().parent
EXE = HERE / 'game_backup' / 'Rhakmu.exe'
UNITS, UNIT_SIZE = 0x775A38, 0x138
LEAD = 0xB412D0                  # 고른 유닛 (정보 창)
NET = 0xB411A4                   # 네트워크 객체 포인터, +0x44 = 보낼 명령 버퍼
SEND = 0x4494C0                  # 명령 보내기 (thiscall)
SCRATCH = 0x2000000              # 시험용 메모리 (스택·버퍼·표)
SENTINEL = 0x2FF0000             # 돌아올 주소 (여기서 멈춤)


def _emulator(image):
    try:
        import pefile
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    except ImportError as e:
        raise unittest.SkipTest(str(e))
    img = pefile.PE(data=image).get_memory_mapped_image()
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    size = max(len(img), 0x1100000 - 0x400000)
    mu.mem_map(0x400000, (size + 0xFFF) & ~0xFFF)
    mu.mem_write(0x400000, img)
    mu.mem_map(SCRATCH, 0x1000000)
    return mu


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXE.is_file():
            raise unittest.SkipTest('game_backup/Rhakmu.exe 없음')
        cls.original = EXE.read_bytes()


class PatchFileTests(Base):
    def test_state_roundtrip_and_code(self):
        for mod in (rc, rs):
            self.assertFalse(mod.state(self.original))
            on = mod.transform(self.original, True)
            self.assertTrue(mod.state(on))
            self.assertEqual(mod.transform(on, False), self.original)
            try:
                self.assertEqual(mod.assemble(), mod.CODE)
            except ImportError as e:
                self.skipTest(str(e))

    def test_caves_are_free_in_original(self):
        for mod in (rc, rs):
            for offset, before, _ in mod.SITES[1:]:
                self.assertEqual(self.original[offset:offset + len(before)], bytes(len(before)))

    def test_every_build_is_idempotent_and_switchable(self):
        """모든 패치 조합: 건설 중 집결지는 항상, 생산 위치는 설정대로. 다시 빌드해도 같은 결과."""
        for hr, gold, keys, sel, rec, play, spawn in itertools.product((False, True), repeat=7):
            args = (hr, gold, keys, sel, rec, rec, play)
            built = minimap_patch.build(self.original, *args, spawn)
            base = minimap_patch.underlying(built)
            self.assertTrue(rc.state(base))
            self.assertEqual(rs.state(base), spawn)
            self.assertEqual(minimap_patch.build(built, *args, spawn), built)
            other = minimap_patch.build(built, *args, not spawn)
            self.assertEqual(rs.state(minimap_patch.underlying(other)), not spawn)
            self.assertEqual(minimap_patch.build(other, *args, spawn), built)

    def test_default_build_keeps_original_spawn(self):
        """인자를 주지 않는 기존 호출(게임 판 확인 등)은 생산 위치를 바꾸지 않는다."""
        base = minimap_patch.underlying(minimap_patch.build(self.original, False, False, False, False))
        self.assertFalse(rs.state(base))
        self.assertTrue(rc.state(base))


class ConstructionRallyTests(Base):
    """0x447E60(부명령, 대상, 층, 지점) 을 실행해 보낸 명령을 본다."""

    def order(self, image, building_state, sub=3, point=(0x340, 0x120)):
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP
        mu = _emulator(image)
        unit = 7
        mu.mem_write(LEAD, struct.pack('<h', unit))
        mu.mem_write(UNITS + unit * UNIT_SIZE + 6, struct.pack('<H', building_state))
        net, buf = SCRATCH + 0x1000, SCRATCH + 0x2000
        mu.mem_write(NET, struct.pack('<I', net))
        mu.mem_write(net + 0x44, struct.pack('<I', buf))
        sent = []

        def send(uc, addr, size, _):
            sent.append(bytes(uc.mem_read(buf, 0x0F)))
            esp = uc.reg_read(UC_X86_REG_ESP)
            uc.reg_write(UC_X86_REG_EIP, struct.unpack('<I', uc.mem_read(esp, 4))[0])
            uc.reg_write(UC_X86_REG_ESP, esp + 4)
        mu.hook_add(UC_HOOK_CODE, send, begin=SEND, end=SEND)
        esp = SCRATCH + 0x80000
        x, y = point
        mu.mem_write(esp, struct.pack('<IIIII', SENTINEL, sub, unit, 0, x | y << 16))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(0x447E60, SENTINEL, count=10000)
        return sent

    def test_original_blocks_rally_while_constructing(self):
        self.assertEqual(self.order(self.original, 0x1004), [])
        self.assertEqual(len(self.order(self.original, 0)), 1)          # 완성된 건물은 원래도 됨

    def test_patch_sends_rally_while_constructing(self):
        built = rc.transform(self.original, True)
        [packet] = self.order(built, 0x1004)
        kind, size, sub, unit, target, layer, x, y = struct.unpack('<HHhhhBhh', packet)
        self.assertEqual((kind, size, sub, unit, layer, x, y), (0x400E, 0x0F, 3, 7, 0, 0x340, 0x120))

    def test_patch_keeps_other_blocks(self):
        built = rc.transform(self.original, True)
        self.assertEqual(self.order(built, 0x1004, sub=1), [])          # 공격 대상 지정은 그대로 막음
        self.assertEqual(self.order(built, 0x1007), [])                 # 다른 막힌 상태도 그대로
        self.assertEqual(len(self.order(built, 0)), 1)
        self.assertEqual(len(self.order(built, 0x1005)), 1)             # 생산 중은 원래도 됨


# 시험 지도: 128 x 128 칸, 건물 종류 9, 모양 3번 = 폭 4 x 높이 3 칸, 건물 중심 칸 (40, 40)
MAP = 128
BTYPE, SHAPE, W, H = 9, 3, 4, 3
CX, CY = 40, 40
LEFT, TOP = CX - W // 2, CY - H // 2          # 38, 39 -> 건물 칸 x 38..41, y 39..41
TERRAIN, OCCUPANCY = rs.TERRAIN, rs.OCCUPANCY


class SpawnTests(Base):
    """0x43900A ~ 0x43902A (생산 완료 함수 안 빈 자리 탐색 호출) 을 실행해 유닛이 나올 칸을 본다."""

    def spawn(self, image, rally=None, layer=0, rally_layer=0, blocked=(), building_cells=True, map_w=MAP):
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EBP, UC_X86_REG_EDX, UC_X86_REG_EAX
        mu = _emulator(image)
        mu.mem_write(rs.MAP_W, struct.pack('<hh', map_w, MAP))
        terrain = bytearray(0x208 * MAP)
        for yy in range(MAP):
            for xx in range(MAP):
                terrain[yy * 0x208 + xx] = 0x40
        if building_cells:
            for yy in range(TOP, TOP + H):
                for xx in range(LEFT, LEFT + W):
                    terrain[yy * 0x208 + xx] = 0x01           # 건물이 차지한 칸
        mu.mem_write(TERRAIN, bytes(terrain))
        for xx, yy in blocked:                                 # 다른 유닛이 서 있는 칸
            mu.mem_write(OCCUPANCY + (yy * 0x208 + xx) * 2, struct.pack('<h', 99))
        btype_data, shapes = SCRATCH + 0x3000, SCRATCH + 0x4000
        mu.mem_write(rs.BUILDING_TYPES + BTYPE * 0x14, struct.pack('<I', btype_data))
        mu.mem_write(btype_data + 0x40, struct.pack('<h', SHAPE))
        mu.mem_write(rs.SHAPES, struct.pack('<I', shapes))
        mu.mem_write(shapes + SHAPE * 0x5C + 0x18, struct.pack('<II', W, H))
        bld = UNITS + 3 * UNIT_SIZE
        mu.mem_write(bld + 0x0E, struct.pack('<h', BTYPE))
        mu.mem_write(bld + rs.LAYER, bytes([layer]))
        mu.mem_write(bld + 0x18, struct.pack('<hh', CX, CY))
        if rally is None:
            mu.mem_write(bld + rs.RALLY_LAYER, b'\xff')
        else:
            mu.mem_write(bld + rs.RALLY_LAYER, bytes([rally_layer]))
            mu.mem_write(bld + rs.RALLY_POINT, struct.pack('<hh', rally[0] * 32 + 16, rally[1] * 32 + 16))
        frame = SCRATCH + 0x80000
        mu.mem_write(frame + 8, struct.pack('<I', bld))      # 0x438E50 의 [ebp+8] = 건물
        mu.reg_write(UC_X86_REG_EBP, frame)
        mu.reg_write(UC_X86_REG_ESP, frame - 0x80)
        mu.reg_write(UC_X86_REG_EDX, 1)                      # 새 유닛 크기 (+0x58 byte)
        mu.mem_write(rs.SPOT_X, b'\0' * 4)
        mu.emu_start(0x43900A, 0x43902A, count=500000)
        ok = mu.reg_read(UC_X86_REG_EAX) & 0xFF
        self.assertEqual(mu.reg_read(UC_X86_REG_ESP), frame - 0x80)       # 스택 균형
        self.assertEqual(struct.unpack('<I', mu.mem_read(frame + 8, 4))[0], bld)
        return struct.unpack('<hh', mu.mem_read(rs.SPOT_X, 4)) if ok else None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.patched = rs.transform(cls.original, True)

    def test_original_spawns_below_building(self):
        x, y = self.spawn(self.original)
        self.assertEqual(y, TOP + H)                         # 건물 아래 줄 바로 밑
        self.assertEqual(self.spawn(self.original, rally=(40, 5)), (x, y))   # 집결지와 무관

    def test_without_rally_same_as_original(self):
        self.assertEqual(self.spawn(self.patched), self.spawn(self.original))
        self.assertEqual(self.spawn(self.patched, rally=(40, 5), rally_layer=1),     # 다른 층 집결지
                         self.spawn(self.original))

    def test_rally_north_spawns_on_north_edge(self):
        self.assertEqual(self.spawn(self.patched, rally=(40, 5)), (40, TOP - 1))
        self.assertEqual(self.spawn(self.patched, rally=(20, 5)), (LEFT - 1, TOP - 1))   # 북서쪽 멀리 -> 모서리

    def test_rally_each_side(self):
        self.assertEqual(self.spawn(self.patched, rally=(90, 40)), (LEFT + W, 40))       # 동
        self.assertEqual(self.spawn(self.patched, rally=(5, 40)), (LEFT - 1, 40))        # 서
        self.assertEqual(self.spawn(self.patched, rally=(39, 100)), (39, TOP + H))       # 남
        self.assertEqual(self.spawn(self.patched, rally=(100, 100)), (LEFT + W, TOP + H))  # 남동 모서리

    def test_blocked_edge_takes_nearest_free_cell(self):
        # 북쪽 가운데 칸 (40, 38) 에 유닛 -> 가장 가까운 칸 중 표 순서 첫째 (0, -1): (40, 37)
        self.assertEqual(self.spawn(self.patched, rally=(40, 5), blocked=[(40, 38)]), (40, 37))
        self.assertEqual(self.spawn(self.patched, rally=(40, 5), blocked=[(40, 38), (40, 37)]), (39, 38))
        # 북쪽 줄이 모두 막히면 표 안의 건물 옆 칸 (2, 1) -> 동쪽 (42, 39)
        north = [(xx, yy) for xx in range(30, 50) for yy in range(30, 39)]
        self.assertEqual(self.spawn(self.patched, rally=(40, 5), blocked=north), (42, 39))
        # 표 안이 모두 막히면 원래 탐색 그대로
        wall = [(xx, yy) for xx in range(30, 50) for yy in range(30, 45)]
        self.assertEqual(self.spawn(self.patched, rally=(40, 5), blocked=wall),
                         self.spawn(self.original, blocked=wall))

    def test_rally_inside_building_or_map_edge(self):
        self.assertEqual(self.spawn(self.patched, rally=(39, 40)), self.spawn(self.original))   # 건물 안
        self.assertEqual(self.spawn(self.patched, rally=(40, 0)), (40, TOP - 1))     # 지도 맨 위 집결지

    def test_map_border_cells_are_skipped(self):
        """지도 안 4 <= x < 폭 만 고른다 (원래 탐색과 같은 경계): 폭을 줄여 동쪽 가장자리 칸을 지도 밖으로."""
        # 폭 42 -> x 42 는 지도 밖: 동쪽 집결지의 가장자리 칸 (42, 40) 대신 표에서 다음으로 가까운 지도 안 칸
        self.assertEqual(self.spawn(self.patched, rally=(90, 40), map_w=42), (41, 38))

    def test_same_inputs_same_result(self):
        a = self.spawn(self.patched, rally=(70, 12), blocked=[(42, 38)])
        b = self.spawn(self.patched, rally=(70, 12), blocked=[(42, 38)])
        self.assertEqual(a, b)
        self.assertEqual(a, (42, 37))       # 북동쪽 모서리 (42, 38) 이 막혀 그 바로 위 칸


class RallySpawnServerRuleTests(unittest.TestCase):
    """접속 PC: 서버 규칙에 rally_spawn 이 없으면(NAS 인터넷 서버) 켠다. 명시적으로 끈 서버만 끈다."""

    def sync(self, body):
        import io
        import json
        from types import SimpleNamespace
        from unittest import mock
        import launcher
        app = SimpleNamespace(cfg={}, latency=SimpleNamespace(current=lambda: 4, apply=lambda t: (True, '')))
        resp = io.BytesIO(json.dumps(body).encode())
        resp.__enter__ = lambda *a: resp
        resp.__exit__ = lambda *a: False
        with mock.patch("urllib.request.urlopen", return_value=resp), \
                mock.patch.object(launcher.game_address_patch, "_local_ipv4s", return_value=[]):
            launcher.App._sync_rules_from_server(app, "112.159.73.235")
        return app._rally_spawn_override

    def test_nas_without_rules_file_turns_it_on(self):
        self.assertTrue(self.sync({"server_version": "0.9019", "p2p": 1}))

    def test_server_pc_that_turned_it_off(self):
        self.assertFalse(self.sync({"turns": 4, "rally_spawn": False, "p2p": 1}))
        self.assertTrue(self.sync({"turns": 4, "rally_spawn": True, "p2p": 1}))


if __name__ == '__main__':
    unittest.main()
