"""P1-9 社区 API：帖子 CRUD + 搜索 + [[book:id]] 解析."""
from __future__ import annotations
import re
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, or_, delete
from app.models.product import Publication
from app.models.product import PostModeration
from app.services.writing.content import clean_html
from app.services.writing.content import reading_html
from app.core.security import decode_token
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Book
from app.models import Post
from app.models import PostBookLink
from app.models import User
from app.schemas import PostCreateIn
from app.schemas import PostUpdateIn
from app.schemas import PostOut
from app.schemas import PostListOut
from app.schemas import BookLinkOut
from app.schemas import SearchResultOut

router = APIRouter(prefix="/community", tags=["community"])

BOOK_LINK_RE = re.compile(r"\[\[book:(\d+)\]\]")


async def _post_to_out(db: AsyncSession, p: Post, include_links: bool = True) -> PostOut:
    """将 Post ORM 转为 PostOut，解析 [[book:id]] 链接."""
    u = await db.get(User, p.user_id)
    author_name = u.username if u else ""
    book_links: list[BookLinkOut] = []
    if include_links:
        links = await db.scalars(select(PostBookLink).where(PostBookLink.post_id == p.id))
        for link in links:
            b = await db.get(Book, link.book_id)
            publication = await db.get(Publication, link.book_id)
            if b and publication and publication.visible:
                book_links.append(BookLinkOut(
                    book_id=publication.book_id, book_title=publication.snapshot.get("title",""), book_cover_url=publication.snapshot.get("cover_url", "")))
    return PostOut(
        id=p.id, user_id=p.user_id, author_name=author_name,
        title=p.title, content_html=clean_html(p.content_html), content_text=p.content_text,
        book_links=book_links, created_at=p.created_at, updated_at=p.updated_at,
    )


def _extract_book_ids(content: str) -> list[int]:
    """从内容中提取 [[book:id]] 的 book_id 列表."""
    return [int(m) for m in BOOK_LINK_RE.findall(content)]


def _render_book_links(content_html: str) -> str:
    """将 [[book:id]] 替换为 <a href='/read/{id}'>链接</a>."""
    def replacer(m):
        bid = m.group(1)
        return f'<a href="/read/{bid}" class="book-link">📖 查看作品 #{bid}</a>'
    return BOOK_LINK_RE.sub(replacer, content_html)


@router.get("/posts", response_model=PostListOut)
async def list_posts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """列出帖子（公开，分页，不含 content_html 详情，但含 book_links）."""
    offset = (page - 1) * size
    visible = ~select(PostModeration.post_id).where(PostModeration.post_id==Post.id,PostModeration.status=="hidden").exists()
    total = await db.scalar(select(func.count(Post.id)).where(visible))
    rs = await db.scalars(select(Post).where(visible).order_by(
        Post.created_at.desc()
    ).offset(offset).limit(size))
    items = [await _post_to_out(db, p, include_links=True) for p in rs]
    return PostListOut(items=items, total=total or 0, page=page, page_size=size)


@router.get("/posts/{pid}", response_model=PostOut)
async def get_post(pid: int, db: AsyncSession = Depends(get_db)):
    """获取帖子详情（公开，渲染 [[book:id]] 为链接）."""
    p = await db.get(Post, pid)
    moderation=await db.get(PostModeration,pid)
    if not p or (moderation and moderation.status=="hidden"):
        raise HTTPException(404, "帖子不存在或已下架")
    out = await _post_to_out(db, p, include_links=True)
    out.content_html = _render_book_links(out.content_html)
    return out


