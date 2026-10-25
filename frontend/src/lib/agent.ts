import api from './api'
export interface AgentRun {
 id:string;status:string;error:string|null;job_id:string|null;credits_cost:number
 request:{entry:string;message:string;scope:{book_id?:number;chapter_id?:number};conversation_id?:string}
 result:null|{content:string;data?:{job_id?:string;job_result?:Record<string,unknown>}}
 decision:null|{id:string;summary:string;command:string;content_hash:string}
}
export interface AgentEvent {id:number;seq:number;type:string;payload:Record<string,unknown>}
export const listAgentRuns=async(bookId:number)=>(await api.get<AgentRun[]>('/agent/runs',{params:{book_id:bookId}})).data
export const startAgent=async(body:Record<string,unknown>)=>(await api.post<AgentRun>('/agent/runs',body)).data
export const agentDecision=async(run:AgentRun,accept:boolean)=>(await api.post<AgentRun>(`/agent/runs/${run.id}/decisions`,{decision_id:run.decision?.id,accept})).data
