import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Check, ChevronDown, ChevronRight, Compass } from "lucide-react";
import api from "@/lib/http";
import { useAuthStore } from "@/stores/auth";
import type { Book, Chapter } from "@/types";
import { WorkJob } from "@/features/jobs/types";
type Tab = "书籍信息" | "角色" | "大纲" | "创作" | "任务" | "数据库";
export default function CreationGuide({
  bookId,
  book,
  chapters,
  jobs,
  onNavigate,
}: {
  bookId: number;
  book?: Book;
  chapters: Chapter[];
  jobs: WorkJob[];
  onNavigate: (tab: Tab) => void;
}) {
  const uid = useAuthStore((s) => s.user?.id);
  const key = `sc-guide-${uid}-${bookId}`;
  const [closed, setClosed] = useState(
    () => localStorage.getItem(key) !== "open",
  );
  const outline = useQuery({
    queryKey: ["guide-outline", book?.id],
    enabled: !!book,
    queryFn: async () => {
      try {
        return (await api.get(`/books/${book!.id}/outline`)).data;
      } catch (e) {
        if ((e as { response?: { status: number } }).response?.status === 404)
          return null;
        throw e;
      }
    },
    refetchInterval: 5000,
    retry: false,
  });
  const hasOutline = !!outline.data?.content?.volumes?.length;
  const confirmed = hasOutline && !!outline.data?.content?._review;
  const hasBody = chapters.some((c) => c.word_count > 0);
  const steps: [string, string, Tab, boolean][] = [
    [
      "确认开书资料",
      "核对简介、主角与篇幅目标",
      "书籍信息",
      !!book?.intro?.trim() && !!book?.title,
    ],
    [
      "规划大纲与设定",
      "角色可先整理；大纲在后台生成，进度见任务",
      "大纲",
      hasOutline,
    ],
    [
      "审阅并确认大纲",
      "保存修改后，点击确认此版大纲，解锁 AI 写作",
      "大纲",
      confirmed,
    ],
    [
      "创建第一章",
      "大纲是规划；还需从目录新增真实章节",
      "创作",
      chapters.length > 0,
    ],
    [
      "逐章规划情节",
      "在本章情节面板手写，或向助手提出规划需求，再审阅确认",
      "创作",
      jobs.some(
        (j) => j.kind === "chapter-outline" && j.status === "succeeded",
      ),
    ],
    ["完成正文初稿", "向助手提出写章需求，或直接手写并保存", "创作", hasBody],
    [
      "审阅并更新故事记忆",
      "核对当前正文后确认入库，再开始下一章",
      "数据库",
      hasBody &&
        chapters
          .filter((c) => c.word_count > 0)
          .every((c) => c.rag_status === "loaded"),
    ],
  ];
  const next = steps.findIndex((s) => !s[3]);
  const count = steps.filter((s) => s[3]).length;
  const toggle = () =>
    setClosed((v) => {
      localStorage.setItem(key, v ? "open" : "closed");
      return !v;
    });
  return (
    <section className="creation-guide">
      <button className="guide-toggle" onClick={toggle} aria-expanded={!closed}>
        <Compass size={16} />
        <strong>创作路线</strong>
        <small>
          {count}/{steps.length}
        </small>
        {closed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
      </button>
      {!closed && (
        <div className="guide-checklist">
          <p>
            先确认大纲，再推进情节、场景和正文。同一本书每次执行一个任务；不会自动生成或发布。
          </p>
          <div className="guide-steps-scroll">
            {steps.map(([title, hint, tab, done], i) => (
              <div
                className={`guide-step ${i === next ? "current" : ""}`}
                key={title}
              >
                <button
                  className="guide-step-link"
                  onClick={() => onNavigate(tab)}
                >
                  <span className={done ? "done" : ""}>
                    {done ? <Check size={11} /> : i + 1}
                  </span>
                  <div>
                    <strong>{title}</strong>
                    <small>{hint}</small>
                  </div>
                  <ChevronRight size={12} />
                </button>
              </div>
            ))}
          </div>
          <div className="guide-next">
            <button
              onClick={() => onNavigate(next < 0 ? "创作" : steps[next][2])}
            >
              {next < 0 ? "继续下一章 →" : `下一步：${steps[next][0]} →`}
            </button>
            <Link to="/help#workflow">查看完整说明</Link>
          </div>
          {outline.error && (
            <p role="alert">大纲状态暂时不可用，请到大纲页核对。</p>
          )}
          <small className="guide-local-note">
            正文确认绑定具体版本；修改后旧索引停用，需要重新确认并入库。
          </small>
        </div>
      )}
    </section>
  );
}
