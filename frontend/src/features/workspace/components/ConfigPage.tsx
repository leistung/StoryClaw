import { useState, useEffect } from "react";
import { prepareJobPrompt } from "@/features/assistant/prompts";
import { toast } from "sonner";
import { stageAssistantPrompt } from "@/features/assistant/draft-store";
import { Link } from "react-router-dom";
import { extractError } from "@/lib/http";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listConfigEntities,
  createConfigEntity,
  updateConfigEntity,
  deleteConfigEntity,
} from "@/features/workspace/api";
import type { ConfigEntity, ConfigEntityType, EntityKv } from "@/types";
import { Plus, Trash2, Save, Database, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface ConfigPageProps {
  bid: number;
  entityType: ConfigEntityType;
}

const TYPE_LABELS: Record<
  ConfigEntityType,
  { label: string; categories: string[] }
> = {
  world: {
    label: "世界观",
    categories: ["时代地理", "社会制度", "能力与代价", "叙事规则"],
  },
  character: { label: "角色", categories: ["主角", "配角", "反派", "路人"] },
  scene: { label: "场景", categories: ["室内", "室外", "幻想", "回忆"] },
  item: { label: "物品", categories: ["武器", "道具", "信物", "消耗品"] },
  plot: { label: "情节", categories: ["主线", "支线", "伏笔", "转折"] },
  outline: { label: "大纲", categories: ["卷", "章", "段"] },
};

export default function ConfigPage({ bid, entityType }: ConfigPageProps) {
  const qc = useQueryClient();
  const meta = TYPE_LABELS[entityType];
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data: listData, isLoading } = useQuery({
    queryKey: ["config-entities", bid, entityType],
    queryFn: () => listConfigEntities(bid, entityType),
  });
  const items = listData?.items || [];
  const selected = items.find((e) => e.id === selectedId) || null;

  useEffect(() => {
    if (!selectedId && items.length > 0) setSelectedId(items[0].id);
    if (selectedId && !items.find((e) => e.id === selectedId)) {
      setSelectedId(items.length > 0 ? items[0].id : null);
    }
  }, [items, selectedId]);

  const prepareDesign = () => {
    try {
      prepareJobPrompt({
        book_id: bid,
        kind: "story-design",
        design_type: entityType as "character" | "world" | "plot",
      });
    } catch (e) {
      toast.error(extractError(e, "请先处理助手中的草稿"));
    }
  };
  const createMut = useMutation({
    mutationFn: () =>
      createConfigEntity(bid, entityType, {
        name: `新${meta.label}${items.length + 1}`,
        category: meta.categories[0],
      }),
    onSuccess: (e) => {
      qc.invalidateQueries({ queryKey: ["config-entities", bid, entityType] });
      setSelectedId(e.id);
    },
  });

  const delMut = useMutation({
    mutationFn: (eid: number) => deleteConfigEntity(bid, entityType, eid),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["config-entities", bid, entityType] }),
  });

  const updateMut = useMutation({
    mutationFn: ({
      eid,
      body,
    }: {
      eid: number;
      body: Record<string, unknown>;
    }) => updateConfigEntity(bid, entityType, eid, body),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["config-entities", bid, entityType] }),
  });

  return (
    <div className="flex h-full flex-col">
      {["character", "world", "plot"].includes(entityType) && (
        <div className="border-b px-4 py-2 flex items-center gap-3 text-xs">
          <Button size="sm" variant="outline" onClick={prepareDesign}>
            向助手提出{meta.label}设计需求
          </Button>
          <span className="text-muted-foreground">
            需求将填入右侧输入框，可修改后发送；采用草案后新增卡片。
          </span>
          <Link to={`/workspace/${bid}?tab=任务`}>查看任务 →</Link>
        </div>
      )}
      <div className="flex flex-1 min-h-0">
        <div className="w-64 border-r flex flex-col bg-muted/40">
          <div className="p-2 border-b bg-background flex items-center justify-between">
            <span className="text-sm font-medium text-foreground">
              {meta.label}列表
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-primary"
              onClick={() => createMut.mutate()}
              disabled={createMut.isPending}
              title={`新增${meta.label}`}
            >
              <Plus size={16} />
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="p-3 text-sm text-muted-foreground">加载中...</div>
            ) : items.length === 0 ? (
              <div className="p-3 text-sm text-muted-foreground">
                暂无{meta.label}，点击 + 新增
              </div>
            ) : (
              items.map((e) => (
                <div
                  key={e.id}
                  onClick={() => setSelectedId(e.id)}
                  className={`px-3 py-2 cursor-pointer border-b flex items-center justify-between group ${
                    selectedId === e.id
                      ? "bg-primary/10 border-l-2 border-l-primary"
                      : "hover:bg-muted"
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-foreground truncate">
                      {e.name}
                    </div>
                    {e.category && (
                      <span className="text-[10px] text-muted-foreground">
                        {e.category}
                      </span>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="opacity-0 group-hover:opacity-100 h-6 w-6 text-destructive hover:bg-destructive/10"
                    title="删除"
                    onClick={(ev) => {
                      ev.stopPropagation();
                      delMut.mutate(e.id);
                    }}
                  >
                    <Trash2 size={12} />
                  </Button>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {selected ? (
            <EntityEditor
              key={selected.id}
              entity={selected}
              categories={meta.categories}
              onSave={(body) => updateMut.mutate({ eid: selected.id, body })}
              saving={updateMut.isPending}
              onQueryMemory={() => {
                try {
                  stageAssistantPrompt(
                    bid,
                    `请检索本书前文中与${meta.label}“${selected?.name || ""}”相关的记忆、实体关系和证据，说明与现有设定的关联。`,
                    null,
                  );
                } catch (e) {
                  toast.error(extractError(e, "请先处理助手中的草稿"));
                }
              }}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              选择左侧{meta.label}或点击 + 新增
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface EntityEditorProps {
  entity: ConfigEntity;
  categories: string[];
  onSave: (body: Record<string, unknown>) => void;
  saving: boolean;
  onQueryMemory: () => void;
}

function EntityEditor({
  entity,
  categories,
  onSave,
  saving,
  onQueryMemory,
}: EntityEditorProps) {
  const [name, setName] = useState(entity.name);
  const [category, setCategory] = useState(entity.category);
  const [description, setDescription] = useState(entity.description);
  const [imageUrl, setImageUrl] = useState(entity.image_url || "");
  const [kvs, setKvs] = useState<EntityKv[]>(entity.kv || []);
  const [extraText, setExtraText] = useState(
    entity.extra_json ? JSON.stringify(entity.extra_json, null, 2) : "",
  );

  const addKv = () => setKvs([...kvs, { key: "", value: "" }]);
  const updKv = (i: number, field: "key" | "value", val: string) =>
    setKvs(kvs.map((k, idx) => (idx === i ? { ...k, [field]: val } : k)));
  const delKv = (i: number) => setKvs(kvs.filter((_, idx) => idx !== i));

  const handleSave = () => {
    let extraJson: Record<string, unknown> | null = null;
    if (extraText.trim()) {
      try {
        extraJson = JSON.parse(extraText);
      } catch {
        alert("扩展字段 JSON 格式错误");
        return;
      }
    }
    onSave({
      name,
      category,
      description,
      image_url: imageUrl || null,
      extra_json: extraJson,
      kv: kvs.filter((k) => k.key.trim()),
    });
  };

  return (
    <div className="p-4 space-y-4 max-w-2xl">
      <div className="space-y-3">
        <div className="space-y-1">
          <Label className="text-xs">名称</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">类别</Label>
          <Select
            value={category || "__none"}
            onValueChange={(v) => setCategory(v === "__none" ? "" : (v ?? ""))}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none">无</SelectItem>
              {categories.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">描述</Label>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">图片 URL（头像/封面）</Label>
          <Input
            value={imageUrl}
            onChange={(e) => setImageUrl(e.target.value)}
            placeholder="https://..."
          />
          {imageUrl && (
            <img
              src={imageUrl}
              alt="preview"
              className="mt-2 w-24 h-24 rounded object-cover border"
            />
          )}
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted-foreground">自定义字段</span>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-primary text-xs"
            onClick={addKv}
          >
            <Plus size={12} /> 添加字段
          </Button>
        </div>
        <div className="space-y-1.5">
          {kvs.length === 0 && (
            <div className="text-xs text-muted-foreground">无自定义字段</div>
          )}
          {kvs.map((kv, i) => (
            <div key={i} className="flex gap-1.5 items-center">
              <Input
                value={kv.key}
                onChange={(e) => updKv(i, "key", e.target.value)}
                placeholder="字段名"
                className="w-28 text-xs"
              />
              <Input
                value={kv.value}
                onChange={(e) => updKv(i, "value", e.target.value)}
                placeholder="值"
                className="flex-1 text-xs"
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-destructive hover:bg-destructive/10"
                onClick={() => delKv(i)}
              >
                <X size={12} />
              </Button>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-xs">扩展字段（JSON，可选）</Label>
        <Textarea
          value={extraText}
          onChange={(e) => setExtraText(e.target.value)}
          rows={3}
          placeholder='{"chapter_start": 1, "chapter_end": 5}'
          className="text-xs font-mono"
        />
      </div>

      <Button onClick={handleSave} disabled={saving}>
        <Save size={14} /> {saving ? "保存中..." : "保存"}
      </Button>

      <div className="border-t pt-3">
        <Button
          variant="ghost"
          size="sm"
          className="text-xs text-muted-foreground"
          onClick={onQueryMemory}
        >
          <Database size={12} /> 向助手查询相关记忆
        </Button>
      </div>
    </div>
  );
}
