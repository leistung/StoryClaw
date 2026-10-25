#!/usr/bin/env python3
"""查看本地实验检查点；不登录，不调用模型。"""
import argparse,json,os
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'runs/borrowed-fire-v1');a=p.parse_args()
def read(name):
    path=a.output/name
    return json.loads(path.read_text()) if path.exists() else {}
s=read('state.json');r=read('report.json');job=read('job.json');alive=False
if job.get('pid'):
    try:os.kill(job['pid'],0);alive=True
    except ProcessLookupError:pass
    except PermissionError:alive=None
print(json.dumps({'title':r.get('title'),'book_id':s.get('book_id'),'worker_alive':alive,'pid':job.get('pid'),'run_status':s.get('run_status'),'accepted_chapters':r.get('accepted_chapters',0),'target_chapters':r.get('expected_chapters',40),'words':r.get('total_words',0),'cjk_characters':r.get('cjk_characters',0),'completed':bool(s.get('completed') and r.get('full_manuscript_complete')),'pending':s.get('pending'),'last_error':s.get('last_error'),'updated_at':s.get('updated_at'),'log':job.get('log')},ensure_ascii=False,indent=2))
