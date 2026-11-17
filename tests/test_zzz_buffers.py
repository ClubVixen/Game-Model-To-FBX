import struct
import tempfile
import unittest
from pathlib import Path
from multigame import validate_zzz_buffers

class BufferValidationTests(unittest.TestCase):
    def fixture(self, root, indices=(0,1,2), offset=0):
        p=Path(root)/'Body.ib'
        p.write_bytes(struct.pack('<%dI'%len(indices),*indices))
        p.with_suffix('.vb0').write_bytes(bytes(36))
        p.with_suffix('.fmt').write_text('stride: 12\ntopology: trianglelist\nformat: DXGI_FORMAT_R32_UINT\nelement[0]:\n SemanticName: POSITION\n SemanticIndex: 0\n Format: R32G32B32_FLOAT\n InputSlot: 0\n AlignedByteOffset: %d\n'%offset)
        return p
    def test_bad_index_fails_before_import(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'exceeds 3 vertices'):
                validate_zzz_buffers(self.fixture(d,(0,1,3)))
    def test_layout_overflow_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'exceeds vertex layout'):
                validate_zzz_buffers(self.fixture(d,offset=4))
    def test_selected_draw_excludes_inactive_variant(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.fixture(d,(0,1,2,9,10,11))
            validate_zzz_buffers(p,[[3,0,0]])
            self.assertEqual(struct.unpack('<3I',p.read_bytes()),(0,1,2))
    def test_invalid_range_does_not_modify_input(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.fixture(d); original=p.read_bytes()
            with self.assertRaisesRegex(ValueError,'invalid drawindexed'):
                validate_zzz_buffers(p,[[6,0,0]])
            self.assertEqual(p.read_bytes(),original)

if __name__=='__main__': unittest.main()
