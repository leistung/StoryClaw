import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles, StopCircle } from "lucide-react";
import { toast } from "sonner";
import api, { extractError } from "@/lib/http";
import { agentDecision, type AgentRun } from "../api";
import { useRunEvents } from "../hooks/useRunEvents";
import { Button } from "@/components/ui/button";
import AgentExecution, { commandLabel } from "./AgentExecution";
import AssistantMarkdown from "./AssistantMarkdown";
import CreationPlanCard from "./CreationPlanCard";
import ManuscriptReferences from "./ManuscriptReferences";

// 一次运行的展示与作者决定，与输入框草稿、会话列表分开维护。
export default function AgentRunCard({
  run,
  onAnswer,
  beforeAdopt,
}: {
  run: AgentRun;
  onAnswer: (answer: string) => void;
  beforeAdopt: (id: number) => Promise<unknown>;
}) {
  const qc = useQueryClient();
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const active = ["accepted", "running", "waiting_task"].includes(run.status);
  const events = useRunEvents(run.id, active);
  const live = events
    .filter((e) => e.type === "message.delta")
    .map((e) => String(e.payload.text || ""))
    .join("");
  const decide = useMutation({
    mutationFn: (accept: boolean) => agentDecision(run, accept),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["agent-runs"] });
      void qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => toast.error(extractError(e, "确认失败")),
  });
  const cancel = useMutation({
    mutationFn: () => api.post(`/agent/runs/${run.id}/cancel`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["agent-runs"] });
      void qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => toast.error(extractError(e, "取消失败")),
  });
  const adopt = useMutation({
    mutationFn: async () => {
      if (run.result?.data?.chapter_id)
        await beforeAdopt(run.result.data.chapter_id);
      return api.post(`/agent/runs/${run.id}/adopt`, {
        expected_hash: run.result?.data?.base_hash,
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries();
      toast.success(
        run.result?.data?.kind === "setting.update"
          ? "设定修改已采用，请复核受影响的章纲与正文"
          : "候选已采用，正文需要重新审阅入库",
      );
      window.dispatchEvent(
        new CustomEvent("storyclaw:manuscript-updated", {
          detail: { chapterId: run.result?.data?.chapter_id },
        }),
      );
    },
    onError: (e) => toast.error(extractError(e, "采用失败")),
  });
  const label: Record<string, string> = {
    accepted: "等待执行",
    running: "正在处理",
    waiting_task: "后台任务执行中",
    waiting_author: "请你确认",
    succeeded: "已完成",
    failed: "未完成",
    cancelled: "已取消",
    partial: "部分完成",
  };
  return (
    <article className="agent-run-card">
      <p className="agent-user-message">
        {run.request.message || commandLabel(run.request.command)}
      </p>
      {!!run.request.references?.length && (
        <ManuscriptReferences items={run.request.references} />
      )}
      <div className="agent-run-meta">
        <Sparkles size={13} />
        <span>{label[run.status] || run.status}</span>
        {run.credits_cost > 0 && (
          <small>对话与候选 {run.credits_cost} 积分</small>
        )}
      </div>
      <AgentExecution events={events} active={active} error={run.error} />
      {run.result?.data?.kind === "author.question" ? (
        <form
          className="agent-questions"
          onSubmit={(e) => {
            e.preventDefault();
            onAnswer(
              (run.result?.data?.questions || [])
                .map((q, i) => q.question + "：" + answers[i])
                .join("\n"),
            );
          }}
        >
          {run.result.data.questions?.map((q, i) => (
            <fieldset key={i}>
              <legend>{q.question}</legend>
              <div>
                {q.options.map((o) => (
                  <button
                    type="button"
                    className={answers[i] === o ? "selected" : ""}
                    key={o}
                    onClick={() => setAnswers({ ...answers, [i]: o })}
                  >
                    {o}
                  </button>
                ))}
              </div>
              <input
                aria-label={q.question + " 自填答案"}
                placeholder="也可以填写自己的答案"
                value={q.options.includes(answers[i]) ? "" : answers[i] || ""}
                onChange={(e) =>
                  setAnswers({ ...answers, [i]: e.target.value })
                }
              />
            </fieldset>
          ))}
          <Button
            size="sm"
            type="submit"
            disabled={
              !run.result.data.questions?.every((_, i) => answers[i]?.trim())
            }
          >
            将选择填入消息框
          </Button>
        </form>
      ) : (
        <div className="agent-answer">
          <AssistantMarkdown>
            {run.error ||
              run.result?.content ||
              live ||
              (active ? "正在读取作品状态…" : "")}
          </AssistantMarkdown>
        </div>
      )}
      {run.decision?.kind === "creation_plan" &&
        run.decision.plan &&
        (run.status === "waiting_author" ? (
          <CreationPlanCard key={run.decision.id} run={run} />
        ) : (
          <details className="agent-approved-plan">
            <summary>查看本次生成计划</summary>
            <CreationPlanCard key={run.decision.id} run={run} />
          </details>
        ))}
      {run.status === "waiting_author" &&
        run.decision &&
        run.decision.kind !== "creation_plan" && (
          <div className="agent-decision">
            <small>
              {run.decision.book_title}
              {run.decision.chapter_number
                ? ` · 第${run.decision.chapter_number}章 ${run.decision.chapter_title || ""}`
                : ""}
            </small>
            <p>{run.decision.summary}</p>
            <small>
              {run.decision.kind === "studio_plan"
                ? "仅授权上述范围与总预算；可以暂不执行，在输入框补充新的需求。"
                : "仅针对当前章、当前正文版本；资料变化后需要重新核对。"}
            </small>
            <div>
              <Button
                size="sm"
                disabled={decide.isPending}
                onClick={() => decide.mutate(true)}
              >
                确认执行
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={decide.isPending}
                onClick={() => decide.mutate(false)}
              >
                暂不执行
              </Button>
            </div>
          </div>
        )}
      {run.status === "succeeded" &&
        run.result?.data?.artifact &&
        (String(run.result.data.kind).startsWith("text.") ||
          run.result.data.kind === "setting.update") &&
        !run.result.data.adopted && (
          <Button
            size="sm"
            variant="outline"
            disabled={adopt.isPending}
            onClick={() => adopt.mutate()}
          >
            {run.result.data.kind === "setting.update"
              ? "审阅并采用设定修改"
              : "审阅并采用候选"}
          </Button>
        )}
      {run.result?.data?.setting_change && (
        <details className="agent-setting-diff">
          <summary>对照设定修改前后</summary>
          <h5>修改前 · {run.result.data.setting_change.before.name}</h5>
          <AssistantMarkdown>
            {run.result.data.setting_change.before.description}
          </AssistantMarkdown>
          <h5>修改后 · {run.result.data.setting_change.after.name}</h5>
          <AssistantMarkdown>
            {run.result.data.setting_change.after.description}
          </AssistantMarkdown>
        </details>
      )}
      {run.result?.data?.job_result && (
        <details>
          <summary>查看任务结果</summary>
          <pre>{JSON.stringify(run.result.data.job_result, null, 2)}</pre>
        </details>
      )}
      {active && (
        <Button
          size="sm"
          variant="ghost"
          disabled={cancel.isPending}
          onClick={() => cancel.mutate()}
        >
          <StopCircle size={12} />
          取消待执行步骤
        </Button>
      )}
    </article>
  );
}
