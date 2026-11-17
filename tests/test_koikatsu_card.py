import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
import msgpack
from kkloader import KoikatuCharaData
from koikatsu_card import convert_sunshine, audit_dependencies


def fixture(version='0.0.6'):
    dependencies = [{'ModID':'test.hair','Property':'outfit0.accessory2'},
                    {'ModID':'test.hat','Property':'outfit0.accessory3'},
                    {'ModID':'other.outfit','Property':'outfit1.accessory0'}]
    blocks = [('Parameter',version,msgpack.packb({'version':version,'fullname':'Example'})),
              ('KKEx','0.0.0',msgpack.packb({'com.bepis.sideloader.universalautoresolver':
                  [1,{'info':[msgpack.packb(d) for d in dependencies]}]})),
              ('FuturePlugin','9.0',b'opaque plugin data')]
    entries, payload = [], b''
    for name, ver, data in blocks:
        entries.append(dict(name=name,version=ver,pos=len(payload),size=len(data)))
        payload += data
    header=msgpack.packb({'lstInfo':entries})
    marker='【KoiKatuCharaSun】'.encode()
    return (b'\x89PNG\r\n\x1a\n\0\0\0\0IEND\0\0\0\0' + struct.pack('<i',100)
            +bytes([len(marker)])+marker+b'\x050.0.0'+struct.pack('<ii',0,len(header))
            +header+struct.pack('<q',len(payload))+payload)


class Compatibility(unittest.TestCase):
    def test_versions_and_opaque_data_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            src,dst=Path(root)/'source.png',Path(root)/'converted.png'
            original=fixture(); src.write_bytes(original)
            result=convert_sunshine(src,dst)
            self.assertTrue(result['changed'])
            self.assertEqual(src.read_bytes(),original)
            card=KoikatuCharaData.load(str(dst))
            self.assertEqual(card.Parameter.version,'0.0.5')
            self.assertEqual(card['Parameter']['version'],'0.0.5')
            self.assertEqual(card.FuturePlugin.serialize()[0],b'opaque plugin data')
            for target in (src,dst):
                with self.assertRaisesRegex(ValueError,'never overwritten'):
                    convert_sunshine(src,target)

    def test_missing_accessory_and_outfit_filter(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); card=root/'source.png'; card.write_bytes(fixture())
            with zipfile.ZipFile(root/'hair.zipmod','w') as z:
                z.writestr('manifest.xml','<manifest><guid>test.hair</guid></manifest>')
            report=audit_dependencies(card,root,0)
            self.assertEqual(report['missing'],['test.hat'])
            self.assertEqual(len(report['dependencies']),2)
            self.assertTrue(report['dependencies'][0]['installed_packages'])

    def test_unknown_version_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            src=Path(root)/'source.png'; src.write_bytes(fixture('9.0.0'))
            with self.assertRaisesRegex(ValueError,'Unsupported Parameter'):
                convert_sunshine(src,Path(root)/'out.png')


if __name__ == '__main__': unittest.main()
