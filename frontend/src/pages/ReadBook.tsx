import { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getBookForRead, listChaptersForRead, getChapterForRead } from '@/features/reading/api'
import type { ReadBook as ReadBookType, ReadChapter, ReadChapterDetail, ReadingConfigData } from '@/types'
import {
  Settings,
  Plus,
  Minus,
  Sun,
  Moon,
  Eye,
  Book as BookIcon,
  ChevronRight,
  ChevronLeft,
  ArrowLeft,
} from 'lucide-react'

interface ReadBookProps {
  bookId: number
}

const STORAGE_KEY = (bid: number) => `reader-config-${bid}`

const DEFAULT_CONFIG: ReadingConfigData = {
  font_size: 18,
  font_family: 'serif',
  line_height: 1.8,
  margin: 'medium',
  background: '#ffffff',
  text_color: '#1a1a1a',
  brightness: 1.0,
}

// 预设场景：日间 / 夜间 / 护眼 / 沉浸 / 户外
const SCENES: { name: string; bg: string; color: string; label: string }[] = [
  { name: '日间', bg: '#ffffff', color: '#1a1a1a', label: '日间' },
  { name: '夜间', bg: '#1a1a1a', color: '#c8c8c8', label: '夜间' },
  { name: '护眼', bg: '#c7edcc', color: '#1a3a1a', label: '护眼' },
  { name: '沉浸', bg: '#2b2b2b', color: '#e0e0e0', label: '沉浸' },
  { name: '户外', bg: '#fff8dc', color: '#3a2a00', label: '户外' },
]

const MARGIN_MAP: Record<string, string> = {
  narrow: '0 auto',
  medium: '0 auto',
  wide: '0 auto',
}

function getContainerMaxWidth(margin: string): string {
  if (margin === 'narrow') return '640px'
  if (margin === 'wide') return '1100px'
  return '820px'
}

function clampNumber(v: number, min: number, max: number): number {
  if (Number.isNaN(v)) return min
  return Math.max(min, Math.min(max, v))
}

function loadConfig(bid: number): ReadingConfigData {
  try {
    const raw = localStorage.getItem(STORAGE_KEY(bid))
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ReadingConfigData>
      return {
        font_size: clampNumber(parsed.font_size ?? DEFAULT_CONFIG.font_size, 14, 24),
        font_family: parsed.font_family || DEFAULT_CONFIG.font_family,
        line_height: clampNumber(parsed.line_height ?? DEFAULT_CONFIG.line_height, 1.4, 2.2),
        margin: parsed.margin || DEFAULT_CONFIG.margin,
        background: parsed.background || DEFAULT_CONFIG.background,
        text_color: parsed.text_color || DEFAULT_CONFIG.text_color,
        brightness: clampNumber(parsed.brightness ?? DEFAULT_CONFIG.brightness, 0.3, 1.0),
      }
    }
  } catch {
    // ignore
  }
  return { ...DEFAULT_CONFIG }
}

function saveConfig(bid: number, cfg: ReadingConfigData) {
  try {
    localStorage.setItem(STORAGE_KEY(bid), JSON.stringify(cfg))
  } catch {
    // ignore
  }
}

