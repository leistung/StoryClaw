import type { AgentEvent } from "@/features/assistant/api";

const names: Record<string, string> = {
  "project.status": "读取作品状态",
  "material.read": "读取本章与作品资料",
  "memory.search": "检索前文记忆",
  "library.search": "检索来源证据",
  "library.status": "检查来源覆盖",
  "character.knowledge": "查询角色知情边界",
  "framework.draft": "拟订大纲生成计划",
  "setting.draft": "拟订设定生成计划",
  "setting.read": "读取设定与版本",
  "setting.update": "提出设定修改候选",
  "chapter.plan": "规划本章情节",
  "chapter.write": "生成章节正文",
  "chapter.revise": "修订章节正文",
  "chapter.scenes": "生成场景任务单",
  "knowledge.ingest": "更新故事记忆",
  "book.analyze": "分析作品",
  query_setting: "查询设定档案",
  query_memory: "检索前文记忆",
  get_outline: "读取章纲",
  get_prev_chapter: "读取前章摘要",
  get_book_meta: "读取作品资料",
  writer: "正文写作",
  reviewer: "审阅正文",
  "model.call": "调用创作模型",
  "creation.plan": "拟订生成计划",
  "lead.model": "理解需求与选择能力",
  "skills.list": "查看创作方法目录",
  "skills.read": "读取创作Skill",
  "skills.load": "加载创作Skill",
  "creation.revise": "按补充调整生成计划",
  "plans.create": "拟订连续或来源分析计划",
  "plans.resume": "核对恢复计划",
  "source.analysis": "分析来源章节",
  "job.validate": "校验任务依赖",
  "job.save": "保存生成结果",
  "job.execute": "执行创作任务",
  "outline.volume": "展开分卷",
  "outline.chapters": "展开章节大纲",
  "design.batch": "分批生成档案",
};
export const commandLabel = (command?: string) =>
  names[command || ""] || "创作操作";

export default function AgentExecution({
  events,
  active,
  error,
}: {
  events: AgentEvent[];
  active: boolean;
  error: string | null;
}) {
  const steps: {
    key: string;
    name: string;
    start?: AgentEvent;
    end?: AgentEvent;
  }[] = [];
  for (const e of events) {
    if (!/^(tool|step)\.(started|completed|failed)$/.test(e.type)) continue;
    const name = String(e.payload.name || "");
    const id = e.payload.call_id;
    if (e.type.endsWith(".started"))
      steps.push({ key: String(e.seq), name, start: e });
    else {
      const pending = [...steps]
        .reverse()
        .find(
          (s) =>
            !s.end &&
            s.name === name &&
            (!id || s.start?.payload.call_id === id),
        );
      if (pending) pending.end = e;
      else steps.push({ key: String(e.seq), name, end: e });
    }
  }
  if (!steps.length && !error) return null;
  const failures = steps.filter((s) => s.end?.type.endsWith("failed")).length;
  const pending = steps.filter((s) => !s.end);
  return (
    <details className="agent-execution">
      <summary>
        {active ? "执行中" : "执行记录"} · {steps.length} 个步骤
        {active && pending.length > 0
          ? ` · ${names[pending[pending.length - 1].name] || pending[pending.length - 1].name}`
          : failures
            ? ` · ${failures} 个步骤出错`
            : ""}
      </summary>
      <ol>
        {steps.map((s) => {
          const state = s.end?.type.endsWith("failed")
            ? "failed"
            : s.end
              ? "done"
              : active
                ? "running"
                : error
                  ? "failed"
                  : "stopped";
          const p = s.end?.payload || s.start?.payload || {};
          return (
            <li key={s.key} data-state={state}>
              <details>
                <summary>
                  <span className="agent-step-state">
                    {
                      {
                        failed: "失败",
                        done: "完成",
                        running: "执行中",
                        stopped: "已停止",
                      }[state]
                    }
                  </span>
                  <span>
                    {String(
                      s.start?.payload.label ||
                        p.label ||
                        names[s.name] ||
                        s.name,
                    )}
                  </span>
                  {typeof p.duration_ms === "number" && (
                    <small>{(p.duration_ms / 1000).toFixed(1)}s</small>
                  )}
                </summary>
                <code>{s.name}</code>
                {s.start?.payload.arguments !== undefined && (
                  <>
                    <h5>调用参数</h5>
                    <pre>
                      {JSON.stringify(s.start.payload.arguments, null, 2)}
                    </pre>
                  </>
                )}
                <h5>{state === "failed" ? "错误与返回" : "执行详情"}</h5>
                <pre>{JSON.stringify(p, null, 2)}</pre>
              </details>
            </li>
          );
        })}
      </ol>
      {error && <p className="agent-trace-error">{error}</p>}
    </details>
  );
}
