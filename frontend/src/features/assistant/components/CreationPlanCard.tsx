import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { extractError } from "@/lib/http";
import { agentDecision, type AgentRun } from "@/features/assistant/api";
import { Button } from "@/components/ui/button";
import AssistantMarkdown from "@/features/assistant/components/AssistantMarkdown";
import { stageAssistantPrompt } from "@/features/assistant/draft-store";

const range = (values: number[]) =>
  values.map((v) => v.toLocaleString()).join("–");
export default function CreationPlanCard({ run }: { run: AgentRun }) {
  const qc = useQueryClient();
  const decision = run.decision!;
  const plan = decision.plan!;
  const estimate = decision.estimate;
  const editable = run.status === "waiting_author";
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["agent-runs"] });
    void qc.invalidateQueries({ queryKey: ["jobs"] });
  };
  const prepareRevision = () => {
    try {
      stageAssistantPrompt(
        run.request.scope.book_id!,
        `请调整生成计划 ${run.id}。我希望补充或修改：`,
        run.request.scope.chapter_id ?? null,
      );
    } catch (e) {
      toast.error(extractError(e, "请先处理输入框中的草稿"));
    }
  };
  const confirm = useMutation({
    mutationFn: (accept: boolean) => agentDecision(run, accept),
    onSuccess: refresh,
    onError: (e) => toast.error(extractError(e, "确认失败")),
  });
  const busy = confirm.isPending;
  return (
    <section className="agent-creation-plan" aria-label="待确认的生成计划">
      <header>
        <strong>
          生成计划 ·{" "}
          {editable
            ? "等你确认"
            : run.status === "cancelled"
              ? "已取消"
              : ["accepted", "running"].includes(run.status)
                ? "正在调整"
                : "已确认"}
        </strong>
        <span>{decision.book_title}</span>
      </header>
      <AssistantMarkdown>{plan.goal}</AssistantMarkdown>
      <p className="agent-plan-scale">
        {decision.command === "framework.draft"
          ? `${plan.sections.length} 卷 / 阶段`
          : `${plan.item_count} 张档案`}{" "}
        · 每{decision.command === "framework.draft" ? "卷" : "张"}约{" "}
        {plan.detail_words} 字
      </p>
      <ol>
        {plan.sections.map((s, i) => (
          <li key={i}>
            <strong>{s.name}</strong>
            <AssistantMarkdown>{s.brief}</AssistantMarkdown>
          </li>
        ))}
      </ol>
      {plan.notes && (
        <div className="agent-plan-notes">
          <strong>请核对 / 补充</strong>
          <AssistantMarkdown>{plan.notes}</AssistantMarkdown>
        </div>
      )}
      {estimate && (
        <details className="agent-plan-estimate" open>
          <summary>预计规模与消耗</summary>
          <dl>
            <div>
              <dt>本次生成内容</dt>
              <dd>约 {range(estimate.words)} 字</dd>
            </div>
            <div>
              <dt>Token 合计</dt>
              <dd>{range(estimate.total_tokens)}</dd>
            </div>
            <div>
              <dt>输入 / 输出 Token</dt>
              <dd>
                {range(estimate.input_tokens)} / {range(estimate.output_tokens)}
              </dd>
            </div>
            <div>
              <dt>预计积分</dt>
              <dd>
                {estimate.credits
                  ? `${range(estimate.credits)} 积分`
                  : "价格未就绪，暂无法估算"}
              </dd>
            </div>
          </dl>
          <small>
            {estimate.model || "未配置模型"} · 约 {estimate.calls} 次调用
          </small>
          <p>{estimate.note}</p>
        </details>
      )}
      {editable && (
        <>
          <p>这个规模和方向符合预期吗？可在输入框补充后发送。</p>
          <div className="agent-plan-actions">
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={prepareRevision}
            >
              在对话中补充调整
            </Button>
            <Button
              size="sm"
              disabled={busy}
              onClick={() => confirm.mutate(true)}
            >
              符合预期，开始生成
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => confirm.mutate(false)}
            >
              暂不生成
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
