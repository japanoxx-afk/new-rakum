import struct
import unittest
from command_path_diagnostics import decode,summarize

class CommandDiagnosticsTests(unittest.TestCase):
    def test_native_offsets_and_local_slots(self):
        for local in range(8):
            data=bytearray(0x1470)
            struct.pack_into('<I',data,0x38,42)
            struct.pack_into('<h',data,0x48,4)
            base=0x50+local*0x284
            struct.pack_into('<2h2x2x2x2x2I',data,base+0x10,9,4,123,124)
            row=decode(data,77,local)
            self.assertEqual(row['batch_sequence'],42)
            self.assertEqual(row['latency_turns'],4)
            self.assertEqual(row['player_counters'],(9,4))
            self.assertEqual(row['player_sequence_counters'],(123,124))
        with self.assertRaises(ValueError):decode(data,0,-1)

    def test_measurement_does_not_mislabel_network_latency(self):
        rows=[dict(ms=ms,batch_sequence=seq,latency_turns=4) for ms,seq in ((0,1),(20,1),(100,2),(200,3),(700,8),(800,9))]
        result=summarize(rows)
        self.assertEqual(result['batch_interval_median_ms'],100)
        self.assertEqual(result['latency_values'],[4])
        self.assertIn('not click-to-action',result['warning'])

if __name__=='__main__':unittest.main()
