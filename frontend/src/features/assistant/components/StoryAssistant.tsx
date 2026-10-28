import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, Sparkles, History, Paperclip, X } from "lucide-react";
import { extractError } from "@/lib/http";
import {
  listChatSessions,
  getChatMessages,
} from "@/features/assistant/history-api";
import { listAgentRuns, startAgent } from "@/features/assistant/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAuthStore } from "@/stores/auth";
import { toast } from "sonner";
import AgentRunCard from "./AgentRunCard";
import ManuscriptReferences from "@/features/assistant/components/ManuscriptReferences";
import {
  useAssistantDraft,
  getAssistantDraft,
  assistantDraftKey,
  type ManuscriptReference,
} from "@/features/assistant/draft-store";

export default function StoryAssistant({
  bookId,
  chapterId,
  chapterLabel,
  onTasks,
  beforeSend,
}: {
  bookId: number;
  chapterId: number | null;
  chapterLabel?: string;
  onTasks: () => void;
  beforeSend: (
    target: number | null,
    refs: ManuscriptReference[],
  ) => Promise<ManuscriptReference[]>;
}) {
  const uid = useAuthStore((s) => s.user?.id);
  const qc = useQueryClient();
  const cached = useAssistantDraft((s) => s.drafts[assistantDraftKey(bookId)]);
  const [initial] = useState(() => getAssistantDraft(bookId));
  const draft = cached || initial;
  const input = draft.text;
  const put = useAssistantDraft((s) => s.put);
  const setInput = (text: string) =>
    put(bookId, { ...getAssistantDraft(bookId), text });
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const appendInput = (text: string) => {
    const previous = getAssistantDraft(bookId).text;
    setInput(previous ? `${previous}\n\n${text}` : text);
  };
  const targetChapter =
    draft.chapterId === undefined ? chapterId : draft.chapterId;
  const targetLabel =
    draft.references[0]?.title ||
    (targetChapter === chapterId ? chapterLabel : "已绑定的章节") ||
    "当前章节";
  useEffect(() => {
    const focus = (event: Event) => {
      if ((event as CustomEvent).detail?.bookId === bookId)
        inputRef.current?.focus();
    };
    window.addEventListener("storyclaw:show-assistant", focus);
    inputRef.current?.focus();
    return () => window.removeEventListener("storyclaw:show-assistant", focus);
  }, [bookId]);
  const [conversation] = useState(() => {
    const key = `sc-agent-conversation-${uid}-${bookId}`;
    const value = localStorage.getItem(key) || crypto.randomUUID();
    localStorage.setItem(key, value);
    return value;
  });
  const bottom = useRef<HTMLDivElement>(null);
  const { data: runs = [] } = useQuery({
    queryKey: ["agent-runs", uid, bookId],
    queryFn: () => listAgentRuns(bookId),
    refetchInterval: 1500,
  });
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [legacyThread, setLegacyThread] = useState("");
  const { data: legacySessions = [] } = useQuery({
    queryKey: ["legacy-agent-sessions", uid],
    queryFn: listChatSessions,
    enabled: legacyOpen,
  });
  const { data: legacyMessages = [] } = useQuery({
    queryKey: ["legacy-agent-messages", uid, legacyThread],
    queryFn: () => getChatMessages(legacyThread),
    enabled: legacyOpen && !!legacyThread,
  });
  const sending = runs.some((r) => ["accepted", "running"].includes(r.status));
  const send = useMutation({
    mutationFn: async () => {
      const snapshot = getAssistantDraft(bookId);
      const target =
        snapshot.chapterId === undefined ? chapterId : snapshot.chapterId;
      const references = await beforeSend(target, snapshot.references);
      const run = await startAgent({
        request_id: crypto.randomUUID(),
        entry: "chat",
        message: snapshot.text,
        scope: { book_id: bookId, chapter_id: target },
        references,
        conversation_id: conversation,
      });
      return { run, snapshot };
      // 发送期间用户可能继续输入；只清空本次提交的快照，避免覆盖新草稿。
    },
    onSuccess: ({ snapshot }) => {
      if (
        JSON.stringify(getAssistantDraft(bookId)) === JSON.stringify(snapshot)
      )
        put(bookId, { text: "", references: [] });
      void qc.invalidateQueries({ queryKey: ["agent-runs"] });
      bottom.current?.scrollIntoView({ block: "nearest" });
    },
    onError: (e) => toast.error(extractError(e, "发送失败")),
  });
  const visible = runs
    .filter((r) => r.request.entry === "chat" || r.request.command)
    .slice(0, 30)
    .reverse();
  useEffect(() => {
    void qc.invalidateQueries({ queryKey: ["chapters", bookId] });
    void qc.invalidateQueries({ queryKey: ["jobs", bookId] });
    void qc.invalidateQueries({ queryKey: ["blueprint"] });
    void qc.invalidateQueries({ queryKey: ["outline", bookId] });
    void qc.invalidateQueries({ queryKey: ["config-entities"] });
  }, [runs.filter((r) => r.status === "succeeded").length, bookId, qc]);
  return (
    <section className="story-assistant">
      <header>
        <Sparkles size={15} />
        <strong>创作助手</strong>
        <button onClick={() => setLegacyOpen(!legacyOpen)}>旧会话</button>
        <Button size="sm" variant="ghost" onClick={onTasks}>
          <History size={13} />
          任务
        </Button>
      </header>
      <div className="story-assistant-scroll">
        {legacyOpen && (
          <details open className="agent-legacy-history">
            <summary>旧版对话记录（仅查看，不作为本书参考）</summary>
            <select
              aria-label="选择旧会话"
              value={legacyThread}
              onChange={(e) => setLegacyThread(e.target.value)}
            >
              <option value="">选择会话</option>
              {legacySessions.map((s) => (
                <option key={s.thread_id} value={s.thread_id}>
                  {s.title || s.thread_id}
                </option>
              ))}
            </select>
            {legacyMessages.map((m) => (
              <p className="agent-answer" key={m.id}>
                {m.role === "user" ? "你：" : "助手："}
                {m.content}
              </p>
            ))}
          </details>
        )}
        {visible.length ? (
          visible.map((r) => (
            <AgentRunCard
              key={r.id}
              run={r}
              onAnswer={appendInput}
              beforeAdopt={(id) => beforeSend(id, [])}
            />
          ))
        ) : (
          <div className="agent-intro">
            <h3>从当前作品出发</h3>
            <p>
              工作台按钮只准备需求。你编辑并发送后，我再读取资料、调用工具，展示执行过程和可审阅的结果。
            </p>
            {["看看现在该做什么", "帮我规划本章", "检查角色和前文是否一致"].map(
              (t) => (
                <button key={t} onClick={() => appendInput(t)}>
                  {t}
                </button>
              ),
            )}
          </div>
        )}
        <div ref={bottom} />
      </div>
      <div className="agent-shortcuts">
        {["大纲建议", "情节建议", "角色弧光", "一致性检查", "前情提要"].map(
          (t) => (
            <button key={t} disabled={sending} onClick={() => appendInput(t)}>
              {t}
            </button>
          ),
        )}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim() && !sending) send.mutate();
        }}
      >
        <div className="assistant-composer-context">
          <small>
            {targetChapter
              ? `当前作品 · ${targetLabel}`
              : "当前作品 · 全书范围"}
          </small>
          {(input || draft.references.length > 0) && (
            <button
              type="button"
              onClick={() => put(bookId, { text: "", references: [] })}
              aria-label="清空助手草稿"
            >
              <X size={13} />
            </button>
          )}
        </div>
        {chapterId && !draft.references.length && (
          <button
            type="button"
            className="assistant-attach"
            onClick={() =>
              put(bookId, {
                ...draft,
                chapterId,
                references: [
                  {
                    kind: "chapter",
                    chapter_id: chapterId,
                    title: chapterLabel || "当前章节",
                    line_start: 1,
                    line_end: 1,
                    text: "",
                    offset: 0,
                  },
                ],
              })
            }
          >
            <Paperclip size={13} />
            引用当前完整章节
          </button>
        )}
        <ManuscriptReferences
          items={draft.references}
          onRemove={(i) =>
            put(bookId, {
              ...draft,
              references: draft.references.filter((_, index) => index !== i),
            })
          }
        />
        <Textarea
          ref={inputRef}
          maxLength={12000}
          aria-label="创作需求"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入需求，或从工作台添加正文引用…"
          rows={4}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              (e.ctrlKey || e.metaKey) &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              if (input.trim() && !sending && !send.isPending) send.mutate();
            }
          }}
        />
        <Button
          size="sm"
          disabled={!input.trim() || sending || send.isPending}
          type="submit"
        >
          <Send size={14} />
          {send.isPending ? "正在提交…" : "发送"}
        </Button>
      </form>
    </section>
  );
}
