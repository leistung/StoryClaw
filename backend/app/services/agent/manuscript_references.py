"""Resolve author-attached text ranges against a verified manuscript version."""
import re
from fastapi import HTTPException
from storyclaw.workflows.continuity import prose
from app.models import Chapter
from app.services.writing.revisions import chapter_hash

def resolve_reference(content,reference):
    text=prose(content)
    positions=[i for i,c in enumerate(text) if not c.isspace()]
    compact=''.join(text[i] for i in positions)
    offset=reference.offset
    if offset>len(positions):raise ValueError('引用位置已失效，请重新选择')
    if reference.kind=='selection':
        selected=re.sub(r'\s+','',reference.text)
        if not selected or compact[offset:offset+len(selected)]!=selected:
            raise ValueError('引用片段与正文不一致，请重新选择')
        start=positions[offset];end=positions[offset+len(selected)-1]+1
    elif reference.kind=='cursor':
        start=(positions[offset-1]+1 if offset else 0) if reference.affinity=='after' else (positions[offset] if offset<len(positions) else len(text))
        end=start
    else:start,end=0,len(text)
    result={'start':start,'end':end,'text':text[start:end]}
    if reference.kind=='cursor':result['affinity']=reference.affinity
    return result

async def validate_references(db,request):
    for reference in request.references:
        if reference.chapter_id!=request.scope.chapter_id or not request.scope.book_id:
            raise HTTPException(422,'正文引用必须属于本次操作的章节')
        chapter=await db.get(Chapter,reference.chapter_id)
        if not chapter or chapter.book_id!=request.scope.book_id:raise HTTPException(404,'引用章节不存在')
        if chapter_hash(chapter)!=reference.expected_hash:raise HTTPException(409,'引用的正文版本已变化，请重新选择后发送')
        if reference.line_end<reference.line_start:raise HTTPException(422,'引用行范围无效')
        try:resolve_reference(chapter.content,reference)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc

def replace_range(content,start,end,replacement,affinity='before'):
    """Keep unaffected reading HTML and formatting while replacing text nodes."""
    from html.parser import HTMLParser
    from html import escape
    from app.services.writing.content import clean_html,reading_html
    if not re.search(r'<[a-zA-Z][^>]*>',content or ''):
        return reading_html((content or '')[:start]+replacement+(content or '')[end:])
    class Replace(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=True);self.pos=0;self.parts=[];self.inserted=False
        def handle_starttag(self,tag,attrs):self.parts.append(self.get_starttag_text())
        def handle_endtag(self,tag):
            if not self.inserted and self.pos==start==end==0 and tag in ('p','h1','h2','h3','blockquote'):
                self.parts.append(escape(replacement).replace('\n','<br>'));self.inserted=True
            self.parts.append(f'</{tag}>')
        def handle_data(self,data):
            first=self.pos;last=first+len(data);self.pos=last
            if last==start and first<last and (start!=end or affinity=='before'):
                self.parts.append(escape(data));return
            left=data[:max(0,min(len(data),start-first))]
            right=data[max(0,min(len(data),end-first)):]
            if last<start or first>end or (self.inserted and start==end):self.parts.append(escape(data));return
            self.parts.append(escape(left))
            if not self.inserted and first<=start<=last:
                self.parts.append(escape(replacement).replace('\n','<br>'));self.inserted=True
            self.parts.append(escape(right))
    parser=Replace();parser.feed(content);parser.close()
    if not parser.inserted:raise ValueError('正文插入位置不可用，请手动对照采用')
    return clean_html(''.join(parser.parts))
