import { useState, useEffect, useRef, useLayoutEffect } from "react";
import { Sparkles, ArrowUp, RotateCcw, Check, Loader2 } from "lucide-react";
import IdeaChoiceSheet, {
  type ChoiceQuestion,
  type ChoiceAnswer,
} from "@/features/ideation/components/IdeaChoiceSheet";
import { streamIdeation } from "@/features/ideation/api";
import type { BookInput } from "@/types";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
type Turn = { role: "user" | "assistant"; content: string };
type Proposal = Pick<
  BookInput,
  | "title"
  | "intro"
  | "genre"
  | "protagonist_name"
  | "protagonist_intro"
  | "target_chapters"
  | "per_chapter_words"
>;
type Reply = {
  reply: string;
  proposal: Proposal | null;
  credits_cost: number;
  questions?: ChoiceQuestion[];
  session_id?: string;
  stage?: string;
  question_round?: number;
};
export default function IdeaDiscussion({
  onConfirm,
}: {
  onConfirm: (draft: Partial<BookInput>) => void;
}) {
  const uid = useAuthStore((s) => s.user?.id);
  const key = `sc-ideation-${uid}`;
  const [initial] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem(key) || "{}");
    } catch {
      return {};
    }
  });
  const [sessionId, setSessionId] = useState<string | undefined>(
    initial.sessionId,
  );
  const [stage, setStage] = useState(initial.stage || "");
  const [round, setRound] = useState(initial.round || 0);
  const [messages, setMessages] = useState<Turn[]>(initial.messages || []);
  const [proposal, setProposal] = useState<Proposal | null>(
    initial.proposal || null,
  );
  const [questions, setQuestions] = useState<ChoiceQuestion[]>(
    initial.questions || [],
  );
  const [choicesOpen, setChoicesOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [cost, setCost] = useState<number | null>(null);
  const [focused, setFocused] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const anchor = useRef<HTMLDivElement>(null);
  const pinned = useRef(false);
  const reserve = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focused)
      root.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focused]);
  const [streamed, setStreamed] = useState("");
  const viewport = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useLayoutEffect(() => {
    const view = viewport.current;
    const turn = anchor.current;
    if (view && turn && reserve.current && focused) {
      const next = turn.nextElementSibling as HTMLElement | null;
      reserve.current.style.height = `${Math.max(24, view.clientHeight - turn.offsetHeight - (next?.offsetHeight ?? 0) - 50)}px`;
      if (pinned.current) view.scrollTop = turn.offsetTop - 20;
    }
  }, [messages, focused, streamed]);
  const [retry, setRetry] = useState<{
    messages: Turn[];
    mode: "discuss" | "proposal" | "revise";
    request_id: string;
    guided: boolean;
    session_id?: string;
    answers?: ChoiceAnswer[];
  } | null>(null);
  const persist = (
    turns: Turn[],
    draft: Proposal | null,
    qs: ChoiceQuestion[] = [],
    meta?: Reply,
  ) =>
    sessionStorage.setItem(
      key,
      JSON.stringify({
        messages: turns,
        proposal: draft,
        questions: qs,
        sessionId: meta?.session_id || sessionId,
        stage: meta?.stage || stage,
        round: meta?.question_round ?? round,
      }),
    );
  const send = async (
    mode: "discuss" | "proposal" | "revise",
    again = false,
    answer?: string,
    answers: ChoiceAnswer[] = [],
  ) => {
    if (busy) return;
    const text = (answer ?? input).trim();
    if (!again && mode !== "proposal" && !text) return;
    const turns: Turn[] =
      again && retry
        ? retry.messages
        : mode !== "proposal"
          ? [...messages, { role: "user", content: text }]
          : [
              ...messages,
              {
                role: "user",
                content:
                  text ||
                  "请根据我们已经讨论的内容整理开书方案，未确定的地方给出明确建议。",
              },
            ];
    const payload =
      again && retry
        ? retry
        : {
            messages: turns.slice(-12),
            mode: proposal && mode === "discuss" ? ("revise" as const) : mode,
            request_id: crypto.randomUUID(),
            guided: true,
            session_id: sessionId,
            answers,
          };
    setQuestions([]);
    setChoicesOpen(false);
    setFocused(true);
    pinned.current = true;
    setBusy(true);
    setError("");
    setRetry(payload);
    setMessages(turns);
    setStreamed("");
    setInput("");
    follow.current = true;
    controller.current = new AbortController();
    try {
      const data = await streamIdeation<Reply>(
        payload,
        (delta) => setStreamed((value) => value + delta),
        controller.current.signal,
      );
      const next: Turn[] = [
        ...turns,
        { role: "assistant", content: data.reply },
      ];
      setMessages(next);
      setProposal(data.proposal);
      setInput("");
      setCost(data.credits_cost);
      setRetry(null);
      persist(next, data.proposal, data.questions || [], data);
      setSessionId(data.session_id);
      setStage(data.stage || "");
      setRound(data.question_round || 0);
      setQuestions(data.questions || []);
      setChoicesOpen(!!data.questions?.length);
    } catch (e) {
      if ((e as Error).name !== "AbortError")
        setError((e as Error).message || "回复未完成，请重试本次请求");
    } finally {
      setBusy(false);
      setStreamed("");
    }
  };
  return (
    <div
      ref={root}
      className={`idea-discussion ${focused ? "is-focused" : ""}`}
    >
      <IdeaChoiceSheet
        key={messages.length}
        questions={questions}
        open={choicesOpen}
        onOpenChange={setChoicesOpen}
        onSubmit={(answer, answers) =>
          void send("discuss", false, answer, answers)
        }
      />
      {focused && (
        <div className="idea-focus-header">
          <span>
            <Sparkles size={15} />
            选题讨论
            <small>
              {stage === "review"
                ? "方案待确认 · 可直接提出修改"
                : `最多两轮选项 · 当前第 ${Math.min(2, round || 1)} 轮`}
            </small>
          </span>
          <button
            onClick={() => {
              pinned.current = false;
              setFocused(false);
              requestAnimationFrame(() =>
                root.current
                  ?.closest(".creation-hero")
                  ?.scrollIntoView({ behavior: "smooth", block: "start" }),
              );
            }}
          >
            返回首页 ↗
          </button>
        </div>
      )}
      {!focused && messages.length > 0 && (
        <button
          className="idea-resume"
          onClick={() => {
            setFocused(true);
            pinned.current = true;
          }}
        >
          继续上次选题讨论 →
        </button>
      )}
      <div className="idea-chat-shell">
        <div
          className="idea-transcript"
          ref={viewport}
          role="log"
          aria-label="选题讨论消息"
          onWheel={() => {
            pinned.current = false;
          }}
          onTouchStart={() => {
            pinned.current = false;
          }}
          onPointerDown={() => {
            pinned.current = false;
          }}
        >
          {!messages.length && (
            <div className="idea-chat-welcome">
              <Sparkles size={23} />
              <h2>还没想好写什么？我们可以慢慢聊。</h2>
              <p>从你的兴趣、经历，或一个模糊的念头开始。</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              ref={
                i === (busy ? messages.length - 1 : messages.length - 2)
                  ? anchor
                  : undefined
              }
              key={i}
              className={`idea-turn ${m.role}`}
            >
              <small>{m.role === "user" ? "你" : "选题伙伴"}</small>
              <ReplyText text={m.content} />
            </div>
          ))}
          {busy && (
            <div className="idea-turn assistant streaming">
              <small>选题伙伴 · 正在回复</small>
              {streamed ? (
                <ReplyText text={streamed} />
              ) : (
                <p className="idea-thinking">
                  <Loader2 size={13} className="animate-spin" />
                  正在思考你的想法…
                </p>
              )}
            </div>
          )}
          {proposal && (
            <section className="idea-proposal">
              <div className="section-heading">
                <span className="section-overline">待你确认的开书方案</span>
                <span className="text-xs text-muted-foreground">尚未创建</span>
              </div>
              <h2>{proposal.title}</h2>
              <p>{proposal.intro}</p>
              <div className="proposal-facts">
                <span>{proposal.genre}</span>
                <span>
                  全书暂定约
                  {(
                    (proposal.target_chapters * proposal.per_chapter_words) /
                    10000
                  ).toLocaleString("zh-CN", { maximumFractionDigits: 1 })}
                  万字 · {proposal.target_chapters}章
                </span>
                <span>每章约{proposal.per_chapter_words}字</span>
                <span>主角：{proposal.protagonist_name}</span>
              </div>
              <p className="text-sm">{proposal.protagonist_intro}</p>
              <Button
                disabled={busy}
                onClick={() =>
                  onConfirm({
                    ...proposal,
                    target_words:
                      proposal.target_chapters * proposal.per_chapter_words,
                  })
                }
              >
                <Check size={15} />
                采用方案，核对开书信息
              </Button>
              <Button
                variant="outline"
                className="ml-2"
                disabled={busy}
                onClick={() => {
                  setInput("我想修改：");
                  root.current?.querySelector("textarea")?.focus();
                }}
              >
                需要修改方案
              </Button>
              <small>
                这是全书目标，不会一次生成全部正文。创建后建议先打磨开篇或第一卷，再逐章写作；篇幅可调整。采用后仍可编辑资料。
              </small>
            </section>
          )}
          {questions.length > 0 && !busy && (
            <div className="idea-choice-invite">
              <p>有 {questions.length} 个问题，点选即可回答。</p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setChoicesOpen(true)}
              >
                选择我的偏好 →
              </Button>
            </div>
          )}
          <div ref={reserve} className="idea-turn-reserve" aria-hidden="true" />
        </div>
        <form
          className="idea-composer"
          onSubmit={(e) => {
            e.preventDefault();
            void send("discuss");
          }}
        >
          <label className="sr-only" htmlFor="story-idea">
            和 AI 讨论选题
          </label>
          <textarea
            id="story-idea"
            value={input}
            disabled={busy}
            onChange={(e) => {
              setInput(e.target.value);
              setRetry(null);
            }}
            placeholder={
              messages.length
                ? "补充你的想法，或告诉我想调整的方向……"
                : "想写什么故事？说一个念头，我们一起把选题聊清楚。"
            }
            maxLength={5000}
          />
          <div className="composer-bottom">
            <span className="composer-label">
              <Sparkles size={14} />
              选题伙伴
            </span>
            <span className="composer-guidance" role="status">
              {busy
                ? "正在推敲选题…"
                : cost === 0
                  ? "偏好已记录 · 生成方案时结算积分"
                  : cost !== null
                    ? `本轮 ${cost} 积分 · 开书由你确认`
                    : "讨论使用积分 · 开书前由你确认"}
            </span>
            <button
              type="submit"
              className="composer-send"
              disabled={busy || !input.trim()}
              aria-label="发送选题想法"
            >
              {busy ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <ArrowUp size={20} />
              )}
            </button>
          </div>
        </form>
      </div>
      {messages.length > 0 && (
        <div className="idea-actions">
          {messages.length > 0 && (
            <>
              <button
                disabled={busy}
                onClick={() => {
                  if (
                    window.confirm(
                      "清空这组选题讨论？已经创建的作品不会受影响。",
                    )
                  ) {
                    setSessionId(undefined);
                    setStage("");
                    setRound(0);
                    setMessages([]);
                    setQuestions([]);
                    setChoicesOpen(false);
                    setProposal(null);
                    setInput("");
                    setError("");
                    setRetry(null);
                    setCost(null);
                    sessionStorage.removeItem(key);
                  }
                }}
              >
                <RotateCcw size={12} />
                重新讨论
              </button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => void send("proposal")}
              >
                {proposal ? "重新整理方案" : "直接给我方案"}
              </Button>
            </>
          )}
        </div>
      )}
      {error && (
        <div className="idea-error" role="alert">
          <span>{error}</span>
          {retry && (
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => void send(retry.mode, true)}
            >
              重试本次请求
            </Button>
          )}
        </div>
      )}

      {!messages.length && (
        <div className="idea-shortcuts idea-discovery">
          {[
            [
              "帮我找到想写的方向",
              "请先向我提问，了解我平时喜欢的故事和关注的事，帮我发现真正想写的方向。先不要限定题材，每次问一两个问题。",
            ],
            [
              "把我的经历变成故事",
              "我想从自己的经历或观察出发写故事。请通过提问帮我找到值得展开的人物和冲突，先不要替我编造经历。",
            ],
            [
              "一起打磨一个灵感",
              "我有一个还不完整的灵感。请先问我这个念头是什么，再一起打磨人物、冲突和适合的题材。",
            ],
          ].map(([label, prompt]) => (
            <button
              key={label}
              disabled={busy}
              onClick={() => setInput(prompt)}
            >
              <Sparkles size={12} />
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ReplyText({ text }: { text: string }) {
  const formatted = text.replace(/([。！？：:])\s*(?=\d+[.、]\s*)/g, "$1\n\n");
  return (
    <div className="idea-reply-text">
      {formatted
        .split(/\n\s*\n/)
        .filter(Boolean)
        .map((part, i) => (
          <p key={i}>{part}</p>
        ))}
    </div>
  );
}
