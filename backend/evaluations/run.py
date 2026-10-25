#!/usr/bin/env python3
"""可恢复的小说 API 验证与长篇生成。只调用 StoryClaw API，不直连模型或数据库。"""
from __future__ import annotations
import argparse
import fcntl
import getpass
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4
from quality import chapter_checks, count, fingerprint, plain, validate_outline

ROOT=Path(__file__).resolve().parent

def save(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    text=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(text,encoding='utf-8');tmp.replace(path)

def read(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default

class Failure(RuntimeError): pass
class API:
    def __init__(self,base,out,state):self.base=base.rstrip('/');self.out=out;self.state=state;self.token=None
    def call(self,method,path,body=None,raw=False):
        start=time.monotonic();payload=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(self.base+path,data=payload,method=method,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+self.token} if self.token else {})})
        private=path.startswith('/auth/')
        try:
            with urllib.request.urlopen(req,timeout=600) as response:
                text=response.read().decode('utf-8');status=response.status
            data=text if raw else (json.loads(text) if text else {})
        except urllib.error.HTTPError as exc:
            text=exc.read().decode('utf-8','replace');status=exc.code
            if not private:save(self.out/'errors'/f'{time.time_ns()}.json',{'method':method,'path':path,'status':status,'body':text[:2000]})
            raise Failure(f'{method} {path}: HTTP {status}; {text[:250]}') from None
        except (TimeoutError,urllib.error.URLError,ConnectionError) as exc:
            raise Failure(f'{method} {path}: 请求结果未知（{type(exc).__name__}）。停止自动重试；续跑时先核对服务器已保存的内容。') from None
        duration=round(time.monotonic()-start,2)
        event={'method':method,'path':path,'status':status,'seconds':duration}
        if not private:
            if isinstance(data,dict):
                event.update({k:data[k] for k in ('in_tokens','out_tokens','credits_cost','total_in_tokens','total_out_tokens','total_credits_cost','word_count') if k in data})
                self.state['reported_tokens']=self.state.get('reported_tokens',0)+int(data.get('in_tokens',data.get('total_in_tokens',0)))+int(data.get('out_tokens',data.get('total_out_tokens',0)))
                self.state['reported_credits']=self.state.get('reported_credits',0)+int(data.get('credits_cost',data.get('total_credits_cost',0)))
            with (self.out/'requests.jsonl').open('a') as log:log.write(json.dumps(event,ensure_ascii=False)+'\n')
        print(time.strftime('%H:%M:%S'),method,path,status,f'{duration}s',flush=True)
        return data

    def stream(self,path,body):
        start=time.monotonic();done=None;event='message';lines=[];events=0;last_progress=start;draft_chars=0
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode(),method='POST',headers={
            'Content-Type':'application/json','Accept':'text/event-stream','Authorization':'Bearer '+self.token})
        try:
            with urllib.request.urlopen(req,timeout=600) as response:
                for raw in response:
                    line=raw.decode('utf-8').rstrip('\r\n')
                    if line.startswith('event:'):event=line[6:].strip()
                    elif line.startswith('data:'):lines.append(line[5:].strip())
                    elif not line and lines:
                        data=json.loads('\n'.join(lines));lines=[];events+=1
                        if event=='draft':draft_chars+=len(data.get('delta',''))
                        if time.monotonic()-last_progress>=30:
                            print(time.strftime('%H:%M:%S'),'SSE progress',events,'events',draft_chars,'draft characters',flush=True);last_progress=time.monotonic()
                        if event=='error':raise Failure('SSE 返回错误：'+str(data)[:300])
                        if event=='done':done=data
                        event='message'
        except (TimeoutError,urllib.error.URLError,ConnectionError) as exc:
            raise Failure(f'SSE 连接中断，结果未知，请先核对已保存章节：{type(exc).__name__}') from None
        if done is None:raise Failure('SSE 结束但没有 done 事件，不能视为生成成功')
        self.state['reported_tokens']=self.state.get('reported_tokens',0)+int(done.get('in_tokens',0))+int(done.get('out_tokens',0))
        self.state['reported_credits']=self.state.get('reported_credits',0)+int(done.get('credits_cost',0))
        with (self.out/'requests.jsonl').open('a') as log:log.write(json.dumps({'method':'POST','path':path,'stream':True,'events':events,'seconds':round(time.monotonic()-start,2),'in_tokens':done.get('in_tokens',0),'out_tokens':done.get('out_tokens',0),'credits_cost':done.get('credits_cost',0)})+'\n')
        print(time.strftime('%H:%M:%S'),'SSE',path,'done',events,'events',flush=True)
        return done

