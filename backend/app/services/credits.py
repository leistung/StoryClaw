"""余额修改通过原子 SQL 执行；与管理员行锁调整兼容。"""
from fastapi import HTTPException
from sqlalchemy import update
from ..models import User

async def debit(db, user, cost):
    if cost < 0:
        raise ValueError("积分费用不能为负数")
    result = await db.execute(update(User).where(User.id == user.id, User.credits_balance >= cost)
        .values(credits_balance=User.credits_balance-cost).returning(User.credits_balance)
        .execution_options(synchronize_session=False))
    balance = result.scalar_one_or_none()
    if balance is None:
        raise HTTPException(402, "积分不足")
    # Expire rather than mark an ORM value dirty (which could overwrite a concurrent update).
    db.expire(user, ["credits_balance"])
