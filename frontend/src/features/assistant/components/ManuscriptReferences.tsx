import { X, FileText } from "lucide-react";
import type { ManuscriptReference } from "@/features/assistant/draft-store";

export default function ManuscriptReferences({
  items,
  onRemove,
}: {
  items: ManuscriptReference[];
  onRemove?: (index: number) => void;
}) {
  return (
    <div className="assistant-references">
      {items.map((item, i) => (
        <div className="assistant-reference" key={`${item.chapter_id}-${i}`}>
          <details>
            <summary>
              <FileText size={13} />
              <span>
                {item.title} ·{" "}
                {item.kind === "chapter"
                  ? "完整章节"
                  : item.kind === "cursor"
                    ? `光标 · 第 ${item.line_start} 行`
                    : `第 ${item.line_start}–${item.line_end} 行`}
              </span>
              <small>
                {item.kind === "selection"
                  ? "选中片段"
                  : item.kind === "cursor"
                    ? "插入位置"
                    : "章节引用"}
              </small>
            </summary>
            {item.text ? (
              <pre>{item.text}</pre>
            ) : (
              <p>发送后由助手读取本章正文、章纲和作品资料。</p>
            )}
          </details>
          {onRemove && (
            <button
              type="button"
              aria-label={`移除引用：${item.title}`}
              onClick={() => onRemove(i)}
            >
              <X size={13} />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
