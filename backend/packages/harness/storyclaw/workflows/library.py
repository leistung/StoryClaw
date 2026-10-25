"""Safe manuscript parsing and evidence-based takeover analysis; no transport or SQL."""
import hashlib,io,json,re,zipfile
from xml.etree import ElementTree
from typing import Literal
from pydantic import BaseModel,Field
from storyclaw.models.calls import llm_respond
from storyclaw.models.calls import strip_code_fence
from storyclaw.skills.loader import method_instructions

MAX_FILE=24*1024*1024

def decode_manuscript(filename: str, data: bytes) -> str:
    if not data or len(data)>MAX_FILE:raise ValueError('文件必须非空且不超过24MB')
    if filename.lower().endswith('.docx'):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos=archive.infolist()
            if len(infos)>2000 or sum(x.file_size for x in infos)>80*1024*1024:raise ValueError('文档解压规模过大')
            doc=archive.read('word/document.xml')
            if len(doc)>60*1024*1024:raise ValueError('文档内容过大')
        tree=ElementTree.fromstring(doc)
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        return '\n'.join(''.join(p.itertext()) for p in tree.findall('.//w:p',ns)).strip()
    if not filename.lower().endswith('.txt'):raise ValueError('目前支持TXT和DOCX，请转换后上传')
    for encoding in (('utf-8-sig','utf-16','gb18030') if data.startswith((b'\xff\xfe',b'\xfe\xff')) else ('utf-8-sig','gb18030')):
        try:
            text=data.decode(encoding)
            if '\x00' not in text:return text.strip()
        except UnicodeError:continue
    raise ValueError('无法识别编码，请保存为UTF-8文本')

def split_manuscript(text: str) -> tuple[list[dict],list[str]]:
    pattern=re.compile(r'^\s*((?:第[0-9零〇一二三四五六七八九十百千万两]+[章回节]|Chapter\s+\d+)[^\n]{0,120})\s*$',re.M|re.I)
    matches=list(pattern.finditer(text));warnings=[];chapters=[]
    if not matches:
        warnings.append('没有识别到章标题，已按约5000字的段落块拆分；采用前请核对章序')
        for start in range(0,len(text),5000):chapters.append({'title':f'导入片段 {len(chapters)+1}','content':text[start:start+5000].strip()})
    else:
        preface=text[:matches[0].start()].strip()
        if preface:chapters.append({'title':'导入前言（请核对是否正文）','content':preface})
        for i,m in enumerate(matches):chapters.append({'title':m.group(1).strip(),'content':text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip()})
    if len(chapters)>6000:raise ValueError('单批最多6000章，请分批导入')
    seen={};prior_number=None
    for i,c in enumerate(chapters,1):
        ordinal=re.match(r'第(\d+)[章回节]|Chapter\s+(\d+)',c['title'],re.I)
        if ordinal:
            original_number=int(ordinal.group(1) or ordinal.group(2))
            if prior_number is not None and original_number!=prior_number+1:warnings.append(f'来源章号{prior_number}之后出现{original_number}，请核对缺章/重复章号或分卷')
            prior_number=original_number
        c.update(number=i,words=len(re.sub(r'\s','',c['content'])),hash=hashlib.sha256(c['content'].encode()).hexdigest())
        if len(c['content'])>100000:raise ValueError(f'第{i}个章节过长，请先拆分该章')
        if not c['content']:warnings.append(f'第{i}个章节为空')
        if c['hash'] in seen:warnings.append(f'第{i}个章节与第{seen[c["hash"]]}个章节正文相同')
        seen[c['hash']]=i
    return chapters,warnings[:100]

class EvidenceFact(BaseModel):
    subject:str=Field(min_length=1,max_length=100)
    kind:Literal['event','state','belief','rule']='event'
    certainty:Literal['observed','claim','inference']='claim'
    holder:str=Field(default='',max_length=100)
    statement:str=Field(min_length=1,max_length=1000)
    quote:str=Field(min_length=2,max_length=600)
class ChapterDigest(BaseModel):
    summary:str=Field(min_length=10,max_length=2000)
    facts:list[EvidenceFact]=Field(default_factory=list,max_length=30)
    unresolved:list[str]=Field(default_factory=list,max_length=15)
    uncertainties:list[str]=Field(default_factory=list,max_length=15)

async def analyze_source_chapter(title,content):
    system=('分析作者提供的小说章节，提炼已发生事件、人物状态、角色信念与未解问题。不可补写正文。'
        '只输出JSON：{"summary":"摘要","facts":[{"subject":"人物或对象","kind":"event/state/belief/rule",'
        '"statement":"事实或明确标注的角色信念","quote":"原文连续引用作为证据"}],"unresolved":[],"uncertainties":[]}。'
        'facts另含certainty(observed/claim/inference)和holder(信念持有者，没有则空)。不是所有角色说的话都是真的。无法确定的内容放uncertainties。')
    raw,ins,outs,model=await llm_respond({'model_choice':{'kind':'business'},'response_format':{'type':'json_object'},'response_max_tokens':2500},system+'\n'+method_instructions('story-summarization'),json.dumps({'title':title,'content':content},ensure_ascii=False))
    result=ChapterDigest.model_validate(json.loads(strip_code_fence(raw)))
    for fact in result.facts:
        if fact.quote not in content:raise ValueError('事实证据不在源章节，分析未采用')
    return result.model_dump(),ins,outs,model

async def digest_document(content):
    from storyclaw.workflows.continuity import prose
    text=prose(content);segments=[]
    for start in range(0,len(text),6000):
        digest,*_=await analyze_source_chapter('审阅后的章节',text[start:start+6000])
        segments.append({'offset':start,'length':len(text[start:start+6000]),'digest':digest})
    return {'segments':segments,'summary':'\n'.join(p['digest']['summary'] for p in segments)[:6000],
            'facts':[f for p in segments for f in p['digest']['facts']],
            'unresolved':[s for p in segments for s in p['digest']['unresolved']],
            'authority':'derived-evidence-not-author-canon'}

async def index_source_segment(user_id,namespace,physical_id,text,digest):
    """Source namespace is disjoint from every editable book; use validated evidence only."""
    from storyclaw.rag import service as rag
    result=await rag.ingest_text(user_id,namespace,physical_id,None,text,extract_entities=False)
    if result.get('error'):return result
    entities={f['subject']:{'name':f['subject'],'type':'character','description':f['statement'][:300]} for f in digest['facts']}
    if not (rag._neo4j.available or rag._neo4j.connect()):return {**result,'error':'来源图谱不可用，请检查Neo4j后显式重试'}
    n,_=rag._neo4j.upsert_chapter(user_id,namespace,physical_id,list(entities.values()),[])
    if n!=len(entities):return {**result,'error':'来源图谱写入不完整'}
    return {**result,'entities':n,'stores':{**result['stores'],'graph':'neo4j'}}
