"""Writing context composition and hybrid retrieval; accepts plain data only."""
from types import SimpleNamespace
from .context import find_outline_node,summarize_prev
from .rag.service import query_context

def _entity_brief(rows, limit: int = 12) -> str:
    """把配置实体压缩成可注入 prompt 的摘要文本。"""
    if not rows:
        return ""
    parts = []
    for r in rows:
        extra = ""
        if r.extra_json:
            try:
                extra = "，" + "、".join(f"{k}:{v}" for k, v in (r.extra_json.items() if isinstance(r.extra_json, dict) else []))[:200]
            except Exception:
                extra = ""
        desc = (r.description or "").strip()
        line = f"- {r.name}"
        if r.category:
            line += f"（{r.category}）"
        if desc:
            limit_chars = 2200 if r.category == "continuity" else 500
            line += f"：{desc[:limit_chars]}"
        line += extra
        parts.append(line)
    return "\n".join(parts[:limit])


async def compose_context(*, user_id,book_id,book,chapter,outline,settings,previous,allowed,chapter_numbers,scene_plan,pending):
    from .continuity import prose
    recent=prose(previous or '')
    outline_node=find_outline_node(outline,chapter['number'])
    setting_briefs={key:_entity_brief([SimpleNamespace(**r) for r in settings.get(kind,[])]) for key,kind in [('characters','character'),('scenes','scene'),('items','item'),('plots','plot'),('world','world')]}
    if outline.get('overview'):setting_briefs['plots']='全书总纲：'+str(outline['overview'])[:1800]+'\n'+setting_briefs['plots']
    query=' '.join(str(x) for x in [outline_node.get('title'),outline_node.get('summary'),chapter['title']] if x)[:500]
    rag=await query_context(user_id,book_id,query,top_k=5,allowed_chapter_ids=allowed)
    parts=[]
    for chunk in (rag.get('chunks') or [])[:4]:
        parts.append(f"[第{chapter_numbers.get(chunk.get('chapter_id'),'?')}章 / 来源ID {chunk.get('chapter_id')}] {chunk.get('text','')[:500]}")
    for relation in (rag.get('relations') or [])[:10]:
        parts.append(f"[来源ID {relation.get('chapter_id','?')}] {relation.get('from','')} {relation.get('type','')} {relation.get('to','')}")
    entities=rag.get('entities') or []
    if entities:parts.append('相关实体：'+'、'.join(f"{e.get('name','')}({e.get('type','')})" for e in entities[:12]))
    if rag.get('error'):parts.append('记忆检索失败：'+rag['error'])
    return {'book_brief':(book.get('intro') or '')[:3000],'chapter_meta':chapter,'outline_node':outline_node,
            'setting_briefs':setting_briefs,'prev_chapter_summary':summarize_prev(previous or ''),
            'recent_chapter_text':recent[-12000:],'recent_chapter_truncated':len(recent)>12000,'scene_plan':scene_plan,'rag_briefs':'\n'.join(parts),'memory_status':{'error':rag.get('error'),'pending_chapters':pending,'eligible_chapters':len(allowed),'sources':[{'chapter_id':c.get('chapter_id'),'chapter_number':chapter_numbers.get(c.get('chapter_id'))} for c in rag.get('chunks',[])]}}

async def query_memory_tool(user_id,book_id,query,allowed,chapter_numbers):
    """Writer's on-demand tool uses the same scoped evidence contract as preloading."""
    result=await query_context(user_id,book_id,query,top_k=5,allowed_chapter_ids=allowed)
    if result.get('error'):return '检索失败：'+result['error']
    parts=[]
    for c in result.get('chunks',[])[:4]:
        parts.append(f"- 第{chapter_numbers.get(c.get('chapter_id'),'?')}章（来源ID {c.get('chapter_id')}）：{c.get('text','')[:500]}")
    for r in result.get('relations',[])[:10]:
        parts.append(f"- [来源ID {r.get('chapter_id','?')}] {r.get('from','')} {r.get('type','')} {r.get('to','')}")
    if result.get('entities'):parts.append('相关实体：'+'、'.join(e.get('name','') for e in result['entities'][:12]))
    return '\n'.join(parts) if parts else '本书已确认记忆中未检索到相关证据；不能据此声称某事从未发生。'
