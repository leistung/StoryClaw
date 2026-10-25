import axios, { AxiosError } from 'axios'

export const TOKEN_KEY = 'sc_token'

export const API_PREFIX = '/api/v1'

const api = axios.create({
  baseURL: API_PREFIX,
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
})

// 请求拦截器：附加 Bearer token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 清 token 跳 /login
api.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      const path = location.pathname
      if (!path.startsWith('/login') && !path.startsWith('/share/')) {
        const from = encodeURIComponent(path + location.search)
        location.href = `/login?from=${from}`
      }
    }
    return Promise.reject(error)
  },
)

// 友好的错误信息提取
export function extractError(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data
    if (data) {
      if (typeof data === 'string') return data
      if (typeof data === 'object' && data !== null) {
        const d = data as Record<string, unknown>
        // 统一错误格式：{ error: { code, message, details } }
        if (typeof d.error === 'object' && d.error !== null) {
          const e = d.error as Record<string, unknown>
          if (typeof e.message === 'string') return e.message
        }
        if (typeof d.detail === 'string') return d.detail
        if (Array.isArray(d.detail) && d.detail.length) {
          const first = d.detail[0]
          if (
            first &&
            typeof first === 'object' &&
            'msg' in first &&
            typeof (first as { msg: unknown }).msg === 'string'
          ) {
            return (first as { msg: string }).msg
          }
        }
        if (typeof d.message === 'string') return d.message
      }
    }
    if (err.message) return err.message
  } else if (err instanceof Error) {
    return err.message
  }
  return fallback
}

export default api


// ===== P0-4 SSE 流式消费 =====
export interface SSEHandlers {
  onStart?: (data: { thread_id: string }) => void
  onState?: (data: Record<string, unknown>) => void
  onDone?: (data: Record<string, unknown>) => void
  onError?: (msg: string) => void
}

/**
 * 调用 /api/chat/stream 并按 SSE 事件分发。
 * 返回一个 AbortController，调用 .abort() 可中断。
 */
export async function listChatSessions(): Promise<ChatSession[]> {
  const res = await api.get<ChatSession[]>('/chat/sessions')
  return res.data
}

export async function getChatMessages(threadId: string): Promise<ChatMessage[]> {
  const res = await api.get<ChatMessage[]>('/messages', { params: { thread_id: threadId } })
  return res.data
}

