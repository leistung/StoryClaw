"""Bounded text reuse warning, not a semantic contradiction detector."""
import html,re
from difflib import SequenceMatcher

def prose(text):
    return html.unescape(re.sub(r'<[^>]+>','',text or ''))

def repetition_evidence(draft,previous):
    a=re.sub(r'\s+','',prose(previous))[-12000:]
    b=re.sub(r'\s+','',prose(draft))[:12000]
    if not a or not b:return {'warning':False,'max_run':0,'reused_chars':0}
    blocks=SequenceMatcher(None,a,b,autojunk=False).get_matching_blocks()
    longest=max(x.size for x in blocks)
    reused=sum(x.size for x in blocks if x.size>=24)
    return {'warning':longest>=40 or reused>=100,'max_run':longest,'reused_chars':reused}
