import struct
import tempfile
import unittest
from pathlib import Path
import msgpack
from card_reader import inspect_card


class Cards(unittest.TestCase):
    def check_bytes(self, data):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)/'card.png'
            p.write_bytes(data)
            return inspect_card(p)

    def test_plain_png_is_not_card(self):
        with self.assertRaisesRegex(ValueError, 'payload'):
            self.check_bytes(b'\x89PNG\r\n\x1a\n' + b'\0\0\0\0IEND\0\0\0\0')

    def test_bounds(self):
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            self.check_bytes(b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 999999) + b'IDAT1234')

    def test_plugins_without_loading_game(self):
        extra = msgpack.packb({'example.plugin': [1, {}]})
        header = msgpack.packb({'lstInfo': [{'name': 'KKEx', 'pos': 0, 'size': len(extra)}]})
        marker = '【KoiKatuChara】'.encode()
        data = b'\x89PNG\r\n\x1a\n\0\0\0\0IEND\0\0\0\0'
        data += struct.pack('<i',100) + bytes([len(marker)]) + marker + b'\x050.0.0'
        data += struct.pack('<ii', 0, len(header)) + header + struct.pack('<q',len(extra)) + extra
        result = self.check_bytes(data)
        self.assertEqual(result['plugins'], ['example.plugin'])
        self.assertTrue(result['requires_game_assembly'])


if __name__ == '__main__': unittest.main()
