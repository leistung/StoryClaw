/** 快捷操作只生成可编辑对话草稿；真正执行必须经过用户发送。 */
import { stageAssistantPrompt } from "./draft-store";
import type { JobKind } from "@/features/jobs/types";
/** Shortcuts only stage an editable chat draft. They never submit work. */
export function prepareJobPrompt(body: {
  planning_mode?: "serial" | "fixed";
  design_type?: "character" | "world" | "plot";
  book_id: number;
  chapter_id?: number;
  kind: JobKind;
  prompt?: string;
  skill?: string;
  start?: number;
  end?: number;
}) {
  const types = { character: "角色", world: "世界观", plot: "情节" };
  const prompts: Record<JobKind, string> = {
    outline: `请结合本书题材、已有设定和目标篇幅，先拟订${body.planning_mode === "fixed" ? "固定分卷与章节" : "连载分卷阶段"}的大纲生成计划，说明每卷具体内容、详细程度与预计用量，供我补充和确认。`,
    "story-design": `请结合本书已确认大纲和现有档案，先拟订${types[body.design_type || "character"]}设计计划，说明分组、数量、关系与每张档案的详细程度，供我补充和确认。`,
    "chapter-outline":
      "请先读取本章状态、已确认总纲和前文章节记忆，为本章拟订详细情节章纲，写明目标、阻碍、行动、转折和章末接续点。",
    "scene-plan":
      "请读取本章已确认章纲和前文，细化本章场景任务单，包含各场景目标、地点、人物与推进作用。",
    generate:
      "请先读取本章状态、已确认章纲、作品设定和前文记忆，按目标字数创作本章正文。已有正文时先让我核对覆盖范围。",
    revise: "请读取本章完整正文与章纲，按下面的要求修订本章，保留旧稿版本：",
    index:
      "请核对本章当前正文版本，为本章更新故事记忆。在执行入库前展示要确认的正文版本。",
    analysis: `请分析本书第 ${body.start || 1}–${body.end || 10} 章，关注${({ "book-summary": "前情提要", "consistency-check": "连续性和设定一致性", "character-development": "人物关系与成长弧", "plot-planning": "情节推进与伏笔" } as Record<string, string>)[body.skill || "book-summary"]}，结合真实前文给出具体证据和建议。`,
  };
  stageAssistantPrompt(
    body.book_id,
    [prompts[body.kind], body.prompt].filter(Boolean).join("\n\n"),
    body.chapter_id ?? null,
  );
}
