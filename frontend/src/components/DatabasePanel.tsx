import { enqueueJob } from '@/lib/jobs'
import { toast } from 'sonner'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Database, Search, Boxes, Network, RefreshCw, Loader2 } from 'lucide-react'
import api, { extractError } from '@/lib/api'
import type { RagQueryResult, RagStatus } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

type SubTab = 'chunks' | 'entities'

interface Props {
  bookId: number
  onError: (msg: string) => void
}

export default function DatabasePanel({ bookId, onError }: Props) {
  const qc = useQueryClient()
  const [subTab, setSubTab] = useState<SubTab>('chunks')
  const [query, setQuery] = useState('')
  const [queryResult, setQueryResult] = useState<RagQueryResult | null>(null)
  const [topK, setTopK] = useState(5)

  // RAG 入库状态
  const { data: status, isLoading: statusLoading, refetch } = useQuery({
    queryKey: ['rag-status', bookId],
    refetchInterval:5000,
    queryFn: async () => (await api.get<RagStatus>(`/books/${bookId}/rag-status`)).data,
    enabled: !!bookId,
  })

  // 入库单章
  const ingestMutation = useMutation({
    mutationFn: async (chapterId: number) => {
      const chapter=(await api.get(`/chapters/${chapterId}`)).data
      if(!window.confirm(`确认已审阅《${chapter.title}》的当前正文，并将其作为后续章节的故事记忆？修改正文后需要重新更新。`))return
      return enqueueJob({book_id:bookId,chapter_id:chapterId,kind:"index",reviewed_hash:chapter.content_hash})
    },
    onSuccess: (job) => {
      if(!job)return
      toast.success('记忆更新已排队，请在任务中心查看结果')
      qc.invalidateQueries({ queryKey: ['jobs', bookId] })
      qc.invalidateQueries({ queryKey: ['rag-status', bookId] })
      qc.invalidateQueries({ queryKey: ['chapters', bookId] })
    },
    onError: (e) => onError(extractError(e, '入库失败')),
  })

  // 检索
  const queryMutation = useMutation({
    mutationFn: async (q: string) =>
      (await api.post<RagQueryResult>('/rag/query', { book_id: bookId, query: q, top_k: topK })).data,
    onSuccess: (data) => {
      setQueryResult(data)
      if (data.error) onError(data.error)
    },
    onError: (e) => onError(extractError(e, '检索失败')),
  })

  const doQuery = () => {
    const q = query.trim()
    if (!q) return
    queryMutation.mutate(q)
  }

  const ingestedChapters = status?.chapters.filter((c) => c.ingested).length ?? 0
  const totalChapters = status?.chapters.length ?? 0

  return (
    <div className="flex flex-col h-full bg-muted/30">
      {/* 头部：标题 + 统计 */}
      <div className="bg-background border-b px-4 py-3 flex items-center gap-3">
        <Database size={18} className="text-primary" />
        <span className="font-medium">故事记忆</span>
        <span className="text-xs text-muted-foreground">
          已入库 <span className="text-primary font-medium">{ingestedChapters}</span> / {totalChapters} 章
        </span>
        <span className="text-xs text-muted-foreground">
          切片 <span className="text-purple-600 font-medium">{status?.total_chunks ?? 0}</span>
        </span>
        <span className="text-xs text-muted-foreground">
          实体 <span className="text-emerald-600 font-medium">{status?.total_entities ?? 0}</span>
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto h-7 w-7"
          onClick={() => refetch()}
          title="刷新"
        >
          <RefreshCw size={14} className={statusLoading ? 'animate-spin' : ''} />
        </Button>
      </div>

      {/* 双 Tab */}
      <div className="bg-background border-b flex gap-1 px-4">
        <button
          onClick={() => setSubTab('chunks')}
          className={`px-3 py-2 text-sm border-b-2 ${
            subTab === 'chunks' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'
          }`}
        >
          <Boxes size={14} className="inline mr-1" /> 向量切片
        </button>
        <button
          onClick={() => setSubTab('entities')}
          className={`px-3 py-2 text-sm border-b-2 ${
            subTab === 'entities' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'
          }`}
        >
          <Network size={14} className="inline mr-1" /> 实体关系
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {subTab === 'chunks' ? (
          <ChunksTab
            status={status}
            loading={statusLoading}
            query={query}
            setQuery={setQuery}
            topK={topK}
            setTopK={setTopK}
            doQuery={doQuery}
            querying={queryMutation.isPending}
            result={queryResult}
            onIngest={(cid) => ingestMutation.mutate(cid)}
            ingesting={ingestMutation.isPending}
          />
        ) : (
          <EntitiesTab result={queryResult} status={status} />
        )}
      </div>
    </div>
  )
}

// ============ 切片 Tab ============