export default function ReadBook({ bookId }: ReadBookProps) {
  const bid = bookId
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null)
  const [config, setConfig] = useState<ReadingConfigData>(() => loadConfig(bid))
  const [panelOpen, setPanelOpen] = useState(false)

  // 数据加载（公开 API）
  const { data: book } = useQuery<ReadBookType>({
    queryKey: ['read-book', bid],
    queryFn: () => getBookForRead(bid),
    enabled: !!bid && !Number.isNaN(bid),
  })
  const { data: chapters } = useQuery<ReadChapter[]>({
    queryKey: ['read-chapters', bid],
    queryFn: () => listChaptersForRead(bid),
    enabled: !!bid && !Number.isNaN(bid),
  })
  const { data: chapterDetail, isFetching: chapterLoading } = useQuery<ReadChapterDetail>({
    queryKey: ['read-chapter', bid, selectedChapterId],
    queryFn: () => getChapterForRead(bid, selectedChapterId as number),
    enabled: !!bid && !!selectedChapterId,
  })

  // 默认选中第一章
  useEffect(() => {
    if (chapters && chapters.length && selectedChapterId === null) {
      setSelectedChapterId(chapters[0].id)
    }
  }, [chapters, selectedChapterId])

  // 配置变更时持久化
  useEffect(() => {
    saveConfig(bid, config)
  }, [bid, config])

  // 阅读区样式
  const contentStyle = useMemo<React.CSSProperties>(() => ({
    fontSize: `${config.font_size}px`,
    fontFamily: config.font_family === 'serif'
      ? 'Georgia, "Songti SC", "SimSun", serif'
      : '"Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif',
    lineHeight: config.line_height,
    color: config.text_color,
    maxWidth: getContainerMaxWidth(config.margin),
    margin: MARGIN_MAP[config.margin],
    padding: '1.5rem 1rem',
    filter: `brightness(${config.brightness})`,
    background: config.background,
    minHeight: '100%',
  }), [config])

  // 配置更新辅助
  const patch = (delta: Partial<ReadingConfigData>) => setConfig((c) => ({ ...c, ...delta }))

  // 上一章 / 下一章
  const { prevId, nextId } = useMemo(() => {
    if (!chapters || !selectedChapterId) return { prevId: null, nextId: null }
    const idx = chapters.findIndex((c) => c.id === selectedChapterId)
    return {
      prevId: idx > 0 ? chapters[idx - 1].id : null,
      nextId: idx >= 0 && idx < chapters.length - 1 ? chapters[idx + 1].id : null,
    }
  }, [chapters, selectedChapterId])

  // 预设场景切换
  const applyScene = (scene: string) => {
    const target = SCENES.find((s) => s.name === scene)
    if (!target) return
    patch({ background: target.bg, text_color: target.color })
  }

  if (!bid || Number.isNaN(bid)) {
    return <div className="p-8 text-muted-foreground">无效书籍</div>
  }

  return (
    <div className="flex h-full bg-muted/30">
      {/* 左：目录树（只读） */}
      <div className="w-64 border-r flex flex-col bg-background shrink-0">
        <div className="px-3 py-2 border-b flex items-center justify-between">
          <span className="text-sm font-medium flex items-center gap-1">
            <BookIcon size={14} /> 目录
          </span>
          {book && <span className="text-xs text-muted-foreground truncate ml-2">{book.title}</span>}
        </div>
        <div className="flex-1 overflow-y-auto text-sm">
          {chapters?.map((c) => (
            <ChapterRow
              key={c.id}
              chapter={c}
              active={c.id === selectedChapterId}
              onClick={() => setSelectedChapterId(c.id)}
            />
          ))}
          {chapters?.length === 0 && (
            <div className="px-3 py-4 text-center text-muted-foreground text-xs">暂无章节</div>
          )}
        </div>
        <div className="px-3 py-2 border-t">
          <Link
            to="/community"
            className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1"
          >
            <ArrowLeft size={12} /> 返回社区
          </Link>
        </div>
      </div>

      {/* 右：阅读区 + 顶部工具栏 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 顶部工具栏（只读，无保存/导入/模板按钮） */}
        <div className="bg-white border-b px-4 py-2 flex items-center gap-2 flex-wrap shrink-0">
          <button
            onClick={() => patch({ font_size: clampNumber(config.font_size - 1, 14, 24) })}
            className="p-1.5 rounded hover:bg-gray-100 text-gray-700"
            title="字号减小"
          >
            <Minus size={16} />
          </button>
          <span className="text-xs text-gray-500 w-12 text-center">{config.font_size}px</span>
          <button
            onClick={() => patch({ font_size: clampNumber(config.font_size + 1, 14, 24) })}
            className="p-1.5 rounded hover:bg-gray-100 text-gray-700"
            title="字号增大"
          >
            <Plus size={16} />
          </button>

          <div className="w-px h-5 bg-gray-200 mx-1" />

          <button
            onClick={() => patch({ font_family: config.font_family === 'serif' ? 'sans' : 'serif' })}
            className="px-2 py-1 text-xs rounded hover:bg-gray-100 text-gray-700 border"
            title="切换字体"
          >
            {config.font_family === 'serif' ? '衬线' : '无衬线'}
          </button>

          <button
            onClick={() => patch({ line_height: clampNumber(Math.round((config.line_height - 0.1) * 10) / 10, 1.4, 2.2) })}
            className="p-1.5 rounded hover:bg-gray-100 text-gray-700"
            title="行距减小"
          >
            <span className="text-xs leading-none">⇕-</span>
          </button>
          <span className="text-xs text-gray-500 w-8 text-center">{config.line_height.toFixed(1)}</span>
          <button
            onClick={() => patch({ line_height: clampNumber(Math.round((config.line_height + 0.1) * 10) / 10, 1.4, 2.2) })}
            className="p-1.5 rounded hover:bg-gray-100 text-gray-700"
            title="行距增大"
          >
            <span className="text-xs leading-none">⇕+</span>
          </button>

          <div className="w-px h-5 bg-gray-200 mx-1" />

          {/* 预设场景按钮 */}
          {SCENES.map((s) => (
            <button
              key={s.name}
              onClick={() => applyScene(s.name)}
              className="px-2 py-1 text-xs rounded hover:bg-gray-100 text-gray-700 border flex items-center gap-1"
              title={`切换到${s.label}模式`}
            >
              {s.name === '日间' && <Sun size={12} />}
              {s.name === '夜间' && <Moon size={12} />}
              {s.name === '护眼' && <Eye size={12} />}
              {s.name}
            </button>
          ))}

          <div className="w-px h-5 bg-gray-200 mx-1" />

          {/* 亮度调节 */}
          <Sun size={14} className="text-gray-500" />
          <input
            type="range"
            min={0.3}
            max={1.0}
            step={0.05}
            value={config.brightness}
            onChange={(e) => patch({ brightness: clampNumber(parseFloat(e.target.value), 0.3, 1.0) })}
            className="w-24"
            title="亮度"
          />
          <span className="text-xs text-gray-500 w-8 text-center">{Math.round(config.brightness * 100)}%</span>

          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={() => setPanelOpen((v) => !v)}
              className={`p-1.5 rounded hover:bg-muted ${panelOpen ? 'bg-primary/10 text-primary' : 'text-muted-foreground'}`}
              title="展开配置面板"
            >
              <Settings size={16} />
            </button>
          </div>
        </div>

        {/* 配置面板（可展开/收起） */}
        {panelOpen && (
          <div className="bg-white border-b px-4 py-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs shrink-0">
            <ConfigField label="字号 (14-24)">
              <input
                type="number"
                min={14}
                max={24}
                value={config.font_size}
                onChange={(e) => patch({ font_size: clampNumber(parseInt(e.target.value, 10), 14, 24) })}
                className="w-full border rounded px-2 py-1"
              />
            </ConfigField>
            <ConfigField label="字体">
              <select
                value={config.font_family}
                onChange={(e) => patch({ font_family: e.target.value })}
                className="w-full border rounded px-2 py-1 bg-white"
              >
                <option value="serif">衬线</option>
                <option value="sans">无衬线</option>
              </select>
            </ConfigField>
            <ConfigField label="行距 (1.4-2.2)">
              <input
                type="number"
                step={0.1}
                min={1.4}
                max={2.2}
                value={config.line_height}
                onChange={(e) => patch({ line_height: clampNumber(parseFloat(e.target.value), 1.4, 2.2) })}
                className="w-full border rounded px-2 py-1"
              />
            </ConfigField>
            <ConfigField label="页边距">
              <select
                value={config.margin}
                onChange={(e) => patch({ margin: e.target.value })}
                className="w-full border rounded px-2 py-1 bg-white"
              >
                <option value="narrow">窄</option>
                <option value="medium">中</option>
                <option value="wide">宽</option>
              </select>
            </ConfigField>
            <ConfigField label="背景色">
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={config.background}
                  onChange={(e) => patch({ background: e.target.value })}
                  className="w-8 h-8 rounded border"
                />
                <input
                  type="text"
                  value={config.background}
                  onChange={(e) => patch({ background: e.target.value })}
                  className="flex-1 border rounded px-2 py-1 font-mono"
                />
              </div>
            </ConfigField>
            <ConfigField label="文字颜色">
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={config.text_color}
                  onChange={(e) => patch({ text_color: e.target.value })}
                  className="w-8 h-8 rounded border"
                />
                <input
                  type="text"
                  value={config.text_color}
                  onChange={(e) => patch({ text_color: e.target.value })}
                  className="flex-1 border rounded px-2 py-1 font-mono"
                />
              </div>
            </ConfigField>
            <ConfigField label="亮度 (0.3-1.0)">
              <input
                type="range"
                min={0.3}
                max={1.0}
                step={0.05}
                value={config.brightness}
                onChange={(e) => patch({ brightness: clampNumber(parseFloat(e.target.value), 0.3, 1.0) })}
                className="w-full"
              />
            </ConfigField>
            <ConfigField label="恢复默认">
              <button
                onClick={() => setConfig({ ...DEFAULT_CONFIG })}
                className="px-3 py-1 border rounded hover:bg-gray-100 w-full"
              >
                重置
              </button>
            </ConfigField>
          </div>
        )}

        {/* 阅读区 */}
        <div className="flex-1 overflow-y-auto" style={{ background: config.background }}>
          {!selectedChapterId ? (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm">
              请选择左侧章节开始阅读
            </div>
          ) : chapterLoading && !chapterDetail ? (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm">加载中…</div>
          ) : chapterDetail ? (
            <article style={contentStyle}>
              <h1 className="text-2xl font-bold mb-4 text-center" style={{ color: config.text_color }}>
                {chapterDetail.title}
              </h1>
              <div
                className="reader-content"
                // 章节内容是富文本 HTML（公开只读）
                dangerouslySetInnerHTML={{ __html: chapterDetail.content || '<p class="text-gray-400">本章暂无内容</p>' }}
              />
              {/* 上一章 / 下一章 */}
              <div className="flex items-center justify-between mt-8 pt-4 border-t" style={{ borderColor: 'rgba(128,128,128,0.2)' }}>
                <button
                  onClick={() => prevId && setSelectedChapterId(prevId)}
                  disabled={!prevId}
                  className="px-3 py-1.5 text-sm rounded border disabled:opacity-40 hover:bg-black/5 flex items-center gap-1"
                  style={{ color: config.text_color }}
                >
                  <ChevronLeft size={14} /> 上一章
                </button>
                <span className="text-xs" style={{ color: config.text_color }}>
                  第 {chapterDetail.number} 章 · {chapterDetail.word_count} 字
                </span>
                <button
                  onClick={() => nextId && setSelectedChapterId(nextId)}
                  disabled={!nextId}
                  className="px-3 py-1.5 text-sm rounded border disabled:opacity-40 hover:bg-black/5 flex items-center gap-1"
                  style={{ color: config.text_color }}
                >
                  下一章 <ChevronRight size={14} />
                </button>
              </div>
            </article>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function ChapterRow({ chapter, active, onClick }: { chapter: ReadChapter; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-1.5 flex items-center justify-between hover:bg-primary/10 ${
        active ? 'bg-primary/10 text-primary' : 'text-foreground'
      }`}
    >
      <span className="truncate">{chapter.title}</span>
      <span className="text-[10px] text-muted-foreground ml-1 shrink-0">{chapter.word_count}</span>
    </button>
  )
}

function ConfigField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[11px] text-muted-foreground mb-1">{label}</label>
      {children}
    </div>
  )
}

