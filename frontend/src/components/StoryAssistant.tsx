import { useEffect,useRef,useState } from 'react'
import { useMutation,useQuery,useQueryClient } from '@tanstack/react-query'
import { Send,Sparkles,History,StopCircle } from 'lucide-react'
import api,{extractError,listChatSessions,getChatMessages} from '@/lib/api'
import {agentDecision,listAgentRuns,startAgent,type AgentRun,type AgentEvent} from '@/lib/agent'
import {Button} from './ui/button'
import {Textarea} from './ui/textarea'
import {useAuthStore} from '@/stores/auth'
import {toast} from 'sonner'

function RunCard({run,onAnswer}:{run:AgentRun;onAnswer:(answer:string)=>void}) {
 const qc=useQueryClient();const [answers,setAnswers]=useState<Record<number,string>>({});const [live,setLive]=useState('');const seq=useRef(0)
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
 const adopt=useMutation({mutationFn:()=>api.post(`/agent/runs/${run.id}/adopt`,{expected_hash:run.result?.data?.base_hash}),onSuccess:()=>{void qc.invalidateQueries();toast.success('候选已采用，正文需要重新审阅入库')},onError:e=>toast.error(extractError(e,'采用失败'))})
 const label:Record<string,string>={accepted:'等待执行',running:'正在处理',waiting_task:'后台任务执行中',waiting_author:'请你确认',succeeded:'已完成',failed:'未完成',cancelled:'已取消',partial:'部分完成'}
 return <article className="agent-run-card">
  <p className="agent-user-message">{run.request.message||'执行创作操作'}</p>
  <div className="agent-run-meta"><Sparkles size={13}/><span>{label[run.status]||run.status}</span>{run.credits_cost>0&&<small>对话与候选 {run.credits_cost} 积分</small>}</div>
  {run.result?.data?.kind==='author.question'?<form className="agent-questions" onSubmit={e=>{e.preventDefault();onAnswer((run.result?.data?.questions||[]).map((q,i)=>q.question+'：'+answers[i]).join('\n'))}}>{run.result.data.questions?.map((q,i)=><fieldset key={i}><legend>{q.question}</legend><div>{q.options.map(o=><button type="button" className={answers[i]===o?'selected':''} key={o} onClick={()=>setAnswers({...answers,[i]:o})}>{o}</button>)}</div><input aria-label={q.question+' 自填答案'} placeholder="也可以填写自己的答案" value={q.options.includes(answers[i])?'':answers[i]||''} onChange={e=>setAnswers({...answers,[i]:e.target.value})}/></fieldset>)}<Button size="sm" type="submit" disabled={!run.result.data.questions?.every((_,i)=>answers[i]?.trim())}>将选择填入消息框</Button></form>:<div className="agent-answer">{run.error||run.result?.content||live||(active?'正在读取作品状态…':'')}</div>}
  {run.status==='waiting_author'&&run.decision&&<div className="agent-decision"><small>{run.decision.book_title} · 第{run.decision.chapter_number}章 {run.decision.chapter_title}</small><p>{run.decision.summary}</p><small>仅针对当前章、当前正文版本；资料变化后需要重新核对。</small><div><Button size="sm" disabled={decide.isPending} onClick={()=>decide.mutate(true)}>确认执行</Button><Button size="sm" variant="outline" disabled={decide.isPending} onClick={()=>decide.mutate(false)}>暂不执行</Button></div></div>}
  {run.status==='succeeded'&&run.result?.data?.artifact&&String(run.result.data.kind).startsWith('text.')&&!run.result.data.adopted&&<Button size="sm" variant="outline" disabled={adopt.isPending} onClick={()=>adopt.mutate()}>审阅并采用候选</Button>}
  {run.result?.data?.job_result&&<details><summary>查看任务结果</summary><pre>{JSON.stringify(run.result.data.job_result,null,2)}</pre></details>}
  {active&&<Button size="sm" variant="ghost" disabled={cancel.isPending} onClick={()=>cancel.mutate()}><StopCircle size={12}/>取消待执行步骤</Button>}
 </article>
}

