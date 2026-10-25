import unittest
from unittest.mock import AsyncMock
from storyclaw.workflows.ideation.workflow import ideation_graph
from storyclaw.workflows.ideation.workflow import story
from storyclaw.workflows.ideation.workflow import GENRES
class DirectorTests(unittest.IsolatedAsyncioTestCase):
 async def test_two_interviews_then_draft(self):
  model=AsyncMock(return_value='proposal')
  first=await ideation_graph.ainvoke({'round':0,'mode':'discuss','draft_tool':model})
  self.assertEqual(first['action'],'preferences');self.assertEqual(first['questions'][0]['id'],'genre');self.assertIn('历史',first['questions'][0]['options'])
  second=await ideation_graph.ainvoke({'round':1,'mode':'discuss','genre':'历史','draft_tool':model})
  self.assertEqual(second['action'],'story');self.assertIn('架空历史',second['questions'][0]['options']);self.assertNotIn('修炼成长',str(second['questions']))
  third=await ideation_graph.ainvoke({'round':2,'mode':'discuss','genre':'历史','draft_tool':model})
  self.assertEqual(third['result'],'proposal');self.assertEqual(third['questions'],[]);model.assert_awaited_once()
 async def test_revisions_and_early_proposals_do_not_restart_questions(self):
  for payload in ({'mode':'revise'},{'mode':'proposal'},{'mode':'discuss','has_proposal':True},{'mode':'discuss','round':10}):
   result=await ideation_graph.ainvoke({**payload,'draft_tool':AsyncMock(return_value='updated')})
   self.assertEqual(result['action'],'draft');self.assertFalse(result['questions'])
 def test_every_genre_has_relevant_grouped_questions(self):
  for genre in GENRES:
   questions=story(genre);self.assertEqual(len(questions),3)
   self.assertEqual([q['id'] for q in questions],['subgenre','protagonist','conflict'])
