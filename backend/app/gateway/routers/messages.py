"""P2-10 消息系统 API."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_current_user
from app.database import get_db
from app.models import User
from app.models import Friendship
from app.models import SocialMessage

router = APIRouter(prefix="/messages", tags=["messages"])


class FriendRequestIn(BaseModel):
    friend_username: str


class SendMessageIn(BaseModel):
    receiver_id: int
    content: str
    msg_type: str = "text"  # text | emoji | image | video
    attachment_url: str | None = None


@router.post("/friend-request")
async def send_friend_request(
    data: FriendRequestIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    friend = await db.scalar(select(User).where(User.username == data.friend_username))
    if not friend:
        raise HTTPException(404, "用户不存在")
    if friend.id == u.id:
        raise HTTPException(400, "不能加自己为好友")
    existing = await db.scalar(select(Friendship).where(
        or_(and_(Friendship.user_id == u.id, Friendship.friend_id == friend.id),
            and_(Friendship.user_id == friend.id, Friendship.friend_id == u.id))
    ))
    if existing:
        if existing.status == "accepted":
            raise HTTPException(400, "已经是好友")
        raise HTTPException(400, "已有待处理的好友请求")
    f = Friendship(user_id=u.id, friend_id=friend.id, status="pending")
    db.add(f)
    await db.commit()
    return {"ok": True, "friend_id": friend.id, "status": "pending"}


@router.get("/friend-requests")
async def list_friend_requests(
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rs = await db.scalars(select(Friendship).where(
        Friendship.friend_id == u.id, Friendship.status == "pending"
    ).order_by(Friendship.created_at.desc()))
    result = []
    for f in rs:
        sender = await db.get(User, f.user_id)
        result.append({"id": f.id, "sender_id": f.user_id,
                       "sender_name": sender.username if sender else "",
                       "created_at": str(f.created_at) if f.created_at else None})
    return result


@router.post("/friend-request/{fid}/accept")
async def accept_friend_request(
    fid: int,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    f = await db.get(Friendship, fid)
    if not f or f.friend_id != u.id:
        raise HTTPException(404, "好友请求不存在")
    f.status = "accepted"
    # 创建反向好友关系
    reverse = Friendship(user_id=u.id, friend_id=f.user_id, status="accepted")
    db.add(reverse)
    await db.commit()
    return {"ok": True, "status": "accepted"}


@router.post("/friend-request/{fid}/reject")
async def reject_friend_request(
    fid: int,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    f = await db.get(Friendship, fid)
    if not f or f.friend_id != u.id:
        raise HTTPException(404, "好友请求不存在")
    await db.delete(f)
    await db.commit()
    return {"ok": True, "status": "rejected"}


@router.get("/friends")
async def list_friends(
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rs = await db.scalars(select(Friendship).where(
        Friendship.user_id == u.id, Friendship.status == "accepted"
    ))
    result = []
    for f in rs:
        friend = await db.get(User, f.friend_id)
        if friend:
            result.append({"id": friend.id, "username": friend.username,
                           "created_at": str(f.created_at) if f.created_at else None})
    return result


@router.post("/send")
async def send_message(
    data: SendMessageIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 检查是否是好友
    is_friend = await db.scalar(select(Friendship).where(
        Friendship.user_id == u.id, Friendship.friend_id == data.receiver_id,
        Friendship.status == "accepted"
    ))
    if not is_friend:
        raise HTTPException(403, "只能给好友发消息")
    msg = SocialMessage(sender_id=u.id, receiver_id=data.receiver_id,
                        content=data.content, msg_type=data.msg_type,
                        attachment_url=data.attachment_url)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return {"id": msg.id, "sender_id": msg.sender_id, "receiver_id": msg.receiver_id,
            "content": msg.content, "msg_type": msg.msg_type,
            "created_at": str(msg.created_at) if msg.created_at else None}


@router.get("/conversation/{friend_id}")
async def get_conversation(
    friend_id: int,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    offset = (page - 1) * size
    rs = await db.scalars(select(SocialMessage).where(
        or_(and_(SocialMessage.sender_id == u.id, SocialMessage.receiver_id == friend_id),
            and_(SocialMessage.sender_id == friend_id, SocialMessage.receiver_id == u.id))
    ).order_by(SocialMessage.created_at.desc()).offset(offset).limit(size))
    msgs = list(rs)
    # 标记已读
    for m in msgs:
        if m.receiver_id == u.id and not m.read:
            m.read = True
    await db.commit()
    return [{"id": m.id, "sender_id": m.sender_id, "receiver_id": m.receiver_id,
             "content": m.content, "msg_type": m.msg_type,
             "attachment_url": m.attachment_url, "read": m.read,
             "created_at": str(m.created_at) if m.created_at else None}
            for m in reversed(msgs)]


@router.get("/unread-count")
async def unread_count(
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    count = await db.scalar(select(func.count(SocialMessage.id)).where(
        SocialMessage.receiver_id == u.id, SocialMessage.read == False
    ))
    return {"unread": count or 0}
