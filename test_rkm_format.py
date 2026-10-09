from pathlib import Path
import tempfile
import unittest
from rkm_format import RkmMap

MAPS=Path(r'C:\Program Files (x86)\TriggerSoft\RhakMu\Data\Maps')


class MapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths=list(MAPS.glob('*.rkm'))
        if not cls.paths:raise unittest.SkipTest('Installed RKM samples missing')

    def test_all_installed_maps_round_trip(self):
        for path in self.paths:
            with self.subTest(map=path.name):
                data=path.read_bytes()
                model=RkmMap(data)
                self.assertEqual(bytes(model.data),data)
                with tempfile.TemporaryDirectory() as folder:
                    dest=Path(folder)/'copy.rkm'
                    model.export(dest,path)
                    self.assertEqual(dest.read_bytes(),data)

    def test_only_selected_record_changes(self):
        model=RkmMap(self.paths[0].read_bytes())
        record=next(r for r in model.palette if r!=model.record(0))
        before=model.paint(0,record)
        self.assertEqual(model.data[:model.start],model.original[:model.start])
        self.assertEqual(model.data[model.start+5:],model.original[model.start+5:])
        model.paint(0,before)
        self.assertEqual(bytes(model.data),model.original)

    def test_no_overwrite_and_reject_unknown_records(self):
        model=RkmMap(self.paths[0].read_bytes())
        with self.assertRaises(ValueError):model.export(self.paths[0],self.paths[0])
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'test.rkm'
            model.export(target)
            with self.assertRaises(FileExistsError):model.export(target)
        with self.assertRaises(ValueError):model.paint(0,b'\xff'*5)
        with self.assertRaises(IndexError):model.paint(-1,model.palette[0])

    def test_invalid_header_and_offset_refused(self):
        data=self.paths[0].read_bytes()
        for damaged in (b'bad',b'WGM!'+data[4:],data[:20],data[:16]+b'\xff'*4+data[20:]):
            with self.assertRaises(ValueError):RkmMap(damaged)

    def test_resource_add_delete_preserves_other_chunks_all_maps(self):
        for path in self.paths:
            with self.subTest(map=path.name):
                model=RkmMap(path.read_bytes())
                if not model.resources():continue
                before=model.objects()
                template=model.resources()[0][1]
                occupied={tuple(__import__('struct').unpack_from('<II',r,8)) for _,r in model.resources()}
                x,y=next((x,y) for y in range(4,model.height-4) for x in range(4,model.width-4) if (x,y) not in occupied)
                model.add_resource(template,x,y)
                self.assertEqual(len(model.objects()),len(before)+1)
                self.assertEqual(len(model.data),len(model.original)+20)
                with tempfile.TemporaryDirectory() as folder:
                    target=Path(folder)/'resource.rkm';model.export(target,path)
                    loaded=RkmMap(target.read_bytes())
                    self.assertEqual(loaded.objects()[:-1],before)
                model.remove_resource(len(model.objects())-1)
                self.assertEqual(bytes(model.data),model.original)

    def test_resource_rejects_edges_and_nonresource_deletion(self):
        model=RkmMap(self.paths[0].read_bytes())
        template=model.resources()[0][1]
        with self.assertRaises(ValueError):model.add_resource(template,-1,4)
        with self.assertRaises(ValueError):model.add_resource(template,model.width,4)
        index=next(i for i,r in enumerate(model.objects()) if r[2]!=7)
        with self.assertRaises(ValueError):model.remove_resource(index)

    def test_exactly_two_resource_types_and_custom_amount_roundtrip(self):
        import struct
        for path in self.paths:
            model=RkmMap(path.read_bytes())
            self.assertEqual(len(model.resource_templates()),2)
            index,_=model.resources()[0]
            model.set_resource_amount(index,12345)
            self.assertEqual(struct.unpack_from('<I',model.objects()[index],16)[0],12345)
            self.assertEqual(len(model.resource_templates()),2)
            with tempfile.TemporaryDirectory() as folder:
                target=Path(folder)/'amount.rkm';model.export(target)
                self.assertEqual(struct.unpack_from('<I',RkmMap(target.read_bytes()).objects()[index],16)[0],12345)
            for invalid in (0,-1,1000001,1.5,True):
                with self.assertRaises(ValueError):model.set_resource_amount(index,invalid)

    def test_new_blank_preserves_start_preset_and_removes_objects(self):
        import struct
        for path in self.paths:
            old=RkmMap(path.read_bytes());new=RkmMap.new_blank(old.data)
            self.assertEqual((old.width,old.height),(new.width,new.height))
            self.assertEqual(new.objects(),[])
            self.assertEqual(new.resources(),[])
            self.assertEqual(len(new.resource_templates()),2)
            a,b=old.sections[1];c,d=new.sections[1]
            self.assertEqual(old.data[a:b],new.data[c:d])
            self.assertEqual(len({new.record(i) for i in range(new.rows*new.columns)}),1)
            a,b=new.sections[6];self.assertEqual(new.data[a:b],bytes(4))
            new.add_resource(new.resource_templates()[0],10,10,6789)
            self.assertEqual(struct.unpack_from('<I',new.resources()[0][1],16)[0],6789)
            with tempfile.TemporaryDirectory() as folder:new.export(Path(folder)/'new.rkm')


if __name__=='__main__':unittest.main()
