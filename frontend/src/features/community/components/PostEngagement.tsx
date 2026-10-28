import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Heart, Flag, MessageCircle, Send } from "lucide-react";
import { toast } from "sonner";
import api, { extractError } from "@/lib/http";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
interface Comment {
  id: number;
  user_id: number;
  author: string;
  content: string;
  created_at: string;
}
export default function PostEngagement({ postId }: { postId: number }) {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const [text, setText] = useState("");
  const [page, setPage] = useState(1);
  const counts = useQuery({
    queryKey: ["post-engagement", postId],
    queryFn: async () =>
      (
        await api.get<{ likes: number; liked: boolean; comments: number }>(
          `/community/posts/${postId}/engagement`,
        )
      ).data,
  });
  const comments = useQuery({
    queryKey: ["post-comments", postId, page],
    queryFn: async () =>
      (
        await api.get<Comment[]>(`/community/posts/${postId}/comments`, {
          params: { page },
        })
      ).data,
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["post-engagement", postId] });
    qc.invalidateQueries({ queryKey: ["post-comments", postId] });
  };
  const liked = useMutation({
    mutationFn: async () =>
      api.put(`/community/posts/${postId}/like`, {
        liked: !counts.data?.liked,
      }),
    onSuccess: refresh,
    onError: (e) => toast.error(extractError(e, "操作失败")),
  });
  const send = useMutation({
    mutationFn: async () =>
      api.post(`/community/posts/${postId}/comments`, { content: text.trim() }),
    onSuccess: () => {
      setText("");
      setPage(1);
      refresh();
    },
    onError: (e) => toast.error(extractError(e, "评论失败")),
  });
  const remove = useMutation({
    mutationFn: async (id: number) => api.delete(`/community/comments/${id}`),
    onSuccess: refresh,
    onError: (e) => toast.error(extractError(e, "删除失败")),
  });
  const report = useMutation({
    mutationFn: async (reason: string) =>
      api.post(`/community/posts/${postId}/report`, { reason }),
    onSuccess: () => toast.success("举报已提交，运营会核实处理"),
    onError: (e) => toast.error(extractError(e, "举报失败")),
  });
  return (
    <section className="post-engagement">
      <div className="flex items-center gap-3 pb-6 border-b">
        <Button
          variant="outline"
          className={counts.data?.liked ? "text-primary" : ""}
          disabled={liked.isPending || !counts.data}
          onClick={() => liked.mutate()}
        >
          <Heart
            size={16}
            fill={counts.data?.liked ? "currentColor" : "none"}
          />
          {counts.data?.likes ?? 0} 赞
        </Button>
        <span className="text-xs text-muted-foreground flex items-center gap-2">
          <MessageCircle size={15} />
          {counts.data?.comments ?? 0} 条评论
        </span>
        <Button
          size="sm"
          className="ml-auto"
          variant="ghost"
          disabled={report.isPending}
          onClick={() => {
            const reason = window.prompt(
              "请说明举报原因（至少3个字），运营会核实处理。",
            );
            if (reason && reason.trim().length >= 3)
              report.mutate(reason.trim());
          }}
        >
          <Flag size={14} />
          举报
        </Button>
      </div>
      <h2 className="text-lg font-medium mt-7 mb-4">聊聊你的看法</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) send.mutate();
        }}
      >
        <Textarea
          aria-label="评论内容"
          maxLength={2000}
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="分享一个想法，也给故事一点回声。"
        />
        <div className="flex justify-end mt-3">
          <Button
            type="submit"
            size="sm"
            disabled={send.isPending || !text.trim()}
          >
            <Send size={14} />
            发表评论
          </Button>
        </div>
      </form>
      {comments.error ? (
        <p role="alert">{extractError(comments.error, "评论加载失败")}</p>
      ) : !comments.data?.length ? (
        <p className="product-empty">还没有评论，来留下第一句话吧。</p>
      ) : (
        <div className="comment-list">
          {comments.data.map((c) => (
            <article key={c.id}>
              <div>
                <strong>{c.author}</strong>
                <small>{new Date(c.created_at).toLocaleString("zh-CN")}</small>
                {(String(c.user_id) === String(user?.id) || user?.is_admin) && (
                  <button
                    disabled={remove.isPending}
                    onClick={() => {
                      if (window.confirm("删除这条评论？")) remove.mutate(c.id);
                    }}
                  >
                    删除
                  </button>
                )}
              </div>
              <p>{c.content}</p>
            </article>
          ))}
        </div>
      )}
      <div className="flex justify-end gap-3 mt-4">
        <Button
          size="sm"
          variant="ghost"
          disabled={page === 1}
          onClick={() => setPage((p) => p - 1)}
        >
          上一页
        </Button>
        <span className="text-xs self-center">{page}</span>
        <Button
          size="sm"
          variant="ghost"
          disabled={(comments.data?.length ?? 0) < 30}
          onClick={() => setPage((p) => p + 1)}
        >
          下一页
        </Button>
      </div>
    </section>
  );
}
