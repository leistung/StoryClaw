import StudioManager from '@/features/workspace/components/StudioManager'
import StoryAssistant from '@/features/assistant/components/StoryAssistant'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import ChapterPlanning from '@/features/workspace/components/ChapterPlanning'
import CreationGuide from '@/features/workspace/components/CreationGuide'
import JobCenter from '@/features/jobs/components/JobCenter'
import ChapterVersions from '@/features/workspace/components/ChapterVersions'
import {prepareJobPrompt} from '@/features/assistant/prompts'
import {type WorkJob} from '@/features/jobs/types'
import {stageAssistantPrompt,compactText,manuscriptPlainText,type ManuscriptReference} from '@/features/assistant/draft-store'
import { toEditorContent } from '@/lib/editor-content'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Highlight from '@tiptap/extension-highlight'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import api, { extractError } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import type { Book, Chapter, ChapterDetail, Volume } from '@/types'
import {
  X, Plus, Save, Bold, Italic, Heading1, Heading2,
  Highlighter, List, RotateCcw, PenLine, Wand2, CornerDownRight, History, Feather, Focus, PanelLeft, Download, ChevronRight, BookOpen, Users, MapPin, Package, GitBranch, FileText, Network, Settings, Library,
} from 'lucide-react'
import OutlinePanel from '@/features/workspace/components/OutlinePanel'
import DatabasePanel from '@/features/workspace/components/DatabasePanel'
import ConfigPage from '@/features/workspace/components/ConfigPage'
import ReaderPage from '@/features/reading/components/ReaderPage'
import BookInfoPage from '@/features/workspace/components/BookInfoPage'
import WorkspaceSettings from '@/features/workspace/components/WorkspaceSettings'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const TABS = ['创作', '大纲', '世界观', '角色', '场景', '物品', '情节', '数据库', '任务', '阅读', '书籍信息', '创作管理', '设置'] as const
const ENABLED_TABS: ReadonlySet<string> = new Set(['创作', '阅读', '世界观', '角色', '场景', '物品', '情节', '大纲', '数据库', '书籍信息', '创作管理', '设置', '任务', '创作管理'])

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export default function Workspace() {
  const { bookId = '' } = useParams<{ bookId: string }>()
  const bid = Number(bookId)
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const fetchMe = useAuthStore((s) => s.fetchMe)
  const [searchParams,setSearchParams] = useSearchParams()
  const [activeTab, setActiveTabState] = useState<typeof TABS[number]>(() => TABS.find(t=>t===searchParams.get('tab')) || '创作')
  const setActiveTab=(tab:typeof TABS[number])=>{setActiveTabState(tab);setSearchParams({tab},{replace:true})}
  useEffect(()=>{const tab=TABS.find(t=>t===searchParams.get('tab'));if(tab)setActiveTabState(tab)},[searchParams])
  const [focusMode, setFocusMode] = useState(() => window.innerWidth < 800)
  useEffect(()=>{const show=(event:Event)=>{if((event as CustomEvent).detail?.bookId===bid)setFocusMode(false)};window.addEventListener('storyclaw:show-assistant',show);return()=>window.removeEventListener('storyclaw:show-assistant',show)},[bid])
  const [compact, setCompact] = useState(() => window.innerWidth < 800)
  const [exporting, setExporting] = useState(false)
  const [hideRouteGuide,setHideRouteGuide]=useState(()=>localStorage.getItem('sc-hide-route-guide')==='1')
  useEffect(() => { const resize=()=>setCompact(window.innerWidth<800);window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize) }, [])
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [chapterTitle, setChapterTitle] = useState('')
  const [error, setError] = useState('')
  const [saveConflict,setSaveConflict]=useState(false)
  const saveTimer = useRef<number | null>(null)
  const lastSavedId = useRef<number | null>(null)
  const baseHash = useRef<string | undefined>()
  const [showVersions, setShowVersions] = useState(false)
  const finishedJobs = useRef(new Set<string>())
  const {data: workJobs=[]}=useQuery({queryKey:['jobs',bid],queryFn:async()=>(await api.get<WorkJob[]>('/jobs',{params:{book_id:bid}})).data,enabled:!!bid,refetchInterval:3000})
  const {data:workflow}=useQuery({queryKey:['workflow',bid],enabled:!!bid,queryFn:async()=>(await api.get<{impacts:{chapter_id:number;reason:string}[]}>(`/books/${bid}/workflow`)).data,refetchInterval:5000})
  const chapterBusy=workJobs.some(j=>j.chapter_id===selectedChapterId && ['queued','running'].includes(j.status))

  const { data: book } = useQuery({
    queryKey: ['book', bid],
    queryFn: async () => (await api.get<Book>(`/books/${bid}`)).data,
    enabled: !!bid,
  })
  const { data: chapters } = useQuery({
    queryKey: ['chapters', bid],
    queryFn: async () => (await api.get<Chapter[]>(`/chapters/books/${bid}`)).data,
    enabled: !!bid,
  })
  const { data: volumes } = useQuery({
    queryKey: ['volumes', bid],
    queryFn: async () => (await api.get<Volume[]>(`/books/${bid}/volumes`)).data,
    enabled: !!bid,
  })

  // ===== 模型配置就绪检测（本地版需自配 LLM + Embedding） =====
  const navigate = useNavigate()
  const [autoSaveMs, setAutoSaveMs] = useState(() => {
    const v = Number(localStorage.getItem('sc_autosave_ms'))
    return Number.isFinite(v) && v > 0 ? v : 5000
  })
  const { data: modelStatus } = useQuery({queryKey: ['model-status'], queryFn: async () => (await api.get<{chat:boolean; embedding:boolean}>('/model-status')).data})
  const llmReady = modelStatus?.chat ?? false
  const embeddingReady = modelStatus?.embedding ?? false
  // 模型由平台中台统一维护，用户无需配置密钥。

  const { data: chapterDetail } = useQuery({
    queryKey: ['chapter', selectedChapterId],
    queryFn: async () => (await api.get<ChapterDetail>(`/chapters/${selectedChapterId}`)).data,
    enabled: !!selectedChapterId,
  })

  const doSave = useCallback(async (html: string, title: string) => {
    if (!selectedChapterId) return false
    setSaveStatus('saving')
    setError('')
    try {
      const saved = await api.put<ChapterDetail>(`/chapters/${selectedChapterId}`, { content: html, title, expected_hash: baseHash.current })
      baseHash.current=saved.data.content_hash
      setSaveStatus('saved')
      setSaveConflict(false)
      saveTimer.current = null
      qc.invalidateQueries({ queryKey: ['chapters', bid] })
      qc.invalidateQueries({ queryKey: ['book', bid] })
      qc.invalidateQueries({ queryKey: ['stats'] })
      return true
    } catch (e) {
      setSaveStatus('error')
      if((e as {response?:{status?:number}}).response?.status===409)setSaveConflict(true)
      setError(extractError(e, '保存失败'))
      return false
    }
  }, [selectedChapterId, bid, qc])

  const editor = useEditor({
    extensions: [StarterKit, Highlight],
    content: '',
    immediatelyRender: false,
    onUpdate: ({ editor: ed }) => {
      setSaveStatus('idle')
      if (saveTimer.current) window.clearTimeout(saveTimer.current)
      saveTimer.current = window.setTimeout(() => {
        void doSave(ed.getHTML(), chapterTitle)
      }, autoSaveMs)
    },
  })

  // 选中章节时加载内容到编辑器
  useEffect(() => {
    if (!editor || !chapterDetail) return
    if (lastSavedId.current === chapterDetail.id) return
    lastSavedId.current = chapterDetail.id
    baseHash.current=chapterDetail.content_hash
    setChapterTitle(chapterDetail.title)
    setSaveStatus('idle')
    editor.commands.setContent(toEditorContent(chapterDetail.content || ''), { emitUpdate: false })
    editor.commands.setTextSelection(0)
    requestAnimationFrame(() => editor.view.dom.closest('.manuscript-scroll')?.scrollTo({ top: 0 }))
  }, [editor, chapterDetail])

  // 卸载/切换章节时清理定时器
  useEffect(() => {
    return () => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current)
    }
  }, [])

  const selectChapter = async (id: number) => {
    if (saveTimer.current && editor && selectedChapterId) {
      window.clearTimeout(saveTimer.current);saveTimer.current=null
      const saved = await doSave(editor.getHTML(), chapterTitle)
      if (!saved) return
    }
    setSelectedChapterId(id)
  }
  const exportBook = async () => {
    setExporting(true)
    try {
      const result=await api.get(`/books/${bid}/export`, {responseType:'blob'})
      const url=URL.createObjectURL(result.data);const a=document.createElement('a')
      a.href=url;a.download=`${book?.title || '小说'}.md`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
    } catch(e) {toast.error(extractError(e,'导出失败，请先确认作品包含正文'))}
    finally {setExporting(false)}
  }
  const manualSave = () => {
    if (!editor) return
    if (saveTimer.current) window.clearTimeout(saveTimer.current)
    void doSave(editor.getHTML(), chapterTitle)
  }

  const titleInputSave = (title: string) => {
    setChapterTitle(title)
    if (editor && selectedChapterId) {
      if (saveTimer.current) window.clearTimeout(saveTimer.current)
      saveTimer.current = window.setTimeout(() => {
        void doSave(editor.getHTML(), title)
      }, 2000)
    }
  }

  const createChapter = useMutation({
    mutationFn: async (title: string) => (await api.post<ChapterDetail>(`/chapters/books/${bid}`, { title })).data,
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['chapters', bid] })
      setSelectedChapterId(c.id)
    },
    onError: (e) => setError(extractError(e, '新建章节失败')),
  })

  // 自动定位最新章节
  useEffect(() => {
    if (chapters && chapters.length && selectedChapterId === null) {
      setSelectedChapterId(chapters.find(c=>c.id===Number(searchParams.get('chapter')))?.id ?? [...chapters].reverse().find(c=>c.word_count>0)?.id ?? chapters[0].id)
    }
  }, [chapters, selectedChapterId])

  const startTask=(kind:'generate'|'scene-plan')=>{
    if(!selectedChapterId)return
    try{prepareJobPrompt({book_id:bid,chapter_id:selectedChapterId,kind})}catch(e){toast.error(extractError(e,'请先处理助手中的草稿'))}
  }
  const generateChapter=()=>startTask('generate')
  useEffect(()=>{editor?.setEditable(!chapterBusy, false)},[editor,chapterBusy])
  useEffect(()=>{
    for(const j of workJobs){
      if(j.status!=='succeeded' || finishedJobs.current.has(j.id))continue
      finishedJobs.current.add(j.id)
      if(j.chapter_id===selectedChapterId && ['generate','revise'].includes(j.kind)){
        lastSavedId.current=null
        void qc.invalidateQueries({queryKey:['chapter',selectedChapterId]})
      }
      if(j.kind==='chapter-outline'){void qc.invalidateQueries({queryKey:['blueprint',j.chapter_id]})}
      if(j.kind==='outline'){void qc.invalidateQueries({queryKey:['outline',bid]});void qc.invalidateQueries({queryKey:['guide-outline',bid]})}
      void qc.invalidateQueries({queryKey:['chapters',bid]})
      void qc.invalidateQueries({queryKey:['rag-status',bid]})
      void qc.invalidateQueries({queryKey:['book',bid]})
      void fetchMe()
    }
  },[workJobs,selectedChapterId,bid,qc,fetchMe])

  const prepareTextRequest=(kind:'selection'|'cursor')=>{
    if(!editor||!selectedChapterId)return
    const {from,to,empty}=editor.state.selection
    if(kind==='selection'&&empty){toast.info('请先选中要修改的正文片段');return}
    const position=kind==='cursor'?to:from
    const prefix=editor.state.doc.textBetween(0,position,'\n')
    const text=editor.state.doc.textBetween(from,to,'\n')
    if(kind==='selection'&&text.length>6000){toast.info('单次引用最多 6000 字，请缩小选区');return}
    const line=prefix.split('\n').length
    const reference:ManuscriptReference={kind,chapter_id:selectedChapterId,title:chapterTitle||'当前章节',
      affinity:editor.state.doc.resolve(position).parentOffset===0?'before':'after',line_start:line,line_end:line+text.split('\n').length-1,offset:Array.from(compactText(prefix)).length,
      text:kind==='selection'?text:`${prefix.slice(-160)}▏${editor.state.doc.textBetween(to,editor.state.doc.content.size,'\n').slice(0,160)}`,
      expected_hash:baseHash.current,snapshot:editor.getHTML()}
    try{stageAssistantPrompt(bid,kind==='selection'?'请润色引用的选中片段，保持事实、人物语气和原意，提升表达与画面感。结合本章完整正文理解上下文，返回可对照采用的修改候选。':'请先阅读本章完整正文、章纲和前文记忆，在引用的光标位置续写约 600 字，与后文自然衔接，避免重复已写事件。返回可插入的续写候选。',selectedChapterId,[reference])}
    catch(e){toast.error(extractError(e,'请先处理助手中的草稿'))}
  }
  useEffect(()=>{const update=(event:Event)=>{const id=(event as CustomEvent).detail?.chapterId;if(id===selectedChapterId){lastSavedId.current=null;void qc.invalidateQueries({queryKey:['chapter',id]})}};window.addEventListener('storyclaw:manuscript-updated',update);return()=>window.removeEventListener('storyclaw:manuscript-updated',update)},[selectedChapterId,qc])
  const prepareSend=async(targetChapter:number|null,references:ManuscriptReference[])=>{
    if(targetChapter===selectedChapterId&&editor){
      if(saveStatus==='saving')throw new Error('正文正在保存，请稍后发送；需求和引用仍保留')
      if(saveTimer.current||saveStatus==='error'){
        if(saveTimer.current){window.clearTimeout(saveTimer.current);saveTimer.current=null}
        if(!await doSave(editor.getHTML(),chapterTitle))throw new Error('正文保存失败，需求仍保留，请处理冲突后再发送')
      }
    }
    const result:ManuscriptReference[]=[]
    for(const reference of references){
      const current=(await api.get<ChapterDetail>(`/chapters/${reference.chapter_id}`)).data
      if(reference.snapshot&&compactText(manuscriptPlainText(current.content))!==compactText(manuscriptPlainText(reference.snapshot)))
        throw new Error('引用后的正文已经改变，请移除旧引用并重新选择；输入的需求已保留')
      const {snapshot,...wire}=reference
      result.push({...wire,expected_hash:current.content_hash})
    }
    return result
  }

  if (!bid) return <div className="p-8 text-muted-foreground">无效书籍</div>

  const chaptersByVol = (volId: number | null) => chapters?.filter((c) => c.volume_id === volId) ?? []

  return (
    <div className={`writer-studio h-screen flex flex-col bg-background ${focusMode ? 'writer-focused' : ''}`}>
      <header className="writer-header">
        <Link to="/" className="writer-home" aria-label="返回创作首页"><Feather size={22}/><span>StoryClaw</span></Link>
        <ChevronRight size={14} className="text-muted-foreground opacity-50"/>
        <div className="writer-book-title"><strong>{book?.title ?? '加载作品…'}</strong><span>{book?.genre || '小说'} · 创作空间</span></div>
        <span className={`writer-save-state ${saveStatus}`}><i/>{saveStatus==='saving' ? '正在保存' : saveStatus==='saved' ? '已保存' : saveStatus==='error' ? '保存失败' : '自动保存已开启'}</span>
        <div className="writer-header-actions"><Button size="sm" variant="ghost" onClick={()=>setActiveTab('任务')}><History size={15}/><span>任务{workJobs.some(j=>['queued','running'].includes(j.status))?' · 处理中':''}</span></Button><Button size="sm" variant="ghost" onClick={()=>setFocusMode(!focusMode)} title={focusMode?'展开目录与助手':'专注写作'}>{focusMode?<PanelLeft size={15}/>:<Focus size={15}/>}<span>{focusMode?'展开面板':'专注模式'}</span></Button><Button aria-label="导出作品" size="sm" variant="outline" onClick={()=>void exportBook()} disabled={exporting || !chapters?.some(c=>c.word_count>0)}><Download size={14}/><span>{exporting?'导出中…':'导出作品'}</span></Button><Button aria-label="保存章节" onClick={manualSave} disabled={!editor || !selectedChapterId || chapterBusy} size="sm"><Save size={14}/><span>保存</span></Button></div>
      </header>
      {compact && <div className="mobile-chapter-picker"><span>当前章节</span><select aria-label="选择章节" value={selectedChapterId ?? ''} onChange={e=>void selectChapter(Number(e.target.value))}><option value="" disabled>选择章节开始创作</option>{chapters?.map(c=><option key={c.id} value={c.id}>第{c.number}章 · {c.title}</option>)}</select></div>}

      {saveConflict && <div className="save-conflict" role="alert"><p>当前正文已被其他窗口或任务修改，本地稿未覆盖服务器。请先保留本地稿，再加载最新版本核对。</p><Button size="sm" variant="outline" onClick={()=>{const blob=new Blob([editor?.getText() ?? ''],{type:'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`${chapterTitle}-本地稿.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}}>下载本地稿</Button><Button size="sm" onClick={()=>{if(window.confirm('确认丢弃未保存的本地修改并加载服务器最新版本？')){if(saveTimer.current)window.clearTimeout(saveTimer.current);saveTimer.current=null;lastSavedId.current=null;setSaveConflict(false);void qc.refetchQueries({queryKey:['chapter',selectedChapterId]})}}}>加载最新版本</Button></div>}
      {!!workflow?.impacts.length&&<details className="continuity-notice"><summary>{workflow.impacts.length} 个章节因前文或设定变更需要复核</summary><p>核对受影响章节，再到故事记忆确认并入库；后文不会自动改写。</p>{workflow.impacts.map(n=><button key={n.chapter_id} onClick={()=>{setActiveTab('创作');void selectChapter(n.chapter_id)}}>章节 #{n.chapter_id}：{n.reason} →</button>)}</details>}
      <ChapterVersions chapterId={selectedChapterId} open={showVersions} onClose={()=>setShowVersions(false)} onRestored={()=>{lastSavedId.current=null;void qc.invalidateQueries({queryKey:['chapter',selectedChapterId]});void qc.invalidateQueries({queryKey:['chapters',bid]})}}/>
      {!hideRouteGuide&&<div className="writer-route-guide"><div><span className="status-dot"/><span>{activeTab==='创作'?'选择章节开始写作，先规划场景，再生成和修订正文。':activeTab==='大纲'?'先确定故事走向，再把分卷与章节组织起来。':activeTab==='数据库'?'将审阅后的正文更新为故事记忆，为后续创作提供参考。':activeTab==='任务'?'耗时操作在后台执行，展开任务查看结果与修订建议。':'设定、正文与公开阅读，在同一个创作空间里衔接。'}</span></div><Link to="/help#workflow">创作流程与使用指南 ↗</Link><button aria-label="关闭创作提示" title="关闭提示；使用指南仍可从创作路线打开" onClick={()=>{setHideRouteGuide(true);localStorage.setItem('sc-hide-route-guide','1')}}><X size={15}/></button></div>}
      {/* Tab 栏 */}
      <nav className="writer-tabs bg-background border-b flex gap-1 px-4 shrink-0 overflow-x-auto">
        {TABS.map((t) => {
          const enabled = ENABLED_TABS.has(t)
          return (
            <button key={t} onClick={() => enabled ? setActiveTab(t) : undefined}
              disabled={!enabled} aria-current={activeTab===t?'page':undefined} title={({'创作':'编辑、生成与修订章节','大纲':'规划分卷、章节与摘要','世界观':'维护时代、社会与力量规则','角色':'维护人物与动机','场景':'管理地点与环境规则','物品':'记录重要道具','情节':'整理冲突与伏笔','数据库':'入库正文，检索历史记忆','任务':'查看后台进度与结果','阅读':'阅读当前作品','书籍信息':'作品资料和公开发布','创作管理':'旧稿接管、连续计划与投稿准备','设置':'调整创作参数'})[t]}
              className={`px-3 h-full text-sm border-b-2 transition ${
                activeTab === t ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'
              } ${!enabled ? 'opacity-40 cursor-not-allowed' : 'hover:text-foreground'}`}>
              {(() => { const Icon = ({'创作':PenLine,'阅读':BookOpen,'世界观':Library,'角色':Users,'场景':MapPin,'物品':Package,'情节':GitBranch,'大纲':FileText,'数据库':Network,'书籍信息':Library,'设置':Settings,'任务':History,'创作管理':Library})[t]; return <Icon size={14}/> })()}{t==='数据库'?'故事记忆':t}
            </button>
          )
        })}
      </nav>

      {/* 三栏工作区 */}
      <div className="writer-panels flex-1 min-h-0">
        <PanelGroup key={activeTab==='创作'?'writing':'planning'} direction={compact ? "vertical" : "horizontal"}>
          {/* 左：目录树（阅读 tab 时隐藏，由 ReaderPage 提供自己的目录） */}
          {activeTab === '创作' && !focusMode && (
            <>
            <Panel key="left-toc" defaultSize={16} minSize={12} className="writer-toc bg-background border-r">
            <div className="h-full flex flex-col">
              <div className="px-3 py-2 border-b flex items-center justify-between">
                <span className="toc-heading"><List size={14}/>章节目录<small>{chapters?.length ?? 0}</small></span>
                <Button variant="ghost" size="icon" className="text-primary h-7 w-7" title="新增章节" onClick={() => {
                  const t = prompt('章节标题', `第 ${(chapters?.length ?? 0) + 1} 章`)
                  if (t) createChapter.mutate(t)
                }}>
                  <Plus size={16} />
                </Button>
              </div>
              <div className="flex-1 overflow-y-auto text-sm">
                <div className="px-3 py-1 text-xs text-muted-foreground font-medium">{book?.title}</div>
                {volumes?.map((v) => (
                  <div key={v.id}>
                    <div className="px-3 py-1.5 text-xs text-muted-foreground font-medium bg-muted">{v.name}</div>
                    {chaptersByVol(v.id).map((c) => (
                      <ChapterItem key={c.id} chapter={c} active={c.id === selectedChapterId} onClick={() => void selectChapter(c.id)} />
                    ))}
                  </div>
                ))}
                {/* 未分卷章节 */}
                {(chaptersByVol(null).length > 0 || (volumes?.length === 0 && (chapters?.length ?? 0) > 0)) && (
                  volumes?.length ? <div className="px-3 py-1.5 text-xs text-muted-foreground font-medium bg-muted">未分卷</div> : null
                )}
                {chaptersByVol(null).map((c) => (
                  <ChapterItem key={c.id} chapter={c} active={c.id === selectedChapterId} onClick={() => void selectChapter(c.id)} />
                ))}
                {chapters?.length === 0 && <div className="px-3 py-4 text-center text-muted-foreground text-xs">点击 + 新建章节</div>}
              </div>
            </div>
            </Panel>
            <PanelResizeHandle className="w-1 bg-muted hover:bg-primary/60 transition" />
            </>
          )}

          {/* 中：编辑器 */}
          <Panel defaultSize={focusMode ? 100 : activeTab==='创作' ? 60 : 76} minSize={30} className="writer-center flex flex-col">
            {activeTab === '任务' ? (
              <JobCenter bookId={bid}/>
            ) : activeTab === '大纲' ? (
              <OutlinePanel key={bid} bookId={bid} />
            ) : activeTab === '数据库' ? (
              <div className="flex flex-col h-full min-h-0">
                {!embeddingReady && (
                  <div className="px-4 py-2 bg-amber-50 dark:bg-amber-950/40 border-b flex items-center justify-between gap-2 shrink-0">
                    <span className="text-xs text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
                      <Wand2 size={12} /> 尚未配置向量模型（Embedding），章节入库与 RAG 检索不可用
                    </span>
                    <Button size="sm" variant="outline" className="h-6 px-2 text-[11px] shrink-0" onClick={() => navigate(user?.is_admin ? '/admin' : '/help')}>
                      去配置
                    </Button>
                  </div>
                )}
                <div className="flex-1 min-h-0">
                  <DatabasePanel bookId={bid} onError={(msg) => setError(msg)} />
                </div>
              </div>
            ) : activeTab === '阅读' ? (
              <ReaderPage bid={bid} />
            ) : activeTab === '世界观' ? (
              <ConfigPage bid={bid} entityType="world" />
            ) : activeTab === '角色' ? (
              <ConfigPage bid={bid} entityType="character" />
            ) : activeTab === '场景' ? (
              <ConfigPage bid={bid} entityType="scene" />
            ) : activeTab === '物品' ? (
              <ConfigPage bid={bid} entityType="item" />
            ) : activeTab === '情节' ? (
              <ConfigPage bid={bid} entityType="plot" />
            ) : activeTab === '书籍信息' ? (
              <BookInfoPage book={book} bid={bid} onSaved={() => qc.invalidateQueries({ queryKey: ['book', bid] })} />
            ) : activeTab === '创作管理' ? (
              <StudioManager bid={bid} chapterId={selectedChapterId} />
            ) : activeTab === '设置' ? (
              <WorkspaceSettings
                autoSaveMs={autoSaveMs}
                setAutoSaveMs={(ms) => { setAutoSaveMs(ms); localStorage.setItem('sc_autosave_ms', String(ms)) }}
                llmReady={llmReady}
                embeddingReady={embeddingReady}
                onGoConfig={() => navigate(user?.is_admin ? '/admin' : '/help')}
              />
            ) : selectedChapterId ? (
              <>
                <div className="manuscript-heading px-6 pt-4 pb-2 bg-background border-b">
                  <Input
                    className="w-full text-xl font-bold outline-none border-transparent shadow-none px-0 focus-visible:ring-0"
                    value={chapterTitle}
                    onChange={(e) => titleInputSave(e.target.value)}
                    disabled={chapterBusy}
                    aria-label="章节标题"
                    placeholder="章节标题"
                  />
                  <div className="text-xs text-muted-foreground mt-1">
                    {chapterDetail ? `第 ${chapterDetail.number} 章 · ${chapterDetail.word_count.toLocaleString()} 字${book?.per_chapter_words ? ` / 目标 ${book.per_chapter_words.toLocaleString()} 字` : ''}` : ''}
                  </div>
                </div>
                {chapterBusy && <div className="mx-6 mb-3 text-xs text-primary">该章节任务正在处理中，正文暂时只读。可在任务中心查看进度。</div>}
            <ChapterPlanning key={selectedChapterId} bookId={bid} chapterId={selectedChapterId} jobs={workJobs} onTasks={()=>setActiveTab('任务')}/>
            <CreationGuide key={bid} bookId={bid} book={book} chapters={chapters ?? []} jobs={workJobs} onNavigate={setActiveTab}/>
                <div className="manuscript-toolbar px-4 py-1.5 bg-background border-b flex items-center gap-1 flex-wrap">
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleBold().run()} active={!!editor?.isActive('bold')} title="加粗"><Bold size={16} /></ToolBtn>
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleItalic().run()} active={!!editor?.isActive('italic')} title="斜体"><Italic size={16} /></ToolBtn>
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleHeading({ level: 1 }).run()} active={!!editor?.isActive('heading', { level: 1 })} title="一级标题"><Heading1 size={16} /></ToolBtn>
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()} active={!!editor?.isActive('heading', { level: 2 })} title="二级标题"><Heading2 size={16} /></ToolBtn>
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleHighlight().run()} active={!!editor?.isActive('highlight')} title="高亮"><Highlighter size={16} /></ToolBtn>
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleBulletList().run()} active={!!editor?.isActive('bulletList')} title="列表"><List size={16} /></ToolBtn>
                  <div className="w-px h-5 bg-muted mx-1" /><Button size="sm" variant="ghost" onClick={async()=>{if(saveTimer.current && editor){window.clearTimeout(saveTimer.current);if(!await doSave(editor.getHTML(),chapterTitle))return}setShowVersions(true)}}><History size={13}/>版本</Button><Button size="sm" variant="ghost" disabled={chapterBusy} onClick={()=>void startTask('scene-plan')}><List size={13}/>场景规划</Button>
                  <Button
                    size="sm"
                    className="writer-generate"
                    onClick={() => void generateChapter()}
                    disabled={!selectedChapterId || chapterBusy}
                    title="根据本章大纲和已有设定生成正文"
                  >
                    <PenLine size={14} /> 写本章需求
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => prepareTextRequest('selection')}
                    disabled={!selectedChapterId || chapterBusy}
                    title="选中一段文字，优化表达与描写"
                  >
                    <Wand2 size={14} /> 润色选中
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => prepareTextRequest('cursor')}
                    disabled={!selectedChapterId || chapterBusy}
                    title="把光标放在段尾，接着当前内容续写"
                  >
                    <CornerDownRight size={14} /> 续写需求
                  </Button>
                </div>
                <div className="manuscript-scroll flex-1 overflow-y-auto bg-background px-6 py-4 prose max-w-none">
                  <EditorContent editor={editor} />
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-muted-foreground">
                <div className="text-center">
                  <div className="writer-blank-mark"><Feather size={36}/></div><h2 className="text-xl text-foreground font-serif mt-5 mb-3">下一章，从这里开始。</h2><p className="text-xs leading-6">选择一个章节，继续你的故事。<br/>也可以创建新章节，或先在大纲里整理思路。</p>
                  <Button className="mt-3" onClick={() => {
                    const t = prompt('章节标题', `第 ${(chapters?.length ?? 0) + 1} 章`)
                    if (t) createChapter.mutate(t)
                  }}>
                    <Plus size={16} /> 新建第一章
                  </Button>
                </div>
              </div>
            )}
          </Panel>
          {!focusMode && <>
          <PanelResizeHandle className="w-1 bg-muted hover:bg-primary/60 transition" />

          {/* 右：Ask 面板 */}
          <Panel defaultSize={24} minSize={20} className="writer-assistant bg-background border-l flex flex-col">
            <StoryAssistant key={bid} bookId={bid} chapterId={selectedChapterId} chapterLabel={chapterDetail?`第${chapterDetail.number}章 · ${chapterTitle}`:undefined} beforeSend={prepareSend} onTasks={()=>setActiveTab('任务')}/>
          </Panel>
          </>}
        </PanelGroup>
      </div>

      {error && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-destructive text-white text-sm px-4 py-2 rounded-lg shadow z-50">
          {error}
          <button onClick={() => setError('')} className="ml-2"><RotateCcw size={12} /></button>
        </div>
      )}
    </div>
  )
}

