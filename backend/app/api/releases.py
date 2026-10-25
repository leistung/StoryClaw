"""Frozen export packages, readiness review and explicit external receipts."""
import json,hashlib,io,zipfile
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import Response
from pydantic import BaseModel,Field
from sqlalchemy import select
from ..core.deps import get_current_user
from ..database import get_db
from ..models import User,Chapter,ConfigEntity
from ..models.studio import ReleaseRecord,ProjectBaseline,StorySource,PrivateMethod
from ..services.library import own_book
from ..services.revisions import chapter_hash
router=APIRouter(tags=['release-preparation'])
class Prepare(BaseModel):
    platform:str=Field(min_length=1,max_length=100)
    start:int=Field(default=1,ge=1)
    end:int=Field(default=10000,ge=1)
    rights_confirmed:bool=False
    ai_policy_confirmed:bool=False
    scheduled_at:datetime|None=None
@router.post('/books/{bid}/releases')
async def prepare(bid:int,data:Prepare,u:User=Depends(get_current_user),db=Depends(get_db)):
    b=await own_book(db,u.id,bid,True)
    if not data.rights_confirmed or not data.ai_policy_confirmed:raise HTTPException(422,'请先核对投稿平台的权利要求与AI使用规则')
    baseline=await db.get(ProjectBaseline,bid)
    if baseline:
        source=await db.get(StorySource,baseline.source_id)
        if source.status=='revoked' or not source.rights.get('commercial_allowed'):raise HTTPException(409,'来源未确认商业使用许可，不能准备商业投稿包')
        if baseline.status=='stale':raise HTTPException(409,'请先重新核对接管基线')
    chapters=list(await db.scalars(select(Chapter).where(Chapter.book_id==bid,Chapter.number>=data.start,Chapter.number<=data.end,Chapter.word_count>0).order_by(Chapter.number)))
    if not chapters:raise HTTPException(422,'范围内没有正文')
    impacts=list(await db.scalars(select(ConfigEntity).where(ConfigEntity.book_id==bid,ConfigEntity.category=='continuity-impact')))
    chosen={c.id for c in chapters}
    if any((r.extra_json or {}).get('active') and (r.extra_json or {}).get('chapter_id') in chosen for r in impacts):raise HTTPException(409,'待投稿章节仍有前文变更复核提示')
    snapshot={'title':b.title,'intro':b.intro,'genre':b.genre,'chapters':[{'id':c.id,'number':c.number,'title':c.title,'content':c.content,'hash':chapter_hash(c)} for c in chapters]}
    snapshot['hash']=hashlib.sha256(json.dumps(snapshot,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    r=ReleaseRecord(id=str(uuid4()),user_id=u.id,book_id=bid,platform=data.platform,status='prepared',snapshot=snapshot,policy=data.model_dump(mode='json'),receipt={},scheduled_at=data.scheduled_at)
    db.add(r);await db.commit();return out(r)
def out(r):return {'id':r.id,'platform':r.platform,'status':r.status,'hash':r.snapshot['hash'],'chapters':len(r.snapshot['chapters']),'receipt':r.receipt,'scheduled_at':r.scheduled_at,'delivery':'manual-export'}
@router.get('/books/{bid}/releases')
async def listing(bid:int,u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_book(db,u.id,bid)
    from ..models.operations import ReleaseDelivery
    result=[]
    for r in await db.scalars(select(ReleaseRecord).where(ReleaseRecord.book_id==bid).order_by(ReleaseRecord.created_at.desc())):
        delivery=await db.get(ReleaseDelivery,r.id)
        result.append({**out(r),'delivery_status':delivery.status if delivery else None,'due_at':delivery.due_at if delivery else None,'delivery_error':delivery.error if delivery else None})
    return result
async def owned(db,uid,rid):
    r=await db.scalar(select(ReleaseRecord).where(ReleaseRecord.id==rid,ReleaseRecord.user_id==uid))
    if not r:raise HTTPException(404,'投稿记录不存在')
    return r
@router.get('/releases/{rid}/export')
async def export(rid:str,u:User=Depends(get_current_user),db=Depends(get_db)):
    r=await owned(db,u.id,rid);buf=io.BytesIO()
    from ..services.content import plain_text
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps({'snapshot':r.snapshot['hash'],'platform':r.platform,'policy':r.policy},ensure_ascii=False,indent=2))
        z.writestr('manuscript.txt',r.snapshot['title']+'\n\n'+'\n\n'.join(c['title']+'\n'+plain_text(c['content']) for c in r.snapshot['chapters']))
    return Response(buf.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="storyclaw-release.zip"'})
class Receipt(BaseModel):
    status:str=Field(pattern='^(submitted|accepted|rejected|withdrawn)$')
    reference:str=Field(default='',max_length=1000)
    note:str=Field(default='',max_length=4000)
    snapshot_hash:str=Field(min_length=64,max_length=64)
@router.post('/releases/{rid}/receipt')
async def receipt(rid:str,data:Receipt,u:User=Depends(get_current_user),db=Depends(get_db)):
    r=await owned(db,u.id,rid)
    if r.platform=='storyclaw':raise HTTPException(422,'本站发布状态由投递任务管理，请在书籍信息中公开或下架')
    if r.snapshot['hash']!=data.snapshot_hash:raise HTTPException(409,'投稿快照不一致')
    r.status=data.status;r.receipt={'history':[*r.receipt.get('history',[]),data.model_dump()],'source':'author-reported'};await db.commit();return out(r)
class MethodIn(BaseModel):
    title:str=Field(min_length=1,max_length=150)
    content:str=Field(min_length=10,max_length=12000)
    enabled:bool=False
@router.get('/private-methods')
async def methods(u:User=Depends(get_current_user),db=Depends(get_db)):
    return [{'id':r.id,'title':r.title,'content':r.content,'enabled':r.enabled} for r in await db.scalars(select(PrivateMethod).where(PrivateMethod.user_id==u.id))]
@router.post('/private-methods')
async def method(data:MethodIn,u:User=Depends(get_current_user),db=Depends(get_db)):
    rows=list(await db.scalars(select(PrivateMethod).where(PrivateMethod.user_id==u.id)))
    if len(rows)>=20:raise HTTPException(422,'最多20份私人写作方法，请先整理已有内容')
    if data.enabled and sum(r.enabled for r in rows)>=5:raise HTTPException(422,'同时最多启用5份私人方法')
    r=PrivateMethod(id=str(uuid4()),user_id=u.id,**data.model_dump());db.add(r);await db.commit();return {'id':r.id}
@router.put('/private-methods/{mid}')
async def update_method(mid:str,data:MethodIn,u:User=Depends(get_current_user),db=Depends(get_db)):
    r=await db.scalar(select(PrivateMethod).where(PrivateMethod.id==mid,PrivateMethod.user_id==u.id))
    if not r:raise HTTPException(404,'私人方法不存在')
    if data.enabled and not r.enabled:
        enabled=list(await db.scalars(select(PrivateMethod).where(PrivateMethod.user_id==u.id,PrivateMethod.enabled==True)))
        if len(enabled)>=5:raise HTTPException(422,'同时最多启用5份私人方法')
    for k,v in data.model_dump().items():setattr(r,k,v)
    await db.commit();return {'id':r.id}
@router.delete('/private-methods/{mid}')
async def delete_method(mid:str,u:User=Depends(get_current_user),db=Depends(get_db)):
    r=await db.scalar(select(PrivateMethod).where(PrivateMethod.id==mid,PrivateMethod.user_id==u.id))
    if not r:raise HTTPException(404,'私人方法不存在')
    await db.delete(r);await db.commit();return {'deleted':True}

class DeliveryIn(BaseModel):
    snapshot_hash:str=Field(min_length=64,max_length=64)
    confirmed:bool=False
    due_at:datetime
@router.post('/releases/{rid}/schedule')
async def schedule(rid:str,data:DeliveryIn,u:User=Depends(get_current_user),db=Depends(get_db)):
    from datetime import timezone
    from ..models.operations import ReleaseDelivery
    first=await owned(db,u.id,rid)
    await own_book(db,u.id,first.book_id,True)
    r=await db.scalar(select(ReleaseRecord).where(ReleaseRecord.id==rid,ReleaseRecord.user_id==u.id).with_for_update())
    if not r:raise HTTPException(404,'投稿记录不存在')
    if not data.confirmed or data.snapshot_hash!=r.snapshot['hash']:raise HTTPException(409,'请核对并明确批准这一固定版本公开发布')
    if r.platform!='storyclaw':raise HTTPException(422,'预约自动发布仅支持本站；外部平台仍需手动投稿')
    if data.due_at.tzinfo is None or data.due_at<=datetime.now(timezone.utc):raise HTTPException(422,'请选择带时区的未来发布时间')
    row=await db.get(ReleaseDelivery,rid)
    if row and row.status=='delivered':raise HTTPException(409,'该版本已投递，请创建新版本')
    if not row:row=ReleaseDelivery(release_id=rid,due_at=data.due_at,status='scheduled');db.add(row)
    else:row.due_at=data.due_at;row.status='scheduled';row.error=None
    await db.commit();return {'status':row.status,'due_at':row.due_at}
@router.delete('/releases/{rid}/schedule')
async def unschedule(rid:str,u:User=Depends(get_current_user),db=Depends(get_db)):
    from ..models.operations import ReleaseDelivery
    await owned(db,u.id,rid)
    row=await db.scalar(select(ReleaseDelivery).where(ReleaseDelivery.release_id==rid).with_for_update())
    if not row:raise HTTPException(404,'没有预约')
    if row.status=='delivered':raise HTTPException(409,'已经公开，请使用书籍信息中的下架操作')
    row.status='cancelled';await db.commit();return {'status':'cancelled'}
