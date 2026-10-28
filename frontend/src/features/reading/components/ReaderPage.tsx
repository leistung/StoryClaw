import { useState, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/http";
import {
  listReadingConfigs,
  createReadingConfig,
  exportReadingConfig,
} from "@/features/reading/api";
import type {
  Book,
  Chapter,
  ChapterDetail,
  Volume,
  ReadingConfig,
  ReadingConfigData,
} from "@/types";
import {
  Settings,
  Plus,
  Minus,
  Sun,
  Moon,
  Eye,
  Download,
  Upload,
  Save,
  Book as BookIcon,
  ChevronRight,
  X,
} from "lucide-react";

interface ReaderPageProps {
  bid: number;
}

const STORAGE_KEY = (bid: number) => `reader-config-${bid}`;

const DEFAULT_CONFIG: ReadingConfigData = {
  font_size: 18,
  font_family: "serif",
  line_height: 1.8,
  margin: "medium",
  background: "#ffffff",
  text_color: "#1a1a1a",
  brightness: 1.0,
};

// 预设场景：日间 / 夜间 / 护眼 / 沉浸 / 户外
const SCENES: { name: string; bg: string; color: string; label: string }[] = [
  { name: "日间", bg: "#ffffff", color: "#1a1a1a", label: "日间" },
  { name: "夜间", bg: "#1a1a1a", color: "#c8c8c8", label: "夜间" },
  { name: "护眼", bg: "#c7edcc", color: "#1a3a1a", label: "护眼" },
  { name: "沉浸", bg: "#2b2b2b", color: "#e0e0e0", label: "沉浸" },
  { name: "户外", bg: "#fff8dc", color: "#3a2a00", label: "户外" },
];

const MARGIN_MAP: Record<string, string> = {
  narrow: "0 auto",
  medium: "0 auto",
  wide: "0 auto",
};

function getContainerMaxWidth(margin: string): string {
  if (margin === "narrow") return "640px";
  if (margin === "wide") return "1100px";
  return "820px";
}

function clampNumber(v: number, min: number, max: number): number {
  if (Number.isNaN(v)) return min;
  return Math.max(min, Math.min(max, v));
}

function loadConfig(bid: number): ReadingConfigData {
  try {
    const raw = localStorage.getItem(STORAGE_KEY(bid));
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ReadingConfigData>;
      return {
        font_size: clampNumber(
          parsed.font_size ?? DEFAULT_CONFIG.font_size,
          14,
          24,
        ),
        font_family: parsed.font_family || DEFAULT_CONFIG.font_family,
        line_height: clampNumber(
          parsed.line_height ?? DEFAULT_CONFIG.line_height,
          1.4,
          2.2,
        ),
        margin: parsed.margin || DEFAULT_CONFIG.margin,
        background: parsed.background || DEFAULT_CONFIG.background,
        text_color: parsed.text_color || DEFAULT_CONFIG.text_color,
        brightness: clampNumber(
          parsed.brightness ?? DEFAULT_CONFIG.brightness,
          0.3,
          1.0,
        ),
      };
    }
  } catch {
    // ignore
  }
  return { ...DEFAULT_CONFIG };
}

function saveConfig(bid: number, cfg: ReadingConfigData) {
  try {
    localStorage.setItem(STORAGE_KEY(bid), JSON.stringify(cfg));
  } catch {
    // ignore
  }
}

