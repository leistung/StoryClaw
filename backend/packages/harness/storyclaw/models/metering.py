"""Request-local model metering: host callbacks own funds, package owns inference."""
import asyncio,json
from contextvars import ContextVar
from dataclasses import dataclass,field
from typing import Any

@dataclass
class Meter:
    reserve:Any
    settle:Any
    calls:int=0
    spent:int=0
    call_ids:list[str]=field(default_factory=list)
active_meter:ContextVar[Meter|None]=ContextVar('storyclaw_meter',default=None)

def response_usage(response):
    usage=dict(getattr(response,'usage_metadata',None) or {})
    meta=getattr(response,'response_metadata',None) or {}
    request_id=(meta.get('headers') or {}).get('x-request-id') or meta.get('request_id')
    if request_id:usage['supplier_request_id']=str(request_id)[:255]
    response_id=getattr(response,'id',None)
    if response_id and not str(response_id).startswith('run-'):usage['supplier_response_id']=str(response_id)[:255]
    return usage

class MeteredModel:
    def __init__(self,client,model,meter,options=None):self.client=client;self.model=model;self.meter=meter;self.options=options or {}
    def bind(self,**kwargs):return MeteredModel(self.client.bind(**kwargs),self.model,self.meter,{**self.options,**kwargs})
    def bind_tools(self,tools,**kwargs):return MeteredModel(self.client.bind_tools(tools,**kwargs),self.model,self.meter,{**self.options,'tools':tools})
    def __getattr__(self,name):return getattr(self.client,name)
    async def _reserve(self,messages):
        bound=len(json.dumps([[(getattr(m,'type',''),str(getattr(m,'content',m))) for m in messages],self.options],ensure_ascii=False,default=str).encode())+2048
        limit=int(self.options.get('max_tokens') or getattr(self.client,'max_tokens',None) or 8192)
        return await self.meter.reserve(self.model,bound,limit)
    async def ainvoke(self,messages,**kwargs):
        if not self.options.get('max_tokens') and not getattr(self.client,'max_tokens',None):kwargs.setdefault('max_tokens',8192)
        call=await self._reserve(messages);self.meter.call_ids.append(call);response=None
        try:
            async with asyncio.timeout(180):response=await self.client.ainvoke(messages,**kwargs)
            return response
        finally:
            self.meter.spent+=await self.meter.settle(call,response_usage(response),response is not None)
            self.meter.calls+=1
    async def astream(self,messages,**kwargs):
        if not self.options.get('max_tokens') and not getattr(self.client,'max_tokens',None):kwargs.setdefault('max_tokens',8192)
        call=await self._reserve(messages);self.meter.call_ids.append(call);response=None;complete=False
        try:
            async with asyncio.timeout(180):
                async for chunk in self.client.astream(messages,**kwargs):
                    response=chunk if response is None else response+chunk
                    yield chunk
            complete=True
        finally:
            self.meter.spent+=await self.meter.settle(call,response_usage(response),complete)
            self.meter.calls+=1

def wrap_model(client,model):
    meter=active_meter.get()
    return MeteredModel(client,model,meter) if meter else client
