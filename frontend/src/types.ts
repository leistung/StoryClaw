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

// LLM 配置（本地版）
export type LLMFormat = 'openai_chat' | 'anthropic' | 'openai_responses'

export interface LLMConfig {
  id: string
  name: string
  format: LLMFormat
  base_url: string
  model: string
  temperature: number
  max_tokens: number
  is_default: boolean
  has_key: boolean
  // embedding（向量化）配置
  embedding_model: string | null
  embedding_base_url: string | null
  has_embedding_key: boolean
}

export interface LLMConfigInput {
  name: string
  format: LLMFormat
  base_url: string
  model: string
  api_key?: string
  temperature: number
  max_tokens: number
  is_default: boolean
  embedding_model?: string
  embedding_base_url?: string
  embedding_api_key?: string
}

// 模型 / 定价（商业版）
export interface ModelInfo {
  id: string
  display_name: string
  format: LLMFormat
  base_url: string
  context_limit: number
  business_only: boolean
  enabled: boolean
}

export interface PricingEntry {
  display_name: string
  input_price: number
  output_price: number
  [k: string]: unknown
}

export interface PricingData {
  pricing: Record<string, PricingEntry>
  defaults: { currency_unit: string; [k: string]: unknown }
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

export interface ChatResponse {
  thread_id: string
  message_id: string
  content: string
  model: string
  in_tokens: number
  out_tokens: number
  credits_cost: number
}

export interface ChatSession {
  thread_id: string
  title: string
  msg_count: number
  last_at: string | null
}

export interface LLMChoice {
  config_id?: string
  model_id?: string
}

export interface ChatRequest {
  message: string
  thread_id?: string
  llm_choice?: LLMChoice
}

export interface ShareResponse {
  share_token: string
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

export interface OkResponse {
  ok: true
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


// ===== P0-4 Agent Loop / SSE =====
export interface ChatStreamState {
  node: string
  intent?: string
  content?: string
  review_feedback?: string
  review_round?: number
  active_skill?: string
  status?: string
}

export interface ChatStreamDone {
  thread_id: string
  message_id: number
  content: string
  model: string
  in_tokens: number
  out_tokens: number
  credits_cost: number
  review_feedback?: string
  active_skill?: string | null
  credits_balance?: number
}

export interface ChapterGenerateRequest {
  prompt?: string
  llm_choice?: LLMChoice
  thread_id?: string
}

export interface ChapterGenerateResponse {
  chapter_id: number
  title: string
  content: string
  word_count: number
  model: string
  in_tokens: number
  out_tokens: number
  credits_cost: number
  thread_id: string
  message_id: number
  review_feedback: string
}

export interface SkillMeta {
  name: string
  description: string
  parameters?: string
  output?: string
}


// ===== P0-5 RAG =====
export interface IngestResult {
  chapter_id: number
  chunks: number
  entities: number
  relations: number
  rag_status: string
  error?: string | null
}

export interface RagChunk {
  text: string
  chapter_id: number
  volume_id: number | null
  chunk_idx: number
  score: number
  chapter_title: string
  chapter_number: number
}

export interface RagEntity {
  id: number
  name: string
  type: string
  description: string
  chapter_id: number | null
}

export interface RagRelation {
  from: string
  to: string
  type: string
  chapter_id: number | null
}

export interface RagQueryResult {
  chunks: RagChunk[]
  entities: RagEntity[]
  relations: RagRelation[]
  query: string
  error?: string | null
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


// ===== P1-6 写作 Skill 全集 =====
export interface PolishRequest {
  selected_text: string
  polish_goal?: string
  llm_choice?: LLMChoice
  thread_id?: string
}

export interface PolishResponse {
  content: string
  word_count: number
  model: string
  in_tokens: number
  out_tokens: number
  credits_cost: number
  thread_id: string
  message_id: number
}

export interface ContinueRequest {
  prefix_text?: string
  max_words?: number
  llm_choice?: LLMChoice
  thread_id?: string
}

export interface ContinueResponse {
  content: string
  word_count: number
  model: string
  in_tokens: number
  out_tokens: number
  credits_cost: number
  thread_id: string
  message_id: number
}

export interface MultiWriteRequest {
  start_number: number
  end_number?: number
  count?: number
  skip_existing?: boolean
  llm_choice?: LLMChoice
  thread_id?: string
}

export interface MultiWriteItem {
  chapter_id: number
  number: number
  title: string
  word_count: number
  status: string // generated | skipped | error
  error?: string | null
}

export interface MultiWriteResponse {
  book_id: number
  chapters: MultiWriteItem[]
  model: string
  total_in_tokens: number
  total_out_tokens: number
  total_credits_cost: number
  thread_id: string
}

export type AnalyzeSkill =
  | 'plot-planning'
  | 'character-development'
  | 'consistency-check'
  | 'book-summary'
  | 'outline-planning'

export interface AnalyzeRequest {
  skill: AnalyzeSkill
  book_id: number
  chapter_range?: { start: number; end: number } | null
  character_name?: string
  llm_choice?: LLMChoice
  thread_id?: string
}

export interface AnalyzeResponse {
  report: string
  model: string
  in_tokens: number
  out_tokens: number
  credits_cost: number
  thread_id: string
  message_id: number
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

export interface RagRelated {
  entities: RagEntity[]
  relations: RagRelation[]
  chunks: RagChunk[]
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

// ===== P1-8 辅助 skill =====
export interface AssistOut {
  content: string
  model: string
  in_tokens: number
  out_tokens: number
  credits_cost: number
  thread_id: string
  message_id: number
}

export interface BrainstormInput {
  topic: string
  genre?: string
  direction?: string
  count?: number
  llm_choice?: { config_id?: string; model_id?: string }
  thread_id?: string
}

export interface TitleGenInput {
  content?: string
  keywords?: string[]
  style?: string
  count?: number
  target?: string
  llm_choice?: { config_id?: string; model_id?: string }
  thread_id?: string
}

export interface SceneEnhanceInput {
  scene_text: string
  senses?: string[]
  mood?: string
  pov?: string
  preserve_length?: boolean
  llm_choice?: { config_id?: string; model_id?: string }
  thread_id?: string
}

export interface DialoguePolishInput {
  dialogue_text: string
  characters?: { name: string; personality: string; speech_style: string }[]
  goal?: string
  preserve_info?: boolean
  llm_choice?: { config_id?: string; model_id?: string }
  thread_id?: string
}

export interface ReadingConfigGenInput {
  scene?: string
  user_prefs?: Record<string, unknown>
  book_genre?: string
  llm_choice?: { config_id?: string; model_id?: string }
  thread_id?: string
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

// ===== P2-10 后台管理 =====
export interface AdminUser {
  id: number
  username: string
  version: string
  credits_balance: number
  is_admin: boolean
  created_at: string | null
}

export interface CreditsReport {
  by_user: { user_id: number; total_delta: number; tx_count: number }[]
  by_model: { model: string; total_delta: number; tx_count: number }[]
}

// ===== P2-10 充值 =====
export interface Membership {
  id: string
  name: string
  period: string
  duration_days: number
  price_cny: number
  bonus_credits: number
  enabled: boolean
}

export interface MembershipConfig {
  memberships: Membership[]
  defaults: { currency_unit: string }
}

export interface PurchaseResult {
  ok: boolean
  membership: string
  credits_added: number
  new_balance: number
  payment_status: string
}

export interface RechargeHistory {
  id: number
  delta: number
  reason: string
  created_at: string | null
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