@router.post("/posts", response_model=PostOut)
async def create_post(
    data: PostCreateIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建帖子（需登录），自动解析 [[book:id]] 关联."""
    p = Post(user_id=u.id, title=data.title, content_html=clean_html(data.content_html), content_text=data.content_text)
    db.add(p)
    await db.flush()
    # 提取并存储 book links
    book_ids = _extract_book_ids(data.content_html + " " + data.content_text)
    for bid in set(book_ids):
        b = await db.get(Book, bid)
        pub=await db.get(Publication,bid)
        if b and pub and pub.visible:
            db.add(PostBookLink(post_id=p.id, book_id=bid))
    await db.commit()
    await db.refresh(p)
    return await _post_to_out(db, p, include_links=True)


@router.put("/posts/{pid}", response_model=PostOut)
async def update_post(
    pid: int, data: PostUpdateIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新帖子（仅作者）."""
    p = await db.get(Post, pid)
    if not p or p.user_id != u.id:
        raise HTTPException(404, "帖子不存在或无权限")
    if data.title is not None:
        p.title = data.title
    if data.content_html is not None:
        p.content_html = clean_html(data.content_html)
    if data.content_text is not None:
        p.content_text = data.content_text
    # 重新解析 book links
    await db.execute(delete(PostBookLink).where(PostBookLink.post_id == pid))
    content = (p.content_html or "") + " " + (p.content_text or "")
    book_ids = _extract_book_ids(content)
    for bid in set(book_ids):
        b = await db.get(Book, bid)
        pub=await db.get(Publication,bid)
        if b and pub and pub.visible:
            db.add(PostBookLink(post_id=pid, book_id=bid))
    await db.commit()
    await db.refresh(p)
    return await _post_to_out(db, p, include_links=True)


@router.delete("/posts/{pid}")
async def delete_post(
    pid: int,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除帖子（仅作者）."""
    p = await db.get(Post, pid)
    if not p or p.user_id != u.id:
        raise HTTPException(404, "帖子不存在或无权限")
    await db.delete(p)
    await db.commit()
    return {"ok": True, "id": pid}


@router.get("/search", response_model=SearchResultOut)
async def search(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    """搜索帖子内容/书名/简介."""
    kw = f"%{q}%"
    # 搜索帖子
    post_rs = await db.scalars(select(Post).where(
        or_(Post.title.ilike(kw), Post.content_text.ilike(kw)),
        ~select(PostModeration.post_id).where(PostModeration.post_id==Post.id,PostModeration.status=="hidden").exists()
    ).order_by(Post.created_at.desc()).limit(20))
    posts = [await _post_to_out(db, p, include_links=True) for p in post_rs]
    publications=await db.scalars(select(Publication).where(Publication.visible==True).limit(200))
    books=[{k:p.snapshot.get(k,'') for k in ('id','title','intro','genre','cover_url')} for p in publications if q.casefold() in (' '.join(str(p.snapshot.get(k,'')) for k in ('title','intro','genre'))).casefold()][:20]
    return SearchResultOut(posts=posts, books=books, total=len(posts) + len(books))


async def _read_snapshot(bid,request,db):
    # Owners can preview their drafts; everyone else only sees an explicit snapshot.
    token=request.headers.get('authorization','').removeprefix('Bearer ')
    sub=decode_token(token) if token else None
    b=await db.get(Book,bid)
    if b and sub==str(b.user_id):
        from app.models import Chapter
        rows=await db.scalars(select(Chapter).where(Chapter.book_id==bid).order_by(Chapter.number))
        result={k:getattr(b,k) or '' for k in ('id','title','intro','genre','cover_url','protagonist_name','protagonist_intro')}
        result['chapters']=[{'id':c.id,'number':c.number,'title':c.title,'word_count':c.word_count,'content':reading_html(c.content)} for c in rows]
        return result
    p=await db.get(Publication,bid)
    if not p or not p.visible:raise HTTPException(404,'作品尚未公开或已下架')
    return p.snapshot

@router.get('/books/{bid}/read')
async def get_book_for_read(bid:int,request:Request,db:AsyncSession=Depends(get_db)):
    data=await _read_snapshot(bid,request,db)
    return {k:v for k,v in data.items() if k!='chapters'}

@router.get('/books/{bid}/read/chapters')
async def list_chapters_for_read(bid:int,request:Request,db:AsyncSession=Depends(get_db)):
    data=await _read_snapshot(bid,request,db)
    return [{k:v for k,v in c.items() if k!='content'} for c in data['chapters']]

@router.get('/books/{bid}/read/chapters/{cid}')
async def get_chapter_for_read(bid:int,cid:int,request:Request,db:AsyncSession=Depends(get_db)):
    data=await _read_snapshot(bid,request,db)
    c=next((c for c in data['chapters'] if c['id']==cid),None)
    if not c:raise HTTPException(404,'章节未公开')
    return c
