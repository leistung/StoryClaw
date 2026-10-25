import IdeaDiscussion from '@/components/IdeaDiscussion'
import { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth'
import api, { extractError } from '@/lib/api'
import type { Book, BookInput, Stats } from '@/types'
import { Plus, Sparkles, ArrowRight, Search, ArrowUp, ChevronRight, LayoutGrid, List, X, Feather as FeatherMark } from 'lucide-react'
import type { FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

const GENRES = ['玄幻','仙侠','历史','都市','科幻','末世','悬疑','奇幻','武侠','古代言情','现代言情','现实','游戏体育','军事','轻小说','诸天无限','其他']
const PLATFORMS = ['起点', '番茄', '晋江', '七猫', '黑岩', '知乎盐选']

const emptyForm: BookInput = {
  title: '', intro: '', genre: '都市', platforms: [], cover_url: '',
  target_chapters: 20, target_words: 60000, per_chapter_words: 3000,
  protagonist_name: '', protagonist_intro: '',
  generate_outline: false, generate_plots: false, generate_characters: false,
}

export default function Home() {
  const user = useAuthStore(s => s.user)
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const library = params.get('view') === 'books'
  const [showModal, setShowModal] = useState(false)
  const [fromProposal,setFromProposal]=useState(false)
  const [form, setForm] = useState<BookInput>(emptyForm)
  const [idea, setIdea] = useState('')
  const [search, setSearch] = useState('')
  const [genre, setGenre] = useState('全部作品')
  const [listView, setListView] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (params.get('new') === '1') { setShowModal(true); const next = new URLSearchParams(params); next.delete('new'); setParams(next, {replace:true}) } }, [params, setParams])
  const { data: stats } = useQuery({queryKey:['stats'],queryFn:async () => (await api.get<Stats>('/books/stats')).data,refetchInterval:30000})
  const { data: books, isLoading, isError, refetch } = useQuery({queryKey:['books'],queryFn:async () => (await api.get<Book[]>('/books')).data,refetchInterval:30000})
  const openBook = (id:number, tab?:string) => navigate(`/workspace/${id}${tab ? '?tab='+encodeURIComponent(tab) : ''}`)
  const start = (intro = idea, selectedGenre = form.genre) => { setFromProposal(false);setForm({...emptyForm, intro, genre:selectedGenre}); setError(''); setShowModal(true) }
  const recompute = (next:Partial<BookInput>) => { const merged={...form,...next}; if (merged.target_chapters>0 && (next.target_words!==undefined || next.target_chapters!==undefined)) merged.per_chapter_words=Math.round(merged.target_words/merged.target_chapters); setForm(merged) }
  const togglePlatform = (p:string) => recompute({platforms:form.platforms.includes(p) ? form.platforms.filter(x=>x!==p) : [...form.platforms,p]})
  const createMutation = useMutation({mutationFn:async () => (await api.post<Book>('/books',{...form,title:form.title.trim()})).data,onSuccess:b=>{if(fromProposal)sessionStorage.removeItem(`sc-ideation-${user?.id}`);qc.invalidateQueries({queryKey:['books']});qc.invalidateQueries({queryKey:['stats']});setShowModal(false);setForm(emptyForm);setError('');openBook(b.id)},onError:err=>setError(extractError(err,'创建失败'))})
  const submit = (e:FormEvent) => {e.preventDefault();if(!form.title.trim()){setError('请填写书名');return}setError('');createMutation.mutate()}
  const filtered=(books ?? []).filter(b=>(genre==='全部作品'||b.genre===genre) && (b.title+' '+b.genre).toLowerCase().includes(search.toLowerCase()))
  const hour = new Date().getHours()
  const greeting = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好'
  return (<div className="studio-home">
    {!library && <section className="creation-hero">
      <div className="hero-orbit orbit-one"/><div className="hero-orbit orbit-two"/>
      <div className="hero-eyebrow"><span className="status-dot"/> STORYCLAW · YOUR STORY STARTS HERE</div>
      <h1><span>{greeting}，{user?.username}。</span>今天，写一个怎样的世界？</h1>
      <p className="hero-subtitle">每一个值得被讲述的故事，都始于一个小小的念头。</p>
      <IdeaDiscussion onConfirm={draft=>{setFromProposal(true);setForm({...emptyForm,...draft});setError('');setShowModal(true)}}/>
    </section>}
    {!library && <div className="studio-metrics">{[['作品集',books?.length ?? 0,'部作品'],['今日落笔',stats?.today_words ?? 0,'字'],['累计创作',stats?.total_words ?? 0,'字']].map(([label,value,unit])=><div key={label}><span>{label}</span><strong>{Number(value).toLocaleString()}<small>{unit}</small></strong></div>)}<p><FeatherMark/> 让每一次落笔，都离完稿更近一点。</p></div>}
    <section className="books-section">
      <div className="section-heading"><div><span className="section-overline">YOUR STORIES</span><h2>{library ? '我的作品' : '继续你的故事'}<span>{books?.length ?? 0}</span></h2></div><button className="quiet-action" onClick={()=>start('')}><Plus size={16}/>新建作品</button></div>
      <div className="library-toolbar"><div className="genre-filters">{['全部作品',...Array.from(new Set((books ?? []).map(b=>b.genre).filter(Boolean)))].map(g=><button key={g} onClick={()=>setGenre(g)} className={genre===g?'selected':''}>{g}</button>)}</div><div className="library-controls"><div className="book-search"><Search size={14}/><input aria-label="搜索作品" placeholder="搜索作品" value={search} onChange={e=>setSearch(e.target.value)}/>{search && <button aria-label="清除搜索" onClick={()=>setSearch('')}><X size={12}/></button>}</div><button className={!listView?'selected':''} aria-label="卡片视图" onClick={()=>setListView(false)}><LayoutGrid size={16}/></button><button className={listView?'selected':''} aria-label="列表视图" onClick={()=>setListView(true)}><List size={16}/></button></div></div>
      {isLoading ? <div className="books-grid">{[1,2,3].map(i=><div key={i} className="book-skeleton animate-pulse"/>)}</div> : isError ? <div className="library-empty"><p>暂时无法加载作品</p><Button variant="outline" onClick={()=>void refetch()}>重新加载</Button></div> : <div className={listView?'books-list':'books-grid'}>
        {filtered.map((b,i)=><button key={b.id} className="story-card" onClick={()=>openBook(b.id)}>
          <div className={`story-cover cover-${i%4}`}>{b.cover_url ? <img src={b.cover_url} alt={b.title+'封面'}/> : <><div className="cover-moon"/><svg viewBox="0 0 500 230" preserveAspectRatio="xMidYMax slice" aria-hidden="true"><path d="M-20 220L92 74L154 143L225 35L339 166L402 95L530 220Z" fill="currentColor" opacity=".15"/><path d="M-20 230L91 125L168 191L264 94L348 181L442 140L530 240Z" fill="currentColor" opacity=".22"/><path d="M0 210Q140 150 260 205T500 184V260H0Z" fill="currentColor" opacity=".22"/></svg><span className="cover-serial">STORY / {String(i+1).padStart(2,'0')}</span><span className="cover-title">{b.title}</span><span className="cover-tagline">一个世界，正在成形。</span></>}<span className="book-genre">{b.genre || '小说'}</span><span className="cover-open"><ArrowUp size={17}/></span></div>
          <div className="story-card-info"><div className="story-title-row"><h3>{b.title}</h3><ChevronRight size={16}/></div><p>{b.chapter_count} 章 <span>·</span> {(b.total_words ?? 0).toLocaleString()} 字</p><div className="book-progress"><span style={{width:Math.min(100,(b.total_words / Math.max(1,b.target_words))*100)+'%'}}/></div><div className="book-progress-label"><span>创作进度</span><span>{Math.min(100,Math.round(b.total_words/Math.max(1,b.target_words)*100))}%</span></div></div>
        </button>)}
        {!search && genre==='全部作品' && <button className="new-story-card" onClick={()=>start('')}><span><Plus size={25}/></span><strong>新的故事，新的可能</strong><p>从一个想法，开启下一个世界</p><small>创建新作品 <ArrowRight size={14}/></small></button>}
        {!filtered.length && (search || genre!=='全部作品') && <div className="library-empty">没有找到对应作品，试试其他关键词。</div>}
      </div>}
    </section>
    <footer className="studio-footer"><span>STORYCLAW <span> / </span> 为长篇创作而设计</span><span>把下一章，交给想象力。</span></footer>
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>创建新书</DialogTitle>
            <DialogDescription>设置你的故事与创作目标，创建后即可进入工作台。</DialogDescription>
          </DialogHeader>
          <form onSubmit={submit} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="bk-title">书名 *</Label>
              <Input id="bk-title" required maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="我的小说" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="bk-intro">简介</Label>
              <Textarea id="bk-intro" rows={2} value={form.intro} onChange={(e) => setForm({ ...form, intro: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label>类型</Label>
              <Select value={form.genre ?? ''} onValueChange={(v) => setForm({ ...form, genre: v ?? '' })}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {GENRES.map((g) => (
                    <SelectItem key={g} value={g}>{g}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>发布平台</Label>
              <div className="flex flex-wrap gap-2">
                {PLATFORMS.map((p) => (
                  <Button
                    key={p}
                    type="button"
                    variant={form.platforms.includes(p) ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => togglePlatform(p)}
                  >
                    {p}
                  </Button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="bk-chapters">全书预计章数</Label>
                <Input id="bk-chapters" type="number" min={1} max={3000} required value={form.target_chapters} onChange={(e) => recompute({ target_chapters: Number(e.target.value) || 1 })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="bk-words">全书目标字数</Label>
                <Input id="bk-words" type="number" min={1000} max={15000000} required value={form.target_words} onChange={(e) => recompute({ target_words: Number(e.target.value) || 0 })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="bk-per">每章字数</Label>
                <Input id="bk-per" type="number" className="bg-muted" value={form.per_chapter_words} readOnly />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="bk-pname">主角名</Label>
                <Input id="bk-pname" value={form.protagonist_name} onChange={(e) => setForm({ ...form, protagonist_name: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="bk-cover">封面 URL（可选）</Label>
                <Input id="bk-cover" value={form.cover_url} onChange={(e) => setForm({ ...form, cover_url: e.target.value })} placeholder="https://..." />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="bk-pintro">主角介绍</Label>
              <Textarea id="bk-pintro" rows={2} value={form.protagonist_intro} onChange={(e) => setForm({ ...form, protagonist_intro: e.target.value })} />
            </div>
            <div className="rounded-lg border bg-muted/40 p-3 text-xs leading-6 text-muted-foreground">创建后进入创作台，先整理设定、生成并确认大纲，再按需规划情节和章节。AI 任务由你逐步发起，可在任务中心查看进度。</div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" onClick={() => setShowModal(false)}>取消</Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? '创建中…' : '创建并进入'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
