import { create } from "zustand";
import { useAuthStore } from "@/stores/auth";

export interface ManuscriptReference {
  kind: "selection" | "cursor" | "chapter";
  chapter_id: number;
  title: string;
  line_start: number;
  line_end: number;
  text: string;
  offset: number;
  expected_hash?: string;
  affinity?: "before" | "after";
  /** Local editor snapshot; stripped before sending the request. */
  snapshot?: string;
}
export interface AssistantDraft {
  text: string;
  chapterId?: number | null;
  references: ManuscriptReference[];
}
const empty: AssistantDraft = { text: "", references: [] };
export const assistantDraftKey = (bookId: number) =>
  `sc-assistant-draft-${useAuthStore.getState().user?.id || "guest"}-${bookId}`;
const key = assistantDraftKey;
function read(bookId: number): AssistantDraft {
  try {
    return JSON.parse(sessionStorage.getItem(key(bookId)) || "null") || empty;
  } catch {
    return empty;
  }
}
export const useAssistantDraft = create<{
  drafts: Record<string, AssistantDraft>;
  put: (id: number, draft: AssistantDraft) => void;
}>((set) => ({
  drafts: {},
  put: (id, draft) => {
    sessionStorage.setItem(key(id), JSON.stringify(draft));
    set((state) => ({ drafts: { ...state.drafts, [key(id)]: draft } }));
  },
}));
export const getAssistantDraft = (id: number) =>
  useAssistantDraft.getState().drafts[key(id)] || read(id);
export function stageAssistantPrompt(
  bookId: number,
  text: string,
  chapterId?: number | null,
  references: ManuscriptReference[] = [],
) {
  const old = getAssistantDraft(bookId);
  if (
    (old.text || old.references.length) &&
    old.chapterId !== undefined &&
    old.chapterId !== chapterId
  )
    throw new Error("输入框已有其他范围的草稿，请先发送或清空后再添加。");
  useAssistantDraft
    .getState()
    .put(bookId, {
      text: old.text ? `${old.text}\n\n${text}` : text,
      chapterId,
      references: references.length ? references : old.references,
    });
  window.dispatchEvent(
    new CustomEvent("storyclaw:show-assistant", { detail: { bookId } }),
  );
}

export function manuscriptPlainText(html: string) {
  return (
    new DOMParser().parseFromString(html, "text/html").body.textContent || ""
  );
}
export const compactText = (text: string) => text.replace(/\s/gu, "");
