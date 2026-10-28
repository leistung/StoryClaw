/** 作者端当前使用的数据契约；业务交互类型优先放在对应 features 目录。 */
// 账户与版本
export type UserVersion = 'local' | 'business'

export interface User {
  id: string
  username: string
  version: UserVersion
  credits_balance: number
  is_admin?: boolean
}

export interface AuthResponse {
  user: User
  token: string
}

// 对话
export type ChatRole = 'user' | 'assistant'
export type Feedback = 'like' | 'dislike' | null

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  model?: string | null
  in_tokens?: number | null
  out_tokens?: number | null
  credits_cost?: number | null
  feedback?: Feedback
  created_at?: string
}

export interface ChatSession {
  thread_id: string
  title: string
  msg_count: number
  last_at: string | null
}

export interface ShareData {
  content: string
  model: string
  in_tokens: number
  out_tokens: number
  credits_cost: number
  created_at: string
  username: string
}

// ===== P0-3 书籍 / 卷 / 章节 =====
export interface Book {
  id: number
  user_id: number
  title: string
  intro: string | null
  genre: string
  platforms: string[]
  cover_url: string | null
  target_chapters: number
  target_words: number
  per_chapter_words: number
  protagonist_name: string | null
  protagonist_intro: string | null
  chapter_count: number
  total_words: number
  created_at: string | null
  updated_at: string | null
}

export interface BookInput {
  title: string
  intro?: string
  genre: string
  platforms: string[]
  cover_url?: string
  target_chapters: number
  target_words: number
  per_chapter_words: number
  protagonist_name?: string
  protagonist_intro?: string
  generate_outline?: boolean
  generate_plots?: boolean
  generate_characters?: boolean
}

export interface Volume {
  id: number
  book_id: number
  name: string
  sort: number
  created_at: string | null
}

export interface Chapter {
  id: number
  book_id: number
  volume_id: number | null
  number: number
  title: string
  word_count: number
  rag_status: string
  created_at: string | null
  updated_at: string | null
}

export interface ChapterDetail extends Chapter {
  content_hash?: string
  content: string
}

export interface Stats {
  today_words: number
  month_words: number
  total_words: number
}

// ===== P1-1 大纲 =====
export interface OutlineChapter {
  number: number
  title: string
  summary: string
}

export interface OutlineVolume {
  goal?:string
  name: string
  chapters: OutlineChapter[]
}

export interface Outline {
  id: number
  book_id: number
  content: { volumes: OutlineVolume[] } | Record<string, unknown>
  error?: string | null
  created_at: string | null
  updated_at: string | null
}

export interface RagStatusItem {
  chapter_id: number
  number: number
  title: string
  has_content: boolean
  chunk_count: number
  entity_count: number
  ingested: boolean
}

export interface RagStatus {
  book_id: number
  chapters: RagStatusItem[]
  total_chunks: number
  total_entities: number
}

// ===== P1-7 配置实体 =====
export type ConfigEntityType = 'character' | 'scene' | 'item' | 'plot' | 'outline' | 'world'

export interface EntityKv {
  id?: number
  entity_type?: string
  entity_id?: number
  key: string
  value: string
}

export interface ConfigEntity {
  id: number
  book_id: number
  entity_type: string
  category: string
  name: string
  description: string
  image_url: string | null
  extra_json: Record<string, unknown> | null
  sort_order: number
  kv: EntityKv[]
}

export interface ConfigEntityInput {
  name: string
  category?: string
  description?: string
  image_url?: string | null
  extra_json?: Record<string, unknown> | null
  kv?: EntityKv[]
}

export interface ConfigEntityList {
  book_id: number
  entity_type: string
  items: ConfigEntity[]
  total: number
}

// ===== P1-8 阅读配置 =====
export interface ReadingConfig {
  id: number
  user_id: number
  book_id: number | null
  name: string
  scene: string
  config_json: ReadingConfigData
  is_default: boolean
  created_at: string | null
}

export interface ReadingConfigData {
  font_size: number
  font_family: string
  line_height: number
  margin: string
  background: string
  text_color: string
  brightness: number
}

export interface ReadingConfigInput {
  name: string
  scene: string
  config_json: ReadingConfigData
  book_id?: number | null
  is_default?: boolean
}

export interface ReadingConfigList {
  items: ReadingConfig[]
  total: number
}

// ===== P1-9 社区 =====
export interface BookLink {
  book_id: number
  book_title: string
  book_cover_url: string | null
}

export interface Post {
  id: number
  user_id: number
  author_name: string
  title: string
  content_html: string
  content_text: string
  book_links: BookLink[]
  created_at: string | null
  updated_at: string | null
}

export interface PostInput {
  title: string
  content_html: string
  content_text: string
}

export interface PostList {
  items: Post[]
  total: number
  page?: number
  page_size?: number
}

export interface SearchResult {
  posts: Post[]
  books: { id: number; title: string; intro: string; genre: string; cover_url: string | null }[]
  total: number
}

export interface ReadBook {
  id: number
  title: string
  intro: string
  genre: string
  cover_url: string | null
  protagonist_name: string
  protagonist_intro: string
}

export interface ReadChapter {
  id: number
  number: number
  title: string
  word_count: number
}

export interface ReadChapterDetail {
  id: number
  number: number
  title: string
  content: string
  word_count: number
}

// ===== P2-10 消息系统 =====
export interface FriendRequest {
  id: number
  sender_id: number
  sender_name: string
  created_at: string | null
}

export interface Friend {
  id: number
  username: string
  created_at: string | null
}

export interface SocialMessageData {
  id: number
  sender_id: number
  receiver_id: number
  content: string
  msg_type: string
  attachment_url: string | null
  read: boolean
  created_at: string | null
}

export interface SendMessageInput {
  receiver_id: number
  content: string
  msg_type?: string
  attachment_url?: string
}
