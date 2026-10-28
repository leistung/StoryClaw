import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import api, { extractError } from "@/lib/http";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogHeader,
} from "@/components/ui/dialog";
interface Revision {
  id: number;
  title: string;
  word_count: number;
  source: string;
  created_at: string;
}
export default function ChapterVersions({
  chapterId,
  open,
  onClose,
  onRestored,
}: {
  chapterId: number | null;
  open: boolean;
  onClose: () => void;
  onRestored: () => void;
}) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const list = useQuery({
    queryKey: ["revisions", chapterId],
    queryFn: async () =>
      (await api.get<Revision[]>(`/chapters/${chapterId}/revisions`)).data,
    enabled: open && !!chapterId,
  });
  const detail = useQuery({
    queryKey: ["revision", chapterId, selected],
    queryFn: async () =>
      (
        await api.get<{ title: string; content: string }>(
          `/chapters/${chapterId}/revisions/${selected}`,
        )
      ).data,
    enabled: open && !!selected && !!chapterId,
  });
  const restore = useMutation({
    mutationFn: async () => {
      const latest = (await api.get(`/chapters/${chapterId}`)).data;
      return api.post(`/chapters/${chapterId}/revisions/${selected}/restore`, {
        expected_hash: latest.content_hash,
      });
    },
    onSuccess: () => {
      toast.success("已恢复版本，恢复前的正文也已留档");
      qc.invalidateQueries({ queryKey: ["revisions", chapterId] });
      onRestored();
      onClose();
    },
    onError: (e) => toast.error(extractError(e, "恢复失败")),
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setSelected(null);
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>章节版本历史</DialogTitle>
          <DialogDescription>
            编辑或 AI 替换正文前自动留档。恢复版本不会删除当前稿。
          </DialogDescription>
        </DialogHeader>
        {list.isLoading ? (
          <p>加载中…</p>
        ) : list.error ? (
          <p>{extractError(list.error, "加载失败")}</p>
        ) : !list.data?.length ? (
          <p className="product-empty">
            还没有历史版本。下一次修改正文时，当前版本会被保存。
          </p>
        ) : (
          <div className="grid md:grid-cols-[210px_1fr] gap-5">
            <div className="space-y-2">
              {list.data.map((r) => (
                <button
                  className={`version-item ${selected === r.id ? "selected" : ""}`}
                  key={r.id}
                  onClick={() => setSelected(r.id)}
                >
                  <strong>{r.title}</strong>
                  <small>
                    {r.word_count} 字 ·{" "}
                    {(
                      {
                        manual: "手动编辑",
                        ai: "AI写作",
                        "ai-batch": "批量写作",
                        before_restore: "恢复前备份",
                      } as Record<string, string>
                    )[r.source] || r.source}
                  </small>
                  <small>
                    {new Date(r.created_at).toLocaleString("zh-CN")}
                  </small>
                </button>
              ))}
            </div>
            <div>
              {detail.data ? (
                <>
                  <h3 className="font-medium mb-3">{detail.data.title}</h3>
                  <div className="version-preview whitespace-pre-wrap">
                    {detail.data.content.replace(/<[^>]+>/g, "\n")}
                  </div>
                  <Button
                    className="mt-4"
                    disabled={restore.isPending}
                    onClick={() => {
                      if (
                        window.confirm("恢复此版本？当前正文也会留存到历史中。")
                      )
                        restore.mutate();
                    }}
                  >
                    恢复此版本
                  </Button>
                </>
              ) : (
                <p className="text-muted-foreground text-sm">
                  选择一个版本预览正文。
                </p>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
