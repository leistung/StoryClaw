import api from "@/lib/http";
import type { ManuscriptReference } from "@/features/assistant/draft-store";
export interface CreationPlan {
  goal: string;
  sections: { name: string; brief: string }[];
  item_count: number;
  detail_words: number;
  notes: string;
}
export interface PlanEstimate {
  words: number[];
  input_tokens: number[];
  output_tokens: number[];
  total_tokens: number[];
  credits: number[] | null;
  model: string | null;
  calls: number;
  note: string;
}
export interface AgentRun {
  id: string;
  status: string;
  error: string | null;
  job_id: string | null;
  credits_cost: number;
  request: {
    references?: ManuscriptReference[];
    entry: string;
    message: string;
    command?: string;
    scope: { book_id?: number; chapter_id?: number };
    conversation_id?: string;
  };
  result: null | {
    content: string;
    data?: {
      questions?: { question: string; options: string[] }[];
      chapter_id?: number;
      range?: { start: number; end: number; text: string };
      setting_change?: {
        before: { name: string; description: string };
        after: { name: string; description: string };
      };
      artifact?: boolean;
      kind?: string;
      adopted?: boolean;
      base_hash?: string;
      job_id?: string;
      job_result?: Record<string, unknown>;
    };
  };
  decision: null | {
    id: string;
    summary: string;
    command: string;
    content_hash?: string;
    book_title?: string;
    chapter_title?: string;
    chapter_number?: number;
    kind?: string;
    plan?: CreationPlan;
    estimate?: PlanEstimate;
  };
}
export interface AgentEvent {
  id: number;
  seq: number;
  type: string;
  payload: Record<string, unknown>;
}
export const listAgentRuns = async (bookId: number) =>
  (await api.get<AgentRun[]>("/agent/runs", { params: { book_id: bookId } }))
    .data;
export const startAgent = async (body: Record<string, unknown>) =>
  (await api.post<AgentRun>("/agent/runs", body)).data;
export const agentDecision = async (run: AgentRun, accept: boolean) =>
  (
    await api.post<AgentRun>(`/agent/runs/${run.id}/decisions`, {
      decision_id: run.decision?.id,
      accept,
    })
  ).data;
