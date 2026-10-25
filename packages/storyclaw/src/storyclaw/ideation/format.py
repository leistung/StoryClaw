"""Recover superficial model formatting without inventing missing fields."""
import json
import re
from .._util import strip_code_fence

def _without_trailing_commas(text):
    chars=[];quoted=False;escaped=False
    for i,ch in enumerate(text):
        if quoted:
            chars.append(ch)
            if escaped:escaped=False
            elif ch=='\\':escaped=True
            elif ch=='"':quoted=False
        elif ch=='"':quoted=True;chars.append(ch)
        elif ch==',':
            j=i+1
            while j<len(text) and text[j].isspace():j+=1
            if j>=len(text) or text[j] not in '}]':chars.append(ch)
        else:chars.append(ch)
    return ''.join(chars)

def parse_ideation_json(raw):
    text=strip_code_fence(raw.strip().lstrip('\ufeff'))
    # strict=False permits literal newlines inside JSON strings. Trailing commas
    # are removed only outside strings, so creative prose is never rewritten.
    cleaned=_without_trailing_commas(text)
    start=cleaned.find('{')
    if start<0:raise ValueError('missing JSON object')
    result,end=json.JSONDecoder(strict=False).raw_decode(cleaned[start:])
    if not isinstance(result,dict) or not isinstance(result.get('reply'),str):
        raise ValueError('missing reply')
    tail=cleaned[start+end:].strip()
    if tail.startswith(('{','[')):
        raise ValueError('ambiguous multiple objects')
    return result

def partial_reply(raw: str) -> str:
    """Decode only complete characters of the streamed JSON reply string."""
    match=re.search(r'"reply"\s*:\s*"',raw)
    if not match:return ''
    i=match.end();chars=[]
    while i<len(raw):
        ch=raw[i]
        if ch=='"':break
        if ch!='\\':chars.append(ch);i+=1;continue
        if i+1>=len(raw):break
        end=i+(6 if raw[i+1]=='u' else 2)
        if end>len(raw):break
        if raw[i+1]=='u':
            try:code=int(raw[i+2:end],16)
            except ValueError:break
            if 0xD800<=code<=0xDBFF:
                if len(raw)<i+12 or raw[i+6:i+8]!='\\u':break
                end=i+12
            elif 0xDC00<=code<=0xDFFF:break
        try:chars.append(json.loads('"'+raw[i:end]+'"'))
        except ValueError:break
        i=end
    return ''.join(chars)

