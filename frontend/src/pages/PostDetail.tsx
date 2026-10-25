import PostEngagement from '@/components/PostEngagement'
import { useState, MouseEvent, FormEvent } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth'
import {
  getPost,
  updatePost,
  deletePost,
  extractError,
} from '@/lib/api'
import type { Post, PostInput } from '@/types'
import {
  ArrowLeft,
  User,
  Clock,
  Book as BookIcon,
  Edit,
  Trash,
  ChevronRight,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card } from '@/components/ui/card'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '@/components/ui/dialog'

function formatDate(s: string | null): string {
  if (!s) return ''
  try {
    const d = new Date(s)
    if (Number.isNaN(d.getTime())) return s
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return s
  }
}

// 编辑器内纯文本转 HTML：与 Community 一致
function textToHtml(text: string): string {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped
    .split(/\n{2,}/)
    .map((seg) => `<p>${seg.replace(/\n/g, '<br/>')}</p>`)
    .join('')
}

export default function PostDetail() {
  const params = useParams()
  const pid = Number(params.id)
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const qc = useQueryClient()

  const { data: post, isFetching } = useQuery<Post>({
    queryKey: ['post', pid],
    queryFn: () => getPost(pid),
    enabled: !!pid && !Number.isNaN(pid),
  })

  const [showEditor, setShowEditor] = useState(false)
  const [editorForm, setEditorForm] = useState<PostInput>({ title: '', content_html: '', content_text: '' })
  const [error, setError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const isAuthor = !!(user && post && String(user.id) === String(post.user_id))

  const updateMut = useMutation({
    mutationFn: (body: Partial<PostInput>) => updatePost(pid, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['post', pid] })
      qc.invalidateQueries({ queryKey: ['community-posts'] })
      setShowEditor(false)
      setError('')
    },
    onError: (err) => setError(extractError(err, '更新失败')),
  })

  const deleteMut = useMutation({
    mutationFn: () => deletePost(pid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['community-posts'] })
      navigate('/community')
    },
    onError: (err) => {
      setError(extractError(err, '删除失败'))
      setConfirmDelete(false)
    },
  })

  const openEditor = () => {
    if (!post) return
    setEditorForm({
      title: post.title,
      content_text: post.content_text,
      content_html: post.content_html,
    })
    setError('')
    setShowEditor(true)
  }

  const submitEdit = (e: FormEvent) => {
    e.preventDefault()
    if (!editorForm.title.trim()) {
      setError('请填写标题')
      return
    }
    if (!editorForm.content_text.trim()) {
      setError('请填写内容')
      return
    }
    updateMut.mutate({
      title: editorForm.title.trim(),
      content_text: editorForm.content_text,
      content_html: editorForm.content_html || textToHtml(editorForm.content_text),
    })
  }

  // 拦截 content_html 内 <a href="/read/..."> 点击，改为客户端路由
  const handleContentClick = (e: MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement
    const anchor = target.closest('a') as HTMLAnchorElement | null
    if (!anchor) return
    const href = anchor.getAttribute('href') || ''
    // 仅拦截 /read/{id} 形式
    const m = href.match(/^\/read\/(\d+)$/)
    if (m) {
      e.preventDefault()
      navigate(`/read/${m[1]}`)
    }
  }

  if (!pid || Number.isNaN(pid)) {
    return <div className="p-8 text-muted-foreground">无效的帖子 ID</div>
  }

  if (isFetching && !post) {
    return <div className="p-8 text-muted-foreground">加载中…</div>
  }

  if (!post) {
    return <div className="p-8 text-muted-foreground">帖子不存在或已被删除</div>
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      {/* 顶部返回 */}
      <div className="flex items-center justify-between mb-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/community')}
          className="text-muted-foreground"
        >
          <ArrowLeft size={16} /> 返回社区
        </Button>
        {isAuthor && (
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" onClick={openEditor}>
              <Edit size={14} /> 编辑
            </Button>
            <Button variant="outline" size="sm" onClick={() => setConfirmDelete(true)} className="text-destructive hover:text-destructive">
              <Trash size={14} /> 删除
            </Button>
          </div>
        )}
      </div>

      {/* 帖子标题 */}
      <h1 className="text-3xl font-bold mb-3">{post.title}</h1>

      {/* 作者 / 时间 */}
      <div className="flex items-center gap-3 text-sm text-muted-foreground mb-6 flex-wrap">
        <span className="flex items-center gap-1">
          <User size={14} /> {post.author_name}
        </span>
        {post.created_at && (
          <span className="flex items-center gap-1">
            <Clock size={14} /> {formatDate(post.created_at)}
          </span>
        )}
        {post.updated_at && post.updated_at !== post.created_at && (
          <span className="text-xs text-muted-foreground">（已编辑 {formatDate(post.updated_at)}）</span>
        )}
      </div>

      {/* 帖子正文 */}
      <article
        className="reader-content prose prose-sm max-w-none text-foreground leading-relaxed"
        onClick={handleContentClick}
        dangerouslySetInnerHTML={{ __html: post.content_html }}
      />

      <PostEngagement postId={pid}/>
      {/* 关联书籍卡片 */}
      {post.book_links.length > 0 && (
        <div className="mt-8 pt-6 border-t">
          <div className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-1">
            <BookIcon size={14} /> 关联书籍
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {post.book_links.map((bl) => (
              <Link
                key={bl.book_id}
                to={`/read/${bl.book_id}`}
                className="block"
              >
                <Card className="p-3 hover:shadow-md transition flex gap-3 items-center border-none shadow-sm">
                  <div className="w-12 h-16 bg-muted rounded flex items-center justify-center text-muted-foreground overflow-hidden shrink-0">
                    {bl.book_cover_url ? (
                      <img src={bl.book_cover_url} className="w-full h-full object-cover" alt={bl.book_title} />
                    ) : (
                      <BookIcon size={18} />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium truncate">{bl.book_title}</div>
                    <div className="text-xs text-primary mt-1 flex items-center gap-1">
                      点击阅读 <ChevronRight size={12} />
                    </div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* 编辑弹窗 */}
      <Dialog open={showEditor} onOpenChange={setShowEditor}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>编辑帖子</DialogTitle>
          </DialogHeader>
          <form onSubmit={submitEdit} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="edit-title">标题 *</Label>
              <Input id="edit-title" value={editorForm.title} onChange={(e) => setEditorForm({ ...editorForm, title: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-content">内容 *</Label>
              <Textarea
                id="edit-content"
                className="resize-y font-mono text-sm"
                rows={12}
                value={editorForm.content_text}
                onChange={(e) =>
                  setEditorForm({
                    ...editorForm,
                    content_text: e.target.value,
                    content_html: textToHtml(e.target.value),
                  })
                }
              />
              <div className="text-xs text-muted-foreground">
                提示：使用 <code className="bg-muted px-1 rounded">[[book:id]]</code> 语法引用书籍
              </div>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" onClick={() => setShowEditor(false)}>取消</Button>
              <Button type="submit" disabled={updateMut.isPending}>
                {updateMut.isPending ? '保存中…' : '保存'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 删除确认 */}
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              删除后无法恢复，帖子及其引用关系将一并清除。
            </DialogDescription>
          </DialogHeader>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>取消</Button>
            <Button variant="destructive" onClick={() => deleteMut.mutate()} disabled={deleteMut.isPending}>
              {deleteMut.isPending ? '删除中…' : '删除'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