export default function StoryAssistant({bookId,chapterId,onTasks}:{bookId:number;chapterId:number|null;onTasks:()=>void}) {
 const uid=useAuthStore(s=>s.user?.id);const qc=useQueryClient();const [input,setInput]=useState('')
 const [conversation]=useState(()=>{const key=`sc-agent-conversation-${uid}-${bookId}`;const value=localStorage.getItem(key)||crypto.randomUUID();localStorage.setItem(key,value);return value});const bottom=useRef<HTMLDivElement>(null)
 const {data:runs=[]}=useQuery({queryKey:['agent-runs',uid,bookId],queryFn:()=>listAgentRuns(bookId),refetchInterval:1500})
 const [legacyOpen,setLegacyOpen]=useState(false);const [legacyThread,setLegacyThread]=useState('')
 const {data:legacySessions=[]}=useQuery({queryKey:['legacy-agent-sessions',uid],queryFn:listChatSessions,enabled:legacyOpen})
 const {data:legacyMessages=[]}=useQuery({queryKey:['legacy-agent-messages',uid,legacyThread],queryFn:()=>getChatMessages(legacyThread),enabled:legacyOpen&&!!legacyThread})
 const sending=runs.some(r=>['accepted','running'].includes(r.status))
 const send=useMutation({mutationFn:()=>startAgent({request_id:crypto.randomUUID(),entry:'chat',message:input,scope:{book_id:bookId,chapter_id:chapterId},conversation_id:conversation}),
  onSuccess:()=>{setInput('');void qc.invalidateQueries({queryKey:['agent-runs']});bottom.current?.scrollIntoView({block:'nearest'})},onError:e=>toast.error(extractError(e,'发送失败'))})
 const visible=runs.filter(r=>r.request.entry==='chat').slice(0,20).reverse()
 useEffect(()=>{void qc.invalidateQueries({queryKey:['chapters',bookId]});void qc.invalidateQueries({queryKey:['jobs',bookId]});void qc.invalidateQueries({queryKey:['blueprint']});void qc.invalidateQueries({queryKey:['outline',bookId]});void qc.invalidateQueries({queryKey:['config-entities']})},[runs.filter(r=>r.status==='succeeded').length,bookId,qc])
 return <section className="story-assistant"><header><Sparkles size={15}/><strong>创作助手</strong><button onClick={()=>setLegacyOpen(!legacyOpen)}>旧会话</button><Button size="sm" variant="ghost" onClick={onTasks}><History size={13}/>任务</Button></header>
 <div className="story-assistant-scroll">{legacyOpen&&<details open className="agent-legacy-history"><summary>旧版对话记录（仅查看，不作为本书参考）</summary><select aria-label="选择旧会话" value={legacyThread} onChange={e=>setLegacyThread(e.target.value)}><option value="">选择会话</option>{legacySessions.map(s=><option key={s.thread_id} value={s.thread_id}>{s.title||s.thread_id}</option>)}</select>{legacyMessages.map(m=><p className="agent-answer" key={m.id}>{m.role==='user'?'你：':'助手：'}{m.content}</p>)}</details>}{visible.length?visible.map(r=><RunCard key={r.id} run={r} onAnswer={setInput}/>):<div className="agent-intro"><h3>从当前作品出发</h3><p>聊情节、查前文、规划章纲或安排写作。需要确认的操作会先展示给你。</p>{['看看现在该做什么','帮我规划本章','检查角色和前文是否一致'].map(t=><button key={t} onClick={()=>setInput(t)}>{t}</button>)}</div>}<div ref={bottom}/></div>
 <div className="agent-shortcuts">{['大纲建议','情节建议','角色弧光','一致性检查','前情提要'].map(t=><button key={t} disabled={sending} onClick={()=>setInput(t)}>{t}</button>)}</div><form onSubmit={e=>{e.preventDefault();if(input.trim()&&!sending)send.mutate()}}><small>{chapterId?'已关联当前作品与章节':'已关联当前作品；写章前请选择章节'}</small><Textarea aria-label="创作需求" value={input} onChange={e=>setInput(e.target.value)} placeholder="说说你想推进或调整的内容…" rows={3}/><Button size="sm" disabled={!input.trim()||sending||send.isPending} type="submit"><Send size={14}/>发送</Button></form></section>
}
