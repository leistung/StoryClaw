"""Explicitly repair the duplicate-event defect observed in the private smoke sample.

Preserve original receipts and manuscript versions. Re-plan chapter two, generate
one new version using full prior-chapter context, then author-review/rebase later
blueprints while keeping their distinct investigation events.
"""
import os,json,argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evaluations"))
from serial_smoke import Run,plain,repetition_evidence,Failure,sha
args=argparse.Namespace(base_url='http://localhost:8010/api/v1',username='admin',output=Path('backend/evaluations/runs/serial-proof-20261025'),max_credits=300)
r=Run(args)
login=r.api('POST','/auth/login',{'username':args.username,'password':os.environ['STORYCLAW_PASSWORD']});r.token=login['token']
bid=r.state['book_id'];ids=r.state['chapter_ids']
# Recover the already-finished fourth chapter; never repeat its paid job.
r.job('write-4','generate',ids[3])
fourth=r.api('GET',f'/chapters/{ids[3]}')
(r.root/'chapters/004.md').write_text(plain(fourth['content']))
before=r.api('GET',f'/chapters/{ids[1]}');previous=r.api('GET',f'/chapters/{ids[0]}')
evidence=repetition_evidence(before['content'],previous['content'])
if 'observed_duplicate_defect' not in r.state['checks']:
 r.state['checks']['observed_duplicate_defect']={'chapter':2,'before_hash':before['content_hash'],'evidence':evidence};r.save()
 (r.root/'chapter-002-before-repair.md').write_text(plain(before['content']))
plan=r.api('GET',f'/chapters/{ids[1]}/blueprint')['plan']
if not r.state['checks'].get('repair-2-plan'):
 plan['summary']='承接上章借灯读潮已付出记忆代价，沈照次日修灯首次出现辨频迟滞。林婶这次是为大潮前验灯而来，昨夜灯油差款已结清，不再催缴、不再重复疏通油路与交钱对话，也不再像第一次一样盘问旧灯。她检查灯火后，因发现沈照失手，警告不得为私查旧案耽误本区段航道。沈照以巡检为由走上栈道，首次遇见补网的盲眼老曲。老曲凭潮声察觉旧灯的错位共鸣，暗示去旧码头外围查看落潮礁痕。沈照不深入禁地，在外围礁缝找到一块有绞缠纹的灯座残片，首次获得与不熄旧灯相联的实物证据。保持父亲生死未明、能力代价不可免除。'
 plan['constraints']=[*plan.get('constraints',[]),'昨夜灯油差数已经结清，禁止再次催缴同一账目或复用第一章对话','本章是新的验灯与调查行动，不是重演初次借灯读潮'][:12]
 r.api('PUT',f'/chapters/{ids[1]}/blueprint',plan);r.api('POST',f'/chapters/{ids[1]}/blueprint/confirm',plan)
 r.state['checks']['repair-2-plan']=True;r.save()
r.job('repair-write-2','generate',ids[1],prompt='请完整重写第二章。保留辨频迟滞、遇见老曲、外围礁痕和灯座残片这条新调查线。严格阅读提供的完整第一章原文，第一章灯油差款已付清，绝对不要再写同一笔催缴、疏通油路、交钱或第一次盘问旧灯。林婶本章只是验灯并警告。约2500字，正文自然分段，不重用上章的长句或对话。')
after=r.api('GET',f'/chapters/{ids[1]}');check=repetition_evidence(after['content'],previous['content'])
if check['warning']:raise Failure('修订后仍存在跨章复用风险：'+str(check))
(r.root/'chapters/002.md').write_text(plain(after['content']))
r.state['checks']['duplicate_repair']={'revised_hash':after['content_hash'],'after_evidence':check,'original_receipt_preserved':True,'full_previous_chapter_supplied':True};r.save()
r.index(ids[1],'repair-index-2')
# Later events do not depend on the duplicate collection scene; explicitly rebase,
# confirm and reindex after reviewing their existing text, without silently rewriting.
for number,cid in enumerate(ids[2:4],3):
 body=r.api('GET',f'/chapters/{cid}')
 prev=r.api('GET',f'/chapters/{ids[number-2]}')
 reuse=repetition_evidence(body['content'],prev['content'])
 if reuse['warning'] and number==4 and not r.state['checks'].get('repair-4-copyedit'):
  original='当年在旧码头被暗流撕咬崩毁的那盏灯，与她手中这盏从未熄灭的旧灯，记录着完全相同的潮频。'
  revised='眼前残座与篓中旧灯的潮频相合，先前残景留下的猜测，如今有了能摸到的凭据。'
  if body['content'].count(original)!=1:raise Failure('第四章校改原句不匹配，停止写入')
  (r.root/'chapter-004-before-copyedit.md').write_text(plain(body['content']))
  r.api('PUT',f'/chapters/{cid}',{'content':body['content'].replace(original,revised),'expected_hash':body['content_hash']})
  r.state['checks']['repair-4-copyedit']={'reason':'复用第三章总结句，编辑改写一处，保留既有事件与历史版本','before_hash':body['content_hash']};r.save()
  body=r.api('GET',f'/chapters/{cid}');reuse=repetition_evidence(body['content'],prev['content'])
 if reuse['warning']:raise Failure(f'第{number}章也有复用风险，需要单独修订：{reuse}')
 state=r.api('GET',f'/chapters/{cid}/blueprint')
 if state['stale']:
  r.api('PUT',f'/chapters/{cid}/blueprint',state['plan']);r.api('POST',f'/chapters/{cid}/blueprint/confirm',state['plan'])
 r.index(cid,f'repair-review-index-{number}')
 r.state['checks'][f'repair-review-{number}']={'unchanged_body_hash':body['content_hash'],'repetition':reuse,'explicitly_rebased':True};r.save()
r.event('第二章修订与后文复核完成；继续原样书流程')
