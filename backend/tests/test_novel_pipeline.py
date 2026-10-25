import unittest
from pydantic import ValidationError
from storyclaw.nodes.supervisor import supervisor
from storyclaw.runtime import fresh_input
from storyclaw.outline import validate_outline
from app.services.scene_plan import ChapterScenePlan

class NovelPipelineContracts(unittest.TestCase):
    def test_explicit_operations_override_prompt_keywords(self):
        for intent in ('write','polish','continue','modify','assist'):
            state={'intent':intent,'chapter_id':1,'active_skill':'brainstorm','messages':[{'role':'user','content':'不要修改设定，请给出灵感，并进行一致性检查'}]}
            self.assertEqual(supervisor(state)['intent'], intent)

    def test_new_request_does_not_inherit_old_review_or_intent(self):
        state=fresh_input({'messages':[]})
        self.assertIsNone(state['intent'])
        self.assertEqual(state['review_round'],0)
        self.assertEqual(state['draft_content'],'')

    def test_template_and_missing_chapters_rejected(self):
        with self.assertRaises(ValueError): validate_outline({'volumes':[{'chapters':[{'number':1,'title':'待定','summary':'模板'}]}]},1)
        with self.assertRaises(ValueError): validate_outline({'volumes':[{'chapters':[{'number':2,'title':'窑口','summary':'第一章'}]}]},2)

    def test_scene_contract_requires_actionable_beats(self):
        with self.assertRaises(ValidationError):ChapterScenePlan.model_validate({'scenes':[{'title':'空场景'}]})

class WritingRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_short_fragments_do_not_trigger_full_chapter_expansion(self):
        from storyclaw.nodes.reviewer import reviewer
        for skill in ('continue-writing','polish-chapter'):
            result=await reviewer({'active_skill':skill,'draft_content':'他把火罐放在灶边。','context':{'chapter_meta':{'per_chapter_words':2800}}})
            self.assertEqual(result['status'],'finished')

    async def test_oversized_chapter_requests_compression(self):
        from storyclaw.nodes.reviewer import reviewer
        result=await reviewer({'active_skill':'write-chapter','draft_content':'窑火。'*2000,'context':{'chapter_meta':{'per_chapter_words':2800}}})
        self.assertEqual(result['status'],'review_retry')
        self.assertIn('压缩',result['review_feedback'])

    async def test_assistant_templates_preserve_examples(self):
        from storyclaw import prompts
        self.assertIn('3',prompts.ASSIST_BRAINSTORM_SYSTEM.format(count=3))
        self.assertIn('标题',prompts.ASSIST_TITLE_SYSTEM.format(count=3,style='朴素',target='章节'))