export default function ReaderPage({ bid }: ReaderPageProps) {
  const qc = useQueryClient();
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(
    null,
  );
  const [config, setConfig] = useState<ReadingConfigData>(() =>
    loadConfig(bid),
  );
  const [panelOpen, setPanelOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [error, setError] = useState("");

  // 数据加载
  const { data: book } = useQuery({
    queryKey: ["book", bid],
    queryFn: async () => (await api.get<Book>(`/books/${bid}`)).data,
    enabled: !!bid,
  });
  const { data: chapters } = useQuery({
    queryKey: ["chapters", bid],
    queryFn: async () =>
      (await api.get<Chapter[]>(`/chapters/books/${bid}`)).data,
    enabled: !!bid,
  });
  const { data: volumes } = useQuery({
    queryKey: ["volumes", bid],
    queryFn: async () =>
      (await api.get<Volume[]>(`/books/${bid}/volumes`)).data,
    enabled: !!bid,
  });
  const { data: chapterDetail, isFetching: chapterLoading } = useQuery({
    queryKey: ["chapter", selectedChapterId],
    queryFn: async () =>
      (await api.get<ChapterDetail>(`/chapters/${selectedChapterId}`)).data,
    enabled: !!selectedChapterId,
  });

  const {
    data: templatesData,
    refetch: refetchTemplates,
    isFetching: templatesLoading,
  } = useQuery({
    queryKey: ["reading-configs"],
    queryFn: () => listReadingConfigs(),
    enabled: showTemplates,
  });

  // 默认选中第一章
  useEffect(() => {
    if (chapters && chapters.length && selectedChapterId === null) {
      setSelectedChapterId(chapters[0].id);
    }
  }, [chapters, selectedChapterId]);

  // 配置变更时持久化
  useEffect(() => {
    saveConfig(bid, config);
  }, [bid, config]);

  // 阅读区样式
  const contentStyle = useMemo<React.CSSProperties>(
    () => ({
      fontSize: `${config.font_size}px`,
      fontFamily:
        config.font_family === "serif"
          ? 'Georgia, "Songti SC", "SimSun", serif'
          : '"Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif',
      lineHeight: config.line_height,
      color: config.text_color,
      maxWidth: getContainerMaxWidth(config.margin),
      margin: MARGIN_MAP[config.margin],
      padding: "1.5rem 1rem",
      filter: `brightness(${config.brightness})`,
      background: config.background,
      minHeight: "100%",
    }),
    [config],
  );

  // 配置更新辅助
  const patch = (delta: Partial<ReadingConfigData>) =>
    setConfig((c) => ({ ...c, ...delta }));

  // 上一章 / 下一章
  const { prevId, nextId } = useMemo(() => {
    if (!chapters || !selectedChapterId) return { prevId: null, nextId: null };
    const idx = chapters.findIndex((c) => c.id === selectedChapterId);
    return {
      prevId: idx > 0 ? chapters[idx - 1].id : null,
      nextId:
        idx >= 0 && idx < chapters.length - 1 ? chapters[idx + 1].id : null,
    };
  }, [chapters, selectedChapterId]);

  // 预设场景切换
  const applyScene = (scene: string) => {
    const target = SCENES.find((s) => s.name === scene);
    if (!target) return;
    patch({ background: target.bg, text_color: target.color });
  };

  // 导出：下载当前配置为 JSON
  const exportConfig = () => {
    try {
      const blob = new Blob([JSON.stringify(config, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `reader-config-${bid}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setError("");
    } catch {
      setError("导出失败");
    }
  };

  // 导入：粘贴 JSON 文本并应用
  const applyImport = () => {
    try {
      const parsed = JSON.parse(importText) as Partial<ReadingConfigData>;
      patch({
        font_size: clampNumber(parsed.font_size ?? config.font_size, 14, 24),
        font_family: parsed.font_family || config.font_family,
        line_height: clampNumber(
          parsed.line_height ?? config.line_height,
          1.4,
          2.2,
        ),
        margin: parsed.margin || config.margin,
        background: parsed.background || config.background,
        text_color: parsed.text_color || config.text_color,
        brightness: clampNumber(
          parsed.brightness ?? config.brightness,
          0.3,
          1.0,
        ),
      });
      setShowImport(false);
      setImportText("");
      setError("");
    } catch {
      setError("JSON 解析失败");
    }
  };

  // 模板保存
  const saveMut = useMutation({
    mutationFn: () =>
      createReadingConfig({
        name: templateName || `模板 ${new Date().toLocaleString()}`,
        scene: "custom",
        config_json: config,
        book_id: bid,
        is_default: false,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reading-configs"] });
      setTemplateName("");
      setError("模板已保存");
    },
    onError: () => setError("保存模板失败"),
  });

  // 应用模板
  const applyTemplate = (tpl: ReadingConfig) => {
    patch(tpl.config_json);
    setShowTemplates(false);
    setError("");
  };

  // 导出远端模板（调用 /export）
  const exportRemote = async (rcid: number) => {
    try {
      const data = await exportReadingConfig(rcid);
      const blob = new Blob([JSON.stringify(data.config_json, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${data.name || "reading-config"}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError("导出远端模板失败");
    }
  };

  if (!bid) return <div className="p-8 text-muted-foreground">无效书籍</div>;

  const chaptersByVol = (volId: number | null) =>
    chapters?.filter((c) => c.volume_id === volId) ?? [];

  return (
    <div className="flex h-full bg-muted/30">
      {/* 左：目录树 */}
      <div className="w-64 border-r flex flex-col bg-background shrink-0">
        <div className="px-3 py-2 border-b flex items-center justify-between">
          <span className="text-sm font-medium flex items-center gap-1">
            <BookIcon size={14} /> 目录
          </span>
          {book && (
            <span className="text-xs text-muted-foreground truncate ml-2">
              {book.title}
            </span>
          )}
        </div>
        <div className="flex-1 overflow-y-auto text-sm">
          {volumes?.length
            ? volumes.map((v) => (
                <div key={v.id}>
                  <div className="px-3 py-1.5 text-xs text-muted-foreground font-medium bg-muted/30">
                    {v.name}
                  </div>
                  {chaptersByVol(v.id).map((c) => (
                    <ChapterRow
                      key={c.id}
                      chapter={c}
                      active={c.id === selectedChapterId}
                      onClick={() => setSelectedChapterId(c.id)}
                    />
                  ))}
                </div>
              ))
            : chapters?.map((c) => (
                <ChapterRow
                  key={c.id}
                  chapter={c}
                  active={c.id === selectedChapterId}
                  onClick={() => setSelectedChapterId(c.id)}
                />
              ))}
          {volumes?.length ? (
            <>
              {chaptersByVol(null).length > 0 && (
                <div className="px-3 py-1.5 text-xs text-muted-foreground font-medium bg-muted/30">
                  未分卷
                </div>
              )}
              {chaptersByVol(null).map((c) => (
                <ChapterRow
                  key={c.id}
                  chapter={c}
                  active={c.id === selectedChapterId}
                  onClick={() => setSelectedChapterId(c.id)}
                />
              ))}
            </>
          ) : null}
          {chapters?.length === 0 && (
            <div className="px-3 py-4 text-center text-muted-foreground text-xs">
              暂无章节
            </div>
          )}
        </div>
      </div>

      {/* 右：阅读区 + 顶部工具栏 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 顶部阅读配置工具栏 */}
        <div className="bg-background border-b px-4 py-2 flex items-center gap-2 flex-wrap shrink-0">
          <button
            onClick={() =>
              patch({ font_size: clampNumber(config.font_size - 1, 14, 24) })
            }
            className="p-1.5 rounded hover:bg-muted text-muted-foreground"
            title="字号减小"
          >
            <Minus size={16} />
          </button>
          <span className="text-xs text-muted-foreground w-12 text-center">
            {config.font_size}px
          </span>
          <button
            onClick={() =>
              patch({ font_size: clampNumber(config.font_size + 1, 14, 24) })
            }
            className="p-1.5 rounded hover:bg-muted text-muted-foreground"
            title="字号增大"
          >
            <Plus size={16} />
          </button>

          <div className="w-px h-5 bg-muted mx-1" />

          <button
            onClick={() =>
              patch({
                font_family: config.font_family === "serif" ? "sans" : "serif",
              })
            }
            className="px-2 py-1 text-xs rounded hover:bg-muted text-muted-foreground border"
            title="切换字体"
          >
            {config.font_family === "serif" ? "衬线" : "无衬线"}
          </button>

          <button
            onClick={() =>
              patch({
                line_height: clampNumber(
                  Math.round((config.line_height - 0.1) * 10) / 10,
                  1.4,
                  2.2,
                ),
              })
            }
            className="p-1.5 rounded hover:bg-muted text-muted-foreground"
            title="行距减小"
          >
            <span className="text-xs leading-none">⇕-</span>
          </button>
          <span className="text-xs text-muted-foreground w-8 text-center">
            {config.line_height.toFixed(1)}
          </span>
          <button
            onClick={() =>
              patch({
                line_height: clampNumber(
                  Math.round((config.line_height + 0.1) * 10) / 10,
                  1.4,
                  2.2,
                ),
              })
            }
            className="p-1.5 rounded hover:bg-muted text-muted-foreground"
            title="行距增大"
          >
            <span className="text-xs leading-none">⇕+</span>
          </button>

          <div className="w-px h-5 bg-muted mx-1" />

          {/* 预设场景按钮 */}
          {SCENES.map((s) => (
            <button
              key={s.name}
              onClick={() => applyScene(s.name)}
              className="px-2 py-1 text-xs rounded hover:bg-muted text-muted-foreground border flex items-center gap-1"
              title={`切换到${s.label}模式`}
            >
              {s.name === "日间" && <Sun size={12} />}
              {s.name === "夜间" && <Moon size={12} />}
              {s.name === "护眼" && <Eye size={12} />}
              {s.name}
            </button>
          ))}

          <div className="w-px h-5 bg-muted mx-1" />

          {/* 亮度调节 */}
          <Sun size={14} className="text-muted-foreground" />
          <input
            type="range"
            min={0.3}
            max={1.0}
            step={0.05}
            value={config.brightness}
            onChange={(e) =>
              patch({
                brightness: clampNumber(parseFloat(e.target.value), 0.3, 1.0),
              })
            }
            className="w-24"
            title="亮度"
          />
          <span className="text-xs text-muted-foreground w-8 text-center">
            {Math.round(config.brightness * 100)}%
          </span>

          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={() => setShowImport(true)}
              className="p-1.5 rounded hover:bg-muted text-muted-foreground"
              title="导入配置 JSON"
            >
              <Upload size={16} />
            </button>
            <button
              onClick={exportConfig}
              className="p-1.5 rounded hover:bg-muted text-muted-foreground"
              title="导出当前配置为 JSON"
            >
              <Download size={16} />
            </button>
            <button
              onClick={() => {
                setShowTemplates((v) => !v);
                if (!showTemplates) void refetchTemplates();
              }}
              className="p-1.5 rounded hover:bg-muted text-muted-foreground"
              title="模板保存/加载"
            >
              <Save size={16} />
            </button>
            <button
              onClick={() => setPanelOpen((v) => !v)}
              className={`p-1.5 rounded hover:bg-muted ${panelOpen ? "bg-primary/10 text-primary" : "text-muted-foreground"}`}
              title="展开配置面板"
            >
              <Settings size={16} />
            </button>
          </div>
        </div>

        {/* 配置面板（可展开/收起） */}
        {panelOpen && (
          <div className="bg-background border-b px-4 py-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs shrink-0">
            <ConfigField label="字号 (14-24)">
              <input
                type="number"
                min={14}
                max={24}
                value={config.font_size}
                onChange={(e) =>
                  patch({
                    font_size: clampNumber(
                      parseInt(e.target.value, 10),
                      14,
                      24,
                    ),
                  })
                }
                className="w-full border rounded px-2 py-1"
              />
            </ConfigField>
            <ConfigField label="字体">
              <select
                value={config.font_family}
                onChange={(e) => patch({ font_family: e.target.value })}
                className="w-full border rounded px-2 py-1 bg-background"
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
                onChange={(e) =>
                  patch({
                    line_height: clampNumber(
                      parseFloat(e.target.value),
                      1.4,
                      2.2,
                    ),
                  })
                }
                className="w-full border rounded px-2 py-1"
              />
            </ConfigField>
            <ConfigField label="页边距">
              <select
                value={config.margin}
                onChange={(e) => patch({ margin: e.target.value })}
                className="w-full border rounded px-2 py-1 bg-background"
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
                onChange={(e) =>
                  patch({
                    brightness: clampNumber(
                      parseFloat(e.target.value),
                      0.3,
                      1.0,
                    ),
                  })
                }
                className="w-full"
              />
            </ConfigField>
            <ConfigField label="恢复默认">
              <button
                onClick={() => setConfig({ ...DEFAULT_CONFIG })}
                className="px-3 py-1 border rounded hover:bg-muted w-full"
              >
                重置
              </button>
            </ConfigField>
          </div>
        )}

        {/* 模板保存/加载面板 */}
        {showTemplates && (
          <div className="bg-background border-b px-4 py-3 shrink-0">
            <div className="flex items-center gap-2 mb-2">
              <input
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
                placeholder="模板名称"
                className="flex-1 border rounded px-2 py-1 text-sm"
              />
              <button
                onClick={() => saveMut.mutate()}
                disabled={saveMut.isPending}
                className="px-3 py-1 text-sm bg-primary text-white rounded hover:bg-primary/90 disabled:opacity-50 flex items-center gap-1"
              >
                <Save size={14} />{" "}
                {saveMut.isPending ? "保存中…" : "保存为模板"}
              </button>
              <button
                onClick={() => setShowTemplates(false)}
                className="p-1 text-muted-foreground hover:bg-muted rounded"
              >
                <X size={14} />
              </button>
            </div>
            <div className="text-xs text-muted-foreground mb-1">
              已保存的模板：
            </div>
            {templatesLoading ? (
              <div className="text-xs text-muted-foreground">加载中…</div>
            ) : templatesData?.items?.length ? (
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {templatesData.items.map((tpl) => (
                  <div
                    key={tpl.id}
                    className="flex items-center justify-between border rounded px-2 py-1 text-xs hover:bg-muted/30"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-foreground truncate">{tpl.name}</div>
                      <div className="text-[10px] text-muted-foreground">
                        场景: {tpl.scene} · 字号 {tpl.config_json.font_size}px ·
                        行距 {tpl.config_json.line_height}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => applyTemplate(tpl)}
                        className="px-2 py-0.5 text-[11px] bg-emerald-600 text-white rounded hover:bg-emerald-700"
                      >
                        应用
                      </button>
                      <button
                        onClick={() => void exportRemote(tpl.id)}
                        className="p-1 text-muted-foreground hover:bg-muted rounded"
                        title="下载该模板 JSON"
                      >
                        <Download size={12} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">
                暂无模板，输入名称后保存
              </div>
            )}
          </div>
        )}

        {/* 导入 JSON 浮层 */}
        {showImport && (
          <div
            className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center"
            onClick={() => setShowImport(false)}
          >
            <div
              className="bg-background rounded-lg shadow-lg w-[480px] max-w-[90vw]"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="px-4 py-2 border-b flex items-center justify-between">
                <span className="text-sm font-medium">导入配置 JSON</span>
                <button
                  onClick={() => setShowImport(false)}
                  className="text-muted-foreground hover:bg-muted rounded p-1"
                >
                  <X size={14} />
                </button>
              </div>
              <div className="p-4">
                <textarea
                  value={importText}
                  onChange={(e) => setImportText(e.target.value)}
                  rows={10}
                  placeholder='{"font_size":18,"font_family":"serif","line_height":1.8,"margin":"medium","background":"#ffffff","text_color":"#1a1a1a","brightness":1.0}'
                  className="w-full border rounded px-2 py-1.5 text-xs font-mono"
                />
                <div className="flex justify-end gap-2 mt-3">
                  <button
                    onClick={() => setShowImport(false)}
                    className="px-3 py-1 text-sm border rounded hover:bg-muted"
                  >
                    取消
                  </button>
                  <button
                    onClick={applyImport}
                    disabled={!importText.trim()}
                    className="px-3 py-1 text-sm bg-primary text-white rounded hover:bg-primary/90 disabled:opacity-50"
                  >
                    应用
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 阅读区 */}
        <div
          className="flex-1 overflow-y-auto"
          style={{ background: config.background }}
        >
          {!selectedChapterId ? (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              请选择左侧章节开始阅读
            </div>
          ) : chapterLoading && !chapterDetail ? (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              加载中…
            </div>
          ) : chapterDetail ? (
            <article style={contentStyle}>
              <h1
                className="text-2xl font-bold mb-4 text-center"
                style={{ color: config.text_color }}
              >
                {chapterDetail.title}
              </h1>
              <div
                className="reader-content"
                // 章节内容是富文本 HTML
                dangerouslySetInnerHTML={{
                  __html:
                    chapterDetail.content ||
                    '<p class="text-muted-foreground">本章暂无内容</p>',
                }}
              />
              {/* 上一章 / 下一章 */}
              <div
                className="flex items-center justify-between mt-8 pt-4 border-t"
                style={{ borderColor: "rgba(128,128,128,0.2)" }}
              >
                <button
                  onClick={() => prevId && setSelectedChapterId(prevId)}
                  disabled={!prevId}
                  className="px-3 py-1.5 text-sm rounded border disabled:opacity-40 hover:bg-black/5"
                  style={{ color: config.text_color }}
                >
                  上一章
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

      {/* 错误提示 */}
      {error && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-destructive text-white text-sm px-4 py-2 rounded-lg shadow z-50 flex items-center gap-2">
          {error}
          <button onClick={() => setError("")} className="ml-1">
            <X size={12} />
          </button>
        </div>
      )}
    </div>
  );
}

function ChapterRow({
  chapter,
  active,
  onClick,
}: {
  chapter: Chapter;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-1.5 flex items-center justify-between hover:bg-primary/10 ${
        active ? "bg-primary/10 text-primary" : "text-foreground"
      }`}
    >
      <span className="truncate">{chapter.title}</span>
      <span className="text-[10px] text-muted-foreground ml-1 shrink-0">
        {chapter.word_count}
      </span>
    </button>
  );
}

function ConfigField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-[11px] text-muted-foreground mb-1">
        {label}
      </label>
      {children}
    </div>
  );
}
