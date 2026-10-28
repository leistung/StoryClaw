import NarrativeState from "@/features/workspace/components/NarrativeState";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import api, { extractError } from "@/lib/http";
import { toast } from "sonner";
import { stageAssistantPrompt } from "@/features/assistant/draft-store";
import { Button } from "@/components/ui/button";
type Source = {
  id: string;
  title: string;
  file_hash: string;
  chapters: number;
  words: number;
  coverage: Record<string, number>;
  warnings: string[];
  status: string;
};
type Plan = {
  id: string;
  kind: string;
  status: string;
  spent: number;
  budget: number;
  error: string;
  result: Record<string, unknown>;
};
type Release = {
  id: string;
  platform: string;
  status: string;
  chapters: number;
  hash: string;
  delivery_status?: string;
  due_at?: string;
};
type Method = { id: string; title: string; content: string; enabled: boolean };
export default function StudioManager({
  bid,
  chapterId,
}: {
  bid: number;
  chapterId?: number | null;
}) {
  const qc = useQueryClient();
  const [section, setSection] = useState("sources");
  const [busy, setBusy] = useState(false);
  const [sid, setSid] = useState("");
  const [mode, setMode] = useState("takeover");
  const [branchKind, setBranchKind] = useState("continuation");
  const [notes, setNotes] = useState("");
  const [overrides, setOverrides] = useState("");
  const [cutoff, setCutoff] = useState(1);
  const [start, setStart] = useState(1);
  const [end, setEnd] = useState(3);
  const [budget, setBudget] = useState(100);
  const [auto, setAuto] = useState(false);
  const [rights, setRights] = useState(false);
  const [commercial, setCommercial] = useState(false);
  const [platform, setPlatform] = useState("");
  const [due, setDue] = useState("");
  const [method, setMethod] = useState("");
  const [methodTitle, setMethodTitle] = useState("");
  const [preview, setPreview] = useState("");
  const { data: sources = [] } = useQuery<Source[]>({
    queryKey: ["studio-sources", bid],
    queryFn: () => api.get("/sources").then((r) => r.data),
    refetchInterval: 5000,
  });
  const { data: plans = [] } = useQuery<Plan[]>({
    queryKey: ["studio-plans", bid],
    queryFn: () => api.get(`/books/${bid}/plans`).then((r) => r.data),
    refetchInterval: 4000,
  });
  const { data: baseline } = useQuery({
    queryKey: ["studio-baseline", bid],
    queryFn: () => api.get(`/books/${bid}/baseline`).then((r) => r.data),
  });
  const { data: releases = [] } = useQuery<Release[]>({
    queryKey: ["studio-releases", bid],
    queryFn: () => api.get(`/books/${bid}/releases`).then((r) => r.data),
  });
  const { data: methods = [] } = useQuery<Method[]>({
    queryKey: ["private-methods"],
    queryFn: () => api.get("/private-methods").then((r) => r.data),
  });
  const [page, setPage] = useState(0);
  const { data: sourceChapters = [] } = useQuery<
    {
      number: number;
      title: string;
      analysis_status: string;
      error: string | null;
    }[]
  >({
    queryKey: ["source-chapters", sid, page],
    queryFn: () =>
      api
        .get(`/sources/${sid}/chapters`, {
          params: { offset: page * 25, limit: 25 },
        })
        .then((r) => r.data),
    enabled: !!sid && sources.some((s) => s.id === sid),
    refetchInterval: 5000,
  });
  const source = sources.find((s) => s.id === sid);
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await qc.invalidateQueries();
      toast.success("已保存");
    } catch (e) {
      toast.error(extractError(e, "操作失败"));
    } finally {
      setBusy(false);
    }
  }
  function prepare(text: string) {
    try {
      stageAssistantPrompt(bid, text, null);
    } catch (e) {
      toast.error(extractError(e, "请先处理助手中的草稿"));
    }
  }
  async function download(id: string) {
    try {
      const r = await api.get(`/releases/${id}/export`, {
        responseType: "blob",
      });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(r.data);
      a.download = "storyclaw-release.zip";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (e) {
      toast.error(extractError(e, "下载失败"));
    }
  }
  return (
    <div className="studio-manager">
      <header>
        <p className="text-xs text-primary">LONG FORM STUDIO</p>
        <h2>长篇创作管理</h2>
        <p>接管旧稿、管理有限的连续写作计划，保留作者确认与投稿记录。</p>
      </header>
      <nav>
        {[
          ["sources", "旧稿与分支"],
          ["memory", "叙事记忆"],
          ["plans", "连续计划"],
          ["releases", "发布准备"],
          ["methods", "私人方法"],
        ].map(([key, label]) => (
          <Button
            key={key}
            variant={section === key ? "default" : "outline"}
            onClick={() => setSection(key)}
          >
            {label}
          </Button>
        ))}
      </nav>
      {section === "sources" && (
        <>
          <section>
            <h3>导入只读来源</h3>
            <p>
              支持 TXT /
              DOCX，最大24MB。先核对拆章，再确认接续基线。导入本身不调用模型。
            </p>
            <label>
              <input
                type="checkbox"
                checked={rights}
                onChange={(e) => setRights(e.target.checked)}
              />{" "}
              我有权上传并允许模型处理这份资料
            </label>
            <label>
              <input
                type="checkbox"
                checked={commercial}
                onChange={(e) => setCommercial(e.target.checked)}
              />{" "}
              已确认商业使用许可
            </label>
            <input
              type="file"
              accept=".txt,.docx"
              disabled={!rights || busy}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                void act(async () => {
                  const form = new FormData();
                  form.append("file", file);
                  form.append(
                    "basis",
                    mode === "takeover" ? "own" : "licensed",
                  );
                  form.append("read_allowed", "true");
                  form.append("ai_allowed", "true");
                  form.append("commercial_allowed", String(commercial));
                  const r = await api.post(`/books/${bid}/sources`, form, {
                    headers: { "Content-Type": "multipart/form-data" },
                  });
                  setSid(r.data.id);
                  setCutoff(r.data.chapters);
                });
              }}
            />
            <div className="studio-fields">
              <label>
                分析起始章
                <input
                  type="number"
                  min={1}
                  value={start}
                  onChange={(e) => setStart(+e.target.value)}
                />
              </label>
              <label>
                分析结束章
                <input
                  type="number"
                  min={start}
                  value={end}
                  onChange={(e) => setEnd(+e.target.value)}
                />
              </label>
              <label>
                积分预算
                <input
                  type="number"
                  min={1}
                  value={budget}
                  onChange={(e) => setBudget(+e.target.value)}
                />
              </label>
            </div>
            <select value={sid} onChange={(e) => setSid(e.target.value)}>
              <option value="">选择本作品的来源</option>
              {sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title} · {s.chapters}章 / {s.words.toLocaleString()}字
                </option>
              ))}
            </select>
            <p>
              也可以输入同账号其他作品的来源编号，在新建空白作品中建立独立分支。
            </p>
            <input
              aria-label="来源编号"
              placeholder="来源编号"
              value={sid}
              onChange={(e) => setSid(e.target.value)}
            />
            {source && (
              <>
                <p>来源编号：{source.id}</p>
                <p>
                  已分析 {source.coverage.ready || 0} / {source.chapters} 章 ·{" "}
                  {source.status}
                </p>
                {source.warnings.map((w, i) => (
                  <p key={i} className="text-amber-700">
                    {w}
                  </p>
                ))}
                <Button
                  variant="outline"
                  onClick={() =>
                    void act(async () => {
                      const r = await api.get(`/sources/${sid}/chapters/1`);
                      setPreview(r.data.title + "\n" + r.data.content);
                    })
                  }
                >
                  预览第一章
                </Button>
                <Button
                  variant="outline"
                  onClick={() =>
                    prepare(
                      `请为本作品分析来源 ${sid} 的第 ${start}–${Math.min(source.chapters, end)} 章，积分预算 ${budget}，先说明分析范围和执行安排，再由我确认开始。`,
                    )
                  }
                >
                  分析第 {start}–{Math.min(source.chapters, end)} 章
                </Button>
                <Button
                  variant="outline"
                  onClick={() =>
                    void act(() => api.post(`/sources/${sid}/revoke`))
                  }
                >
                  停用来源
                </Button>
              </>
            )}
            {source && (
              <details>
                <summary>核对拆章和分析状态</summary>
                {sourceChapters.map((c) => (
                  <article key={c.number}>
                    <strong>
                      {c.number}. {c.title}
                    </strong>
                    <p>
                      {c.analysis_status}
                      {c.error ? " · " + c.error : ""}
                    </p>
                    <Button
                      variant="outline"
                      onClick={() =>
                        void act(async () => {
                          const r = await api.get(
                            `/sources/${sid}/chapters/${c.number}`,
                          );
                          setPreview(r.data.title + "\n" + r.data.content);
                        })
                      }
                    >
                      查看原文
                    </Button>
                    {["unknown", "running"].includes(c.analysis_status) && (
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() =>
                          void act(() =>
                            api.post(
                              `/sources/${sid}/chapters/${c.number}/retry`,
                            ),
                          )
                        }
                      >
                        核对后允许重试
                      </Button>
                    )}
                  </article>
                ))}
                <Button
                  variant="outline"
                  disabled={page === 0}
                  onClick={() => setPage(page - 1)}
                >
                  上一页
                </Button>
                <Button
                  variant="outline"
                  disabled={sourceChapters.length < 25}
                  onClick={() => setPage(page + 1)}
                >
                  下一页
                </Button>
              </details>
            )}
            {preview && <pre className="studio-preview">{preview}</pre>}
          </section>
          <section>
            <h3>作者确认的接续基线</h3>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="takeover">接管自己的旧稿（目标作品需为空）</option>
              <option value="derivative">独立衍生分支（原作只读）</option>
            </select>
            {mode === "derivative" && (
              <select
                value={branchKind}
                onChange={(e) => setBranchKind(e.target.value)}
              >
                <option value="continuation">原作后续</option>
                <option value="if">IF 命运分歧</option>
                <option value="au">AU 世界规则改写</option>
                <option value="original_character">原创角色进入原作</option>
              </select>
            )}
            <label>
              继承至来源第{" "}
              <input
                type="number"
                min={1}
                value={cutoff}
                onChange={(e) => setCutoff(+e.target.value)}
              />{" "}
              章
            </label>
            <textarea
              placeholder="至少20字：截至此处已发生的事件、人物状态、未解伏笔，以及下一阶段想写什么。"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
            <textarea
              placeholder="分歧规则：哪些原作事实保留，哪些设定或角色命运需要改变？"
              value={overrides}
              onChange={(e) => setOverrides(e.target.value)}
            />
            <Button
              disabled={busy || !sid || notes.length < 20}
              onClick={() =>
                void act(async () => {
                  let selected = source;
                  if (!selected) {
                    const r = await api.get(`/sources/${sid}`);
                    selected = r.data as Source;
                  }
                  return api.post(`/books/${bid}/baseline/confirm`, {
                    source_id: sid,
                    file_hash: selected!.file_hash,
                    mode,
                    cutoff,
                    notes,
                    overrides,
                    branch_kind: branchKind,
                  });
                })
              }
            >
              确认基线
            </Button>
            {baseline && (
              <p>
                当前：{baseline.mode} · {baseline.status} · 版本{" "}
                {baseline.version}
              </p>
            )}
            <p>
              未完成分析时只标记“辅助就绪”；自动连续采用需先完成来源分析，再重新确认基线。
            </p>
          </section>
        </>
      )}
      {section === "memory" && (
        <NarrativeState bid={bid} chapterId={chapterId} />
      )}
      {section === "plans" && (
        <section>
          <h3>分阶段连续写作</h3>
          <p>
            按本章规划 → 作者确认 → 正文 → 审阅 → 入库 →
            下一章推进。默认在确认和审阅处暂停，每次最多101章。
          </p>
          <div className="studio-fields">
            <label>
              起始章
              <input
                type="number"
                min={1}
                value={start}
                onChange={(e) => setStart(+e.target.value)}
              />
            </label>
            <label>
              结束章
              <input
                type="number"
                min={start}
                value={end}
                onChange={(e) => setEnd(+e.target.value)}
              />
            </label>
            <label>
              积分预算
              <input
                type="number"
                min={1}
                value={budget}
                onChange={(e) => setBudget(+e.target.value)}
              />
            </label>
          </div>
          <label>
            <input
              type="checkbox"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked)}
            />{" "}
            授权本范围内自动采用章纲和审阅通过的正文，并入库（仍在问题或预算不足时暂停）
          </label>
          <Button
            disabled={busy}
            onClick={() =>
              prepare(
                `请为本书安排第 ${start}–${end} 章的有限连续写作计划，积分预算 ${budget}。${auto ? "我希望讨论本范围内自动采用章纲和审阅通过正文的安排。" : "每章章纲和正文需要我审阅确认。"}请先核对前置条件并展示计划，等我确认后执行。`,
              )
            }
          >
            向助手提出连续计划
          </Button>
          {plans.map((p) => (
            <article key={p.id}>
              <strong>
                {p.kind === "serial" ? "连续写作" : "来源分析"} · {p.status}
              </strong>
              <p>
                {p.spent} / {p.budget} 积分 ·{" "}
                {String(p.result.phase || "等待执行")}
              </p>
              {p.error && <p>{p.error}</p>}
              {!["succeeded", "cancelled"].includes(p.status) && (
                <div>
                  {["pause", "resume", "cancel"].map((a) => (
                    <Button
                      key={a}
                      disabled={busy}
                      variant="outline"
                      onClick={() =>
                        a === "resume"
                          ? prepare(
                              `请核对并恢复本书计划 ${p.id}，将总预算调整为 ${budget} 积分，先展示继续执行的范围和预算供我确认。`,
                            )
                          : void act(() =>
                              api.post(`/plans/${p.id}/control`, { action: a }),
                            )
                      }
                    >
                      {
                        {
                          pause: "暂停",
                          resume: "恢复（使用当前预算）",
                          cancel: "取消",
                        }[a]
                      }
                    </Button>
                  ))}
                </div>
              )}
            </article>
          ))}
        </section>
      )}
      {section === "releases" && (
        <section>
          <h3>冻结投稿包</h3>
          <p>
            导出固定版本的正文和清单，手动提交平台，再登记回执。平台名称填
            storyclaw 时，可明确批准本站预约公开；外部平台仍通过导出包手动提交。
          </p>
          <label>
            本站预约时间
            <input
              type="datetime-local"
              value={due}
              onChange={(e) => setDue(e.target.value)}
            />
          </label>
          <input
            placeholder="投稿平台名称（本站填 storyclaw）"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
          />
          <label>
            <input
              type="checkbox"
              checked={rights}
              onChange={(e) => setRights(e.target.checked)}
            />{" "}
            已核对作品权利和目标平台的AI使用规则
          </label>
          <Button
            disabled={busy || !rights || !platform}
            onClick={() =>
              void act(() =>
                api.post(`/books/${bid}/releases`, {
                  platform,
                  rights_confirmed: true,
                  ai_policy_confirmed: true,
                }),
              )
            }
          >
            生成固定版本投稿包
          </Button>
          {releases.map((r) => (
            <article key={r.id}>
              <strong>
                {r.platform} · {r.status}
              </strong>
              <p>
                {r.chapters} 章 · {r.hash.slice(0, 12)}
              </p>
              <Button variant="outline" onClick={() => void download(r.id)}>
                下载 ZIP
              </Button>
              {r.platform !== "storyclaw" && (
                <Button
                  variant="outline"
                  onClick={() =>
                    void act(() =>
                      api.post(`/releases/${r.id}/receipt`, {
                        status: "submitted",
                        snapshot_hash: r.hash,
                        note: "作者已手动提交",
                      }),
                    )
                  }
                >
                  登记已提交
                </Button>
              )}
              {r.platform === "storyclaw" && (
                <>
                  <p>
                    预约状态：{r.delivery_status || "未预约"}{" "}
                    {r.due_at ? new Date(r.due_at).toLocaleString() : ""}
                  </p>
                  <Button
                    variant="outline"
                    disabled={!due || !rights}
                    onClick={() =>
                      void act(() =>
                        api.post(`/releases/${r.id}/schedule`, {
                          snapshot_hash: r.hash,
                          confirmed: true,
                          due_at: new Date(due).toISOString(),
                        }),
                      )
                    }
                  >
                    批准此版本预约公开
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() =>
                      void act(() => api.delete(`/releases/${r.id}/schedule`))
                    }
                  >
                    取消预约
                  </Button>
                </>
              )}
            </article>
          ))}
        </section>
      )}
      {section === "methods" && (
        <section>
          <h3>私人写作方法</h3>
          <p>
            只影响写作偏好，不执行代码，也不能跳过作者确认。启用后用于本账号的章节写作。
          </p>
          <input
            placeholder="方法名称"
            value={methodTitle}
            onChange={(e) => setMethodTitle(e.target.value)}
          />
          <textarea
            placeholder="例如：对白简洁，避免用旁白直接评价人物；感情通过行动表现。"
            value={method}
            onChange={(e) => setMethod(e.target.value)}
          />
          <Button
            disabled={busy || !methodTitle || method.length < 10}
            onClick={() =>
              void act(() =>
                api.post("/private-methods", {
                  title: methodTitle,
                  content: method,
                  enabled: false,
                }),
              )
            }
          >
            保存为未启用
          </Button>
          {methods.map((m) => (
            <article key={m.id}>
              <strong>{m.title}</strong>
              <p>{m.content}</p>
              <Button
                variant="outline"
                onClick={() =>
                  void act(() =>
                    api.put(`/private-methods/${m.id}`, {
                      ...m,
                      id: undefined,
                      enabled: !m.enabled,
                    }),
                  )
                }
              >
                {m.enabled ? "停用" : "启用"}
              </Button>
              <Button
                variant="outline"
                onClick={() =>
                  void act(() => api.delete(`/private-methods/${m.id}`))
                }
              >
                删除
              </Button>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
