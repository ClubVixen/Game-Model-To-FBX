import unittest, tempfile, sys
from pathlib import Path
from unittest.mock import patch
import multigame
class UnifiedTests(unittest.TestCase):
 def test_reader_frozen_uses_worker(self):
  with patch.object(sys,'frozen',True,create=True):
   self.assertEqual(multigame.reader_command({})[1],'--worker-script')
 def test_missing_vrf_is_actionable(self):
  with self.assertRaisesRegex(FileNotFoundError,'Source 2 Viewer CLI'):
   multigame.inspect('missing.vpk','deadlock',{})
 def test_rivals_inspect_companions(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'sample.utoc';p.touch()
   self.assertEqual(multigame.inspect(d,'rivals',{})['missing_companions'],[str(p.with_suffix('.ucas'))])
 def test_rivals_batch_continues_after_failure(self):
  with patch('converter.discover',return_value=['a.utoc','b.utoc']), patch('multigame.required_file',return_value='blender'), patch('converter.convert',side_effect=[RuntimeError('bad input'),'result']) as convert:
   with self.assertRaisesRegex(RuntimeError,'1 succeeded'):
    multigame.convert('source','rivals','out',{})
   self.assertEqual(convert.call_count,2)
if __name__=='__main__':unittest.main()
