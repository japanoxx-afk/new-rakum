from pathlib import Path
import struct
import unittest
from map_textures import TerrainTextures,read_asset,sprites565
from rkm_format import RkmMap


class TextureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maps=list(Path(r'C:\Program Files (x86)\TriggerSoft\RhakMu\Data\Maps').glob('*.rkm'))
        if not cls.maps:raise unittest.SkipTest('Local game assets unavailable')
        cls.themes={i:TerrainTextures(i) for i in range(4)}

    def test_all_maps_render_with_resource_images(self):
        for path in self.maps:
            with self.subTest(map=path.name):
                model=RkmMap(path.read_bytes());theme=struct.unpack_from('<I',model.data,76)[0]
                image=self.themes[theme].render(model,4)
                self.assertEqual(image.height,(model.rows*2+4)*4)
                self.assertGreater(len(image.getcolors(image.width*image.height)),100)
                for _,r in model.resources():
                    sprite,_,_=self.themes[theme].resources.get(struct.unpack_from('<H',r,4)[0])
                    self.assertIsNotNone(sprite.getbbox())

    def test_diamond_mask_has_exact_pixel_coverage(self):
        for theme in self.themes.values():
            tile=theme.tile(0)
            self.assertEqual(tile.size,(256,128))
            self.assertEqual(sum(a!=0 for a in tile.getchannel('A').getdata()),16384)
            with self.assertRaises(ValueError):theme.tile(theme.count)

    def test_transparent_texture_hit_testing(self):
        from map_editor import Editor
        from types import SimpleNamespace
        editor=Editor();editor.withdraw()
        try:
            editor.model=RkmMap(self.maps[0].read_bytes());editor.source=self.maps[0]
            editor.textures=self.themes[struct.unpack_from('<I',editor.model.data,76)[0]]
            editor.refresh_resources();editor.redraw();editor.update_idletasks()
            # Convert desired world canvas center into widget-local coordinates.
            x=20+4*editor.scale-editor.canvas.canvasx(0)
            y=20+2*editor.scale-editor.canvas.canvasy(0)
            item=editor.hit(SimpleNamespace(x=x,y=y))
            self.assertIsNotNone(item)
            self.assertEqual(editor.items[item],0)
        finally:editor.destroy()


if __name__=='__main__':unittest.main()
