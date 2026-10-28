import PublicationPanel from "@/features/publishing/components/PublicationPanel";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import api, { extractError } from "@/lib/http";
import type { Book } from "@/types";
import { Save } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

const PLATFORMS = [
  "起点",
  "番茄",
  "晋江",
  "纵横",
  "七猫",
  "QQ阅读",
  "微信读书",
  "其他",
];

interface Props {
  book: Book | undefined;
  bid: number;
  onSaved: () => void;
}

export default function BookInfoPage({ book, bid, onSaved }: Props) {
  const qc = useQueryClient();
  const [form, setForm] = useState(() => ({
    title: book?.title ?? "",
    intro: book?.intro ?? "",
    genre: book?.genre ?? "",
    platforms: book?.platforms ?? [],
    cover_url: book?.cover_url ?? "",
    target_chapters: book?.target_chapters ?? 20,
    target_words: book?.target_words ?? 60000,
    per_chapter_words: book?.per_chapter_words ?? 3000,
    protagonist_name: book?.protagonist_name ?? "",
    protagonist_intro: book?.protagonist_intro ?? "",
  }));

  const saveMutation = useMutation({
    mutationFn: async () => {
      const res = await api.put<Book>(`/books/${bid}`, {
        title: form.title,
        intro: form.intro,
        genre: form.genre,
        platforms: form.platforms,
        cover_url: form.cover_url,
        target_chapters: Number(form.target_chapters),
        target_words: Number(form.target_words),
        per_chapter_words: Number(form.per_chapter_words),
        protagonist_name: form.protagonist_name,
        protagonist_intro: form.protagonist_intro,
      });
      return res.data;
    },
    onSuccess: () => {
      toast.success("书籍信息已保存");
      qc.invalidateQueries({ queryKey: ["book", bid] });
      onSaved();
    },
    onError: (err) => toast.error(extractError(err, "保存失败")),
  });

  const togglePlatform = (p: string) => {
    setForm((f) => ({
      ...f,
      platforms: f.platforms.includes(p)
        ? f.platforms.filter((x) => x !== p)
        : [...f.platforms, p],
    }));
  };

  if (!book) {
    return <div className="p-6 text-muted-foreground text-sm">书籍加载中…</div>;
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-2xl mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">书籍信息</h2>
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
          >
            <Save size={14} className="mr-1" />{" "}
            {saveMutation.isPending ? "保存中…" : "保存"}
          </Button>
        </div>

        <PublicationPanel bookId={bid} />
        {/* 只读概览 */}
        <Card className="border-none shadow-sm">
          <CardContent className="p-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div>
              <div className="text-xs text-muted-foreground">章节数</div>
              <div className="font-medium">
                {book.chapter_count} / {form.target_chapters || "—"}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">总字数</div>
              <div className="font-medium">
                {book.total_words.toLocaleString()} /{" "}
                {(form.target_words || 0).toLocaleString()}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">创建时间</div>
              <div className="font-medium text-xs mt-0.5">
                {book.created_at
                  ? new Date(book.created_at).toLocaleDateString("zh-CN")
                  : "—"}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">最近修改</div>
              <div className="font-medium text-xs mt-0.5">
                {book.updated_at
                  ? new Date(book.updated_at).toLocaleDateString("zh-CN")
                  : "—"}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 基本信息 */}
        <Card className="border-none shadow-sm">
          <CardContent className="p-4 space-y-3">
            <div className="space-y-1.5">
              <Label>书名</Label>
              <Input
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label>简介</Label>
              <Textarea
                rows={3}
                value={form.intro}
                onChange={(e) => setForm({ ...form, intro: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>类型</Label>
                <Input
                  value={form.genre}
                  onChange={(e) => setForm({ ...form, genre: e.target.value })}
                  placeholder="玄幻 / 都市 / 言情…"
                />
              </div>
              <div className="space-y-1.5">
                <Label>封面 URL</Label>
                <Input
                  value={form.cover_url}
                  onChange={(e) =>
                    setForm({ ...form, cover_url: e.target.value })
                  }
                  placeholder="https://…"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>预计发布平台（可多选）</Label>
              <div className="flex flex-wrap gap-1.5">
                {PLATFORMS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => togglePlatform(p)}
                    className={`px-2.5 py-1 rounded-full text-xs border transition ${form.platforms.includes(p) ? "bg-primary text-primary-foreground border-primary" : "border-input text-muted-foreground hover:border-primary/50"}`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 创作目标 */}
        <Card className="border-none shadow-sm">
          <CardContent className="p-4 space-y-3">
            <div className="text-sm font-medium">创作目标</div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label>预计章节数</Label>
                <Input
                  type="number"
                  value={form.target_chapters}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      target_chapters: Number(e.target.value),
                    })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label>预计总字数</Label>
                <Input
                  type="number"
                  value={form.target_words}
                  onChange={(e) =>
                    setForm({ ...form, target_words: Number(e.target.value) })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label>每章字数</Label>
                <Input
                  type="number"
                  value={form.per_chapter_words}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      per_chapter_words: Number(e.target.value),
                    })
                  }
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 主角设定 */}
        <Card className="border-none shadow-sm">
          <CardContent className="p-4 space-y-3">
            <div className="text-sm font-medium">主角设定</div>
            <div className="space-y-1.5">
              <Label>主角名称</Label>
              <Input
                value={form.protagonist_name}
                onChange={(e) =>
                  setForm({ ...form, protagonist_name: e.target.value })
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label>主角介绍</Label>
              <Textarea
                rows={3}
                value={form.protagonist_intro}
                onChange={(e) =>
                  setForm({ ...form, protagonist_intro: e.target.value })
                }
              />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
