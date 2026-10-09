"""Execute the actual x86 UI paths, not just a model of their coordinates."""
from pathlib import Path
import struct
import unittest
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
import viewport_probe
import viewport_patch
from viewport_helpers import helpers, CURSOR_RETURN, LEFT_DECORATION, MENU_CHILDREN, TOOLTIP_RECTS

SOURCE = Path(__file__).parent/'research/runtime/viewport-1280-ui-v5/Rhakmu.exe.original'
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
        cls.original = viewport_patch.transform(SOURCE.read_bytes(),False)
        cls.patched = viewport_probe.transform(cls.original)[0]

    def test_portrait_hp_tables_refresh_on_resolution_transition(self):
        vm=machine(self.patched)
        snapshots=[]
        for x,y in ((112,168),(240,120),(112,168)):
            vm.mem_write(0x106a5e4,struct.pack('<I',1))
            vm.mem_write(0x501ea0,struct.pack('<hh',x,y))
            vm.reg_write(UC_X86_REG_EBP,STACK+16)
            vm.reg_write(UC_X86_REG_ESP,STACK)
            vm.mem_write(STACK,struct.pack('<6I',11,22,33,0,44,STOP))
            vm.emu_start(0x465886,STOP,count=10000)
            self.assertEqual(vm.reg_read(UC_X86_REG_ESP),STACK+24)
            self.assertEqual(struct.unpack('<4I',vm.mem_read(0x4ff500,16)),
                             (x+359,y+520,x+387,y+555))
            self.assertEqual(struct.unpack('<2h',vm.mem_read(0x4ff554,4)),(x+401,y+484))
            self.assertEqual(struct.unpack('<8h',vm.mem_read(0x801c40,16)),
                             (360,557,360+x,557+y,450,557,450+x,557+y))
            self.assertEqual(struct.unpack('<I',vm.mem_read(0x106a5e4,4))[0],1)
            snapshots.append(bytes(vm.mem_read(0x4ff500,0x180)))
        self.assertEqual(snapshots[0],snapshots[2])
        self.assertNotEqual(snapshots[0],snapshots[1])

    def test_resource_anchor_and_native_mouse_rectangles(self):
        for width,height,x,y in ((1280,720,240,120),(1024,768,112,168),(800,600,0,0),(1024,768,240,120)):
            vm=machine(self.patched)
            vm.mem_write(0x106a5e0,struct.pack('<hhI',width,height,int(width>800)))
            vm.mem_write(0x501e9c,struct.pack('<4h',0,0,x,y))
            vm.mem_write(OBJECT+8,struct.pack('<2i',287,-168))
            call(vm,0x4525c0)
            expected_x=792 if (x,y)==(240,120) else 287+x
            expected_y=-6 if (x,y)==(240,120) else y-168
            self.assertEqual(struct.unpack('<hh',vm.mem_read(OBJECT+0x84,4)),(expected_x,expected_y))
            for i in range(5):
                dx,dy=struct.unpack('<2i',vm.mem_read(0x4ff438+i*8,8))
                self.assertEqual(struct.unpack('<4i',vm.mem_read(OBJECT+0x34+i*16,16)),
                                 (expected_x+dx,expected_y+dy,expected_x+dx+20,expected_y+dy+16))

    def test_production_tooltip_tracks_current_panel_without_scaling_size(self):
        for width,height in ((1280,720),(1024,768),(800,600)):
            vm=machine(self.patched);frame=STACK+0x100
            vm.mem_write(0x106a5e0,struct.pack('<hh',width,height))
            vm.mem_write(0x106a690,struct.pack('<I',(width-800)//2))
            for repeat in range(2):
                vm.mem_write(frame-0x14,struct.pack('<I',10))
                vm.mem_write(frame-0xc,struct.pack('<I',200))
                vm.mem_write(frame-0x10,struct.pack('<I',height-185-80))
                vm.mem_write(frame-8,struct.pack('<I',height-185))
                vm.mem_write(frame+8,struct.pack('<I',OBJECT))
                vm.reg_write(UC_X86_REG_EBP,frame)
                vm.emu_start(0x46b59b,0x46b5b5,count=1000)
                offset=240 if width==1280 else 0
                self.assertEqual(struct.unpack('<4I',vm.mem_read(OBJECT,16)),
                                 (10+offset,height-265,200+offset,height-185))

    def test_hud_gate_reproduces_missing_hover_and_accepts_visible_buttons(self):
        for data,inside in ((self.original,False),(self.patched,True)):
            vm=machine(data)
            vm.mem_write(0x106a5e0,struct.pack('<hhI',1280,720,1))
            vm.mem_write(0x501ea0,struct.pack('<hh',240,120))
            vm.mem_write(0x106a690,struct.pack('<4i',240,535,1039,719))
            # Panel loaded at the lobby's 1024x768 then battle ChangeRes.
            vm.mem_write(OBJECT+2,struct.pack('<4h',112,593,911,767))
            frame=STACK+0x100;point=OBJECT+0x600
            vm.mem_write(frame-4,struct.pack('<I',OBJECT))
            vm.mem_write(frame+8,struct.pack('<I',point))
            for table in (0x4ff778,0x4ff790):
                for faction in range(3):
                    x,y=struct.unpack('<ii',vm.mem_read(table+faction*8,8))
                    vm.mem_write(point,struct.pack('<hh',x+240+18,y+120+15))
                    vm.reg_write(UC_X86_REG_EBP,frame);vm.reg_write(UC_X86_REG_ESP,STACK)
                    reached=[]
                    def stop(uc,address,size,_):
                        if address in (0x462e20,0x462e27):
                            reached.append(address);uc.emu_stop()
                    hook=vm.hook_add(UC_HOOK_CODE,stop)
                    vm.emu_start(0x462d9a,STOP,count=1000);vm.hook_del(hook)
                    self.assertEqual(reached,[0x462e27 if inside else 0x462e20])

    def test_tooltip_rects_recomputed_without_drift_for_all_factions(self):
        vm=machine(self.patched)
        for i in range(15):vm.mem_write(0x801c78+i*32,struct.pack('<4i',i,400+i,i+36,430+i))
        for x,y in ((112,168),(240,120),(240,120)):
            vm.mem_write(0x501ea0,struct.pack('<hh',x,y));call(vm,TOOLTIP_RECTS)
            for i in range(15):
                self.assertEqual(struct.unpack('<4i',vm.mem_read(0x801c88+i*32,16)),
                                 (i+x,400+i+y,i+36+x,430+i+y))

    def test_actual_menu_alliance_button_hover_press_release(self):
        for faction in range(3):
            for ident,table in ((0x36,0x4ff778),(0x37,0x4ff790)):
                vm=machine(self.patched)
                x,y=struct.unpack('<ii',vm.mem_read(table+faction*8,8))
                vm.mem_write(0x106a5e4,struct.pack('<I',1))
                vm.mem_write(0x501ea0,struct.pack('<hh',240,120))
                vm.mem_write(OBJECT+8,struct.pack('<4i',x,y,36,30))
                vm.mem_write(OBJECT+0x28,struct.pack('<I',ident));call(vm,0x45b690)
                down,up=0x2000e500,0x2000e510
                vm.mem_write(0x4ec500,struct.pack('<I',down));vm.mem_write(0x4ec4f4,struct.pack('<I',up))
                vm.mem_write(down,b'\xa1'+struct.pack('<I',OBJECT+0x700)+b'\xc3')
                vm.mem_write(up,b'\xa1'+struct.pack('<I',OBJECT+0x704)+b'\xc3')
                point,result=OBJECT+0x600,OBJECT+0x610
                vm.mem_write(point,struct.pack('<hh',x+258,y+135))
                for pressed,released,expected in ((0,0,(-1,ident)),(1,0,(-1,-1)),(0,1,(ident,-1))):
                    vm.mem_write(OBJECT+0x700,struct.pack('<II',pressed,released))
                    vm.reg_write(UC_X86_REG_ESP,STACK);vm.reg_write(UC_X86_REG_ECX,OBJECT)
                    vm.mem_write(STACK,struct.pack('<III',STOP,result,point))
                    vm.emu_start(0x45b4f0,STOP,count=1000)
                    self.assertEqual(struct.unpack('<hh',vm.mem_read(result,4)),expected)

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

    def test_menu_children_follow_parent_not_hud_origin(self):
        vm = machine(self.patched)
        vector, child = OBJECT+0x100, OBJECT+0x200
        vm.mem_write(OBJECT+8, struct.pack('<ii', 495, 25))
        vm.mem_write(OBJECT+0x30, struct.pack('<II', vector, vector+4))
        vm.mem_write(vector, struct.pack('<I', child))
        vm.mem_write(child+8, struct.pack('<ii', 535, 205))
        for parent_x, parent_y in ((495,145), (367,193), (495,145)):
            vm.mem_write(OBJECT+0x3e, struct.pack('<hh', parent_x,parent_y))
            call(vm, MENU_CHILDREN)
            self.assertEqual(struct.unpack('<hh',vm.mem_read(child+0x40,4)),
                             (parent_x+40,parent_y+180))
            # No cumulative drift, and base geometry remains immutable.
            call(vm, MENU_CHILDREN)
            self.assertEqual(struct.unpack('<hh',vm.mem_read(child+0x40,4)),
                             (parent_x+40,parent_y+180))
            self.assertEqual(struct.unpack('<ii',vm.mem_read(child+8,8)),(535,205))

    def test_menu_draw_hook_replays_original_prologue(self):
        vm = machine(self.patched)
        vm.reg_write(UC_X86_REG_ECX,OBJECT)
        vm.reg_write(UC_X86_REG_ESP,STACK)
        vm.reg_write(UC_X86_REG_EBP,1234)
        vm.emu_start(0x459f90,0x459f96,count=1000)
        self.assertEqual(vm.reg_read(UC_X86_REG_ECX),OBJECT)
        self.assertEqual(vm.reg_read(UC_X86_REG_EBP),STACK-4)
        self.assertEqual(vm.reg_read(UC_X86_REG_ESP),STACK-4-0x44)
        self.assertEqual(struct.unpack('<I',vm.mem_read(STACK-4,4))[0],1234)

    def test_end_game_submenu_draw_aligns_all_children_without_drift(self):
        vm=machine(self.patched)
        vector=OBJECT+0x100
        children=[OBJECT+0x200+i*0x100 for i in range(3)]
        vm.mem_write(OBJECT+8,struct.pack('<ii',495,25))
        vm.mem_write(OBJECT+0x30,struct.pack('<II',vector,vector+12))
        vm.mem_write(vector,struct.pack('<3I',*children))
        for i,child in enumerate(children):
            vm.mem_write(child+8,struct.pack('<ii',535,205+i*50))
        for x,y in ((495,145),(367,193),(495,145),(495,145)):
            vm.mem_write(OBJECT+0x3e,struct.pack('<hh',x,y))
            vm.reg_write(UC_X86_REG_ECX,OBJECT)
            vm.reg_write(UC_X86_REG_ESP,STACK)
            vm.emu_start(0x4594b0,0x4594b6,count=1000)
            for i,child in enumerate(children):
                self.assertEqual(struct.unpack('<hh',vm.mem_read(child+0x40,4)),(x+40,y+180+i*50))
            self.assertEqual(vm.reg_read(UC_X86_REG_EBP),STACK-4)

    def test_faction_buttons_pass_local_coordinates_to_create(self):
        for faction in range(3):
            for start, end, table in ((0x461b30,0x461b8c,0x4ff778),
                                      (0x461c65,0x461cc1,0x4ff790)):
                vm = machine(self.patched)
                vm.mem_write(0xb412cc,b'\x00')
                vm.mem_write(0x7f790d,bytes([faction]))
                vm.mem_write(0x106a5e4,struct.pack('<I',1))
                vm.mem_write(0x501ea0,struct.pack('<hh',240,120))
                vm.reg_write(UC_X86_REG_EBP,STACK+0x100)
                vm.mem_write(STACK+0x100-0x1c,struct.pack('<I',OBJECT))
                vm.reg_write(UC_X86_REG_ESP,STACK)
                vm.emu_start(start,end,count=1000)
                _, x, y = struct.unpack('<3i',vm.mem_read(STACK-12,12))
                expected = struct.unpack('<2i',vm.mem_read(table+faction*8,8))
                self.assertEqual((x,y),expected)
                vm.mem_write(OBJECT+8,struct.pack('<ii',x,y))
                call(vm,0x45b690)
                self.assertEqual(struct.unpack('<hh',vm.mem_read(OBJECT+0x40,4)),
                                 (x+240,y+120))

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
