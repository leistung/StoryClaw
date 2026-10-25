"""SQL/auth/jobs/billing implementation of StoryClaw ports; no creative prompts."""
import asyncio,json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select,update
from storyclaw.contracts import CapabilityResult
from storyclaw.contracts import ModelTurn
from storyclaw.contracts import ToolCall
from storyclaw.orchestration.capabilities import get_capability
from app.database import AsyncSessionLocal
from app.models import User
from app.models import Book
from app.models import Chapter
from app.models import Outline
from app.models import CreditsLedger
from app.models.agent import AgentRun
from app.services.agent import agent_runs
from app.services.writing.revisions import chapter_hash

class BackendStoryPorts:
    def __init__(self,rid,uid,request):self.rid=rid;self.uid=uid;self.request=request

    async def emit(self,kind,payload):
        await agent_runs.append(self.rid,self.uid,kind,payload)
        from storyclaw.runtime.deps import get_stream_sink
        sink=get_stream_sink()
        if sink is not None:await sink(kind,payload)

    async def execute(self,name,arguments):
        cap=get_capability(name);scope=self.request.scope
        async with AsyncSessionLocal() as db:
            await agent_runs.validate_scope(db,self.uid,scope)
            row=await db.get(AgentRun,self.rid)
            if row.status=='cancelled':raise HTTPException(409,'请求已取消')
            if not scope.book_id:raise ValueError('请先打开一本作品，再使用此能力；首页选题请使用开书讨论。')
            book=await db.get(Book,scope.book_id)
            chapter=await db.get(Chapter,scope.chapter_id) if scope.chapter_id else None
            if name=='author.ask':
                return CapabilityResult(content='请集中补充：\n'+'\n'.join(q['question']+'：'+' / '.join(q['options']) for q in arguments['questions']),data={'artifact':True,'kind':'author.question','questions':arguments['questions']})
            if name=='project.status':
                from app.services.writing.serial import blueprint_state
                from storyclaw.workflows.workflow import is_confirmed
                outline=await db.scalar(select(Outline).where(Outline.book_id==book.id))
                content=json.loads(outline.content) if outline and outline.content else {}
                recent=list(await db.scalars(select(Chapter).where(Chapter.book_id==book.id).order_by(Chapter.number.desc()).limit(20)))
                data={'title':book.title,'genre':book.genre,'outline_confirmed':is_confirmed(content),
                    'current_chapter':({'id':chapter.id,'number':chapter.number,'words':chapter.word_count,'rag_status':chapter.rag_status} if chapter else None),
                    'recent_chapters':[{'id':c.id,'number':c.number,'words':c.word_count,'rag_status':c.rag_status} for c in recent]}
                if chapter:data['blueprint']=await blueprint_state(db,chapter)
                return CapabilityResult(content='作品状态已读取',data=data)
            if name in ('library.status','library.search','plans.status','release.status'):
                from app.models.studio import StorySource
                from app.models.studio import ProjectBaseline
                from app.models.studio import StudioTask
                from app.models.studio import ReleaseRecord
                from app.services.library.library import coverage
                from app.services.library.library import reference_context
                if name=='library.search':
                    from app.services.platform.metering import usage_scope
                    async with usage_scope(self.uid):data=await reference_context(db,self.uid,book.id,arguments['query'])
                    return CapabilityResult(content='来源证据（不代表读完全书）',data=data)
                if name=='library.status':
                    sources=list(await db.scalars(select(StorySource).where(StorySource.book_id==book.id,StorySource.user_id==self.uid)))
                    baseline=await db.get(ProjectBaseline,book.id)
                    data={'sources':[await coverage(db,r) for r in sources],'baseline':{k:getattr(baseline,k) for k in ('mode','status','cutoff','version','notes','overrides')} if baseline else None}
                elif name=='plans.status':
                    from app.services.jobs.studio_tasks import task_out
                    data={'plans':[task_out(r) for r in await db.scalars(select(StudioTask).where(StudioTask.book_id==book.id).order_by(StudioTask.created_at.desc()).limit(10))]}
                else:
                    data={'releases':[{'id':r.id,'platform':r.platform,'status':r.status,'receipt':r.receipt} for r in await db.scalars(select(ReleaseRecord).where(ReleaseRecord.book_id==book.id).limit(10))]}
                return CapabilityResult(content='已读取本作品真实记录',data=data)
            if name=='material.read':
                outline=await db.scalar(select(Outline).where(Outline.book_id==book.id))
                return CapabilityResult(content='当前范围资料',data={'book':{'title':book.title,'intro':(book.intro or '')[:3000]},
                    'outline':json.loads(outline.content) if outline and outline.content else {},
                    'chapter_text':(chapter.content or '')[:16000] if chapter else '',
                    'content_hash':chapter_hash(chapter) if chapter else None})
            if name=='character.knowledge':
                from app.services.knowledge.narrative_state import view
                from sqlalchemy import func
                before=chapter.number if chapter else (await db.scalar(select(func.max(Chapter.number)).where(Chapter.book_id==book.id)) or 0)+1
                return CapabilityResult(content='人物知情与证据状态（只到本章之前）',data=await view(db,book.id,before,arguments['persona']))
            if name=='memory.search':
                from app.services.agent.agent_tools import execute_writer_tool
                from app.services.platform.metering import usage_scope
                async with usage_scope(self.uid):result=await execute_writer_tool('query_memory',{'query':arguments['query']},self.uid,book.id,scope.chapter_id)
                return CapabilityResult(content=result)
            if name in ('idea.brainstorm','title.suggest','text.polish','text.continue','text.scene_enhance','text.dialogue_polish'):
                from app.services.writing import writing_workflow as writing
                from app.schemas import BrainstormIn
                from app.schemas import TitleGenIn
                from app.schemas import PolishIn
                from app.schemas import ContinueIn
                from app.schemas import SceneEnhanceIn
                from app.schemas import DialoguePolishIn
                from storyclaw.workflows.continuity import prose
                user=await db.get(User,self.uid)
                if user.credits_balance<1:raise HTTPException(402,'积分不足')
                text=arguments.get('selected_text','')
                if name.startswith('text.'):
                    if not chapter:raise ValueError('请先选择当前章节')
                    if text and text not in prose(chapter.content):raise ValueError('指定片段不在当前正文，请重新选择，不会整章替换')
                instruction=arguments['instruction']
                if name=='idea.brainstorm':
                    result=await writing.assist_brainstorm(BrainstormIn(topic=instruction+'\n作品约定：'+(book.intro or '')[:2000],genre=book.genre),user,db)
                elif name=='title.suggest':
                    result=await writing.assist_title_generation(TitleGenIn(content=prose(chapter.content)[:6000] if chapter else (book.intro or ''),keywords=[instruction],target='chapter' if chapter else 'book'),user,db)
                elif name=='text.polish':result=await writing.polish_chapter(chapter.id,PolishIn(selected_text=text,polish_goal=instruction),user,db)
                elif name=='text.continue':result=await writing.continue_writing(chapter.id,ContinueIn(prefix_text=prose(chapter.content)[-1500:]),user,db)
                elif name=='text.scene_enhance':result=await writing.assist_scene_enhance(SceneEnhanceIn(scene_text=text,mood=instruction),user,db)
                else:result=await writing.assist_dialogue_polish(DialoguePolishIn(dialogue_text=text,goal=instruction),user,db)
                await db.execute(update(AgentRun).where(AgentRun.id==self.rid).values(credits_cost=AgentRun.credits_cost+result.credits_cost))
                await db.commit()
                return CapabilityResult(content=result.content,data={'artifact':True,'kind':name,'adopted':False,
                    'selected_text':text,'chapter_id':scope.chapter_id,'base_hash':chapter_hash(chapter) if chapter else None,'credits_cost':result.credits_cost})
            if not cap.job_kind:raise ValueError('此能力尚未实现')
            if cap.job_kind not in ('outline','story-design','analysis') and not chapter:raise ValueError('请先选择要处理的章节')
            # Chat can propose a paid operation; existing manuscript/ingest always needs a real decision.
            needs_confirmation=(name=='knowledge.ingest' and self.request.entry=='chat') or (
                name in ('chapter.write','chapter.revise') and chapter and bool(chapter.content) and self.request.entry=='chat')
            if needs_confirmation:
                if name=='knowledge.ingest':arguments={**arguments,'reviewed_hash':chapter_hash(chapter)}
                decision={'id':str(uuid4()),'command':name,'payload':arguments,'content_hash':chapter_hash(chapter),
                    'book_title':book.title,'chapter_title':chapter.title,'chapter_number':chapter.number,
                    'summary':'确认审阅当前正文并建立知识索引' if name=='knowledge.ingest' else '生成将替换本章正文，旧稿保留在版本历史'}
                return CapabilityResult(status='waiting_author',content=decision['summary'],data={'decision':decision})
            from app.services.agent.work_commands import JobInput
            from app.services.agent.work_commands import create_job
            # Stable operation key even if the worker crashes between submission and Run linking.
            from uuid import uuid5,NAMESPACE_URL
            key=str(uuid5(NAMESPACE_URL,self.rid+':'+name))
            body={'request_id':key,'book_id':book.id,'chapter_id':scope.chapter_id,'kind':cap.job_kind,**arguments}
            user=await db.get(User,self.uid)
            try:
                result=await create_job(JobInput.model_validate(body),user,db)
            except HTTPException as exc:
                if exc.status_code in (400,409):raise ValueError(str(exc.detail)) from exc
                raise
            return CapabilityResult(status='waiting_task',content='任务已提交，切换页面不会取消；完成后请核对结果。',data={'job_id':result['id'],'job':result})

    async def model_turn(self,messages,tools):
        from app.services.platform.llm import build_llm_from_choice
        from app.services.platform.metering import usage_scope
        from storyclaw.models.metering import MeteredModel
        from storyclaw.orchestration.model import generate_lead_turn
        client,model=await build_llm_from_choice({'kind':'business'})
        usage={};meter=None
        try:
            async with usage_scope(self.uid,run_id=self.rid) as meter:
                async def delta(text):await self.emit('message.delta',{'text':text})
                async def record_usage(data):usage.update(data)
                return await generate_lead_turn(MeteredModel(client,model,meter),messages,tools,delta,record_usage)
        finally:
            if meter and meter.calls:
                async with AsyncSessionLocal() as db:
                    run=await db.scalar(select(AgentRun).where(AgentRun.id==self.rid).with_for_update())
                    await agent_runs.event(db,run,'usage.updated',{'model':model,'credits_cost':meter.spent,'usage_known':bool(usage)})
                    await db.commit()

    async def lifecycle(self,action,run_id,data=None):
        from app.services.agent.agent_decisions import owned
        from app.services.agent.agent_decisions import decide
        from app.services.agent.agent_decisions import cancel
        from types import SimpleNamespace
        from app.models.agent import AgentEvent
        async with AsyncSessionLocal() as db:
            user=await db.get(User,self.uid)
            if not user:raise HTTPException(401,'登录失效')
            if action=='decision':return await decide(run_id,SimpleNamespace(**data),user,db)
            if action=='cancel':return await cancel(run_id,user,db)
            row=await owned(run_id,user,db)
            if action=='status':return agent_runs.out(row)
            if action=='events':
                after=int((data or {}).get('after_seq',0))
                if after<0:raise HTTPException(422,'事件位置无效')
                rows=await db.scalars(select(AgentEvent).where(AgentEvent.run_id==run_id,AgentEvent.seq>after).order_by(AgentEvent.seq).limit(200))
                return [{'id':e.id,'run_id':e.run_id,'seq':e.seq,'type':e.type,'payload':e.payload} for e in rows]
            raise ValueError('未知运行操作')
