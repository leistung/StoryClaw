"""Public execution observations, without hidden reasoning or system prompts."""
import json
from storyclaw.runtime.deps import get_stream_sink

async def progress(kind, name, **details):
    sink=get_stream_sink()
    if sink is not None:
        await sink(kind,{'name':name,**details})

def preview(value,limit=6000):
    return json.dumps(value,ensure_ascii=False,default=str)[:limit]
