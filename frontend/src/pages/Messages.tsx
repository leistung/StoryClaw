import { useState, useRef, useEffect, FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient, useQueries } from '@tanstack/react-query'
import { listFriends, listFriendRequests, acceptFriendRequest, rejectFriendRequest, sendFriendRequest, getConversation, sendSocialMessage } from '@/features/social/api'
import { extractError } from '@/lib/http'
import type { Friend, FriendRequest, SocialMessageData } from '@/types'
import {
  Send,
  UserPlus,
  Users,
  MessageCircle,
  Check,
  X,
  Smile,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'

function formatTime(s: string | null): string {
  if (!s) return ''
  try {
    const d = new Date(s)
    if (Number.isNaN(d.getTime())) return s
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return s
  }
}

const EMOJIS = ['😀', '😄', '😍', '😂', '👍', '🙏', '🔥', '🎉', '❤️', '😎', '🤔', '😢']

export default function Messages() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [addName, setAddName] = useState('')
  const [addError, setAddError] = useState('')

  const { data: friends = [], isFetching: friendsLoading } = useQuery<Friend[]>({
    queryKey: ['friends'],
    queryFn: listFriends,
  })

  const { data: requests = [], isFetching: reqLoading } = useQuery<FriendRequest[]>({
    queryKey: ['friend-requests'],
    queryFn: listFriendRequests,
  })

  // 为每个好友并行加载会话，用于显示未读计数
  const convQueries = useQueries({
    queries: friends.map((f) => ({
      queryKey: ['conversation', f.id],
      queryFn: () => getConversation(f.id, 1, 50),
      staleTime: 10 * 1000,
    })),
  })

  const unreadOf = (friendId: number): number => {
    const idx = friends.findIndex((f) => f.id === friendId)
    if (idx < 0) return 0
    const list = convQueries[idx]?.data
    if (!list) return 0
    return list.filter((m) => m.sender_id === friendId && !m.read).length
  }

  // 当前选中好友的会话（复用已加载的数据，避免重复请求）
  const selectedConv = (() => {
    if (selectedId == null) return undefined
    const idx = friends.findIndex((f) => f.id === selectedId)
    if (idx < 0) return undefined
    return convQueries[idx]?.data
  })()

  const sendMut = useMutation({
    mutationFn: (body: { receiver_id: number; content: string; msg_type?: string; attachment_url?: string }) =>
      sendSocialMessage(body),
    onSuccess: () => {
      if (selectedId != null) {
        qc.invalidateQueries({ queryKey: ['conversation', selectedId] })
      }
    },
  })

  const acceptMut = useMutation({
    mutationFn: (fid: number) => acceptFriendRequest(fid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['friend-requests'] })
      qc.invalidateQueries({ queryKey: ['friends'] })
    },
  })

  const rejectMut = useMutation({
    mutationFn: (fid: number) => rejectFriendRequest(fid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['friend-requests'] })
    },
  })

  const addMut = useMutation({
    mutationFn: (name: string) => sendFriendRequest(name),
    onSuccess: () => {
      setShowAdd(false)
      setAddName('')
      setAddError('')
      qc.invalidateQueries({ queryKey: ['friend-requests'] })
    },
    onError: (err) => setAddError(extractError(err, '发送好友请求失败')),
  })

  const submitAdd = (e: FormEvent) => {
    e.preventDefault()
    const name = addName.trim()
    if (!name) {
      setAddError('请输入用户名')
      return
    }
    addMut.mutate(name)
  }

  const selectedFriend = friends.find((f) => f.id === selectedId) ?? null

  return (
    <div className="flex h-full -mx-4 -my-6">
      {/* 左侧：好友 + 请求 + 添加 */}
      <aside className="w-64 sm:w-72 shrink-0 border-r flex flex-col min-h-0">
        <div className="flex items-center justify-between px-3 py-3 border-b">
          <span className="font-bold flex items-center gap-1">
            <Users size={16} /> 好友
          </span>
          <Button variant="outline" size="sm" onClick={() => { setShowAdd(true); setAddError('') }}>
            <UserPlus size={12} /> 添加
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto min-h-0">
          {/* 好友请求 */}
          {requests.length > 0 && (
            <div className="border-b">
              <div className="px-3 py-2 text-xs text-gray-500 bg-gray-50">
                好友请求（{requests.length}）
              </div>
              {reqLoading ? null : requests.map((r) => (
                <div key={r.id} className="px-3 py-2 flex items-center gap-2 hover:bg-gray-50">
                  <MessageCircle size={14} className="text-gray-400 shrink-0" />
                  <span className="text-sm flex-1 truncate">{r.sender_name}</span>
                  <button
                    onClick={() => acceptMut.mutate(r.id)}
                    disabled={acceptMut.isPending}
                    title="接受"
                    className="p-1 text-green-600 hover:bg-green-50 rounded disabled:opacity-40"
                  >
                    <Check size={14} />
                  </button>
                  <button
                    onClick={() => rejectMut.mutate(r.id)}
                    disabled={rejectMut.isPending}
                    title="拒绝"
                    className="p-1 text-red-600 hover:bg-red-50 rounded disabled:opacity-40"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* 好友列表 */}
          {friendsLoading ? (
            <div className="px-3 py-6 text-sm text-gray-400">加载中…</div>
          ) : friends.length > 0 ? (
            friends.map((f) => {
              const unread = unreadOf(f.id)
              const active = selectedId === f.id
              return (
                <button
                  key={f.id}
                  onClick={() => setSelectedId(f.id)}
                  className={`w-full text-left px-3 py-2 flex items-center gap-2 border-b transition ${
                    active ? 'bg-blue-50' : 'hover:bg-gray-50'
                  }`}
                >
                  <span className={`w-8 h-8 rounded-full flex items-center justify-center text-xs ${active ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'}`}>
                    {f.username.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm truncate">{f.username}</span>
                  </span>
                  {unread > 0 && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500 text-white">
                      {unread}
                    </span>
                  )}
                </button>
              )
            })
          ) : (
            <div className="px-3 py-8 text-center text-sm text-gray-400">
              还没有好友，点击右上角添加
            </div>
          )}
        </div>
      </aside>

      {/* 右侧：对话区 */}
      <section className="flex-1 flex flex-col min-h-0">
        {selectedFriend ? (
          <ConversationView
            friend={selectedFriend}
            messages={selectedConv ?? []}
            sending={sendMut.isPending}
            sendError={sendMut.isError ? extractError(sendMut.error, '发送失败') : ''}
            onSend={(content, msgType, attachmentUrl) =>
              sendMut.mutate({
                receiver_id: selectedFriend.id,
                content,
                msg_type: msgType,
                attachment_url: attachmentUrl,
              })
            }
          />
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
            <MessageCircle size={40} className="mb-2 opacity-50" />
            <span className="text-sm">选择左侧好友开始对话</span>
          </div>
        )}
      </section>

      {/* 添加好友弹窗 */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-1">
              <UserPlus size={16} /> 添加好友
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={submitAdd} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="add-friend">用户名</Label>
              <Input
                id="add-friend"
                value={addName}
                onChange={(e) => setAddName(e.target.value)}
                placeholder="输入对方用户名"
                autoFocus
              />
            </div>
            {addError && <p className="text-sm text-destructive">{addError}</p>}
            <DialogFooter className="pt-1">
              <Button type="button" variant="outline" onClick={() => setShowAdd(false)}>取消</Button>
              <Button type="submit" disabled={addMut.isPending}>
                {addMut.isPending ? '发送中…' : '发送请求'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function ConversationView({
  friend,
  messages,
  sending,
  sendError,
  onSend,
}: {
  friend: Friend
  messages: SocialMessageData[]
  sending: boolean
  sendError: string
  onSend: (content: string, msgType: string, attachmentUrl?: string) => void
}) {
  const [text, setText] = useState('')
  const [showEmoji, setShowEmoji] = useState(false)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  const submitText = (e: FormEvent) => {
    e.preventDefault()
    const content = text.trim()
    if (!content || sending) return
    onSend(content, 'text')
    setText('')
    setShowEmoji(false)
  }

  const sendEmoji = (emoji: string) => {
    onSend(emoji, 'emoji')
    setShowEmoji(false)
  }

  const sendMedia = (kind: 'image' | 'video') => {
    const url = window.prompt(kind === 'image' ? '请输入图片 URL' : '请输入视频 URL', '')
    if (!url) return
    onSend('', kind, url)
  }

  return (
    <>
      <div className="px-4 py-3 border-b flex items-center gap-2">
        <span className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs">
          {friend.username.slice(0, 1).toUpperCase()}
        </span>
        <span className="font-medium">{friend.username}</span>
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto min-h-0 px-4 py-4 space-y-2 bg-gray-50">
        {messages.length === 0 ? (
          <div className="text-center text-sm text-gray-400 py-8">
            还没有消息，发送第一条吧
          </div>
        ) : (
          messages.map((m) => {
            const mine = m.sender_id !== friend.id
            return (
              <div key={m.id} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[70%] rounded-lg px-3 py-2 text-sm ${
                  mine ? 'bg-blue-600 text-white' : 'bg-white border'
                }`}>
                  <MessageBody msg={m} />
                  <div className={`text-[10px] mt-1 ${mine ? 'text-blue-100' : 'text-gray-400'}`}>
                    {formatTime(m.created_at)}
                  </div>
                </div>
              </div>
            )
          })
        )}
        <div ref={bottomRef} />
      </div>

      {/* 输入区 */}
      <div className="border-t bg-white">
        {showEmoji && (
          <div className="px-3 py-2 border-b flex flex-wrap gap-1 bg-gray-50">
            {EMOJIS.map((em) => (
              <button
                key={em}
                onClick={() => sendEmoji(em)}
                className="w-8 h-8 text-lg hover:bg-gray-200 rounded"
              >
                {em}
              </button>
            ))}
          </div>
        )}
        <form onSubmit={submitText} className="flex items-end gap-2 px-3 py-2">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => setShowEmoji((v) => !v)}
            className={showEmoji ? 'text-primary' : 'text-muted-foreground'}
            title="表情"
          >
            <Smile size={18} />
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => sendMedia('image')} className="text-muted-foreground">
            图片
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => sendMedia('video')} className="text-muted-foreground">
            视频
          </Button>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submitText(e as unknown as FormEvent)
              }
            }}
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            rows={1}
            className="flex-1 resize-none max-h-32 min-h-9"
          />
          <Button
            type="submit"
            disabled={sending || !text.trim()}
            className="shrink-0"
          >
            <Send size={16} /> 发送
          </Button>
        </form>
        {sendError && <p className="px-3 pb-2 text-xs text-destructive">{sendError}</p>}
      </div>
    </>
  )
}

function MessageBody({ msg }: { msg: SocialMessageData }) {
  if (msg.msg_type === 'image' && msg.attachment_url) {
    return (
      <img
        src={msg.attachment_url}
        alt="图片"
        className="max-w-full max-h-60 rounded"
        onError={(e) => {
          ;(e.target as HTMLImageElement).style.display = 'none'
        }}
      />
    )
  }
  if (msg.msg_type === 'video' && msg.attachment_url) {
    return (
      <video
        src={msg.attachment_url}
        controls
        className="max-w-full max-h-60 rounded"
      />
    )
  }
  if (msg.msg_type === 'emoji') {
    return <span className="text-2xl">{msg.content}</span>
  }
  return <span className="whitespace-pre-wrap break-words">{msg.content}</span>
}
