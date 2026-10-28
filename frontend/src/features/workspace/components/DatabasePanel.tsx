import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Database, RefreshCw } from "lucide-react";
import api, { extractError } from "@/lib/http";
import { prepareJobPrompt } from "@/features/assistant/prompts";
import { stageAssistantPrompt } from "@/features/assistant/draft-store";
import type { RagStatus } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** 本面板只读索引状态、准备需求；模型检索与入库统一由右侧对话执行。 */
export default function DatabasePanel({
  bookId,
  onError,
}: {
  bookId: number;
  onError: (message: string) => void;
}) {
  const [query, setQuery] = useState("");
  const {
    data: status,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["rag-status", bookId],
    queryFn: async () =>
      (await api.get<RagStatus>(`/books/${bookId}/rag-status`)).data,
    refetchInterval: 5000,
  });
  function prepareSearch() {
    if (!query.trim()) return;
    try {
      stageAssistantPrompt(
        bookId,
        `请检索本书有效历史记忆：${query.trim()}。注明证据的来源章节，区分原文事实与推断。`,
        null,
      );
    } catch (cause) {
      onError(extractError(cause, "无法准备检索需求"));
    }
  }
  function prepareIndex(chapterId: number) {
    try {
      prepareJobPrompt({
        book_id: bookId,
        chapter_id: chapterId,
        kind: "index",
      });
    } catch (cause) {
      toast.error(extractError(cause, "无法准备入库需求"));
    }
  }
  const chapters = status?.chapters ?? [];
  return (
    <section className="flex h-full flex-col overflow-auto bg-muted/30">
      <header className="flex flex-wrap items-center gap-3 border-b bg-background px-4 py-3">
        <Database size={18} />
        <strong>故事记忆</strong>
        <span className="text-xs text-muted-foreground">
          已入库 {chapters.filter((chapter) => chapter.ingested).length} /{" "}
          {chapters.length} 章 · {status?.total_chunks ?? 0} 切片 ·{" "}
          {status?.total_entities ?? 0} 实体
        </span>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => void refetch()}
          aria-label="刷新记忆状态"
        >
          <RefreshCw size={14} />
        </Button>
      </header>
      <form
        className="grid gap-3 border-b bg-background p-4"
        onSubmit={(event) => {
          event.preventDefault();
          prepareSearch();
        }}
      >
        <label htmlFor="memory-query">向助手提出记忆检索需求</label>
        <Input
          id="memory-query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="例如：主角何时得知商会的秘密？"
        />
        <Button
          className="justify-self-start"
          type="submit"
          variant="outline"
          disabled={!query.trim()}
        >
          填入右侧对话
        </Button>
        <p className="text-xs text-muted-foreground">
          检索证据、实体关系和回答在助手中展示，点击按钮不会调用模型。
        </p>
      </form>
      {error && (
        <p className="p-4 text-sm" role="alert">
          {extractError(error, "记忆状态加载失败")}
        </p>
      )}
      {isLoading ? (
        <p className="p-4">正在读取记忆状态…</p>
      ) : (
        <div className="p-4">
          <h3 className="mb-3 font-medium">章节索引状态</h3>
          {chapters.length ? (
            <ul className="divide-y">
              {chapters.map((chapter) => (
                <li
                  key={chapter.chapter_id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div>
                    <strong className="text-sm">
                      第 {chapter.number} 章 · {chapter.title}
                    </strong>
                    <p className="text-xs text-muted-foreground">
                      {chapter.ingested
                        ? "当前版本已入库"
                        : chapter.has_content
                          ? "当前正文需要审阅入库"
                          : "暂无正文"}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!chapter.has_content}
                    onClick={() => prepareIndex(chapter.chapter_id)}
                  >
                    向助手提出{chapter.ingested ? "更新" : "入库"}需求
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              尚无章节。写入并审阅正文后，再通过助手更新记忆。
            </p>
          )}
        </div>
      )}
    </section>
  );
}
