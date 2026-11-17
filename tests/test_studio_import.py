import copy
import json
from pathlib import Path
import tempfile
import unittest
from studio_import import read_manifest


class StudioManifestTests(unittest.TestCase):
    def setUp(self):
        self.data={'format':'clubvixen.studio-character.v1','bones':[{'parent':-1}],
                   'materials':[{'textures':[]}], 'meshes':[{'vertices':[{}, {}, {}],
                     'skin':[{'bones':[0],'weights':[1]} for _ in range(3)],
                     'parts':[{'material':0,'indices':[0,1,2]}]}]}
    def read(self,data):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'character.studio.json'; p.write_text(json.dumps(data))
            return read_manifest(p)
    def test_accepts_complete_structure(self):
        self.assertEqual(len(self.read(self.data)['meshes']),1)
    def test_rejects_bone_cycles_and_missing_weights(self):
        bad=copy.deepcopy(self.data); bad['bones'][0]['parent']=0
        with self.assertRaisesRegex(ValueError,'acyclic'): self.read(bad)
        bad=copy.deepcopy(self.data); bad['meshes'][0]['skin'][0]['bones']=[3]
        with self.assertRaisesRegex(ValueError,'missing bone'): self.read(bad)
    def test_rejects_missing_texture(self):
        self.data['materials'][0]['textures']=[{'file':'textures/missing.png'}]
        with self.assertRaisesRegex(ValueError,'texture missing'): self.read(self.data)
    def test_rejects_bad_triangle(self):
        self.data['meshes'][0]['parts'][0]['indices']=[0,1,99]
        with self.assertRaisesRegex(ValueError,'triangle'): self.read(self.data)


if __name__ == '__main__': unittest.main()
