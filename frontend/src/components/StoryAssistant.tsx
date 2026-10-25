import { useEffect,useRef,useState } from 'react'
import { useMutation,useQuery,useQueryClient } from '@tanstack/react-query'
import { Send,Sparkles,History,StopCircle } from 'lucide-react'
import api,{extractError} from '@/lib/api'
import {agentDecision,listAgentRuns,startAgent,type AgentRun,type AgentEvent} from '@/lib/agent'
import {Button} from './ui/button'
import {Textarea} from './ui/textarea'
import {useAuthStore} from '@/stores/auth'
import {toast} from 'sonner'

function RunCard({run}:{run:AgentRun}) {
 const qc=useQueryClient();const [live,setLive]=useState('');const seq=useRef(0)
 const active=['accepted','running','waiting_task'].includes(run.status)
 useEffect(()=>{
  let alive=true;let polling=false
  const read=async()=>{if(polling)return;polling=true;try {
   const items=(await api.get<AgentEvent[]>(`/agent/runs/${run.id}/events`,{params:{after_seq:seq.current}})).data
   if(!alive)return
   for(const e of items){seq.current=Math.max(seq.current,e.seq);if(e.type==='message.delta'&&typeof e.payload.text==='string')setLive(s=>s+e.payload.text)}
  }finally{polling=false}}
  void read().catch(()=>{});const timer=active?window.setInterval(()=>void read().catch(()=>{}),1000):undefined
  return()=>{alive=false;if(timer)window.clearInterval(timer)}
 },[run.id,active])
 const decide=useMutation({mutationFn:(accept:boolean)=>agentDecision(run,accept),onSuccess:()=>qc.invalidateQueries({queryKey:['agent-runs']}),onError:e=>toast.error(extractError(e,'确认失败'))})
 const cancel=useMutation({mutationFn:()=>api.post(`/agent/runs/${run.id}/cancel`),onSuccess:()=>qc.invalidateQueries({queryKey:['agent-runs']}),onError:e=>toast.error(extractError(e,'取消失败'))})
 const label:Record<string,string>={accepted:'等待执行',running:'正在处理',waiting_task:'后台任务执行中',waiting_author:'请你确认',succeeded:'已完成',failed:'未完成',cancelled:'已取消',partial:'部分完成'}
 return <article className="agent-run-card">
  <p className="agent-user-message">{run.request.message||'执行创作操作'}</p>
  <div className="agent-run-meta"><Sparkles size={13}/><span>{label[run.status]||run.status}</span>{run.credits_cost>0&&<small>讨论 {run.credits_cost} 积分</small>}</div>
  <div className="agent-answer">{run.error||run.result?.content||live||(active?'正在读取作品状态…':'')}</div>
  {run.status==='waiting_author'&&run.decision&&<div className="agent-decision"><p>{run.decision.summary}</p><small>仅针对当前章、当前正文版本；资料变化后需要重新核对。</small><div><Button size="sm" disabled={decide.isPending} onClick={()=>decide.mutate(true)}>确认执行</Button><Button size="sm" variant="outline" disabled={decide.isPending} onClick={()=>decide.mutate(false)}>暂不执行</Button></div></div>}
  {run.result?.data?.job_result&&<details><summary>查看任务结果</summary><pre>{JSON.stringify(run.result.data.job_result,null,2)}</pre></details>}
  {active&&<Button size="sm" variant="ghost" disabled={cancel.isPending} onClick={()=>cancel.mutate()}><StopCircle size={12}/>取消待执行步骤</Button>}
 </article>
}

export default function StoryAssistant({bookId,chapterId,onTasks}:{bookId:number;chapterId:number|null;onTasks:()=>void}) {
 const uid=useAuthStore(s=>s.user?.id);const qc=useQueryClient();const [input,setInput]=useState('')
 const [conversation]=useState(()=>{const key=`sc-agent-conversation-${uid}-${bookId}`;const value=localStorage.getItem(key)||crypto.randomUUID();localStorage.setItem(key,value);return value});const bottom=useRef<HTMLDivElement>(null)
 const {data:runs=[]}=useQuery({queryKey:['agent-runs',uid,bookId],queryFn:()=>listAgentRuns(bookId),refetchInterval:1500})
 const sending=runs.some(r=>['accepted','running'].includes(r.status))
 const send=useMutation({mutationFn:()=>startAgent({request_id:crypto.randomUUID(),entry:'chat',message:input,scope:{book_id:bookId,chapter_id:chapterId},conversation_id:conversation}),
  onSuccess:()=>{setInput('');void qc.invalidateQueries({queryKey:['agent-runs']});bottom.current?.scrollIntoView({block:'nearest'})},onError:e=>toast.error(extractError(e,'发送失败'))})
 const visible=runs.filter(r=>r.request.entry==='chat').slice(0,20).reverse()
 useEffect(()=>{void qc.invalidateQueries({queryKey:['chapters',bookId]});void qc.invalidateQueries({queryKey:['jobs',bookId]})},[runs.filter(r=>r.status==='succeeded').length,bookId,qc])
 return <section className="story-assistant"><header><Sparkles size={15}/><strong>创作助手</strong><Button size="sm" variant="ghost" onClick={onTasks}><History size={13}/>任务</Button></header>
 <div className="story-assistant-scroll">{visible.length?visible.map(r=><RunCard key={r.id} run={r}/>):<div className="agent-intro"><h3>从当前作品出发</h3><p>聊情节、查前文、规划章纲或安排写作。需要确认的操作会先展示给你。</p>{['看看现在该做什么','帮我规划本章','检查角色和前文是否一致'].map(t=><button key={t} onClick={()=>setInput(t)}>{t}</button>)}</div>}<div ref={bottom}/></div>
 <form onSubmit={e=>{e.preventDefault();if(input.trim()&&!sending)send.mutate()}}><small>{chapterId?'已关联当前作品与章节':'已关联当前作品；写章前请选择章节'}</small><Textarea aria-label="创作需求" value={input} onChange={e=>setInput(e.target.value)} placeholder="说说你想推进或调整的内容…" rows={3}/><Button size="sm" disabled={!input.trim()||sending||send.isPending} type="submit"><Send size={14}/>发送</Button></form></section>
}
