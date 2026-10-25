import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { extractError } from '@/lib/api'
import {enqueueJob,type WorkJob} from '@/lib/jobs'
import {useAuthStore} from '@/stores/auth'
import type { Outline, OutlineVolume } from '@/types'
import { Sparkles, Save, Plus, Trash2, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { GrowingTextarea } from '@/components/ui/growing-textarea'
import { Card } from '@/components/ui/card'

export default function OutlinePanel({ bookId }: { bookId: number }) {
  const qc = useQueryClient()
  const uid=useAuthStore(s=>s.user?.id)
  const draftKey=`sc-outline-draft-${uid}-${bookId}`
  const [draft]=useState(()=>{try{return JSON.parse(sessionStorage.getItem(draftKey)||'null') as OutlineVolume[]|null}catch{return null}})
  const [volumes, setVolumes] = useState<OutlineVolume[]>(Array.isArray(draft)?draft:(draft as {volumes?:OutlineVolume[]}|null)?.volumes||[])
  const [overview,setOverview]=useState((draft as {overview?:string}|null)?.overview||'')
  const [planningMode,setPlanningMode]=useState<'serial'|'fixed'>((draft as {planning_mode?:'serial'|'fixed'}|null)?.planning_mode||'serial')
  const [error, setError] = useState('')
  const [dirty,setDirty]=useState(!!draft)
  useEffect(()=>{if(dirty)sessionStorage.setItem(draftKey,JSON.stringify({volumes,overview,planning_mode:planningMode}));else sessionStorage.removeItem(draftKey)},[volumes,overview,planningMode,dirty,draftKey])
  const {data:jobs=[]}=useQuery({queryKey:['jobs',bookId],queryFn:async()=>(await api.get<WorkJob[]>('/jobs',{params:{book_id:bookId}})).data,refetchInterval:2000})
  const outlineJob=jobs.find(j=>j.kind==='outline')
  const jobBusy=!!outlineJob&&['queued','running'].includes(outlineJob.status)
  const bookBusy=jobs.some(j=>['queued','running'].includes(j.status))

  const { data: outline, isFetching, error:loadError } = useQuery({
    queryKey: ['outline', bookId],
    refetchInterval: jobBusy ? 2000 : false,
    queryFn: async () => {
      try {
        return (await api.get<Outline>(`/books/${bookId}/outline`)).data
      } catch (e) {
        if ((e as {response?:{status:number}}).response?.status===404) return null
        throw e
      }
    },
  })

  useEffect(() => {
    if (outline && !dirty) {
      setVolumes((outline.content as {volumes?:OutlineVolume[]}).volumes || [])
      setOverview((outline.content as {overview?:string}).overview||'')
      setPlanningMode((outline.content as {planning_mode?:string}).planning_mode==='serial'?'serial':'fixed')
    }
  }, [outline,dirty])
  useEffect(()=>{if(outlineJob?.status==='succeeded')void qc.invalidateQueries({queryKey:['outline',bookId]})},[outlineJob?.id,outlineJob?.status,qc,bookId])
  const generateMutation = useMutation({
    mutationFn:async()=>enqueueJob({book_id:bookId,kind:'outline',planning_mode:planningMode}),
    onSuccess:()=>{setDirty(false);setError('');void qc.invalidateQueries({queryKey:['jobs',bookId]})},
    onError:e=>setError(extractError(e,'任务创建失败')),
  })
  const busy=jobBusy||generateMutation.isPending
  const startGeneration=()=>{
    if((volumes.length>0||dirty)&&!window.confirm('重新生成会替换当前大纲，并需要重新确认；已写正文不会被删除。是否继续？'))return
    generateMutation.mutate()
  }
  const saveMutation = useMutation({
    mutationFn:async()=>(await api.put<Outline>(`/books/${bookId}/outline`,{content:{...outline?.content,overview,volumes,planning_mode:planningMode}})).data,
    onSuccess:o=>{setDirty(false);setError('');qc.setQueryData(['outline',bookId],o);void qc.invalidateQueries({queryKey:['guide-outline',bookId]})},
    onError:e=>setError(extractError(e,'保存失败')),
  })
  const confirmMutation=useMutation({
    mutationFn:async()=>(await api.post<Outline>(`/books/${bookId}/outline/confirm`,{content:outline?.content})).data,
    onSuccess:o=>{setError('');qc.setQueryData(['outline',bookId],o);void qc.invalidateQueries({queryKey:['guide-outline',bookId]})},
    onError:e=>setError(extractError(e,'确认失败')),
  })
  const confirmed=!dirty&&!!(outline?.content as {_review?:unknown}|undefined)?._review

  const updateVolName = (vi: number, name: string) => {
    setDirty(true)
    setVolumes((prev) => prev.map((v, i) => (i === vi ? { ...v, name } : v)))
  }
  const updateChapter = (vi: number, ci: number, field: 'title' | 'summary', value: string) => {
    setDirty(true)
    setVolumes((prev) => prev.map((v, i) =>
      i === vi ? { ...v, chapters: v.chapters.map((c, j) => (j === ci ? { ...c, [field]: value } : c)) } : v
    ))
  }
  const addChapter = (vi: number) => {
    setDirty(true)
    setVolumes((prev) => prev.map((v, i) => {
      if (i !== vi) return v
      const nextNum = (v.chapters[v.chapters.length - 1]?.number ?? 0) + 1
      return { ...v, chapters: [...v.chapters, { number: nextNum, title: `第${nextNum}章 待定`, summary: '' }] }
    }))
  }
  const delChapter = (vi: number, ci: number) => {
    setDirty(true)
    setVolumes((prev) => prev.map((v, i) => (i === vi ? { ...v, chapters: v.chapters.filter((_, j) => j !== ci) } : v)))
  }
  const addVolume = () => {
    setDirty(true)
    setVolumes((prev) => [...prev, { name: `第${prev.length + 1}卷`, chapters: [] }])
  }

  const hasData = volumes.length > 0

  return (
    <div className="h-full flex flex-col bg-background">
      <div className="px-6 py-3 border-b flex items-center gap-2">
        <h2 className="font-bold">故事方向与阶段</h2><select aria-label="规划方式" className="text-xs border rounded px-2 py-1 bg-background" disabled={bookBusy} value={planningMode} onChange={e=>{setPlanningMode(e.target.value as 'serial'|'fixed');setDirty(true)}}><option value="serial">连载 · 逐章规划</option><option value="fixed">定稿 · 全书章纲</option></select>
        <Button size="sm" className="bg-purple-600 hover:bg-purple-700 text-white" onClick={startGeneration} disabled={busy||bookBusy}>
          <Sparkles size={14} /> {busy ? (outlineJob?.status==='queued'?'排队中…':'生成中…') : '生成大纲'}
        </Button>
        {hasData && (
          <Button size="sm" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending||bookBusy}>
            <Save size={14} /> {saveMutation.isPending ? '保存中' : '保存'}
          </Button>
        )}
        <span className="ml-auto text-xs text-muted-foreground">
          {busy ? '后台规划中 · 可切换页面' : isFetching ? '加载中…' : hasData ? `${volumes.length} 卷` : ''}
        </span>
      </div>

      <div className="px-6 py-2 border-b text-xs leading-6 flex flex-wrap items-center gap-3">
        <span>{confirmed?'✓ 当前大纲已确认':dirty?'有未保存修改（本标签页暂存），保存后需要重新确认':'大纲是草稿，请先保存并确认，再规划情节和章节正文'}</span>
        {hasData&&<Button size="sm" variant="outline" disabled={confirmed||dirty||bookBusy||confirmMutation.isPending||saveMutation.isPending} onClick={()=>confirmMutation.mutate()}>{confirmed?'已确认':'确认此版大纲'}</Button>}
        {dirty&&<Button size="sm" variant="ghost" onClick={()=>{if(window.confirm('放弃尚未保存的修改，恢复服务器上的大纲？')){setVolumes((outline?.content as {volumes?:OutlineVolume[]})?.volumes||[]);setOverview((outline?.content as {overview?:string})?.overview||'');setPlanningMode((outline?.content as {planning_mode?:string})?.planning_mode==='serial'?'serial':'fixed');setDirty(false)}}}>放弃本地修改</Button>}
        <span className="text-muted-foreground">角色、场景和物品可提前手动整理。重新生成或保存大纲会重置确认。</span>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {outlineJob?.status==='failed'&&<p role="alert" className="mb-3 text-sm text-destructive">上次大纲任务未完成：{outlineJob.error}。请核对任务与现有内容后重试。</p>}
        {loadError&&<p role="alert">{extractError(loadError,'大纲加载失败，请刷新重试')}</p>}
        {error && (
          <div className="mb-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            {error}
          </div>
        )}
        {!hasData && !busy && (
          <div className="text-center text-muted-foreground py-16">
            <Sparkles size={40} className="mx-auto mb-3 text-muted-foreground/40" />
            <p className="mb-3">点击「生成大纲」，AI 根据书籍设定生成规划草稿；请检查后确认，再推进章节写作</p>
            <Button className="bg-purple-600 hover:bg-purple-700 text-white" onClick={startGeneration} disabled={busy||bookBusy}>
              <Sparkles size={16} /> 立即生成
            </Button>
            <Button className="ml-2" variant="outline" disabled={bookBusy} onClick={addVolume}><Plus size={14}/>手动编写大纲</Button>
          </div>
        )}
        {busy && !hasData && (
          <div className="text-center text-muted-foreground py-16">任务已提交，正在后台规划。切换标签或刷新不会取消；进度和失败原因可在「任务」查看。</div>
        )}
        {hasData && (
          <fieldset disabled={bookBusy} className="outline-document space-y-5 w-full disabled:opacity-60">
            <label className="block text-sm font-medium">故事总纲<GrowingTextarea className="mt-2 font-normal" rows={4} value={overview} placeholder="核心冲突、主角目标、关键转折与结局方向；长连载可标注远期暂定。" onChange={e=>{setOverview(e.target.value);setDirty(true)}}/></label>
            {planningMode==='serial'&&<p className="text-sm text-muted-foreground">只确认故事总纲和近期阶段目标。总章数是估计，后续可随时增加章节；每章情节到创作页单独设计、确认。这里不要求预先列出所有章节。</p>}
            {volumes.map((v, vi) => (
              <Card key={vi} className="p-3 border-none shadow-sm">
                <Input className="font-bold text-lg outline-none w-full bg-transparent border-b border-transparent focus:border-primary px-0 shadow-none"
                  value={v.name} onChange={(e) => updateVolName(vi, e.target.value)} />
                <GrowingTextarea rows={3} aria-label={`第${vi+1}卷阶段目标`} className="mt-3" placeholder="本卷目标、主要转折和阶段收束" value={v.goal||''} onChange={e=>{setDirty(true);setVolumes(prev=>prev.map((vol,i)=>i===vi?{...vol,goal:e.target.value}:vol))}}/>
                <div className="mt-2 space-y-2">
                  {planningMode==='fixed'&&v.chapters.map((c, ci) => (
                    <div key={ci} className="flex gap-2 items-start group">
                      <span className="text-xs text-muted-foreground mt-2 w-6 shrink-0">{c.number}</span>
                      <Input className="flex-1 border-b px-1 py-1 text-sm shadow-none" value={c.title} onChange={(e) => updateChapter(vi, ci, 'title', e.target.value)} />
                      <GrowingTextarea rows={2} aria-label={`第${c.number}章梗概`} className="flex-[2]" value={c.summary} onChange={(e) => updateChapter(vi, ci, 'summary', e.target.value)} placeholder="梗概" />
                      <Button variant="ghost" size="icon" className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 h-7 w-7" title="删除" onClick={() => delChapter(vi, ci)}>
                        <Trash2 size={14} />
                      </Button>
                    </div>
                  ))}
                </div>
                {planningMode==='fixed'&&<Button variant="ghost" size="sm" className="mt-2 text-primary h-7" onClick={() => addChapter(vi)}>
                  <Plus size={12} /> 新增章节
                </Button>}
              </Card>
            ))}
            <Button variant="ghost" className="text-sm text-primary w-full justify-center border-t pt-3 border-dashed rounded-none h-10" onClick={addVolume}>
              <Plus size={14} /> 新增卷
            </Button>
          </fieldset>
        )}
      </div>

      {error && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-destructive text-white text-sm px-4 py-2 rounded-lg shadow z-50 flex items-center gap-2">
          {error}
          <button onClick={() => setError('')}><RotateCcw size={12} /></button>
        </div>
      )}
    </div>
  )
}
