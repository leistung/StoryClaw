from datetime import datetime,timedelta,timezone
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user
from app.core.admin import get_admin_user
from app.models import User
from app.models import Post
from app.models import CreditsLedger
from app.models.product import PostLike
from app.models.product import PostComment
from app.models.product import PostModeration
from app.models.product import ContentReport
from app.models.product import MembershipOrder
from app.models.product import MembershipEntitlement
from app.models.product import WorkJob
from app.models.platform import PlatformEvent
from app.services.platform.configs import load_membership
router=APIRouter(tags=['product-operations'])

def utcnow():return datetime.now(timezone.utc)
async def visible_post(db,pid,lock=False):
    q=select(Post).where(Post.id==pid)
    if lock:q=q.with_for_update()
    p=await db.scalar(q);m=await db.get(PostModeration,pid)
    if not p or (m and m.status=='hidden'):raise HTTPException(404,'帖子不存在或已下架')
    return p

class LikeInput(BaseModel):liked:bool
class CommentInput(BaseModel):content:str=Field(min_length=1,max_length=2000)
class ReportInput(BaseModel):reason:str=Field(min_length=3,max_length=500)

@router.get('/community/posts/{pid}/engagement')
async def engagement(pid:int,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await visible_post(db,pid)
    return {'likes':await db.scalar(select(func.count()).select_from(PostLike).where(PostLike.post_id==pid)), 'liked':bool(await db.get(PostLike,(pid,u.id))),'comments':await db.scalar(select(func.count()).select_from(PostComment).where(PostComment.post_id==pid,PostComment.hidden==False))}

@router.put('/community/posts/{pid}/like')
async def like(pid:int,data:LikeInput,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await visible_post(db,pid,True)
    prior=await db.get(PostLike,(pid,u.id))
    if data.liked and not prior:db.add(PostLike(post_id=pid,user_id=u.id))
    elif not data.liked and prior:await db.delete(prior)
    await db.commit();return {'liked':data.liked}

@router.get('/community/posts/{pid}/comments')
async def comments(pid:int,page:int=Query(1,ge=1),u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await visible_post(db,pid)
    rows=await db.execute(select(PostComment,User.username).join(User,User.id==PostComment.user_id).where(PostComment.post_id==pid,PostComment.hidden==False).order_by(PostComment.created_at.desc()).offset((page-1)*30).limit(30))
    return [{'id':r.id,'user_id':r.user_id,'author':name,'content':r.content,'created_at':r.created_at.isoformat()} for r,name in rows]

@router.post('/community/posts/{pid}/comments')
async def comment(pid:int,data:CommentInput,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await visible_post(db,pid)
    if not data.content.strip():raise HTTPException(400,'评论不能为空')
    r=PostComment(post_id=pid,user_id=u.id,content=data.content.strip());db.add(r);await db.commit();await db.refresh(r)
    return {'id':r.id}

@router.delete('/community/comments/{cid}')
async def remove_comment(cid:int,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    r=await db.get(PostComment,cid)
    if not r or (r.user_id!=u.id and not u.is_admin):raise HTTPException(404,'评论不存在')
    r.hidden=True;await db.commit();return {'ok':True}

@router.post('/community/posts/{pid}/report')
async def report(pid:int,data:ReportInput,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await visible_post(db,pid,True)
    r=await db.scalar(select(ContentReport).where(ContentReport.post_id==pid,ContentReport.user_id==u.id))
    if not r:r=ContentReport(post_id=pid,user_id=u.id,reason=data.reason.strip());db.add(r)
    await db.commit();return {'ok':True,'status':r.status}

@router.get('/wallet')
async def wallet(u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    m=await db.get(MembershipEntitlement,u.id)
    return {'credits_balance':u.credits_balance,'membership':{'name':m.name,'expires_at':m.expires_at.isoformat(),'active':m.expires_at>utcnow()} if m else None,'payment_mode':'manual_review','online_payments_enabled':False}

@router.get('/wallet/ledger')
async def ledger(page:int=Query(1,ge=1),u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    rows=await db.scalars(select(CreditsLedger).where(CreditsLedger.user_id==u.id).order_by(CreditsLedger.id.desc()).offset((page-1)*30).limit(30))
    total=await db.scalar(select(func.count()).select_from(CreditsLedger).where(CreditsLedger.user_id==u.id))
    return {'items':[{'id':r.id,'delta':r.delta,'reason':r.reason,'model':r.model,'created_at':r.created_at.isoformat()} for r in rows],'total':total,'page':page}

class OrderInput(BaseModel):
    membership_id:str
    request_id:str=Field(min_length=16,max_length=64,pattern=r'^[A-Za-z0-9-]+$')

def order_out(r):return {'id':r.id,'user_id':r.user_id,'package':r.package,'status':r.status,'note':r.note,'created_at':r.created_at.isoformat(),'reviewed_at':r.reviewed_at.isoformat() if r.reviewed_at else None}

@router.post('/wallet/orders')
async def create_order(data:OrderInput,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await db.refresh(u,with_for_update=True)
    prior=await db.scalar(select(MembershipOrder).where(MembershipOrder.user_id==u.id,MembershipOrder.request_id==data.request_id))
    if prior:
        if prior.package['id']!=data.membership_id:raise HTTPException(409,'请求编号已被使用')
        return order_out(prior)
    package=next((m for m in load_membership().get('memberships',[]) if m.get('id')==data.membership_id and m.get('enabled')),None)
    if not package:raise HTTPException(400,'套餐不存在或已下线')
    if await db.scalar(select(MembershipOrder.id).where(MembershipOrder.user_id==u.id,MembershipOrder.status=='pending')):raise HTTPException(409,'已有待处理申请，请等待运营审核')
    r=MembershipOrder(id=str(uuid4()),user_id=u.id,request_id=data.request_id,package=package)
    db.add(r);await db.commit();await db.refresh(r);return order_out(r)

@router.get('/wallet/orders')
async def orders(u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return [order_out(r) for r in await db.scalars(select(MembershipOrder).where(MembershipOrder.user_id==u.id).order_by(MembershipOrder.created_at.desc()).limit(100))]

@router.get('/operations/orders')
async def operations_orders(admin:User=Depends(get_admin_user),db:AsyncSession=Depends(get_db)):
    return [dict(order_out(r),username=name) for r,name in await db.execute(select(MembershipOrder,User.username).join(User,MembershipOrder.user_id==User.id).order_by(MembershipOrder.created_at.desc()).limit(100))]

class OrderReview(BaseModel):
    action:Literal['approve','reject']
    note:str=Field(min_length=3,max_length=500)

@router.post('/operations/orders/{oid}/review')
async def review_order(oid:str,data:OrderReview,admin:User=Depends(get_admin_user),db:AsyncSession=Depends(get_db)):
    r=await db.scalar(select(MembershipOrder).where(MembershipOrder.id==oid).with_for_update())
    if not r:raise HTTPException(404,'申请不存在')
    target='approved' if data.action=='approve' else 'rejected'
    if r.status==target:return order_out(r)
    if r.status!='pending':raise HTTPException(409,'该申请已处理')
    user=await db.scalar(select(User).where(User.id==r.user_id).with_for_update())
    if data.action=='approve':
        package=r.package;credits=int(package['bonus_credits'])
        user.credits_balance+=credits
        db.add(CreditsLedger(user_id=user.id,delta=credits,reason=('会员开通-'+package['name'])[:64],model='membership'))
        entitlement=await db.get(MembershipEntitlement,user.id)
        expiry=max(entitlement.expires_at,utcnow()) if entitlement else utcnow()
        if not entitlement:entitlement=MembershipEntitlement(user_id=user.id,name=package['name'],expires_at=expiry);db.add(entitlement)
        entitlement.name=package['name'];entitlement.expires_at=expiry+timedelta(days=int(package['duration_days']))
    r.status=target;r.note=data.note;r.reviewed_at=utcnow()
    db.add(PlatformEvent(kind='audit',actor_id=admin.id,action='membership.'+data.action,target=r.id,details={'user_id':user.id,'note':data.note,'mode':'manual_review'}))
    await db.commit();return order_out(r)

@router.get('/operations/reports')
async def reports(admin:User=Depends(get_admin_user),db:AsyncSession=Depends(get_db)):
    rows=await db.execute(select(ContentReport,Post.title).join(Post,Post.id==ContentReport.post_id).order_by(ContentReport.id.desc()).limit(100))
    return [{'id':r.id,'post_id':r.post_id,'title':title,'reason':r.reason,'status':r.status,'user_id':r.user_id} for r,title in rows]

class ReportReview(BaseModel):
    action:Literal['hide','dismiss','restore']
    note:str=Field(min_length=3,max_length=500)

@router.post('/operations/reports/{rid}/review')
async def review_report(rid:int,data:ReportReview,admin:User=Depends(get_admin_user),db:AsyncSession=Depends(get_db)):
    r=await db.scalar(select(ContentReport).where(ContentReport.id==rid).with_for_update())
    if not r:raise HTTPException(404,'举报不存在')
    await db.scalar(select(Post).where(Post.id==r.post_id).with_for_update())
    if data.action!='dismiss':
        m=await db.get(PostModeration,r.post_id)
        if not m:m=PostModeration(post_id=r.post_id);db.add(m)
        m.status='hidden' if data.action=='hide' else 'visible';m.reason=data.note
    r.status='resolved'
    db.add(PlatformEvent(kind='audit',actor_id=admin.id,action='report.'+data.action,target=str(rid),details={'post_id':r.post_id,'note':data.note}))
    await db.commit();return {'ok':True}

@router.get('/operations/jobs')
async def operation_jobs(admin:User=Depends(get_admin_user),db:AsyncSession=Depends(get_db)):
    from app.gateway.routers.jobs import job_out
    return [dict(job_out(j),user_id=j.user_id) for j in await db.scalars(select(WorkJob).order_by(WorkJob.created_at.desc()).limit(100))]
