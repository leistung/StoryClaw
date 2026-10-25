import hashlib
import html
import re

def plain(text):
    return html.unescape(re.sub(r'<[^>]+>', '', text or ''))

def count(text):
    return len(re.sub(r'\s+', '', plain(text)))

def fingerprint(text):
    return hashlib.sha256(plain(text).encode()).hexdigest()

def validate_outline(outline, expected):
    volumes = outline.get('volumes') if isinstance(outline, dict) else None
    if not isinstance(volumes, list) or not volumes:
        raise ValueError('没有分卷大纲')
    chapters = [ch for v in volumes for ch in v.get('chapters', [])]
    if [ch.get('number') for ch in chapters] != list(range(1, expected+1)):
        raise ValueError('大纲章号缺失、重复、顺序错误或数量不符')
    for ch in chapters:
        if not ch.get('summary') or not ch.get('title') or any(x in str(ch) for x in ['待生成梗概','待定']):
            raise ValueError('大纲含占位内容')
    return chapters

def chapter_checks(content, case):
    size=count(content)
    errors=[]
    if not case['min_chapter_words'] <= size <= case['max_chapter_words']:
        errors.append(f"字数 {size} 不在 {case['min_chapter_words']}..{case['max_chapter_words']} 范围")
    if any(x in content for x in ('作为一个AI','作为一个人工智能','[待补充正文]','（此处省略')):
        errors.append('出现模型自述或占位正文')
    paragraphs=[p.strip() for p in plain(content).split('\n') if p.strip()]
    if len(paragraphs) < 6:
        errors.append('正文缺少正常分段')
    cjk=len(re.findall(r'[\u4e00-\u9fff]',plain(content)))
    if size and cjk / size < 0.65:
        errors.append('汉字比例异常，可能混入乱码或无关输出')
    if plain(content).strip() and plain(content).strip()[-1] not in '。！？……”’」』）)':
        errors.append('正文结尾疑似截断，缺少完整句末标点')
    return {'words':size,'cjk_characters':cjk,'paragraphs':len(paragraphs),'sha256':fingerprint(content),'errors':errors}
