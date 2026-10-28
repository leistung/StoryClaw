import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import api, { extractError } from "@/lib/http";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
type Fact = {
  id: string;
  chapter_id: number;
  subject: string;
  statement: string;
  quote: string;
  kind: string;
  certainty: string;
  holder: string;
  known_by: string[];
  public: boolean;
  story_time: string;
  causes: string[];
  valid_from: number;
  valid_until: number | null;
  review_status: string;
  version: number;
  active: boolean;
};
function FactEditor({ fact, bid }: { fact: Fact; bid: number }) {
  const [value, setValue] = useState(fact);
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();
  async function save(status: string) {
    setBusy(true);
    try {
      const { id, chapter_id, active, valid_from, ...body } = value;
      void id;
      void chapter_id;
      void active;
      void valid_from;
      const r = await api.put(`/books/${bid}/narrative/facts/${fact.id}`, {
        ...body,
        review_status: status,
      });
      setValue({ ...r.data, active: fact.active });
      await qc.invalidateQueries();
      toast.success("记忆审阅已保存，相关章纲需要重新核对");
    } catch (e) {
      toast.error(extractError(e, "保存失败"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <article>
      <strong>
        第{fact.valid_from}章 · {fact.subject}
      </strong>
      <p>{fact.statement}</p>
      <blockquote>原文证据：{fact.quote}</blockquote>
      <p>
        {value.review_status} ·{" "}
        {fact.active ? "当前索引版本" : "旧版本（不作为当前事实）"}
      </p>
      <details>
        <summary>审阅人物知识与时间</summary>
        <label>
          事实／信念描述
          <textarea
            value={value.statement}
            onChange={(e) => setValue({ ...value, statement: e.target.value })}
          />
        </label>
        <div className="studio-fields">
          <label>
            性质
            <select
              value={value.kind}
              onChange={(e) => setValue({ ...value, kind: e.target.value })}
            >
              <option value="event">事件</option>
              <option value="state">状态</option>
              <option value="belief">角色信念</option>
              <option value="rule">世界规则</option>
              <option value="promise">伏笔／承诺</option>
            </select>
          </label>
          <label>
            可信度
            <select
              value={value.certainty}
              onChange={(e) =>
                setValue({ ...value, certainty: e.target.value })
              }
            >
              <option value="observed">原文明确发生</option>
              <option value="claim">角色说法／传闻</option>
              <option value="inference">推断</option>
            </select>
          </label>
        </div>
        <input
          placeholder="信念持有者（角色信念时必填）"
          value={value.holder}
          onChange={(e) => setValue({ ...value, holder: e.target.value })}
        />
        <input
          placeholder="已经知道的人物，逗号分隔"
          value={value.known_by.join(",")}
          onChange={(e) =>
            setValue({
              ...value,
              known_by: e.target.value
                .split(/[,，]/)
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
        />
        <label>
          <input
            type="checkbox"
            checked={value.public}
            onChange={(e) => setValue({ ...value, public: e.target.checked })}
          />{" "}
          作者确认这是公开常识，所有视角可以引用
        </label>
        <input
          placeholder="故事内时间，例如：第三年冬／当夜"
          value={value.story_time}
          onChange={(e) => setValue({ ...value, story_time: e.target.value })}
        />
        <label>
          有效至第几章（留空表示未定）
          <input
            type="number"
            min={fact.valid_from}
            value={value.valid_until ?? ""}
            onChange={(e) =>
              setValue({
                ...value,
                valid_until: e.target.value ? +e.target.value : null,
              })
            }
          />
        </label>
        <input
          placeholder="因果依据的记录ID，逗号分隔"
          value={value.causes.join(",")}
          onChange={(e) =>
            setValue({
              ...value,
              causes: e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
        />
        <small>记录ID：{fact.id}</small>
      </details>
      <Button
        disabled={busy || !fact.active}
        onClick={() => void save("confirmed")}
      >
        确认并保存
      </Button>
      <Button
        variant="outline"
        disabled={busy || !fact.active}
        onClick={() => void save("rejected")}
      >
        排除此条
      </Button>
    </article>
  );
}
export default function NarrativeState({
  bid,
  chapterId,
}: {
  bid: number;
  chapterId?: number | null;
}) {
  const qc = useQueryClient();
  const [page, setPage] = useState(0);
  const [name, setName] = useState("");
  const [aliases, setAliases] = useState("");
  const [entityId, setEntityId] = useState("");
  const [persona, setPersona] = useState("");
  const [before, setBefore] = useState(1);
  const [busy, setBusy] = useState(false);
  const { data: facts = [] } = useQuery<Fact[]>({
    queryKey: ["narrative-facts", bid, page],
    queryFn: () =>
      api
        .get(`/books/${bid}/narrative/facts`, { params: { offset: page * 50 } })
        .then((r) => r.data),
  });
  const { data: entities = [] } = useQuery<
    { id: string; name: string; aliases: string[] }[]
  >({
    queryKey: ["narrative-entities", bid],
    queryFn: () =>
      api.get(`/books/${bid}/narrative/entities`).then((r) => r.data),
  });
  const { data: chapter } = useQuery<{ number: number; content_hash: string }>({
    queryKey: ["narrative-chapter", chapterId],
    queryFn: () => api.get(`/chapters/${chapterId}`).then((r) => r.data),
    enabled: !!chapterId,
  });
  useEffect(() => {
    if (chapter) setBefore(chapter.number);
  }, [chapter?.number]);
  const [manual, setManual] = useState({
    subject: "",
    statement: "",
    quote: "",
  });
  const { data: view } = useQuery({
    queryKey: ["narrative-view", bid, before, persona],
    queryFn: () =>
      api
        .get(`/books/${bid}/narrative/view`, { params: { before, persona } })
        .then((r) => r.data),
  });
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await qc.invalidateQueries();
      toast.success("已保存");
    } catch (e) {
      toast.error(extractError(e, "操作失败"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <section>
        <h3>人物身份与别名</h3>
        <p>
          把姓名、称呼和化名明确映射到同一个人物；有歧义时要求人工核对，不自动合并同名人物。
        </p>
        <input
          placeholder="标准名"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          placeholder="别名，逗号分隔"
          value={aliases}
          onChange={(e) => setAliases(e.target.value)}
        />
        <Button
          disabled={busy || !name.trim()}
          onClick={() =>
            void act(() =>
              entityId
                ? api.put(`/books/${bid}/narrative/entities/${entityId}`, {
                    name,
                    aliases: aliases
                      .split(/[,，]/)
                      .map((s) => s.trim())
                      .filter(Boolean),
                  })
                : api.post(`/books/${bid}/narrative/entities`, {
                    name,
                    aliases: aliases
                      .split(/[,，]/)
                      .map((s) => s.trim())
                      .filter(Boolean),
                  }),
            )
          }
        >
          保存身份映射
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            setEntityId("");
            setName("");
            setAliases("");
          }}
        >
          新映射
        </Button>
        {entities.map((e) => (
          <p key={e.id}>
            {e.name} · {e.aliases.join("、") || "暂无别名"}{" "}
            <Button
              variant="ghost"
              onClick={() => {
                setEntityId(e.id);
                setName(e.name);
                setAliases(e.aliases.join(","));
              }}
            >
              编辑
            </Button>
          </p>
        ))}
      </section>
      <section>
        <h3>本章视角与人物知情范围</h3>
        <p>
          选择人物后，结构化记忆只提供已知或作者公开的事实；信念、传闻与客观事实分别标注。原文检索仍需结合叙事视角审阅。
        </p>
        <input
          placeholder="人物标准名或别名；留空使用全知叙述"
          value={persona}
          onChange={(e) => setPersona(e.target.value)}
        />
        <label>
          查看第几章开始前的知识
          <input
            type="number"
            min={1}
            value={before}
            onChange={(e) => setBefore(+e.target.value)}
          />
        </label>
        <Button
          disabled={busy || !chapterId}
          onClick={() =>
            void act(() =>
              api.put(`/books/${bid}/narrative/focus/${chapterId}`, {
                persona,
              }),
            )
          }
        >
          应用到当前选中章节
        </Button>
        {!chapterId && <p>先在创作页选择章节，再回到这里设置视角。</p>}
        {view && (
          <details>
            <summary>
              可见 {view.facts.length} 条 · 隐去 {view.withheld} 条未授权知识
            </summary>
            <pre className="studio-preview">
              {JSON.stringify(view, null, 2)}
            </pre>
          </details>
        )}
      </section>
      <section>
        <h3>事实、伏笔与信念审阅</h3>
        <p>
          来自审阅入库时的原文证据。模型提炼默认是候选；作者确认不等于让每个角色自动知晓。改稿使旧来源失效，因果引用不能成环或引用未来章节。
        </p>
        <details>
          <summary>从当前选中章节手动登记一条证据</summary>
          <input
            placeholder="人物或对象"
            value={manual.subject}
            onChange={(e) => setManual({ ...manual, subject: e.target.value })}
          />
          <textarea
            placeholder="事实／状态描述"
            value={manual.statement}
            onChange={(e) =>
              setManual({ ...manual, statement: e.target.value })
            }
          />
          <textarea
            placeholder="对应原文中连续存在的证据片段"
            value={manual.quote}
            onChange={(e) => setManual({ ...manual, quote: e.target.value })}
          />
          <Button
            disabled={
              busy ||
              !chapterId ||
              !chapter ||
              !manual.subject ||
              manual.statement.length < 2 ||
              manual.quote.length < 2
            }
            onClick={() =>
              void act(() =>
                api.post(`/books/${bid}/narrative/facts`, {
                  ...manual,
                  chapter_id: chapterId,
                  expected_hash: chapter?.content_hash,
                  kind: "state",
                  certainty: "claim",
                  review_status: "confirmed",
                }),
              )
            }
          >
            确认原文并登记
          </Button>
          <p>当前版本须先审阅入库。登记后可在下方标注知情人物和有效期。</p>
        </details>
        {facts.length ? (
          facts.map((f) => (
            <FactEditor key={f.id + ":" + f.version} fact={f} bid={bid} />
          ))
        ) : (
          <p>尚无结构化事实。章节审阅入库后会显示提炼结果。</p>
        )}
        <Button
          variant="outline"
          disabled={!page}
          onClick={() => setPage(page - 1)}
        >
          上一页
        </Button>
        <Button
          variant="outline"
          disabled={facts.length < 50}
          onClick={() => setPage(page + 1)}
        >
          下一页
        </Button>
      </section>
    </>
  );
}
