import StoryAssistant from '@/components/StoryAssistant'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import ChapterPlanning from '@/components/ChapterPlanning'
import CreationGuide from '@/components/CreationGuide'
import JobCenter from '@/components/JobCenter'
import ChapterVersions from '@/components/ChapterVersions'
import { enqueueJob, type WorkJob } from '@/lib/jobs'
import { toEditorContent } from '@/lib/editor-content'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Highlight from '@tiptap/extension-highlight'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import api, { extractError, streamChat, streamChapterGenerate, listChatSessions, getChatMessages, polishChapter, continueWriting, analyzeBook } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import type { Book, Chapter, ChapterDetail, Volume, ChatMessage, ChatResponse, ChatSession, ChapterGenerateResponse, AnalyzeSkill, LLMConfig } from '@/types'
import {
  X, Plus, Save, Home as HomeIcon, Bold, Italic, Heading1, Heading2,
  Highlighter, List, Send, RotateCcw, PenLine, Wand2, CornerDownRight, Sparkles, History, Feather, Focus, PanelLeft, Download, ChevronRight, BookOpen, Users, MapPin, Package, GitBranch, FileText, Network, Settings, Library,
} from 'lucide-react'
import OutlinePanel from '@/components/OutlinePanel'
import DatabasePanel from '@/components/DatabasePanel'
import ConfigPage from '@/components/ConfigPage'
import ReaderPage from '@/components/ReaderPage'
import BookInfoPage from '@/components/BookInfoPage'
import WorkspaceSettings from '@/components/WorkspaceSettings'
import type { KeyboardEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

const TABS = ['创作', '大纲', '世界观', '角色', '场景', '物品', '情节', '数据库', '任务', '阅读', '书籍信息', '设置'] as const
const ENABLED_TABS: ReadonlySet<string> = new Set(['创作', '阅读', '世界观', '角色', '场景', '物品', '情节', '大纲', '数据库', '书籍信息', '设置', '任务'])

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export default function Workspace() {
  const { bookId = '' } = useParams<{ bookId: string }>()
  const bid = Number(bookId)
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const fetchMe = useAuthStore((s) => s.fetchMe)
  const isBusiness = true
  const [searchParams,setSearchParams] = useSearchParams()
  const [activeTab, setActiveTabState] = useState<typeof TABS[number]>(() => TABS.find(t=>t===searchParams.get('tab')) || '创作')
  const setActiveTab=(tab:typeof TABS[number])=>{setActiveTabState(tab);setSearchParams({tab},{replace:true})}
  useEffect(()=>{const tab=TABS.find(t=>t===searchParams.get('tab'));if(tab)setActiveTabState(tab)},[searchParams])
  const [focusMode, setFocusMode] = useState(() => window.innerWidth < 800)
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
  const {data:planningOutline}=useQuery({queryKey:['outline',bid],enabled:!!bid,queryFn:async()=>{try{return (await api.get(`/books/${bid}/outline`)).data}catch(e){if((e as {response?:{status:number}}).response?.status===404)return null;throw e}},refetchInterval:5000})
  const outlineReady=!!planningOutline?.content?._review
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
  const requireLlm = () => true
  const requireEmbedding = () => true

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
      if (streamingRef.current) return  // 流式生成中不自动保存
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

  // ===== Ask 面板 =====
  const [askMessages, setAskMessages] = useState<ChatMessage[]>([])
  const [askInput, setAskInput] = useState('')
  const [threadId, setThreadId] = useState('')
  const [askSending, setAskSending] = useState(false)

  // ===== Ask 历史记录 =====
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)

  const refreshSessions = async () => {
    try {
      const list = await listChatSessions()
      setSessions(list)
    } catch { /* 静默失败，历史面板仍可用 */ }
  }

  useEffect(() => {
    if (historyOpen) {
      setHistoryLoading(true)
      void refreshSessions().finally(() => setHistoryLoading(false))
    }
  }, [historyOpen])

  const toggleHistory = () => {
    setHistoryOpen((v) => {
      const next = !v
      if (next) void refreshSessions()
      return next
    })
  }

  const loadSession = async (thread_id: string) => {
    if (historyLoading) return
    setHistoryLoading(true)
    try {
      const msgs = await getChatMessages(thread_id)
      setAskMessages(msgs)
      setThreadId(thread_id)
    } catch (e) {
      setError(extractError(e, '加载历史失败'))
    } finally {
      setHistoryLoading(false)
    }
  }

  const fmtTime = (iso?: string | null) => {
    if (!iso) return ''
    const d = new Date(iso)
    const now = new Date()
    const sameDay = d.toDateString() === now.toDateString()
    return sameDay
      ? d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
  }

  const sendAsk = async () => {
    const text = askInput.trim()
    if (!text || askSending) return
    if (!requireLlm()) return
    setAskSending(true)
    setAskInput('')
    const tempId = `temp-${Date.now()}`
    const assistantId = `temp-a-${Date.now()}`
    setAskMessages((prev) => [
      ...prev,
      { id: tempId, role: 'user', content: text },
      { id: assistantId, role: 'assistant', content: '' },
    ])
    await streamChat(
      { message: text, thread_id: threadId || undefined },
      {
        onStart: (d) => { if (d.thread_id) setThreadId(d.thread_id) },
        onState: (s) => {
          if (typeof s.content === 'string') {
            setAskMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: s.content as string } : m,
              ),
            )
          }
        },
        onDone: (d) => {
          const done = d as unknown as ChatResponse
          setAskMessages((prev) => [
            ...prev.filter((m) => m.id !== tempId && m.id !== assistantId),
            { id: tempId, role: 'user', content: text },
            {
              id: String(done.message_id), role: 'assistant', content: done.content,
              model: done.model, in_tokens: done.in_tokens, out_tokens: done.out_tokens,
              credits_cost: done.credits_cost,
            },
          ])
          if (isBusiness) void fetchMe()
        },
        onError: (msg) => {
          setError(msg || '发送失败')
          setAskMessages((prev) => prev.filter((m) => m.id !== tempId && m.id !== assistantId))
        },
      },
    )
    setAskSending(false)
  }

  // ===== 写本章：调用 write-chapter skill =====
  const [generating, setGenerating] = useState(false)
  const streamingRef = useRef(false)
  const startTask = async(kind:'generate'|'scene-plan') => {
    if(!selectedChapterId || chapterBusy || generating)return
    if(!outlineReady){setActiveTab('大纲');toast.info('请先保存并确认大纲，再使用 AI 规划或写作');return}
    if(kind==='generate' && (chapterDetail?.word_count ?? 0)>0 && !window.confirm('重新生成会替换本章正文，原稿将保留在版本历史中。是否继续？'))return
    setGenerating(true)
    try {
      if(saveTimer.current && editor){window.clearTimeout(saveTimer.current);if(!await doSave(editor.getHTML(),chapterTitle))return}
      await enqueueJob({book_id:bid,chapter_id:selectedChapterId,kind,prompt:`请写本章：${chapterTitle}`})
      await qc.invalidateQueries({queryKey:['jobs',bid]})
      toast.success('任务已排队，可以离开页面，稍后在任务中心查看结果')
    } catch(e){toast.error(extractError(e,'任务创建失败'))}
    finally{setGenerating(false)}
  }
  const generateChapter = () => startTask('generate')
  useEffect(()=>{editor?.setEditable(!chapterBusy, false)},[editor,chapterBusy])
  useEffect(()=>{
    for(const j of workJobs){
      if(j.status!=='succeeded' || finishedJobs.current.has(j.id))continue
      finishedJobs.current.add(j.id)
      if(j.chapter_id===selectedChapterId && j.kind==='generate'){
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

  const onAskKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void sendAsk() }
  }

  // ===== P1-6：润色选中 / 段内续写 / 分析 skill =====
  const [polishing, setPolishing] = useState(false)
  const [continuing, setContinuing] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)

  /** 取编辑器选中的纯文本（无 HTML 标签） */
  const getSelectedText = (): string => {
    if (!editor) return ''
    const { state } = editor
    const { from, to, empty } = state.selection
    if (empty) return ''
    return state.doc.textBetween(from, to, '\n')
  }

  /** 取光标前的正文（纯文本，最多 1500 字） */
  const getPrefixText = (): string => {
    if (!editor) return ''
    const { state } = editor
    const from = state.selection.from
    return state.doc.textBetween(0, from, '\n').slice(-1500)
  }

  /** 把 agent 返回的内容插入/替换到编辑器，并触发保存 */
  const applyAgentContent = (text: string, mode: 'replace-selection' | 'append-cursor') => {
    if (!editor) return
    if (mode === 'replace-selection') {
      // 替换选区
      const { from, to, empty } = editor.state.selection
      if (empty) {
        editor.commands.insertContent(text)
      } else {
        editor.chain().focus().deleteRange({ from, to }).insertContent(text).run()
      }
    } else {
      // 在光标处追加续写
      editor.chain().focus().insertContent(text).run()
    }
    // 立即保存
    if (saveTimer.current) window.clearTimeout(saveTimer.current)
    void doSave(editor.getHTML(), chapterTitle)
  }

  const polishSelected = async () => {
    if (!selectedChapterId || polishing) return
    const sel = getSelectedText()
    if (!sel.trim()) {
      setError('请先在编辑器中选中要润色的文本')
      return
    }
    setPolishing(true)
    setError('')
    try {
      const res = await polishChapter(selectedChapterId, {
        selected_text: sel,
        polish_goal: '提升文笔与画面感',
        thread_id: threadId || undefined,
      })
      if (res.thread_id) setThreadId(res.thread_id)
      applyAgentContent(res.content, 'replace-selection')
      lastSavedId.current = null
      qc.invalidateQueries({ queryKey: ['chapter', selectedChapterId] })
      qc.invalidateQueries({ queryKey: ['chapters', bid] })
      if (isBusiness) void fetchMe()
      setError(`已润色 ${res.word_count} 字 · in ${res.in_tokens}/out ${res.out_tokens}${isBusiness ? ` · ${res.credits_cost} 积分` : ''}`)
    } catch (e) {
      setError(extractError(e, '润色失败'))
    } finally {
      setPolishing(false)
    }
  }

  const continueAtCursor = async () => {
    if (!selectedChapterId || continuing) return
    const prefix = getPrefixText()
    if (!prefix.trim()) {
      setError('请把光标放在需要续写的段落位置')
      return
    }
    setContinuing(true)
    setError('')
    try {
      const res = await continueWriting(selectedChapterId, {
        prefix_text: prefix,
        max_words: 600,
        thread_id: threadId || undefined,
      })
      if (res.thread_id) setThreadId(res.thread_id)
      applyAgentContent(res.content, 'append-cursor')
      lastSavedId.current = null
      qc.invalidateQueries({ queryKey: ['chapter', selectedChapterId] })
      qc.invalidateQueries({ queryKey: ['chapters', bid] })
      if (isBusiness) void fetchMe()
      setError(`续写 ${res.word_count} 字 · in ${res.in_tokens}/out ${res.out_tokens}${isBusiness ? ` · ${res.credits_cost} 积分` : ''}`)
    } catch (e) {
      setError(extractError(e, '续写失败'))
    } finally {
      setContinuing(false)
    }
  }

  /** 触发分析 skill，结果回填到 Ask 面板 */
  const runAnalyze = async (skill: AnalyzeSkill) => {
    if(!bid || analyzing)return
    if(skill==='plot-planning'&&!outlineReady){setActiveTab('大纲');toast.info('请先保存并确认大纲，再规划情节');return}
    if(skill==='outline-planning'){setActiveTab('大纲');return}
    setAnalyzing(true)
    try{
      await enqueueJob({book_id:bid,kind:'analysis',skill,start:1,end:Math.max(1,...(chapters ?? []).map(c=>c.number))})
      void qc.invalidateQueries({queryKey:['jobs',bid]})
      toast.success('分析已排队，请在任务中心查看报告')
      setActiveTab('任务')
    }catch(e){toast.error(extractError(e,'创建分析任务失败'))}
    finally{setAnalyzing(false)}
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
              disabled={!enabled} aria-current={activeTab===t?'page':undefined} title={({'创作':'编辑、生成与修订章节','大纲':'规划分卷、章节与摘要','世界观':'维护时代、社会与力量规则','角色':'维护人物与动机','场景':'管理地点与环境规则','物品':'记录重要道具','情节':'整理冲突与伏笔','数据库':'入库正文，检索历史记忆','任务':'查看后台进度与结果','阅读':'阅读当前作品','书籍信息':'作品资料和公开发布','设置':'调整创作参数'})[t]}
              className={`px-3 h-full text-sm border-b-2 transition ${
                activeTab === t ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'
              } ${!enabled ? 'opacity-40 cursor-not-allowed' : 'hover:text-foreground'}`}>
              {(() => { const Icon = ({'创作':PenLine,'阅读':BookOpen,'世界观':Library,'角色':Users,'场景':MapPin,'物品':Package,'情节':GitBranch,'大纲':FileText,'数据库':Network,'书籍信息':Library,'设置':Settings,'任务':History})[t]; return <Icon size={14}/> })()}{t==='数据库'?'故事记忆':t}
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
                <div className="manuscript-toolbar px-4 py-1.5 bg-background border-b flex items-center gap-1 flex-wrap">
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleBold().run()} active={!!editor?.isActive('bold')} title="加粗"><Bold size={16} /></ToolBtn>
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleItalic().run()} active={!!editor?.isActive('italic')} title="斜体"><Italic size={16} /></ToolBtn>
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleHeading({ level: 1 }).run()} active={!!editor?.isActive('heading', { level: 1 })} title="一级标题"><Heading1 size={16} /></ToolBtn>
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()} active={!!editor?.isActive('heading', { level: 2 })} title="二级标题"><Heading2 size={16} /></ToolBtn>
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleHighlight().run()} active={!!editor?.isActive('highlight')} title="高亮"><Highlighter size={16} /></ToolBtn>
                  <ToolBtn disabled={chapterBusy} onClick={() => editor?.chain().focus().toggleBulletList().run()} active={!!editor?.isActive('bulletList')} title="列表"><List size={16} /></ToolBtn>
                  <div className="w-px h-5 bg-muted mx-1" /><Button size="sm" variant="ghost" onClick={async()=>{if(saveTimer.current && editor){window.clearTimeout(saveTimer.current);if(!await doSave(editor.getHTML(),chapterTitle))return}setShowVersions(true)}}><History size={13}/>版本</Button><Button size="sm" variant="ghost" disabled={chapterBusy || generating} onClick={()=>void startTask('scene-plan')}><List size={13}/>场景规划</Button>
                  <Button
                    size="sm"
                    className="writer-generate"
                    onClick={() => void generateChapter()}
                    disabled={!selectedChapterId || generating || chapterBusy}
                    title="根据本章大纲和已有设定生成正文"
                  >
                    <PenLine size={14} /> {generating ? '生成中…' : '写本章'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void polishSelected()}
                    disabled={!selectedChapterId || polishing || chapterBusy}
                    title="选中一段文字，优化表达与描写"
                  >
                    <Wand2 size={14} /> {polishing ? '润色中…' : '润色选中'}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => void continueAtCursor()}
                    disabled={!selectedChapterId || continuing || chapterBusy}
                    title="把光标放在段尾，接着当前内容续写"
                  >
                    <CornerDownRight size={14} /> {continuing ? '续写中…' : '续写'}
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
            {activeTab==='创作'&&<>
            <ChapterPlanning key={selectedChapterId} bookId={bid} chapterId={selectedChapterId} jobs={workJobs} onTasks={()=>setActiveTab('任务')}/>
            <CreationGuide key={bid} bookId={bid} book={book} chapters={chapters ?? []} jobs={workJobs} onNavigate={setActiveTab}/>
            </>}
            <StoryAssistant key={bid} bookId={bid} chapterId={selectedChapterId} onTasks={()=>setActiveTab('任务')}/>
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
