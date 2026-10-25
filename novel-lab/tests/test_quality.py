import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from quality import count, fingerprint, validate_outline, chapter_checks
from run import save, read
import tempfile

class ManuscriptChecks(unittest.TestCase):
    def test_count_has_explicit_punctuation_and_markup_rules(self):
        self.assertEqual(count('<p>他走了。\n</p>'),4)
    def test_missing_and_duplicate_chapters_cannot_pass(self):
        with self.assertRaises(ValueError):validate_outline({'volumes':[{'chapters':[{'number':1,'title':'一','summary':'事件'},{'number':1,'title':'二','summary':'事件'}]}]},2)
    def test_placeholder_and_short_text_fail(self):
        result=chapter_checks('[待补充正文]',{'min_chapter_words':2500,'max_chapter_words':3300})
        self.assertTrue(result['errors'])
    def test_garbled_or_truncated_output_rejected(self):
        case={'min_chapter_words':10,'max_chapter_words':10000}
        text='\n\n'.join(['他在窑口等父亲。']*10)+('A1*?B9'*100)
        self.assertTrue(any('比例异常' in e for e in chapter_checks(text,case)['errors']))
        self.assertTrue(any('截断' in e for e in chapter_checks('\n\n'.join(['他在窑口等父亲']*10),case)['errors']))
    def test_atomic_checkpoint_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';save(path,{'chapters':{'1':{'indexed':True}}})
            self.assertEqual(read(path)['chapters']['1']['indexed'],True)
            self.assertFalse(path.with_suffix('.json.tmp').exists())
