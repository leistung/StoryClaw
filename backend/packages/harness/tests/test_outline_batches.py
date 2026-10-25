import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from storyclaw.workflows.outline import plan_outline
class BatchOutline(unittest.IsolatedAsyncioTestCase):
 async def test_bounded_batches_carry_previous_plot(self):
  prompts=[]
  async def respond(state,system,prompt):
   prompts.append(prompt);first=1+10*(len(prompts)-1);last=min(first+9,25)
   data={'volumes':[{'name':'卷','chapters':[{'number':n,'title':f'窑火{n}','summary':'父子在窑口劳作。'} for n in range(first,last+1)]}]}
   return json.dumps(data,ensure_ascii=False),1,1,'mock'
  with patch('storyclaw.workflows.outline.llm_respond',respond):result=await plan_outline({'book_meta':{'target_chapters':25}})
  self.assertIsNone(result['error']);self.assertEqual(len(prompts),3)
  self.assertIn('窑火1',prompts[1]);self.assertIn('第 21 到 25 章',prompts[2])
 async def test_invalid_response_retried_but_never_success(self):
  calls=[]
  async def respond(*args):calls.append(1);return '{broken',1,1,'mock'
  with patch('storyclaw.workflows.outline.llm_respond',respond):result=await plan_outline({'book_meta':{'target_chapters':40}})
  self.assertEqual(len(calls),2);self.assertTrue(result['error'])
if __name__=='__main__':unittest.main()
