"""Recover this acceptance job's owned checkpoint candidate without any model call or adoption."""
import json,os,sys
from pathlib import Path
from urllib.request import Request,urlopen
path=Path(sys.argv[1]);state=json.loads(path.read_text());token=None
base=os.environ.get('STORYCLAW_API','http://localhost:8010/api/v1')
def call(method,endpoint,body=None):
 req=Request(base+endpoint,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
 with urlopen(req,timeout=60) as r:return json.load(r)
token=call('POST','/auth/login',{'username':os.environ.get('STORYCLAW_USERNAME','admin'),'password':os.environ['STORYCLAW_PASSWORD']})['token']
jobs=call('GET',f'/jobs?book_id={state["book_id"]}')
job=next(j for j in jobs if j['kind']=='generate' and j['status']=='failed')
result=call('POST',f'/jobs/{job["id"]}/candidate/recover');candidate=result['result']['candidate']
path.with_suffix('.candidate.txt').write_text(candidate['content'],encoding='utf-8')
state['recovered_candidate']={'job_id':job['id'],'characters':len(candidate['content']),'adopted':False,'model_calls':0}
path.write_text(json.dumps(state,ensure_ascii=False,indent=2));print(json.dumps(state['recovered_candidate'],ensure_ascii=False))
