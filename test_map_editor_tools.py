from pathlib import Path
from types import SimpleNamespace
import struct
import tempfile
import tkinter as tk
import unittest
from rkm_format import RkmMap
from terrain_palette import TerrainPalette,CATEGORIES

MAPS=Path(r'C:\Program Files (x86)\TriggerSoft\RhakMu\Data\Maps')


class EditingToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths=list(MAPS.glob('*.rkm'))
        if not cls.paths:raise unittest.SkipTest('Installed maps missing')

    def test_palette_all_records_preserved_and_condensed(self):
        for path in self.paths:
            model=RkmMap(path.read_bytes());catalog=TerrainPalette(model)
            self.assertEqual(tuple(catalog.groups),CATEGORIES)
            records=[r for families in catalog.groups.values() for variants in families.values() for r in variants]
            self.assertCountEqual(records,model.palette)
            self.assertLess(sum(len(f) for f in catalog.groups.values()),len(model.palette))
            for record in records:
                category,family,n=catalog.locate(record)
                self.assertEqual(catalog.groups[category][family][n],record)

    def test_start_move_roundtrip_only_coordinates_change(self):
        for path in self.paths:
            with self.subTest(map=path.name):
                model=RkmMap(path.read_bytes());old=bytes(model.data)
                points=model.start_points()
                self.assertEqual(len(points),model.data[89])
                target=next((x,10) for x in range(10,30) if (x,10) not in points)
                previous=model.set_start_point(0,*target)
                self.assertEqual(previous,points[0])
                at=model.sections[1][0]+270
                self.assertEqual(model.data[:at],old[:at])
                self.assertEqual(model.data[at+4:],old[at+4:])
                # Exercise shifted subsequent section offsets too.
                model.add_resource(model.resource_templates()[0],8,8,1234)
                with tempfile.TemporaryDirectory() as folder:
                    dest=Path(folder)/'starts.rkm';model.export(dest)
                    loaded=RkmMap(dest.read_bytes())
                    self.assertEqual(loaded.start_points(),[target]+points[1:])

    def test_start_rejects_invalid_duplicate_and_other_player_metadata(self):
        model=RkmMap(self.paths[0].read_bytes())
        for player,x,y in ((-1,10,10),(100,10,10),(0,0,0),(0,10000,10),(0,1.5,10)):
            with self.assertRaises(ValueError):model.set_start_point(player,x,y)
        with self.assertRaises(ValueError):model.set_start_point(0,*model.start_points()[1])
        model.data[model.sections[1][0]+265]^=1
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):model.export(Path(folder)/'bad.rkm')

    def test_editor_selection_start_undo_and_blank_map(self):
        from map_editor import Editor
        editor=Editor();editor.withdraw()
        try:
            model=RkmMap.new_blank(self.paths[0].read_bytes())
            editor.load_model(model,self.paths[0],None)
            editor.update_idletasks()
            for category in CATEGORIES:
                editor.category.set(category);editor.refresh_families()
                if editor.family_names:
                    self.assertIn(editor.selected_record(),model.palette)
            before=bytes(model.data)
            editor.mode.set('시작 위치')
            x,y=10,10
            event=SimpleNamespace(type=tk.EventType.ButtonPress,
                x=x*editor.scale+20-editor.canvas.canvasx(0),
                y=y*editor.scale+20-editor.canvas.canvasy(0))
            editor.paint(event)
            self.assertEqual(model.start_points()[0],(x,y))
            editor.undo();self.assertEqual(bytes(model.data),before)
            self.assertEqual(len(editor.player_palette['values']),len(model.start_points()))
        finally:editor.destroy()


if __name__=='__main__':unittest.main()
