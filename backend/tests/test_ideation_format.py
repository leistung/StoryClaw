import unittest
from app.services.ideation_format import parse_ideation_json
class IdeationFormatTests(unittest.TestCase):
 def test_literal_newlines_and_trailing_comma(self):
  raw='{"reply":"你好。\n\n请选择。","questions":[{"question":"想写什么？","options":["现实", "幻想",],}],}'
  result=parse_ideation_json(raw)
  self.assertEqual(result['reply'],'你好。\n\n请选择。')
  self.assertEqual(result['questions'][0]['options'],['现实','幻想'])
 def test_wrapped_json(self):
  self.assertEqual(parse_ideation_json('以下是回复：\n```json\n{"reply":"好", "questions": []}\n```')['reply'],'好')
 def test_prose_punctuation_unchanged(self):
  self.assertEqual(parse_ideation_json('{"reply":"保留 ,} 和 \\\"引号\\\""}')['reply'],'保留 ,} 和 "引号"')
 def test_truncated_output_not_invented(self):
  with self.assertRaises(ValueError):parse_ideation_json('{"reply":"还没有结束')
 def test_plain_text_not_mistaken_for_proposal(self):
  with self.assertRaises(ValueError):parse_ideation_json('普通文本，不是结构化数据')
 def test_missing_reply_rejected(self):
  with self.assertRaises(ValueError):parse_ideation_json('{"proposal":{}}')
