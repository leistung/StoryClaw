"""Bounded real dependency probes. Host owns budgets and account selection."""
from langchain_core.messages import HumanMessage
from ..metering import MeteredModel
async def model_probe(client,model,meter):
    report={'text':False,'embedding':False,'model':model}
    try:
        response=await MeteredModel(client,model,meter).bind(max_tokens=256).ainvoke([HumanMessage(content='写80到120字的原创小说片段：修灯匠在雨夜收到一盏父亲留下的旧灯，灯底出现一个陌生村名。直接写正文，不作解释。')])
        report['text']=bool(response.content);report['sample']=str(response.content)[:500]
    except Exception as exc:
        report['text_error']={'type':type(exc).__name__,'http_status':getattr(exc,'status_code',None)}
        body=getattr(exc,'body',None)
        if isinstance(body,dict):report['text_error']['supplier_code']=(body.get('error') or body).get('code')
    try:
        from ..rag.embedding import embed_texts,_resolve_config_async
        from ..config import settings
        cfg=await _resolve_config_async()
        if not cfg.get('api_key'):raise ValueError('A real embedding configuration is required')
        vectors=await embed_texts(['原创小说验收用的旧灯与村名。'],cfg)
        report['embedding']=len(vectors)==1 and len(vectors[0])==settings.milvus_dim
    except Exception as exc:report['embedding_error']=type(exc).__name__
    return report
