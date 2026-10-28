import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { extractError } from "@/lib/http";
import { prepareJobPrompt } from "@/features/assistant/prompts";
import { type WorkJob } from "@/features/jobs/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { useAuthStore } from "@/stores/auth";
type Plan = {
  title: string;
  summary: string;
  ending_hook: string;
  constraints: string[];
};
type State = {
  serial: boolean;
  plan: Plan | null;
  confirmed: boolean;
  stale: boolean;
};
const empty: Plan = {
  title: "",
  summary: "",
  ending_hook: "",
  constraints: [],
};
export default function ChapterPlanning({
  bookId,
  chapterId,
  jobs,
  onTasks,
}: {
  bookId: number;
  chapterId: number | null;
  jobs: WorkJob[];
  onTasks: () => void;
}) {
  const qc = useQueryClient();
  const [closed, setClosed] = useState(true);
  const uid = useAuthStore((s) => s.user?.id);
  const key = `sc-blueprint-draft-${uid}-${bookId}-${chapterId}`;
  const [draft] = useState<Plan | null>(() => {
    try {
      return JSON.parse(sessionStorage.getItem(key) || "null");
    } catch {
      return null;
    }
  });
  const [plan, setPlan] = useState<Plan>(draft || empty);
  const [dirty, setDirty] = useState(!!draft);
  useEffect(() => {
    if (dirty) sessionStorage.setItem(key, JSON.stringify(plan));
    else sessionStorage.removeItem(key);
  }, [plan, dirty, key]);
  const { data, error } = useQuery({
    queryKey: ["blueprint", chapterId],
    enabled: !!chapterId,
    queryFn: async () =>
      (await api.get<State>(`/chapters/${chapterId}/blueprint`)).data,
    refetchInterval: 3000,
  });
  useEffect(() => {
    if (!dirty) setPlan(data?.plan || empty);
  }, [data, dirty]);
  const busy = jobs.some((j) => ["queued", "running"].includes(j.status));
  const preparePlan = () => {
    try {
      prepareJobPrompt({
        book_id: bookId,
        chapter_id: chapterId!,
        kind: "chapter-outline",
        prompt: dirty
          ? "参考我正在编辑的章纲：" + JSON.stringify(plan)
          : undefined,
      });
    } catch (e) {
      toast.error(extractError(e, "请先处理助手中的草稿"));
    }
  };
  const save = useMutation({
    mutationFn: async () =>
      (await api.put<State>(`/chapters/${chapterId}/blueprint`, plan)).data,
    onSuccess: (r) => {
      setDirty(false);
      qc.setQueryData(["blueprint", chapterId], r);
    },
    onError: (e) => toast.error(extractError(e, "保存失败")),
  });
  const confirm = useMutation({
    mutationFn: async () =>
      (await api.post<State>(`/chapters/${chapterId}/blueprint/confirm`, plan))
        .data,
    onSuccess: (r) => {
      qc.setQueryData(["blueprint", chapterId], r);
      void qc.invalidateQueries({ queryKey: ["workflow", bookId] });
      void qc.invalidateQueries({ queryKey: ["chapters", bookId] });
      setClosed(true);
      toast.success("本章章纲已确认，可按需生成场景或正文");
    },
    onError: (e) => toast.error(extractError(e, "确认失败")),
  });
  const locked = busy || save.isPending || confirm.isPending;
  if (!chapterId || !data?.serial)
    return error ? (
      <p className="p-3 text-xs">{extractError(error, "章纲状态加载失败")}</p>
    ) : null;
  return (
    <section className="chapter-planning">
      <button
        className="guide-toggle"
        onClick={() => setClosed(!closed)}
        aria-expanded={!closed}
      >
        {closed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        <strong>本章情节与确认</strong>
        <small>
          {data.confirmed && !dirty
            ? "已确认"
            : data.stale
              ? "参考已变化"
              : "待确认"}
        </small>
      </button>
      {!closed && (
        <div className="chapter-planning-body">
          <p>
            只确定当前章，不锁定后续章数和情节。先审阅上章记忆，再规划本章。
          </p>
          {data.stale && (
            <p role="alert" className="text-amber-700">
              前文、总纲或设定已变化。请重新生成，或核对修改后保存并确认；旧场景任务单不会继续使用。
            </p>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={preparePlan}
            >
              {busy ? "任务处理中" : "向助手提出章纲需求"}
            </Button>
            <Button size="sm" variant="ghost" onClick={onTasks}>
              查看任务
            </Button>
          </div>
          <label>
            章纲标题
            <Input
              value={plan.title}
              disabled={locked}
              onChange={(e) => {
                setPlan({ ...plan, title: e.target.value });
                setDirty(true);
              }}
            />
          </label>
          <label>
            本章情节
            <Textarea
              rows={5}
              value={plan.summary}
              disabled={busy}
              placeholder="本章目标、阻碍、行动、转折和结果；也可以完全手写。"
              onChange={(e) => {
                setPlan({ ...plan, summary: e.target.value });
                setDirty(true);
              }}
            />
          </label>
          <label>
            章末接续点
            <Input
              value={plan.ending_hook}
              disabled={locked}
              onChange={(e) => {
                setPlan({ ...plan, ending_hook: e.target.value });
                setDirty(true);
              }}
            />
          </label>
          <label>
            连续性约束（每行一条）
            <Textarea
              rows={2}
              value={plan.constraints.join("\n")}
              disabled={locked}
              onChange={(e) => {
                setPlan({
                  ...plan,
                  constraints: e.target.value
                    .split("\n")
                    .filter((x) => x.trim())
                    .slice(0, 12),
                });
                setDirty(true);
              }}
            />
          </label>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={
                busy ||
                !dirty ||
                plan.summary.trim().length < 20 ||
                !plan.title.trim() ||
                save.isPending
              }
              onClick={() => save.mutate()}
            >
              保存章纲
            </Button>
            <Button
              size="sm"
              disabled={
                busy ||
                dirty ||
                !data.plan ||
                data.stale ||
                data.confirmed ||
                confirm.isPending
              }
              onClick={() => confirm.mutate()}
            >
              {data.confirmed && !dirty ? "已确认" : "确认本章情节"}
            </Button>
          </div>
          <small>
            改变已写章节的章纲，会将本章及后文标记为待复核；系统不会自动改写正文。章纲标题不自动覆盖目录标题。未保存编辑在当前标签页暂存。
          </small>
        </div>
      )}
    </section>
  );
}
