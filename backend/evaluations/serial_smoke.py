#!/usr/bin/env python3
"""Real-model rolling-writing acceptance. Private sample only; explicit approval required.

State/receipts allow resuming the same jobs without duplicate paid generation.
No tokens or passwords are written to artifacts. This tests plumbing and basic
quality checks, not a guarantee of literary merit or historical consistency.
"""
import argparse,hashlib,html,json,os,re,time,uuid
from pathlib import Path
import importlib.util
_continuity_spec=importlib.util.spec_from_file_location('storyclaw_continuity',Path(__file__).resolve().parents[1]/'packages/harness/storyclaw/workflows/continuity.py')
_continuity=importlib.util.module_from_spec(_continuity_spec);_continuity_spec.loader.exec_module(_continuity)
repetition_evidence=_continuity.repetition_evidence
from urllib.request import Request,urlopen
from urllib.error import HTTPError

class Failure(Exception):pass

def plain(value):
    return html.unescape(re.sub('<[^>]*>','',value.replace('</p>','\n\n'))).strip()
def sha(value):return hashlib.sha256(value.encode()).hexdigest()

class Run:
 def __init__(self,args):
  self.args=args;self.root=args.output;self.root.mkdir(parents=True,exist_ok=True)
  self.path=self.root/'state.json'
  self.state=json.loads(self.path.read_text()) if self.path.exists() else {'run_id':str(uuid.uuid4()),'jobs':{},'receipts':{},'chapter_ids':[],'checks':{},'cost':0}
  self.token='';self.save()
 def save(self):self.path.write_text(json.dumps(self.state,ensure_ascii=False,indent=2))
 def event(self,text):print(time.strftime('%H:%M:%S'),text,flush=True)
 def api(self,method,path,body=None,expected=200):
  request=Request(self.args.base_url+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,method=method,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+self.token} if self.token else {})})
  try:
   with urlopen(request,timeout=90) as response:status=response.status;result=json.load(response)
  except HTTPError as exc:
   status=exc.code
   try:result=json.loads(exc.read())
   except Exception:result={'error':{'message':'HTTP request failed'}}
  if status!=expected:raise Failure(f'{method} {path}: HTTP {status}, '+json.dumps(result,ensure_ascii=False)[:500])
  return result
 def job(self,name,kind,cid=None,**extra):
  if self.state['cost']>=self.args.max_credits:raise Failure('平台积分测试预算已到上限，不再发起任务')
  entry=self.state['jobs'].setdefault(name,{'request_id':str(uuid.uuid4())});self.save()
  if not entry.get('id'):
   result=self.api('POST','/jobs',{'book_id':self.state['book_id'],'kind':kind,'request_id':entry['request_id'],**({'chapter_id':cid} if cid else {}),**extra})
   entry['id']=result['id'];self.save()
  deadline=time.monotonic()+1000;last='';heartbeat=0
  while time.monotonic()<deadline:
   result=self.api('GET','/jobs/'+entry['id'])
   if result['status']!=last or time.monotonic()-heartbeat>30:
    self.event(f'{name}: {result["status"]}');last=result['status'];heartbeat=time.monotonic()
   if result['status']=='succeeded':
    if name not in self.state['receipts']:
     self.state['cost']+=int((result.get('result') or {}).get('credits_cost',0))
     self.state['receipts'][name]=result;self.save()
    (self.root/'receipts').mkdir(exist_ok=True)
    (self.root/'receipts'/f'{name}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result.get('result') or {}
   if result['status'] in ('failed','cancelled'):raise Failure(f'{name}: {result.get("error") or result["status"]}; 不自动重试付费任务，请核对回执')
   time.sleep(3)
  raise Failure(name+' 超过等待时间；保留任务ID，下次恢复查询，不重复提交')
 def index(self,cid,label):
  detail=self.api('GET',f'/chapters/{cid}')
  if detail['rag_status']=='loaded':return
  self.job(label,'index',cid,reviewed_hash=detail['content_hash'])
  current=self.api('GET',f'/chapters/{cid}')
  if current['rag_status']!='loaded':raise Failure('索引未成功持久写入')
 def run(self):
  if not self.args.approve_test_output:raise Failure('真实测试需要 --approve-test-output 显式授权采用样书规划与通过检查的章节')
  password=os.environ.get('STORYCLAW_PASSWORD')
  if not password:raise Failure('请通过 STORYCLAW_PASSWORD 提供测试账号密码，不写入测试报告')
  login=self.api('POST','/auth/login',{'username':self.args.username,'password':password});self.token=login['token']
  self.state['user_id']=login['user']['id'];self.save()
  marker='serial-lab:'+self.state['run_id']
  title='雾港收潮人·流程样书'
  if not self.state.get('book_id'):
   found=next((b for b in self.api('GET','/books') if marker in (b.get('intro') or '')),None)
   if not found:
    found=self.api('POST','/books',{'title':title,'genre':'玄幻','intro':marker+'\n原创东方幻想：雾港靠潮灯辨认航道。年轻修灯匠沈照为了查清父亲失踪的原因，接手一盏无法熄灭的旧潮灯。每次借灯读出潮汐留下的记忆，灯主会失去一段与海有关的私人记忆；代价不可随意免除。她要在不伤害邻里、不轻率断言父亲生死的前提下调查旧码头失灯案。以修灯、谋生、邻里关系和具体调查推动情节，不使用现代网络词汇，不模仿任何现有作品。长期谜团分阶段展开，当前只是第一阶段，不提前找到父亲或结束全书。','protagonist_name':'沈照','protagonist_intro':'二十二岁的女修灯匠，善于辨认灯纹，倔强而重承诺，父亲失踪，母亲在世；她尚不知道旧港契约真相。','target_chapters':12,'target_words':30000,'per_chapter_words':2500,'generate_outline':False,'generate_plots':False,'generate_characters':False})
   self.state['book_id']=found['id'];self.save()
  bid=self.state['book_id'];self.event(f'私密样书 #{bid}，计划三万字阶段，先测试 {self.args.chapters} 章')
  self.job('framework','outline',planning_mode='serial')
  outline=self.api('GET',f'/books/{bid}/outline')['content']
  if outline.get('planning_mode')!='serial' or any(v.get('chapters') for v in outline['volumes']):raise Failure('框架不应预生成全部章纲')
  if not outline.get('_review'):self.api('POST',f'/books/{bid}/outline/confirm',{'content':outline})
  self.state['checks']['framework_without_fixed_chapters']=True;self.save()
  for kind in ('world','character'):
   self.job(kind,'story-design',design_type=kind)
   self.api('POST',f'/jobs/{self.state["jobs"][kind]["id"]}/adopt',{})
  existing=self.api('GET',f'/chapters/books/{bid}')
  while len(self.state['chapter_ids'])<self.args.chapters:
   number=len(self.state['chapter_ids'])+1
   found=next((c for c in existing if c['number']==number),None)
   if not found:found=self.api('POST',f'/chapters/books/{bid}',{'title':f'第{number}章 潮灯纪事'})
   self.state['chapter_ids'].append(found['id']);self.save()
  for number,cid in enumerate(self.state['chapter_ids'][:self.args.chapters],1):
   if not self.state['checks'].get(f'gate-{number}'):
    self.api('POST','/jobs',{'book_id':bid,'chapter_id':cid,'kind':'generate','request_id':str(uuid.uuid4())},expected=409)
    self.state['checks'][f'gate-{number}']=True;self.save()
   self.job(f'blueprint-{number}','chapter-outline',cid,prompt=('本章从修灯的具体生活困境切入，呈现代价规则，留下可追索线索。' if number==1 else '结合上章结尾，推进一个实际调查行动，回应一个此前线索，同时保留长期谜团；不要重复上章情节，也不要为了暂定章数提前完结。'))
   bp=self.api('GET',f'/chapters/{cid}/blueprint')
   if not bp['confirmed']:
    if bp['stale']:raise Failure('章纲参考已变化，需要核对后重新规划，不能自动确认过期稿')
    self.api('POST',f'/chapters/{cid}/blueprint/confirm',bp['plan'])
   if number%2:self.job(f'scenes-{number}','scene-plan',cid)
   self.job(f'write-{number}','generate',cid,prompt='请写本章。依据已经确认的本章情节完成完整正文，约2500字，目标2300到2800字。不要标题、说明或字数统计，不超出本章事件。用自然段呈现行动、对话与细节，不重复前章已经完成的事件，不擅自改变人物亲属关系或免除能力代价。')
   detail=self.api('GET',f'/chapters/{cid}');body=plain(detail['content'])
   if number>1:
    previous=plain(self.api('GET',f'/chapters/{self.state["chapter_ids"][number-2]}')['content'])
    evidence=repetition_evidence(body,previous)
    self.state['checks'][f'repetition-{number}']=evidence;self.save()
    if evidence['warning']:raise Failure(f'第{number}章有跨章重复风险：{evidence}，停止自动确认入库，先核对修订')
   if len(re.sub(r'\s+','',body))<1500:raise Failure(f'第{number}章正文过短，保留结果等待核对，不重复收费生成')
   if any(x in body for x in ('作为AI','作为一个AI','以下是生成的')):raise Failure('正文包含模型说明')
   (self.root/'chapters').mkdir(exist_ok=True);(self.root/'chapters'/f'{number:03}.md').write_text(body)
   self.state['checks'][f'chapter-{number}']={'id':cid,'words':detail['word_count'],'hash':sha(body),'blueprint_confirmed':True,'scene_plan_optional':bool(number%2)};self.save()
   self.index(cid,f'index-{number}')
   query=body[max(0,len(body)//2):len(body)//2+90]
   memory=self.api('POST','/rag/query',{'book_id':bid,'query':query,'top_k':5})
   if memory.get('error') or not memory.get('chunks'):raise Failure('真实检索失败或没有返回片段：'+str(memory.get('error')))
   allowed=set(self.state['chapter_ids'][:number])
   if any(c['chapter_id'] not in allowed for c in memory['chunks']):raise Failure('检索出现未来或其他作品来源')
   (self.root/f'retrieval-{number}.json').write_text(json.dumps(memory,ensure_ascii=False,indent=2))
   self.state['checks'][f'retrieval-{number}']={'chunks':len(memory['chunks']),'current_chapter_recalled':any(c['chapter_id']==cid for c in memory['chunks']),'sources':[c['chapter_id'] for c in memory['chunks']]};self.save()
   self.event(f'第{number}章完成：{detail["word_count"]}字；已入库且真实检索返回证据')
  if self.args.probe_impact and not self.state['checks'].get('impact_probe'):
   first=self.state['chapter_ids'][0];original=self.api('GET',f'/chapters/{first}')
   self.state['probe_original']=original['content'];self.save()
   self.api('PUT',f'/chapters/{first}',{'content':original['content']+'\n\n窗框还留着昨夜的雨痕。','expected_hash':original['content_hash']})
   notices=self.api('GET',f'/books/{bid}/workflow')['impacts']
   expected=set(self.state['chapter_ids'][1:self.args.chapters])
   if not expected.issubset({x['chapter_id'] for x in notices}):raise Failure('前章改稿后没有完整标记后文影响')
   if not self.api('GET',f'/chapters/{self.state["chapter_ids"][1]}/blueprint')['stale']:raise Failure('后文章纲没有过期')
   current=self.api('GET',f'/chapters/{first}')
   self.api('PUT',f'/chapters/{first}',{'content':original['content'],'expected_hash':current['content_hash']})
   for number,cid in enumerate(self.state['chapter_ids'][:self.args.chapters],1):self.index(cid,f'probe-reindex-{number}')
   self.state['checks']['impact_probe']={'affected':len(expected),'original_restored':True,'all_reindexed':True};self.state.pop('probe_original',None);self.save()
  status=self.api('GET',f'/books/{bid}/rag-status')
  if any(not c.get('ingested') for c in status['chapters'] if c['chapter_id'] in self.state['chapter_ids'][:self.args.chapters]):raise Failure('最终索引状态不完整')
  if self.api('GET',f'/books/{bid}/workflow')['impacts']:raise Failure('仍存在未复核影响')
  bodies=[(self.root/'chapters'/f'{n:03}.md').read_text() for n in range(1,self.args.chapters+1)]
  if len({sha(b) for b in bodies})!=len(bodies):raise Failure('章节正文重复')
  manuscript='# 雾港收潮人 · 连载流程样书\n\n'+ '\n\n'.join(f'## 第{i}章\n\n{body}' for i,body in enumerate(bodies,1))
  (self.root/'manuscript.md').write_text(manuscript)
  report={'passed':True,'book_id':bid,'planned_stage_words':30000,'completed_chapters':self.args.chapters,'actual_words':sum(self.state['checks'][f'chapter-{n}']['words'] for n in range(1,self.args.chapters+1)),'platform_credits_recorded':self.state['cost'],'checks':self.state['checks'],'limits':['仅完成阶段样本，不是三万字全书已完结','本地结构检查和显式测试批准不等于人工文学/事实验收','索引模型与embedding成本未完整进入平台积分计量'],'private':True}
  (self.root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));self.event(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base-url',default='http://localhost:8010/api/v1');parser.add_argument('--username',default='admin');parser.add_argument('--chapters',type=int,default=4);parser.add_argument('--output',type=Path,default=Path('backend/evaluations/runs/serial-proof-20261025'));parser.add_argument('--max-credits',type=int,default=300);parser.add_argument('--approve-test-output',action='store_true');parser.add_argument('--probe-impact',action='store_true');args=parser.parse_args()
 if not 2<=args.chapters<=8:parser.error('样本为2到8章，避免意外批量消耗')
 run=Run(args)
 try:run.run()
 except Exception as exc:
  run.state['last_error']=str(exc);run.save();print('FAILED:',str(exc),flush=True);raise SystemExit(1)