function ChunksTab({
  status, loading, query, setQuery, topK, setTopK, doQuery, querying, result, onIngest, ingesting,
}: {
  status: RagStatus | undefined
  loading: boolean
  query: string
  setQuery: (s: string) => void
  topK: number
  setTopK: (n: number) => void
  doQuery: () => void
  querying: boolean
  result: RagQueryResult | null
  onIngest: (cid: number) => void
  ingesting: boolean
}) {
  return (
    <div className="space-y-4">
      {/* 检索框 */}
      <Card className="p-3 space-y-2 border-none shadow-sm">
        <div className="flex gap-2 items-end">
          <div className="flex-1 space-y-1">
            <label className="block text-xs text-muted-foreground">语义检索（cosine topK）</label>
            <Input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') doQuery() }}
              placeholder="如：主角第一次见到反派"
            />
          </div>
          <Select value={String(topK)} onValueChange={(v) => setTopK(Number(v ?? '5'))}>
            <SelectTrigger className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="3">K=3</SelectItem>
              <SelectItem value="5">K=5</SelectItem>
              <SelectItem value="10">K=10</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={doQuery} disabled={querying || !query.trim()}>
            {querying ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            检索
          </Button>
        </div>

        {/* 检索结果 */}
        {result && (
          <div className="space-y-2">
            <div className="text-xs text-muted-foreground">
              返回 {result.chunks.length} 条切片 · {result.entities.length} 个实体 · {result.relations.length} 条关系
            </div>
            {result.chunks.map((c, i) => (
              <div key={i} className="border rounded p-2 bg-muted text-xs">
                <div className="flex justify-between text-muted-foreground mb-1">
                  <span>第 {c.chapter_number} 章 · {c.chapter_title || '无标题'} · #{c.chunk_idx}</span>
                  <span className="text-primary">score: {c.score}</span>
                </div>
                <div className="text-foreground whitespace-pre-wrap line-clamp-3">{c.text}</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* 章节入库状态 */}
      <Card className="border-none shadow-sm">
        <div className="px-3 py-2 border-b text-sm font-medium">章节入库状态</div>
        {loading ? (
          <div className="p-4 text-center text-muted-foreground text-sm">
            <Loader2 size={16} className="animate-spin inline mr-1" /> 加载中…
          </div>
        ) : status?.chapters.length ? (
          <div className="divide-y">
            {status.chapters.map((c) => (
              <div key={c.chapter_id} className="px-3 py-2 flex items-center gap-2 text-sm">
                <span className={`w-2 h-2 rounded-full ${c.ingested ? 'bg-green-500' : c.has_content ? 'bg-amber-400' : 'bg-muted-foreground/40'}`} title={c.ingested ? '已入库' : c.has_content ? '有内容未入库' : '无内容'} />
                <span className="text-muted-foreground w-10 shrink-0">第{c.number}章</span>
                <span className="flex-1 truncate">{c.title}</span>
                <span className="text-xs text-muted-foreground">{c.chunk_count}切片 / {c.entity_count}实体</span>
                {c.has_content && !c.ingested && (
                  <Button size="sm" className="h-6 text-xs bg-purple-600 hover:bg-purple-700 text-white"
                    onClick={() => onIngest(c.chapter_id)}
                    disabled={ingesting}>
                    确认并入库
                  </Button>
                )}
                {c.ingested && (
                  <Button size="sm" variant="outline" className="h-6 text-xs text-muted-foreground"
                    onClick={() => onIngest(c.chapter_id)}
                    disabled={ingesting}
                    title="重新入库（覆盖旧数据）">
                    重整
                  </Button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 text-center text-muted-foreground text-sm">尚无章节</div>
        )}
      </Card>
    </div>
  )
}

// ============ 实体关系 Tab ============

function EntitiesTab({ result, status }: { result: RagQueryResult | null; status: RagStatus | undefined }) {
  // 若没有检索结果，从 status 中提取实体列表占位
  const entities = result?.entities ?? []
  const relations = result?.relations ?? []

  return (
    <div className="space-y-4">
      <div className="bg-primary/5 border border-primary/20 rounded p-2 text-xs text-primary">
        提示：在「向量切片」Tab 中输入查询词后切换到此处查看相关实体关系图。
      </div>

      {/* 实体列表 */}
      <Card className="border-none shadow-sm">
        <div className="px-3 py-2 border-b text-sm font-medium">
          相关实体 ({entities.length})
        </div>
        {entities.length ? (
          <div className="divide-y">
            {entities.map((e) => (
              <div key={e.id} className="px-3 py-2 text-sm">
                <div className="flex items-center gap-2">
                  <EntityTypeBadge type={e.type} />
                  <span className="font-medium">{e.name}</span>
                </div>
                {e.description && <div className="mt-1 text-xs text-muted-foreground">{e.description}</div>}
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 text-center text-muted-foreground text-sm">无实体数据，请先入库并检索</div>
        )}
      </Card>

      {/* 关系列表 */}
      <Card className="border-none shadow-sm">
        <div className="px-3 py-2 border-b text-sm font-medium">
          关系路径 ({relations.length})
        </div>
        {relations.length ? (
          <div className="divide-y">
            {relations.map((r, i) => (
              <div key={i} className="px-3 py-2 text-sm flex items-center gap-2">
                <span className="text-primary">{r.from}</span>
                <span className="text-xs px-2 py-0.5 bg-amber-100 text-amber-800 rounded">{r.type}</span>
                <span className="text-primary">{r.to}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 text-center text-muted-foreground text-sm">无关系数据</div>
        )}
      </Card>

      {/* 章节入库摘要 */}
      {status && (
        <Card className="border-none shadow-sm">
          <div className="px-3 py-2 border-b text-sm font-medium">章节实体统计</div>
          <div className="divide-y">
            {status.chapters.map((c) => (
              <div key={c.chapter_id} className="px-3 py-1.5 text-xs flex justify-between">
                <span className="truncate">第{c.number}章 · {c.title}</span>
                <span className="text-muted-foreground">{c.entity_count} 实体</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

function EntityTypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    character: 'bg-red-100 text-red-700',
    scene: 'bg-green-100 text-green-700',
    item: 'bg-yellow-100 text-yellow-700',
    plot: 'bg-purple-100 text-purple-700',
    hook: 'bg-pink-100 text-pink-700',
  }
  const cls = colors[type] || 'bg-gray-100 text-gray-700'
  const labels: Record<string, string> = {
    character: '人物', scene: '场景', item: '物品', plot: '情节', hook: '伏笔',
  }
  return <span className={`text-xs px-2 py-0.5 rounded ${cls}`}>{labels[type] || type}</span>
}
