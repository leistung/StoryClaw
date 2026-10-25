"""SQL/auth/jobs/billing implementation of StoryClaw ports; no creative prompts."""
import asyncio,json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select,update
from storyclaw.contracts import CapabilityResult,ModelTurn,ToolCall
from storyclaw.orchestration.capabilities import get_capability
from ...database import AsyncSessionLocal
from ...models import User,Book,Chapter,Outline,CreditsLedger
from ...models.agent import AgentRun
from .. import agent_runs
from ..revisions import chapter_hash

class BackendStoryPorts:
    def __init__(self,rid,uid,request):self.rid=rid;self.uid=uid;self.request=request

    async def emit(self,kind,payload):
        await agent_runs.append(self.rid,self.uid,kind,payload)

    async def execute(self,name,arguments):
        cap=get_capability(name);scope=self.request.scope
        async with AsyncSessionLocal() as db:
            await agent_runs.validate_scope(db,self.uid,scope)
            row=await db.get(AgentRun,self.rid)
            if row.status=='cancelled':raise HTTPException(409,'请求已取消')
            if not scope.book_id:raise ValueError('请先打开一本作品，再使用此能力；首页选题请使用开书讨论。')
            book=await db.get(Book,scope.book_id)
            chapter=await db.get(Chapter,scope.chapter_id) if scope.chapter_id else None
            if name=='project.status':
                from ..serial import blueprint_state
                from storyclaw.workflow import is_confirmed
                outline=await db.scalar(select(Outline).where(Outline.book_id==book.id))
                content=json.loads(outline.content) if outline and outline.content else {}
                recent=list(await db.scalars(select(Chapter).where(Chapter.book_id==book.id).order_by(Chapter.number.desc()).limit(20)))
                data={'title':book.title,'genre':book.genre,'outline_confirmed':is_confirmed(content),
                    'current_chapter':({'id':chapter.id,'number':chapter.number,'words':chapter.word_count,'rag_status':chapter.rag_status} if chapter else None),
                    'recent_chapters':[{'id':c.id,'number':c.number,'words':c.word_count,'rag_status':c.rag_status} for c in recent]}
                if chapter:data['blueprint']=await blueprint_state(db,chapter)
                return CapabilityResult(content='作品状态已读取',data=data)
            if name=='material.read':
                outline=await db.scalar(select(Outline).where(Outline.book_id==book.id))
                return CapabilityResult(content='当前范围资料',data={'book':{'title':book.title,'intro':(book.intro or '')[:3000]},
                    'outline':json.loads(outline.content) if outline and outline.content else {},
                    'chapter_text':(chapter.content or '')[:16000] if chapter else '',
                    'content_hash':chapter_hash(chapter) if chapter else None})
            if name=='memory.search':
                from ..agent_tools import execute_writer_tool
                result=await execute_writer_tool('query_memory',{'query':arguments['query']},self.uid,book.id,scope.chapter_id)
                return CapabilityResult(content=result)
            if not cap.job_kind:raise ValueError('此能力尚未实现')
            if cap.job_kind not in ('outline','story-design','analysis') and not chapter:raise ValueError('请先选择要处理的章节')
            # Chat can propose a paid operation; existing manuscript/ingest always needs a real decision.
            needs_confirmation=(name=='knowledge.ingest' and self.request.entry=='chat') or (
                name=='chapter.write' and chapter and bool(chapter.content) and self.request.entry=='chat')
            if needs_confirmation:
                decision={'id':str(uuid4()),'command':name,'payload':arguments,'content_hash':chapter_hash(chapter),
                    'summary':'确认审阅当前正文并建立知识索引' if name=='knowledge.ingest' else '生成将替换本章正文，旧稿保留在版本历史'}
                return CapabilityResult(status='waiting_author',content=decision['summary'],data={'decision':decision})
            from ..work_commands import JobInput,create_job
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
        from ..llm import build_llm_from_choice
        from ..pricing import compute_cost
        from ..credits import debit
        from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
        llm,model=await build_llm_from_choice({'kind':'business'})
        # Byte count bounds ordinary text tokenization conservatively; include tool wrappers.
        bound=len(json.dumps([messages,tools],ensure_ascii=False).encode())+2048
        reserve=compute_cost(model,bound,1024)
        async with AsyncSessionLocal() as db:
            run=await db.scalar(select(AgentRun).where(AgentRun.id==self.rid).with_for_update())
            if run.status!='running':raise HTTPException(409,'请求不再执行')
            if run.credits_cost+reserve>100:raise HTTPException(402,'本轮积分预算上限为100，请缩小目标后重试')
            user=await db.get(User,self.uid);await debit(db,user,reserve);run.reserved=reserve;await db.commit()
        usage={};response=None
        try:
            types={'system':SystemMessage,'user':HumanMessage,'assistant':AIMessage}
            msgs=[types[m['role']](content=str(m['content'])[:20000]) for m in messages]
            client=llm.bind_tools(tools).bind(max_tokens=1024)
            buffer=''
            async with asyncio.timeout(120):
                async for chunk in client.astream(msgs):
                    response=chunk if response is None else response+chunk
                    # Do not expose partial tool JSON as prose.
                    if isinstance(chunk.content,str) and chunk.content:
                        buffer+=chunk.content
                        if len(buffer)>=40:
                            await self.emit('message.delta',{'text':buffer});buffer=''
                if buffer:await self.emit('message.delta',{'text':buffer})
            if response is None:raise ValueError('模型没有返回内容')
            usage=response.usage_metadata or {}
            if response.additional_kwargs.get('tool_calls') and not response.tool_calls:raise ValueError('模型工具调用格式不完整')
            if getattr(response,'invalid_tool_calls',None):raise ValueError('模型工具调用格式不完整')
            reason=(response.response_metadata or {}).get('finish_reason')
            if reason in ('length','max_tokens'):raise ValueError('模型输出被截断，未执行不完整工具')
            return ModelTurn(text=response.content if isinstance(response.content,str) else '',
                calls=[ToolCall(name=c['name'],arguments=c.get('args') or {}) for c in response.tool_calls])
        finally:
            async with AsyncSessionLocal() as db:
                run=await db.scalar(select(AgentRun).where(AgentRun.id==self.rid).with_for_update())
                # Unknown supplier usage is explicitly recorded; no invented token count.
                cost=compute_cost(model,int(usage.get('input_tokens',0)),int(usage.get('output_tokens',0))) if usage else 0
                held=run.reserved
                if cost>held:
                    user=await db.get(User,self.uid);await debit(db,user,cost-held)
                elif held>cost:
                    await db.execute(update(User).where(User.id==self.uid).values(credits_balance=User.credits_balance+held-cost))
                run.reserved=0;run.credits_cost+=cost
                db.add(CreditsLedger(user_id=self.uid,delta=-cost,reason='agent-loop',model=model,
                    in_tokens=int(usage.get('input_tokens',0)),out_tokens=int(usage.get('output_tokens',0))))
                await agent_runs.event(db,run,'usage.updated',{'model':model,'credits_cost':cost,'usage_known':bool(usage)})
                await db.commit()
