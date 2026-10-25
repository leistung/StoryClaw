"""Lead inference and streaming are package-owned; host supplies billing/event callbacks."""
import asyncio
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
from storyclaw.contracts import ModelTurn
from storyclaw.contracts import ToolCall

async def generate_lead_turn(llm,messages,tools,on_delta,on_usage):
    types={'system':SystemMessage,'user':HumanMessage,'assistant':AIMessage}
    msgs=[types[m['role']](content=str(m['content'])[:20000]) for m in messages]
    client=llm.bind_tools(tools).bind(max_tokens=1024)
    response=None;buffer=''
    try:
        async with asyncio.timeout(120):
            async for chunk in client.astream(msgs):
                response=chunk if response is None else response+chunk
                if isinstance(chunk.content,str) and chunk.content:
                    buffer+=chunk.content
                    if len(buffer)>=40:
                        await on_delta(buffer);buffer=''
            if buffer:await on_delta(buffer)
        if response is None:raise ValueError('模型没有返回内容')
        if getattr(response,'invalid_tool_calls',None):raise ValueError('模型工具调用格式不完整')
        if response.additional_kwargs.get('tool_calls') and not response.tool_calls:raise ValueError('模型工具调用格式不完整')
        if (response.response_metadata or {}).get('finish_reason') in ('length','max_tokens'):
            raise ValueError('模型输出被截断，未执行不完整工具')
        return ModelTurn(text=response.content if isinstance(response.content,str) else '',
            calls=[ToolCall(name=c['name'],arguments=c.get('args') or {}) for c in response.tool_calls])
    finally:
        await on_usage((response.usage_metadata or {}) if response is not None else {})
