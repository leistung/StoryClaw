"""SQL/ledger adapter for package-owned creative design inference."""
import json
from sqlalchemy import select
from storyclaw.design import generate_design
from ..models import Book,ConfigEntity,Outline,CreditsLedger
from .credits import debit
from .pricing import compute_cost

async def design_draft(db,user,bid,kind):
    book=await db.get(Book,bid)
    row=await db.scalar(select(Outline).where(Outline.book_id==bid))
    existing=list(await db.scalars(select(ConfigEntity).where(ConfigEntity.book_id==bid).order_by(ConfigEntity.sort_order,ConfigEntity.id).limit(80)))
    draft,ins,outs,model=await generate_design(kind,{k:getattr(book,k) for k in ('title','intro','genre','protagonist_name','protagonist_intro')},json.loads(row.content),[{k:getattr(r,k) for k in ('entity_type','name','description')} for r in existing],{'kind':'business'})
    cost=compute_cost(model,ins,outs)
    await debit(db,user,cost)
    db.add(CreditsLedger(user_id=user.id,delta=-cost,reason='story-design',model=model,in_tokens=ins,out_tokens=outs))
    await db.commit()
    return {**draft.model_dump(),'design_type':kind,'credits_cost':cost,'applied':False}
