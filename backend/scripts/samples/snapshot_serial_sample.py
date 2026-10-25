"""Read-only export after a stopped run; never calls a model or approves indexes."""
import argparse,json,os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evaluations"))
from serial_smoke import Run,plain,sha
args=argparse.Namespace(base_url='http://localhost:8010/api/v1',username='admin',output=Path('backend/evaluations/runs/serial-proof-20261025'),max_credits=300)
r=Run(args)
r.token=r.api('POST','/auth/login',{'username':args.username,'password':os.environ['STORYCLAW_PASSWORD']})['token']
chapters=[];bodies=[]
for n,cid in enumerate(r.state['chapter_ids'],1):
 c=r.api('GET',f'/chapters/{cid}');body=plain(c['content']);bodies.append(body)
 (r.root/'chapters'/f'{n:03}.md').write_text(body)
 chapters.append({'number':n,'id':cid,'words':c['word_count'],'content_hash':c['content_hash'],'rag_status':c['rag_status']})
failed=r.api('GET','/jobs/'+r.state['jobs']['repair-review-index-4']['id'])
(r.root/'receipts/repair-review-index-4.json').write_text(json.dumps(failed,ensure_ascii=False,indent=2))
(r.root/'manuscript.md').write_text('# 雾港收潮人 · 连载流程样书\n\n'+'\n\n'.join(f'## 第{n}章\n\n{b}' for n,b in enumerate(bodies,1)))
report={'passed':False,'status':'blocked_upstream_embedding_quota','book_id':r.state['book_id'],'private':True,'planned_stage_words':30000,'completed_chapters':len(chapters),'actual_words':sum(c['words'] for c in chapters),'chapters':chapters,'platform_credits_recorded':r.state['cost'],'checks':r.state['checks'],'pending':['第四章向量与图索引未完成','完整真实改稿影响探针尚未执行；隔离回归单独验证','三万字阶段尚未写完'],'error':failed['error'],'limits':['重复检测不等于语义一致性审阅','第二章3404字偏离2500字目标，保留审核反馈','索引上游费用未全部纳入积分计量']}
(r.root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:report[k] for k in ('status','completed_chapters','actual_words','chapters')},ensure_ascii=False))
