#!/usr/bin/env python3
"""Bounded real-model serial acceptance. Creates one private fixture and never publishes.

Requires STORYCLAW_PASSWORD. --state is resumable and contains no login token/key.
The server enforces --budget at every model/embedding call. Pauses are reported, not bypassed.
"""
import argparse,json,os,re,time,sys
from pathlib import Path
from urllib.request import Request,urlopen
from uuid import uuid4
parser=argparse.ArgumentParser();parser.add_argument('--state',required=True);parser.add_argument('--chapters',type=int,default=3);parser.add_argument('--budget',type=int,default=200);parser.add_argument('--resume',action='store_true');parser.add_argument('--timeout',type=int,default=3600);args=parser.parse_args()
if not 1<=args.chapters<=12 or not 1<=args.budget<=1000:parser.error('Acceptance is limited to 1–12 chapters and 1–1000 credits')
path=Path(args.state).resolve();path.parent.mkdir(parents=True,exist_ok=True)
state=json.loads(path.read_text()) if path.exists() else {'marker':uuid4().hex[:8],'chapters':args.chapters,'budget':args.budget}
if (state['chapters'],state['budget'])!=(args.chapters,args.budget):sys.exit('State belongs to another chapter range or budget')
def save():
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2));temp.replace(path)
save();token=None;base=os.environ.get('STORYCLAW_API','http://localhost:8010/api/v1').rstrip('/')
def call(method,endpoint,body=None):
 req=Request(base+endpoint,method=method,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
 with urlopen(req,timeout=60) as response:return json.load(response)
auth=call('POST','/auth/login',{'username':os.environ.get('STORYCLAW_USERNAME','admin'),'password':os.environ['STORYCLAW_PASSWORD']});token=auth['token']
if 'book_id' not in state:
 title='雾灯归途·实测'+state['marker'];books=call('GET','/books');existing=next((b for b in books if b['title']==title),None)
 book=existing or call('POST','/books',{'title':title,'genre':'玄幻','intro':'一个修灯匠带着父亲留下的旧灯回到雾港，灯中残存的路线指向一座被潮水从地图上抹去的村庄。他需要辨别幸存者的说法，在不牺牲邻人的前提下寻找父亲。原创连载验收，逐章推进，不预定全部结局。','target_chapters':args.chapters,'target_words':args.chapters*2500,'per_chapter_words':2500,'protagonist_name':'沈照','protagonist_intro':'二十三岁的修灯匠，做事谨慎，记得父亲教的手艺；父亲失踪而非已确认死亡。她不具备预知能力，也不知道雾隐村的真实位置。'})
 state['book_id']=book['id'];save()
bid=state['book_id']
if 'task_id' not in state:
 frame={'planning_mode':'serial','overview':'沈照继承父亲留下的一盏旧灯，在雾港追查失踪与雾隐村的联系。读灯只能显出确实附着在灯上的旧物痕迹，不能直接读取人的全部记忆，也不能预知未来；每次点燃过久会损伤灯芯且需要重新寻找灯油。主线是调查证据与守护邻里之间的选择，父亲下落保持待证。逐章推动新的行动和后果，不重复第一次发现村名，不因为阶段目标就提前结束整部小说。','volumes':[{'name':'旧灯指路','goal':'先确认旧灯的来源，找到可追查的雾隐村线索；让沈照通过具体行动取得航路记录，仍保留父亲失踪的长期谜团。','chapters':[]},{'name':'潮下村路','goal':'在已写事件基础上逐步调查村落和港口旧约，处理线索可信度与人物利益冲突，按实际章节发展调整。','chapters':[]}]}
 call('PUT',f'/books/{bid}/outline',{'content':frame});call('POST',f'/books/{bid}/outline/confirm',{'content':frame})
 settings=[('world',{'name':'灯痕与雾港','category':'规则','description':'雾港是靠修船、灯油和潮汐航路维生的旧港。读灯只能照出附着旧物的历史痕迹，不能直接读取全知记忆；灯芯会损坏，消耗真实灯油。不存在凭空传送和预知未来。'}),('character',{'name':'沈照','category':'主角','description':'二十三岁女修灯匠，谨慎，有修灯手艺，父亲失踪。她不知道雾隐村在哪里，不具备读心能力。做决定要先查证，不为查父亲随意伤害邻人。'}),('character',{'name':'林婶','category':'配角','description':'邻家油铺掌柜，四十多岁，算账精细，关心沈照，但不知道旧灯的全部秘密。不是沈照的母亲。'})]
 for kind,body in settings:
  existing=call('GET',f'/books/{bid}/config/{kind}')['items']
  if not any(r['name']==body['name'] for r in existing):call('POST',f'/books/{bid}/config/{kind}',body)
 state.setdefault('request_id',str(uuid4()));save()
 task=call('POST',f'/books/{bid}/plans',{'kind':'serial','request_id':state['request_id'],'start':1,'end':args.chapters,'budget':args.budget,'auto_adopt':True,'instruction':'本章约2500字。采用清楚、克制但有画面感的原创叙述；每章有行动和进展，接续已发生事件，不重复上一章情节。不要照搬任何既有作品。'})
 state['task_id']=task['id'];save()
if args.resume:
 call('POST',f'/plans/{state["task_id"]}/control',{'action':'resume'})
print(json.dumps({'book_id':bid,'task_id':state['task_id'],'budget':args.budget,'chapters':args.chapters},ensure_ascii=False),flush=True)
deadline=time.monotonic()+args.timeout;last=None
while True:
 tasks=call('GET',f'/books/{bid}/plans');task=next(t for t in tasks if t['id']==state['task_id'])
 progress=(task['status'],task['result'].get('next'),task['result'].get('phase'),task['spent'])
 if progress!=last:print(json.dumps({'status':task['status'],'chapter':progress[1],'phase':progress[2],'spent':task['spent'],'error':task['error']},ensure_ascii=False),flush=True);last=progress
 state['task']=task;save()
 if task['status'] in ('succeeded','paused','waiting_author','cancelled'):break
 if time.monotonic()>deadline:print('Read-only polling timeout; the bounded server plan remains active. Resume this same state file to inspect it.',flush=True);sys.exit(3)
 time.sleep(3)
chapters=call('GET',f'/chapters/books/{bid}');report=[];text=[]
for row in chapters:
 detail=call('GET',f'/chapters/{row["id"]}');body=re.sub(r'<[^>]+>','',detail['content']);text.append(row['title']+'\n'+body)
 report.append({'id':row['id'],'number':row['number'],'title':row['title'],'words':row['word_count'],'rag_status':row['rag_status'],'hash':detail['content_hash']})
state['report']={'chapters':report,'total_words':sum(c['words'] for c in report),'model':'platform-configured','public':False,'quality':'requires-author-review','complete':task['status']=='succeeded' and len(report)==args.chapters and all(c['rag_status']=='loaded' for c in report)};save()
path.with_suffix('.txt').write_text('\n\n'.join(text),encoding='utf-8');print(json.dumps(state['report'],ensure_ascii=False),flush=True)
sys.exit(0 if state['report']['complete'] else 2)
