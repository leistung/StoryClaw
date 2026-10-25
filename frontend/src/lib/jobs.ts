import api from './api'
export type JobKind='generate'|'revise'|'scene-plan'|'index'|'analysis'|'outline'|'story-design'|'chapter-outline'
export interface WorkJob {
  id:string;book_id:number;chapter_id:number|null;kind:JobKind;status:'queued'|'running'|'succeeded'|'failed'|'cancelled';error:string|null;created_at:string;
  result:null|{candidate?:{content:string;chapter_id:number;base_hash:string;adopted:boolean;warning?:string};error_code?:string;blueprint?:{title:string;summary:string;ending_hook?:string};summary?:string;dossiers?:{name:string;category:string;description:string;extra?:Record<string,unknown>}[];design_type?:string;applied?:boolean;added?:number;skipped?:number;report?:string;review_feedback?:string;scenes?:{title:string;goal:string;location:string;target_words:number;characters:string[]}[];word_count?:number;credits_cost?:number;chunks?:number;entities?:number}
}
export const jobNames:Record<JobKind,string>={revise:'章节修订','chapter-outline':'本章情节规划','story-design':'创作档案草案',outline:'大纲规划',generate:'章节写作','scene-plan':'场景任务单',index:'更新故事记忆',analysis:'作品分析'}
export const jobStatuses:Record<WorkJob['status'],string>={queued:'排队中',running:'正在处理',succeeded:'已完成',failed:'未完成',cancelled:'已取消'}
export const enqueueJob=async(body:{planning_mode?:'serial'|'fixed';design_type?:'character'|'world'|'plot';reviewed_hash?:string;book_id:number;chapter_id?:number;kind:JobKind;prompt?:string;skill?:string;start?:number;end?:number})=>{
 const commands:Record<JobKind,string>={'generate':'chapter.write',revise:'chapter.revise','scene-plan':'chapter.scenes',index:'knowledge.ingest',analysis:'book.analyze',outline:'framework.draft','story-design':'setting.draft','chapter-outline':'chapter.plan'}
 const payload:Record<string,unknown>={}
 if(['generate','revise','chapter-outline'].includes(body.kind))payload.prompt=body.prompt||''
 if(body.kind==='outline')payload.planning_mode=body.planning_mode||'serial'
 if(body.kind==='story-design')payload.design_type=body.design_type||'character'
 if(body.kind==='index')payload.reviewed_hash=body.reviewed_hash||''
 if(body.kind==='analysis')Object.assign(payload,{skill:body.skill||'book-summary',start:body.start||1,end:body.end||10})
 const run=(await api.post('/agent/runs',{request_id:crypto.randomUUID(),entry:'command',command:commands[body.kind],payload,scope:{book_id:body.book_id,chapter_id:body.chapter_id}})).data
 // Command submission performs only deterministic checks/job enqueue; never wait for a model here.
 if(run.job_id)return run.result.data.job as WorkJob
 if(run.error)throw new Error(run.error)
 throw new Error('任务尚未提交，请到任务中心检查请求状态')
}
