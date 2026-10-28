"""Host snapshots and price estimates for author-reviewed generation plans."""
import json
from sqlalchemy import select
from app.models import Book, Outline, ConfigEntity
from storyclaw.workflows.serial import digest

async def plan_context(db, book):
    outline = await db.scalar(select(Outline).where(Outline.book_id==book.id))
    cards = list(await db.scalars(select(ConfigEntity).where(ConfigEntity.book_id==book.id,
                 ConfigEntity.entity_type.in_(['character','world','plot','scene','item'])).order_by(ConfigEntity.id)))
    return {'book':{k:getattr(book,k) for k in ('title','intro','genre','protagonist_name','protagonist_intro','target_chapters','target_words','per_chapter_words')},
            'outline':json.loads(outline.content) if outline else {},
            'existing':[{'type':c.entity_type,'name':c.name,'description':c.description,'extra':c.extra_json} for c in cards]}

def inference_context(context):
    outline=context['outline']
    return {'book':context['book'],'outline':{'overview':str(outline.get('overview',''))[:3000],
        'planning_mode':outline.get('planning_mode'),'volumes':[{'name':v.get('name'),'goal':str(v.get('goal',''))[:1000]} for v in outline.get('volumes',[])[:12]]},
        'existing':[{**c,'description':(c['description'] or '')[:700],'extra':{}} for c in context['existing'][:60]],
        'omitted_settings':max(0,len(context['existing'])-60)}

def estimate(plan, kind, context, planning_mode='serial'):
    from app.services.platform.configs import load_models
    from app.services.platform.pricing import compute_cost
    count = len(plan.sections) if kind=='outline' else plan.item_count
    words = count*plan.detail_words + (1000 if kind=='outline' else 400)
    calls = count+1 if kind=='outline' else (count+2)//3
    if kind=='outline' and planning_mode=='fixed':
        chapters = int(context['book'].get('target_chapters') or 20)
        words += chapters*250
        calls += sum(((chapters//count+(i<chapters%count))+4)//5 for i in range(count))
    size = len(json.dumps(inference_context(context),ensure_ascii=False))
    ins = [calls*(size+1200)//2, calls*(size+4000)*2]
    outs = [words, words*3]
    model = next((m['id'] for m in load_models().get('models',[]) if m.get('enabled') and m['id']!='custom-local'),None)
    credits = None
    if model:
        try: credits = [compute_cost(model,ins[0],outs[0])+calls-1, compute_cost(model,ins[1],outs[1])+calls-1]
        except (ValueError,KeyError): pass
    return {'words':[round(words*.8),round(words*1.2)],'input_tokens':ins,'output_tokens':outs,
            'total_tokens':[ins[0]+outs[0],ins[1]+outs[1]],'credits':credits,'model':model,
            'calls':calls,'note':'仅估算正式生成，不含已发生的计划讨论、后续修改、正文或入库；按实际模型用量结算，重试或模型切换会影响费用。'}

async def prepare(db,book,name,arguments,previous,emit):
    from storyclaw.workflows.creation_plan import propose_plan
    context = await plan_context(db,book)
    if name=='setting.draft':
        from app.services.writing.planning import require_outline
        await require_outline(db,book.id)
    await emit('step.started',{'name':'creation.plan','label':'读取作品资料，拟订生成计划',
               'details':{'book_id':book.id,'settings_count':len(context['existing']),'command':name}})
    kind = 'outline' if name=='framework.draft' else arguments['design_type']
    plan = await propose_plan(kind,{**inference_context(context),'instruction':arguments.get('prompt',''),
              'planning_mode':arguments.get('planning_mode','serial'),
              'previous_plan':previous.get('plan'),'feedback':previous.get('feedback','')})
    if kind=='outline' and arguments.get('planning_mode')=='fixed' and len(plan.sections)>int(book.target_chapters or 20):
        raise ValueError('建议卷数超过目标章数，请增加目标章数或补充更少的分卷要求')
    await emit('step.completed',{'name':'creation.plan','label':'生成计划已拟订，等待你补充或确认'})
    return plan,context,estimate(plan,kind,context,arguments.get('planning_mode','serial'))
