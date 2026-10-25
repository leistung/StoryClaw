import unittest
from pydantic import ValidationError
from app.gateway.routers.ideation import DiscussionOut
class ChoiceQuestionTests(unittest.TestCase):
 def test_questions_are_structured_and_allow_multiple_answers(self):
  out=DiscussionOut.model_validate({'reply':'请选择你感兴趣的方向。','questions':[{'question':'想探索什么类型？','options':['现实生活','幻想冒险','悬疑推理'],'multiple':True}]})
  self.assertTrue(out.questions[0].multiple)
  self.assertEqual(out.questions[0].options[1],'幻想冒险')
 def test_legacy_reply_has_no_questions(self):
  self.assertEqual(DiscussionOut(reply='继续聊聊。').questions,[])
 def test_reject_unusable_choice_count(self):
  with self.assertRaises(ValidationError):DiscussionOut.model_validate({'reply':'请选择','questions':[{'question':'选择类型','options':['只有一个']}]})