function ChapterItem({ chapter, active, onClick }: { chapter: Chapter; active: boolean; onClick: () => void }) {
  const ragColor = chapter.rag_status === 'loaded'
    ? 'bg-green-500'
    : chapter.word_count > 0
      ? 'bg-amber-400'
      : 'bg-muted-foreground/40'
  const ragTitle = chapter.rag_status === 'loaded' ? '已入库 RAG' : chapter.word_count > 0 ? '有内容未入库' : '无内容'
  return (
    <button onClick={onClick} className={`w-full text-left px-3 py-1.5 flex items-center justify-between hover:bg-primary/10 ${active ? 'bg-primary/10 text-primary' : 'text-foreground'}`}>
      <span className="truncate flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${ragColor}`} title={ragTitle} />
        {chapter.title}
      </span>
      <span className="text-[10px] text-muted-foreground ml-1 shrink-0">{chapter.word_count}</span>
    </button>
  )
}

function ToolBtn({ onClick, active, title, children, disabled }: { onClick: () => void; active: boolean; title: string; children: React.ReactNode; disabled?: boolean }) {
  return (
    <button disabled={disabled} onClick={onClick} title={title}
      className={`p-1.5 rounded hover:bg-muted ${active ? 'bg-primary/10 text-primary' : 'text-muted-foreground'}`}>
      {children}
    </button>
  )
}