export async function streamChat(
  payload: { message: string; thread_id?: string; llm_choice?: unknown },
  handlers: SSEHandlers,
): Promise<AbortController> {
  const controller = new AbortController()
  const token = localStorage.getItem(TOKEN_KEY) || ''
  try {
    const resp = await fetch(`${API_PREFIX}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    if (!resp.ok || !resp.body) {
      const text = await resp.text().catch(() => '')
      handlers.onError?.(`HTTP ${resp.status}: ${text || resp.statusText}`)
      return controller
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // SSE 事件以双换行分隔
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''
      for (const part of parts) {
        const lines = part.split('\n')
        let event = 'message'
        const dataLines: string[] = []
        for (const ln of lines) {
          if (ln.startsWith('event:')) event = ln.slice(6).trim()
          else if (ln.startsWith('data:')) dataLines.push(ln.slice(5).trim())
        }
        if (!dataLines.length) continue
        let data: unknown = dataLines.join('\n')
        try { data = JSON.parse(data as string) } catch { /* keep raw */ }
        if (event === 'start') handlers.onStart?.(data as { thread_id: string })
        else if (event === 'state') handlers.onState?.(data as Record<string, unknown>)
        else if (event === 'done') handlers.onDone?.(data as Record<string, unknown>)
        else if (event === 'error') handlers.onError?.((data as { message?: string })?.message || '未知错误')
      }
    }
  } catch (e) {
    if ((e as Error).name !== 'AbortError') {
      handlers.onError?.((e as Error).message)
    }
  }
  return controller
}

/** 章节生成 SSE 流式（写本章）：start / node / draft / done / error。 */
export interface ChapterStreamHandlers {
  onStart?: (data: { thread_id: string; chapter_id: number }) => void
  onNode?: (data: { node: string }) => void
  onDraft?: (data: { delta: string }) => void
  onDone?: (data: ChapterGenerateResponse) => void
  onError?: (msg: string) => void
}

export async function streamChapterGenerate(
  cid: number,
  body: { prompt: string; thread_id?: string; llm_choice?: unknown },
  handlers: ChapterStreamHandlers,
): Promise<AbortController> {
  const controller = new AbortController()
  const token = localStorage.getItem(TOKEN_KEY) || ''
  try {
    const resp = await fetch(`${API_PREFIX}/chapters/${cid}/generate-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    if (!resp.ok || !resp.body) {
      const text = await resp.text().catch(() => '')
      handlers.onError?.(`HTTP ${resp.status}: ${text || resp.statusText}`)
      return controller
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''
      for (const part of parts) {
        const lines = part.split('\n')
        let event = 'message'
        const dataLines: string[] = []
        for (const ln of lines) {
          if (ln.startsWith('event:')) event = ln.slice(6).trim()
          else if (ln.startsWith('data:')) dataLines.push(ln.slice(5).trim())
        }
        if (!dataLines.length) continue
        let data: unknown = dataLines.join('\n')
        try { data = JSON.parse(data as string) } catch { /* keep raw */ }
        if (event === 'start') handlers.onStart?.(data as { thread_id: string; chapter_id: number })
        else if (event === 'node') handlers.onNode?.(data as { node: string })
        else if (event === 'draft') handlers.onDraft?.((data as { delta: string }))
        else if (event === 'done') handlers.onDone?.(data as ChapterGenerateResponse)
        else if (event === 'error') handlers.onError?.((data as { message?: string })?.message || '未知错误')
      }
    }
  } catch (e) {
    if ((e as Error).name !== 'AbortError') {
      handlers.onError?.((e as Error).message)
    }
  }
  return controller
}


// ===== P1-6 写作 Skill 全集 =====
import type {
  AnalyzeRequest, AnalyzeResponse, ContinueRequest, ContinueResponse,
  ConfigEntity, ConfigEntityInput, ConfigEntityList, MultiWriteRequest,
  MultiWriteResponse, PolishRequest, PolishResponse, RagRelated,
  ReadingConfig, ReadingConfigData, ReadingConfigInput, ReadingConfigList,
  AssistOut, BrainstormInput, TitleGenInput, SceneEnhanceInput,
  DialoguePolishInput, ReadingConfigGenInput,
  Post, PostInput, PostList, SearchResult, ReadBook, ReadChapter, ReadChapterDetail,
  MembershipConfig, Membership, PurchaseResult,
  RechargeHistory, FriendRequest, Friend, SocialMessageData, SendMessageInput,
  ChatMessage, ChatSession, ChapterGenerateResponse,
} from '../types'

/** 选中文本润色 */
export async function polishChapter(cid: number, body: PolishRequest): Promise<PolishResponse> {
  const { data } = await api.post(`/chapters/${cid}/polish`, body)
  return data
}

/** 段内续写 */
export async function continueWriting(cid: number, body: ContinueRequest): Promise<ContinueResponse> {
  const { data } = await api.post(`/chapters/${cid}/continue`, body)
  return data
}

/** 批量生成多章 */
export async function multiWrite(bid: number, body: MultiWriteRequest): Promise<MultiWriteResponse> {
  const { data } = await api.post(`/books/${bid}/multi-write`, body)
  return data
}

/** 分析 skill 统一入口 */
export async function analyzeBook(bid: number, body: AnalyzeRequest): Promise<AnalyzeResponse> {
  // body 含 book_id，直接透传
  const { data } = await api.post(`/books/${bid}/analyze`, body)
  return data
}

// ===== P1-7 配置实体 =====

/** 列出某类配置实体 */
export async function listConfigEntities(bid: number, entityType: string): Promise<ConfigEntityList> {
  const { data } = await api.get(`/books/${bid}/config/${entityType}`)
  return data
}

/** 创建配置实体 */
export async function createConfigEntity(
  bid: number, entityType: string, body: ConfigEntityInput
): Promise<ConfigEntity> {
  const { data } = await api.post(`/books/${bid}/config/${entityType}`, body)
  return data
}

/** 更新配置实体 */
export async function updateConfigEntity(
  bid: number, entityType: string, eid: number, body: Partial<ConfigEntityInput> & { sort_order?: number }
): Promise<ConfigEntity> {
  const { data } = await api.put(`/books/${bid}/config/${entityType}/${eid}`, body)
  return data
}

/** 删除配置实体 */
export async function deleteConfigEntity(
  bid: number, entityType: string, eid: number
): Promise<{ ok: boolean; id: number }> {
  const { data } = await api.delete(`/books/${bid}/config/${entityType}/${eid}`)
  return data
}

/** 加载 RAG 关联（实体关系 + 相似片段） */
export async function loadRagRelated(
  bid: number, entityType: string, eid: number
): Promise<RagRelated> {
  const { data } = await api.get(`/books/${bid}/config/${entityType}/${eid}/rag-related`)
  return data
}

// ===== P1-8 阅读配置 =====
export async function listReadingConfigs(): Promise<ReadingConfigList> {
  const { data } = await api.get('/reading-configs')
  return data
}

export async function createReadingConfig(body: ReadingConfigInput): Promise<ReadingConfig> {
  const { data } = await api.post('/reading-configs', body)
  return data
}

export async function updateReadingConfig(rcid: number, body: ReadingConfigInput): Promise<ReadingConfig> {
  const { data } = await api.put(`/reading-configs/${rcid}`, body)
  return data
}

export async function deleteReadingConfig(rcid: number): Promise<void> {
  await api.delete(`/reading-configs/${rcid}`)
}

export async function exportReadingConfig(rcid: number): Promise<{ name: string; scene: string; config_json: ReadingConfigData }> {
  const { data } = await api.get(`/reading-configs/${rcid}/export`)
  return data
}

// ===== P1-8 辅助 skill =====
export async function assistBrainstorm(body: BrainstormInput): Promise<AssistOut> {
  const { data } = await api.post('/assist/brainstorm', body)
  return data
}

export async function assistTitleGeneration(body: TitleGenInput): Promise<AssistOut> {
  const { data } = await api.post('/assist/title-generation', body)
  return data
}

export async function assistSceneEnhance(body: SceneEnhanceInput): Promise<AssistOut> {
  const { data } = await api.post('/assist/scene-enhance', body)
  return data
}

export async function assistDialoguePolish(body: DialoguePolishInput): Promise<AssistOut> {
  const { data } = await api.post('/assist/dialogue-polish', body)
  return data
}

export async function assistReadingConfigGen(body: ReadingConfigGenInput): Promise<AssistOut> {
  const { data } = await api.post('/assist/reading-config-gen', body)
  return data
}

// ===== P1-9 社区 =====
export async function listPosts(page = 1, size = 20): Promise<PostList> {
  const { data } = await api.get('/community/posts', { params: { page, size } })
  return data
}

export async function getPost(pid: number): Promise<Post> {
  const { data } = await api.get(`/community/posts/${pid}`)
  return data
}

export async function createPost(body: PostInput): Promise<Post> {
  const { data } = await api.post('/community/posts', body)
  return data
}

export async function updatePost(pid: number, body: Partial<PostInput>): Promise<Post> {
  const { data } = await api.put(`/community/posts/${pid}`, body)
  return data
}

export async function deletePost(pid: number): Promise<void> {
  await api.delete(`/community/posts/${pid}`)
}

export async function searchCommunity(q: string): Promise<SearchResult> {
  const { data } = await api.get('/community/search', { params: { q } })
  return data
}

export async function getBookForRead(bid: number): Promise<ReadBook> {
  const { data } = await api.get(`/community/books/${bid}/read`)
  return data
}

export async function listChaptersForRead(bid: number): Promise<ReadChapter[]> {
  const { data } = await api.get(`/community/books/${bid}/read/chapters`)
  return data
}

export async function getChapterForRead(bid: number, cid: number): Promise<ReadChapterDetail> {
  const { data } = await api.get(`/community/books/${bid}/read/chapters/${cid}`)
  return data
}

// ===== P2-10 充值 =====
export async function listMemberships(): Promise<MembershipConfig> {
  const { data } = await api.get('/recharge/memberships')
  return data
}

export async function purchaseMembership(membershipId: string): Promise<PurchaseResult> {
  const { data } = await api.post('/recharge/purchase', { membership_id: membershipId })
  return data
}

export async function getRechargeHistory(): Promise<RechargeHistory[]> {
  const { data } = await api.get('/recharge/history')
  return data
}

// ===== P2-10 消息系统 =====
export async function sendFriendRequest(friendUsername: string): Promise<void> {
  await api.post('/messages/friend-request', { friend_username: friendUsername })
}

export async function listFriendRequests(): Promise<FriendRequest[]> {
  const { data } = await api.get('/messages/friend-requests')
  return data
}

export async function acceptFriendRequest(fid: number): Promise<void> {
  await api.post(`/messages/friend-request/${fid}/accept`)
}

export async function rejectFriendRequest(fid: number): Promise<void> {
  await api.post(`/messages/friend-request/${fid}/reject`)
}

export async function listFriends(): Promise<Friend[]> {
  const { data } = await api.get('/messages/friends')
  return data
}

export async function sendSocialMessage(body: SendMessageInput): Promise<SocialMessageData> {
  const { data } = await api.post('/messages/send', body)
  return data
}

export async function getConversation(friendId: number, page = 1, size = 50): Promise<SocialMessageData[]> {
  const { data } = await api.get(`/messages/conversation/${friendId}`, { params: { page, size } })
  return data
}

export async function getUnreadCount(): Promise<{ unread: number }> {
  const { data } = await api.get('/messages/unread-count')
  return data
}
