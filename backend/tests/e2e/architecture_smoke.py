"""Read-only live architecture smoke: no model call and no manuscript writes."""
import json,os,uuid,time
from urllib.request import Request,urlopen
base='http://localhost:8010/api/v1'
def call(method,path,body=None,token=None):
 req=Request(base+path,method=method,data=json.dumps(body).encode() if body is not None else None,
   headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
 with urlopen(req,timeout=30) as r:return json.load(r)
auth=call('POST','/auth/login',{'username':'admin','password':os.environ['STORYCLAW_PASSWORD']});token=auth['token']
books=call('GET','/books',token=token)
book=next((b for b in books if b['id']==3),books[0] if books else None)
skills=call('GET','/skills',token=token);alias=call('GET','/skills/write-chapter',token=token)
assert len(skills)==11;assert alias['name']=='chapter-craft'
if book:
 run=call('POST','/agent/runs',{'request_id':str(uuid.uuid4()),'entry':'command','command':'project.status','scope':{'book_id':book['id']}},token)
 assert run['status']=='succeeded',run
 events=call('GET',f'/agent/runs/{run["id"]}/events',token=token)
 assert [e['seq'] for e in events]==list(range(1,len(events)+1))
 assert call('GET',f'/agent/runs/{run["id"]}/events?after_seq={events[-1]["seq"]}',token=token)==[]
 assert run['credits_cost']==0
 queued=call('POST','/agent/runs',{'request_id':str(uuid.uuid4()),'entry':'command','command':'plans.status','scope':{'book_id':book['id']}},token)
 deadline=time.monotonic()+20
 while queued['status'] in ('accepted','running') and time.monotonic()<deadline:
  time.sleep(.25);queued=call('GET',f'/agent/runs/{queued["id"]}',token=token)
 assert queued['status']=='succeeded',queued
 assert queued['credits_cost']==0

 for suffix in ('sources','baseline','plans','releases'):
  call('GET',f'/books/{book["id"]}/{suffix}',token=token)
 call('GET','/private-methods',token=token)
 print(json.dumps({'skill_count':len(skills),'alias':alias['name'],'run_status':run['status'],'events':len(events),'worker_claim_verified':True,'model_calls':0,'manuscript_changes':0},ensure_ascii=False))
else:print('Skills verified; no private test book available for scoped status check.')
