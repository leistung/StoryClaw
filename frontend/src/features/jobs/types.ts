/** 后台任务的只读契约与显示文案，不负责提交 AI 请求。 */
export type JobKind =
  | "generate"
  | "revise"
  | "scene-plan"
  | "index"
  | "analysis"
  | "outline"
  | "story-design"
  | "chapter-outline";
export interface WorkJob {
  id: string;
  book_id: number;
  chapter_id: number | null;
  kind: JobKind;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  error: string | null;
  created_at: string;
  result: null | {
    candidate?: {
      content: string;
      chapter_id: number;
      base_hash: string;
      adopted: boolean;
      warning?: string;
    };
    error_code?: string;
    blueprint?: { title: string; summary: string; ending_hook?: string };
    summary?: string;
    dossiers?: {
      name: string;
      category: string;
      description: string;
      extra?: Record<string, unknown>;
    }[];
    design_type?: string;
    applied?: boolean;
    added?: number;
    skipped?: number;
    report?: string;
    review_feedback?: string;
    scenes?: {
      title: string;
      goal: string;
      location: string;
      target_words: number;
      characters: string[];
    }[];
    word_count?: number;
    credits_cost?: number;
    chunks?: number;
    entities?: number;
  };
}
export const jobNames: Record<JobKind, string> = {
  revise: "章节修订",
  "chapter-outline": "本章情节规划",
  "story-design": "创作档案草案",
  outline: "大纲规划",
  generate: "章节写作",
  "scene-plan": "场景任务单",
  index: "更新故事记忆",
  analysis: "作品分析",
};
export const jobStatuses: Record<WorkJob["status"], string> = {
  queued: "排队中",
  running: "正在处理",
  succeeded: "已完成",
  failed: "未完成",
  cancelled: "已取消",
};
