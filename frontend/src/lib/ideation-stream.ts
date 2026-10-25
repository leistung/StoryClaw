import {API_PREFIX,TOKEN_KEY} from './api'
export async function streamIdeation<T>(payload:unknown,onDelta:(text:string)=>void,signal:AbortSignal):Promise<T>{
 const response=await fetch(`${API_PREFIX}/assist/ideation/stream`,{method:'POST',headers:{'Content-Type':'application/json',Accept:'text/event-stream',Authorization:`Bearer ${localStorage.getItem(TOKEN_KEY)||''}`},body:JSON.stringify(payload),signal})
 if(!response.ok||!response.body)throw new Error(`请求失败（${response.status}），请检查登录状态后重试`)
 const reader=response.body.getReader();const decoder=new TextDecoder();let buffer='';let result:T|undefined
 try{while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const frames=buffer.split('\n\n');buffer=frames.pop()||''
 for(const frame of frames){let event='';const lines:string[]=[];for(const line of frame.split('\n')){if(line.startsWith('event:'))event=line.slice(6).trim();if(line.startsWith('data:'))lines.push(line.slice(5).trim())}if(!lines.length)continue;const data=JSON.parse(lines.join('\n'));if(event==='delta')onDelta(data.text);if(event==='error')throw new Error(data.message||'回复未完成');if(event==='done')result=data as T}
 }}finally{await reader.cancel().catch(()=>{});reader.releaseLock()}
 if(result===undefined)throw new Error('连接中断，回复尚未确认保存，请重试本次请求')
 return result
}