class Lab:
    def __init__(self,args):
        self.args=args;self.case=read(args.case);self.out=Path(args.output);self.out.mkdir(parents=True,exist_ok=True)
        self.lock=(self.out/'.lock').open('w')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Failure('该实例已有脚本运行，不能并发修改同一本书') from None
        digest=fingerprint(json.dumps(self.case,ensure_ascii=False,sort_keys=True))
        self.state=read(self.out/'state.json',{'case_id':self.case['case_id'],'case_hash':digest,'chapters':{},'completed':False})
        if self.state.get('case_hash')!=digest:raise Failure('实例设定已变更，请使用新的 --output，避免混入旧正文')
        self.api=API(args.base_url,self.out,self.state)
        self.report=read(self.out/'report.json',{'checks':{},'limitations':['文学质量与语义一致性仍需人工审稿；自动通过不等于出版质量。','Token 汇总是接口报告值，不含所有工具、抽取和大纲调用，不能视为上游精确账单。']})
        self.book=None
    def checkpoint(self):
        self.state['updated_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
        save(self.out/'state.json',self.state);save(self.out/'report.json',self.report)
    def login(self):
        password=os.environ.get('STORYCLAW_PASSWORD') or getpass.getpass('StoryClaw 密码: ')
        auth=self.api.call('POST','/auth/login',{'username':self.args.username,'password':password})
        self.api.token=auth['token'];self.user=auth['user']
        if self.state.get('user_id',self.user['id'])!=self.user['id']:raise Failure('续跑账号与原账号不同')
        self.state['user_id']=self.user['id'];self.checkpoint()
    def audit(self):
        spec=self.api.call('GET','/openapi.json') if not self.api.base.endswith('/api/v1') else None
        if spec is None:
            with urllib.request.urlopen(self.api.base.removesuffix('/api/v1')+'/openapi.json',timeout=30) as r:spec=json.load(r)
        required={
            'book.create':('post','/books'),'book.read':('get','/books/{bid}'),'book.update':('put','/books/{bid}'),
            'outline.generate':('post','/books/{bid}/outline/generate'),'outline.read':('get','/books/{bid}/outline'),'outline.update':('put','/books/{bid}/outline'),
            'volume.create':('post','/books/{bid}/volumes'),'chapter.create':('post','/chapters/books/{bid}'),'chapter.read':('get','/chapters/{cid}'),'chapter.update':('put','/chapters/{cid}'),
            'chapter.plan':('post','/chapters/{cid}/plan'),'chapter.generate':('post','/chapters/{cid}/generate'),'chapter.stream':('post','/chapters/{cid}/generate-stream'),
            'chapter.multi':('post','/books/{bid}/multi-write'),'chapter.polish':('post','/chapters/{cid}/polish'),'chapter.continue':('post','/chapters/{cid}/continue'),
            'analysis':('post','/books/{bid}/analyze'),'canon':('post','/books/{bid}/config/{entity_type}'),
            'knowledge.ingest':('post','/chapters/{cid}/ingest'),'knowledge.query':('post','/rag/query'),'knowledge.status':('get','/books/{bid}/rag-status'),
            'export':('get','/books/{bid}/export'),'reading':('post','/reading-configs'),
        }
        rows={key:{'method':method,'path':path,'exists':method in spec['paths'].get('/api/v1'+path,{})} for key,(method,path) in required.items()}
        save(self.out/'api-audit.json',rows);save(self.out/'openapi.json',spec)
        missing=[k for k,v in rows.items() if not v['exists']]
        self.report['checks']['api_contract']={'passed':not missing,'missing':missing}
        self.checkpoint()
        if missing:raise Failure('缺少核心接口：'+','.join(missing))
    def budget(self):
        if self.state.get('reported_credits',0)>=self.args.max_credits:raise Failure('达到本次平台积分预算，停止后续生成')
        me=self.api.call('GET','/auth/me')
        if me['credits_balance']<100:raise Failure('剩余积分不足安全余量，请先查看用量')
    def prepare(self):
        c=self.case;marker='【novel-lab:'+c['case_id']+'】'
        if self.state.get('book_id'):
            self.book=self.api.call('GET',f"/books/{self.state['book_id']}")
            if marker not in (self.book.get('intro') or ''):raise Failure('book_id 不属于此测试实例')
        else:
            existing=self.api.call('GET','/books')
            matches=[b for b in existing if marker in (b.get('intro') or '')]
            if len(matches)>1:raise Failure('发现多个同名实例，请人工指定输出状态')
            if matches:self.book=matches[0]
            else:
                body={k:c[k] for k in ('title','genre','target_chapters','target_words','per_chapter_words','protagonist_name','protagonist_intro')}
                body.update(intro=marker+'\n'+c['intro']+'\n文风：'+c['voice']+'\n规则：'+'；'.join(c['rules']),platforms=[],generate_outline=False,generate_plots=False,generate_characters=False)
                self.state['pending']='book.create';self.checkpoint()
                self.book=self.api.call('POST','/books',body)
            self.state['book_id']=self.book['id'];self.state.pop('pending',None);self.checkpoint()
        bid=self.book['id']
        # Idempotent canon creation: unique names within this controlled example, no global data resets.
        for kind,key in [('character','characters'),('scene','scenes'),('item','items')]:
            rows=self.api.call('GET',f'/books/{bid}/config/{kind}')['items'];known={x['name'] for x in rows}
            for row in c[key]:
                if row['name'] not in known:self.api.call('POST',f'/books/{bid}/config/{kind}',row)
        rows=self.api.call('GET',f'/books/{bid}/config/plot')['items']
        ledger=next((x for x in rows if x['name']=='连续性台账'),None)
        if not ledger:ledger=self.api.call('POST',f'/books/{bid}/config/plot',{'name':'连续性台账','category':'continuity','description':'开篇基线：许砚生十七岁，父母健在，与阿棠尚未成家。不要把未来大纲写作已发生事实。'})
        self.state['ledger_id']=ledger['id'];self.api.call('PUT',f'/books/{bid}/config/plot/{ledger["id"]}',{'sort_order':-1000})
        try:outline=self.api.call('GET',f'/books/{bid}/outline')
        except Failure as e:
            if 'HTTP 404' not in str(e):raise
            self.budget();self.state['pending']='outline.generate';self.checkpoint()
            outline=self.api.call('POST',f'/books/{bid}/outline/generate',{})
        if outline.get('error'):raise Failure('大纲返回了降级模板或错误')
        self.outline=outline['content'];nodes=validate_outline(self.outline,c['target_chapters'])
        before_outline=json.dumps(self.outline,ensure_ascii=False,sort_keys=True)
        # Normalize headings only, preserve generated plot and sequencing.
        for node in nodes:node['title']=re.sub(r'^第[一二三四五六七八九十百零\d]+章\s*','',node['title']).strip()
        if json.dumps(self.outline,ensure_ascii=False,sort_keys=True)!=before_outline:
            self.outline=self.api.call('PUT',f'/books/{bid}/outline',{'content':self.outline})['content']
        save(self.out/'outline.json',self.outline)
        self.state.pop('pending',None)
        volumes=self.api.call('GET',f'/books/{bid}/volumes');by_name={v['name']:v for v in volumes}
        chapters=self.api.call('GET',f'/chapters/books/{bid}');by_num={ch['number']:ch for ch in chapters}
        if len(by_num)!=len(chapters):raise Failure('数据库中出现重复章号')
        for i,vol in enumerate(self.outline['volumes']):
            name=vol.get('name') or f'第{i+1}卷'
            if name not in by_name:by_name[name]=self.api.call('POST',f'/books/{bid}/volumes',{'name':name,'sort':i})
            for node in vol['chapters']:
                num=node['number']
                if num not in by_num:
                    if num!=len(by_num)+1:raise Failure('创建章节时序异常，拒绝自动补错章号')
                    by_num[num]=self.api.call('POST',f'/chapters/books/{bid}',{'title':node['title'],'volume_id':by_name[name]['id']})
                elif not by_num[num]['word_count']:
                    self.api.call('PUT',f'/chapters/{by_num[num]["id"]}',{'title':node['title'],'volume_id':by_name[name]['id']})
                self.state['chapters'].setdefault(str(num),{})['id']=by_num[num]['id']
        self.report['checks']['prepare']={'passed':True,'book_id':bid,'outline_chapters':len(nodes),'volumes':len(self.outline['volumes']),'canon_seeded':True}
        self.checkpoint()
    def analyze(self,skill,start,end):
        bid=self.state['book_id'];self.budget()
        data=self.api.call('POST',f'/books/{bid}/analyze',{'book_id':bid,'skill':skill,'chapter_range':{'start':start,'end':end},'character_name':self.case['protagonist_name'],'thread_id':uuid4().hex})
        if not data.get('report') or len(data['report'])<50:raise Failure(f'{skill} 返回空或异常短报告')
        save(self.out/'analysis'/f'{skill}-{start:03}-{end:03}.json',data);self.checkpoint();return data
    def prompt(self,num,plan):
        node=next(x for x in validate_outline(self.outline,self.case['target_chapters']) if x['number']==num)
        message=(f'请写本章《{node["title"]}》，第{num}章。\n'+
            f'正文必须为 {self.case["min_chapter_words"]} 到 {self.case["max_chapter_words"]} 个非空白字符，目标约 {self.case["per_chapter_words"]} 字。不要输出标题、创作说明、场景编号或字数统计。\n'+
            '篇幅安排：最多28个自然段，每段约70到110字，最后一个场景在第24段前开始，第28段内结束。写完本章事件立即收束。\n'+
            '依次完成下面场景，以具体动作、对话和生活细节充实，不重复回顾凑字数。不要写到后续章，不擅自改变人物生死、年龄和亲属关系。\n'+
            '文风：'+self.case['voice']+'\n硬规则：'+'；'.join(self.case['rules'])+'\n当前大纲：'+json.dumps(node,ensure_ascii=False)+'\n本章场景任务单：'+json.dumps(plan['scenes'],ensure_ascii=False))
        if num==self.case['target_chapters']:message+='\n全书收束要求：'+self.case['ending_contract']
        return message
    def write(self):
        bid=self.state['book_id']
        current_outline=self.api.call('GET',f'/books/{bid}/outline')['content']
        if not current_outline.get('_review'):
            if not self.args.approve_test_output:raise Failure('请先在工作台确认大纲；隔离测试可显式使用 --approve-test-output 授权采用测试输出')
            self.api.call('POST',f'/books/{bid}/outline/confirm',{'content':current_outline})
        for num in range(1,min(self.args.through,self.case['target_chapters'])+1):
            st=self.state['chapters'][str(num)];cid=st['id'];detail=self.api.call('GET',f'/chapters/{cid}')
            if st.get('accepted_hash') and fingerprint(detail['content'])!=st['accepted_hash']:raise Failure(f'第{num}章已被外部修改，停止自动覆盖')
            checks=chapter_checks(detail['content'],self.case)
            if checks['errors']:
                if num<max([int(n) for n,s in self.state['chapters'].items() if s.get('accepted_hash')]+[0]):raise Failure('早期章节需要修改，但后文已存在；需要人工处理级联失效')
                self.budget()
                plan_path=self.out/'plans'/f'{num:03}.json'
                if plan_path.exists():plan=read(plan_path)
                else:
                    plan=self.api.call('POST',f'/chapters/{cid}/plan',{});save(plan_path,plan);self.checkpoint()
                base_prompt=self.prompt(num,plan)
                for attempt in range(1,4):
                    self.budget();prompt=base_prompt
                    if attempt>1:prompt+=f'\n上个版本存在以下问题：{checks["errors"]}。请输出新的完整版本，保持既有剧情边界。'
                    save(self.out/'prompts'/f'{num:03}-{attempt}.md',prompt)
                    if detail['content']:save(self.out/'drafts'/f'{num:03}-{time.time_ns()}.md',detail['content'])
                    self.state['pending']={'chapter':num,'operation':'generate','before_hash':fingerprint(detail['content'])};self.checkpoint()
                    # One request = one chapter; never rerun an entire successful batch.
                    if num==1 and attempt==1:
                        generated=self.api.stream(f'/chapters/{cid}/generate-stream', {'prompt':prompt,'thread_id':uuid4().hex})
                    elif num==2 and attempt==1:
                        generated=self.api.call('POST',f'/books/{bid}/multi-write',{'start_number':num,'end_number':num,'skip_existing':True,'sync_settings':False,'instruction':prompt,'thread_id':uuid4().hex})
                        if not generated.get('chapters') or generated['chapters'][0]['status'] not in ('generated','skipped'):raise Failure('批量写作接口返回失败项目')
                    else:
                        generated=self.api.call('POST',f'/chapters/{cid}/generate',{'prompt':prompt,'thread_id':uuid4().hex})
                    save(self.out/'receipts'/f'generate-{num:03}-{attempt}.json',generated)
                    detail=self.api.call('GET',f'/chapters/{cid}');checks=chapter_checks(detail['content'],self.case)
                    self.state.pop('pending',None);self.checkpoint()
                    if not checks['errors']:break
                if checks['errors']:raise Failure(f'第{num}章三次生成仍不满足规则：{checks["errors"]}')
            # Existing valid body is reconciled before any repeat generation after a lost response.
            st['accepted_hash']=checks['sha256'];st['quality']=checks;save(self.out/'chapters'/f'{num:03}.md',detail['content']);self.checkpoint()
            if not st.get('indexed') or detail['rag_status']!='loaded':
                if not self.args.approve_test_output:raise Failure(f'请在工作台审阅第{num}章并确认入库后继续；隔离测试可显式使用 --approve-test-output')
                self.budget();result=self.api.call('POST',f'/chapters/{cid}/ingest',{'reviewed_hash':detail['content_hash']})
                save(self.out/'receipts'/f'ingest-{num:03}.json',result)
                if result.get('error') or result.get('rag_status')!='loaded' or result.get('chunks',0)<1:raise Failure(f'第{num}章未成功持久入库：{result}')
                st['indexed']=True;self.checkpoint()
            if not st.get('retrieval_checked'):
                query=self.api.call('POST','/rag/query',{'book_id':bid,'query':detail['title']+' '+self.case['protagonist_name'],'top_k':3})
                save(self.out/'retrieval'/f'chapter-{num:03}.json',query)
                if query.get('error') or not query.get('chunks'):raise Failure(f'第{num}章入库后未能检索，停止伪成功')
                st['retrieval_checked']=True;self.checkpoint()
            if not st.get('summary'):
                summary=self.analyze('book-summary',max(1,num-2),num);st['summary']=summary['report']
                ledger='已发生内容（严格以正文为准，未知事项不推断）：\n'+summary['report'][:2100]
                self.api.call('PUT',f'/books/{bid}/config/plot/{self.state["ledger_id"]}',{'description':ledger,'category':'continuity','sort_order':-1000})
                self.checkpoint()
            if num%5==0 and not st.get('consistency_report'):
                report=self.analyze('consistency-check',num-4,num);st['consistency_report']=str(self.out/'analysis'/f'consistency-check-{num-4:03}-{num:03}.json');self.checkpoint()
            print(f'CHAPTER {num}/{self.case["target_chapters"]} saved={checks["words"]} indexed=true',flush=True)
            self.export_local();self.verify(final=False)
        self.extras();self.verify(final=self.args.through>=self.case['target_chapters'])
    def extras(self):
        if self.state.get('extras_done'):return
        bid=self.state['book_id'];cid=self.state['chapters']['1']['id'];detail=self.api.call('GET',f'/chapters/{cid}')
        if not detail.get('content'):return
        self.budget();snippet=plain(detail['content'])[:350]
        ending=max(snippet.rfind(mark) for mark in ('。','！','？'))
        if ending>80:snippet=snippet[:ending+1]
        calls=[
            ('polish',f'/chapters/{cid}/polish',{'selected_text':snippet,'polish_goal':'保留事件与信息，使句子自然，避免抽象升华'}),
            ('continue',f'/chapters/{cid}/continue',{'prefix_text':plain(detail['content'])[:500],'max_words':400}),
            ('brainstorm','/assist/brainstorm',{'topic':'低玄幻中普通窑工家庭的日常冲突','genre':'玄幻','direction':'劳动、契约和亲情，不提供超能力捷径','count':3}),
            ('titles','/assist/title-generation',{'content':snippet,'keywords':['窑口','寿火'],'count':3,'target':'chapter'}),
            ('scene','/assist/scene-enhance',{'scene_text':snippet,'mood':'克制','preserve_length':True}),
            ('dialogue','/assist/dialogue-polish',{'dialogue_text':'砚生说：“爹，火不够了。”许承炉说：“把灶口封小一点，饭还能熟。”','goal':'人物口语自然，信息不变'}),
            ('reading','/assist/reading-config-gen',{'scene':'night','book_genre':'玄幻','user_prefs':{'font_size':18}}),
        ]
        for name,path,body in calls:
            if self.state.get('extras',{}).get(name):continue
            self.budget();data=self.api.call('POST',path,{**body,'thread_id':uuid4().hex})
            if not data.get('content'):raise Failure(f'{name} 返回空内容')
            text=data['content'];size=count(text)
            if name in ('polish','continue','scene','dialogue'):
                chars=len(re.findall(r'[\u4e00-\u9fff]',plain(text)))
                if size and chars/size<0.65:raise Failure(f'{name} 返回乱码或无关内容')
            if name=='continue' and not 100<=size<=900:raise Failure(f'续写片段字数异常：{size}')
            if name=='polish' and not count(snippet)*0.5<=size<=count(snippet)*1.8:raise Failure(f'润色长度异常：{size}')
            if name=='reading':
                try:config_json=json.loads(text.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip())
                except (ValueError,TypeError):raise Failure('阅读配置未返回合法JSON') from None
                if not isinstance(config_json,dict) or not 14<=config_json.get('font_size',0)<=24:raise Failure('阅读配置字体范围异常')
            save(self.out/'extras'/f'{name}.json',data);self.state.setdefault('extras',{})[name]=True;self.checkpoint()
        for skill in ('plot-planning','character-development'):
            if not self.state.get('extras',{}).get(skill):self.analyze(skill,1,min(3,self.args.through));self.state['extras'][skill]=True;self.checkpoint()
        # Validate readonly sharing on the novel's assistant message; the share endpoint is public by design.
        polish=read(self.out/'extras/polish.json')
        if polish.get('message_id'):
            shared=self.api.call('POST',f'/messages/{polish["message_id"]}/share',{})
            public=self.api.call('GET',f'/share/{shared["share_token"]}')
            if public.get('content')!=polish['content']:raise Failure('分享内容与原消息不一致')
        config=self.api.call('POST','/reading-configs',{'name':f'novel-lab-{bid}','scene':'night','book_id':bid,'is_default':False,'config_json':{'font_size':18,'line_height':1.8}})
        self.state['reading_config_id']=config['id'];self.state['extras_done']=True
        self.report['checks']['auxiliary_features']={'passed':True,'tested':[x[0] for x in calls]+['plot-planning','character-development','reading-config-save','message-share']}
        self.checkpoint()
    def export_local(self):
        parts=[f'# {self.case["title"]}\n'];names={c['number']:c['title'] for c in validate_outline(self.outline,self.case['target_chapters'])}
        for n in sorted(int(k) for k,v in self.state['chapters'].items() if v.get('accepted_hash')):
            content=(self.out/'chapters'/f'{n:03}.md').read_text()
            parts.append(f'## 第{n}章 {names[n]}\n\n{content}\n')
        save(self.out/'manuscript.md','\n'.join(parts))
    def verify(self,final):
        bid=self.state['book_id'];checks=[]
        for num,st in sorted(self.state['chapters'].items(),key=lambda x:int(x[0])):
            if not st.get('accepted_hash'):continue
            detail=self.api.call('GET',f'/chapters/{st["id"]}');quality=chapter_checks(detail['content'],self.case)
            if quality['sha256']!=st['accepted_hash']:quality['errors'].append('服务器正文与已验收版本不同')
            checks.append({'number':int(num),'id':st['id'],'indexed':st.get('indexed',False),**quality})
        hashes=[c['sha256'] for c in checks];total=sum(c['words'] for c in checks)
        passed=bool(checks) and all(not c['errors'] and c['indexed'] for c in checks) and len(hashes)==len(set(hashes))
        if final:passed=passed and len(checks)==self.case['target_chapters'] and total>=100000
        self.report.update(book_id=bid,title=self.case['title'],expected_chapters=self.case['target_chapters'],accepted_chapters=len(checks),total_words=total,cjk_characters=sum(c['cjk_characters'] for c in checks),chapters=checks,structural_checks_passed=passed,full_manuscript_complete=bool(final and passed),workspace=f'http://localhost:5173/workspace/{bid}')
        self.export_local();self.checkpoint()
        if final:
            if not passed:raise Failure('整本验收未通过，请查看 report.json，不能宣称已完成十万字')
            status=self.api.call('GET',f'/books/{bid}/rag-status');save(self.out/'rag-status.json',status)
            if status.get('total_entities',0)<1:raise Failure('图数据库没有实际实体记录')
            if not all(c.get('ingested') for c in status['chapters']):raise Failure('有章节索引缺失')
            for i,q in enumerate(self.case['retrieval_queries']):
                result=self.api.call('POST','/rag/query',{'book_id':bid,'query':q,'top_k':5});save(self.out/'retrieval'/f'{i+1}.json',result)
                if result.get('error') or not result.get('chunks'):raise Failure('知识库检索未返回片段')
                if any(x['chapter_id'] not in {c['id'] for c in checks} for x in result['chunks']):raise Failure('检索混入其他作品章节')
            exported=self.api.call('GET',f'/books/{bid}/export',raw=True);save(self.out/'server-export.md',exported)
            for c in checks:
                # Ensure each accepted chapter appears verbatim in the server export.
                content=plain((self.out/'chapters'/f'{c["number"]:03}.md').read_text()).strip()
                if content not in exported:raise Failure('服务器导出遗漏正文')
            self.report['checks']['full_book_and_rag']={'passed':True,'retrieval_queries':len(self.case['retrieval_queries'])}
            self.state['completed']=True;self.checkpoint()
            print('COMPLETE',json.dumps({'book_id':bid,'chapters':len(checks),'words':total,'manuscript':str(self.out/'manuscript.md')},ensure_ascii=False),flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://localhost:8010/api/v1');parser.add_argument('--username',default='admin')
    parser.add_argument('--case',type=Path,default=ROOT/'cases/borrowed-fire.json');parser.add_argument('--output',type=Path,default=ROOT/'runs/borrowed-fire-v1')
    parser.add_argument('--approve-test-output',action='store_true',help='仅测试：显式授权确认测试大纲，并索引通过本地检查的测试章节；不等于文学质量与事实经人工验收')
    parser.add_argument('--phase',choices=['audit','prepare','write','extras','verify','all'],default='all');parser.add_argument('--through',type=int,default=40);parser.add_argument('--max-credits',type=int,default=4000)
    args=parser.parse_args();lab=Lab(args)
    try:
        lab.state['run_status']='running';lab.state.pop('last_error',None);lab.checkpoint()
        lab.audit()
        if args.phase=='audit':return
        lab.login();lab.prepare()
        if args.phase in ('all','write'):lab.write()
        elif args.phase=='extras':lab.extras()
        elif args.phase=='verify':lab.verify(final=True)
        lab.state['run_status']='complete' if lab.state.get('completed') else ('sample_complete' if args.phase in ('all','write','extras') else 'prepared')
        lab.checkpoint()
    except (Exception,KeyboardInterrupt) as exc:
        lab.state['run_status']='failed';lab.state['last_error']=str(exc) or '手动停止';lab.report['full_manuscript_complete']=False;lab.state['completed']=False;lab.checkpoint()
        print('STOP:',lab.state['last_error'],file=sys.stderr,flush=True);raise SystemExit(1)

if __name__=='__main__':main()
