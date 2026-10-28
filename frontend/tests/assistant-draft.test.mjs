import {test} from 'node:test'
import assert from 'node:assert/strict'
import {build} from 'esbuild'
import {fileURLToPath} from 'node:url'

const root=fileURLToPath(new URL('../',import.meta.url))
const compiled=await build({stdin:{contents:"export * from './src/features/assistant/prompts';export * from './src/features/assistant/draft-store'",resolveDir:root},bundle:true,write:false,format:'esm',platform:'node',
 plugins:[{name:'test-author',setup(b){b.onResolve({filter:/@\/stores\/auth/},()=>({path:'author',namespace:'test'}));b.onLoad({filter:/.*/,namespace:'test'},()=>({contents:'export const useAuthStore={getState:()=>({user:{id:globalThis.authorId}})}'}))}}]})
const api=await import('data:text/javascript;base64,'+Buffer.from(compiled.outputFiles[0].text).toString('base64'))
globalThis.sessionStorage={values:new Map(),getItem(k){return this.values.get(k)||null},setItem(k,v){this.values.set(k,v)}}
globalThis.window=new EventTarget()
globalThis.authorId=1

test('all work shortcuts stage editable drafts without network or model calls',()=>{
 let requests=0;globalThis.fetch=()=>{requests++;throw Error('unexpected network')}
 for(const kind of ['outline','story-design','chapter-outline','generate','revise','scene-plan','index','analysis']){
  api.useAssistantDraft.getState().put(10,{text:'',references:[]})
  api.prepareJobPrompt({book_id:10,chapter_id:2,kind})
  assert.ok(api.getAssistantDraft(10).text.length>20)
  assert.equal(api.getAssistantDraft(10).chapterId,2)
 }
 assert.equal(requests,0)
})
test('shortcuts preserve an existing author draft and attached selection',()=>{
 const refs=[{kind:'selection',chapter_id:2,title:'第二章',text:'原片段',line_start:3,line_end:4,offset:10}]
 api.useAssistantDraft.getState().put(11,{text:'请保留我的语气',chapterId:2,references:refs})
 api.stageAssistantPrompt(11,'润色这个片段',2)
 assert.equal(api.getAssistantDraft(11).text,'请保留我的语气\n\n润色这个片段')
 assert.deepEqual(api.getAssistantDraft(11).references,refs)
 assert.throws(()=>api.stageAssistantPrompt(11,'另一个章节的需求',3),/其他范围/)
})
test('drafts remain separated by author and book',()=>{
 api.useAssistantDraft.getState().put(12,{text:'作者一的私密草稿',chapterId:2,references:[]})
 globalThis.authorId=2
 assert.equal(api.getAssistantDraft(12).text,'')
 api.stageAssistantPrompt(12,'作者二的草稿',null)
 assert.equal(api.getAssistantDraft(12).text,'作者二的草稿')
 globalThis.authorId=1
 assert.equal(api.getAssistantDraft(12).text,'作者一的私密草稿')
 assert.equal(api.getAssistantDraft(13).text,'')
})
