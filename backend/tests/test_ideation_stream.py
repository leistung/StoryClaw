import json,unittest
from app.api.ideation import partial_reply
class PartialReplyTests(unittest.TestCase):
 def test_every_json_boundary_preserves_complete_prefix(self):
  reply='你好。\n\n1. 喜欢什么？\n\n2. 想写什么？ "记忆" \\ 灯火🔥'
  raw=json.dumps({'reply':reply,'proposal':None},ensure_ascii=True)
  previous=''
  for end in range(len(raw)+1):
   value=partial_reply(raw[:end]);self.assertTrue(reply.startswith(value));self.assertTrue(value.startswith(previous));value.encode('utf-8');previous=value
  self.assertEqual(previous,reply)
 def test_literal_unicode_and_proposal_not_leaked(self):
  self.assertEqual(partial_reply('{"reply":"分段\\n\\n提问","proposal":{"title":"秘密"}}'),'分段\n\n提问')
  self.assertEqual(partial_reply('{"proposal":null}'),'')
