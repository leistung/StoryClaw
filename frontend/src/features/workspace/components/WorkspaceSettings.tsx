import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
export default function WorkspaceSettings({
  autoSaveMs,
  setAutoSaveMs,
  llmReady,
  embeddingReady,
  onGoConfig,
}: {
  autoSaveMs: number;
  setAutoSaveMs: (ms: number) => void;
  llmReady: boolean;
  embeddingReady: boolean;
  onGoConfig: () => void;
}) {
  return (
    <div className="p-6 max-w-2xl space-y-8">
      <div>
        <h2 className="text-xl font-semibold">工作区设置</h2>
        <p className="text-sm text-muted-foreground mt-2">
          调整创作习惯，查看平台模型配置状态。
        </p>
      </div>
      <section className="border rounded-xl p-5 bg-card space-y-3">
        <label htmlFor="autosave" className="text-sm font-medium">
          自动保存间隔（秒）
        </label>
        <Input
          id="autosave"
          type="number"
          min={1}
          max={300}
          value={autoSaveMs / 1000}
          onChange={(e) => {
            const n = Number(e.target.value);
            if (n >= 1 && n <= 300) setAutoSaveMs(n * 1000);
          }}
        />
        <p className="text-xs text-muted-foreground">
          编辑章节后按此间隔保存正文。
        </p>
      </section>
      <section className="border rounded-xl p-5 bg-card space-y-4">
        <h3 className="font-medium">平台模型</h3>
        <div className="flex justify-between text-sm">
          <span>对话与写作</span>
          <span>{llmReady ? "已配置" : "尚未就绪"}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span>上下文向量模型</span>
          <span>{embeddingReady ? "已配置" : "尚未就绪"}</span>
        </div>
        <p className="text-xs text-muted-foreground">
          模型和密钥由平台管理员统一配置，创作者无需填写 API Key。
        </p>
        <Button variant="outline" onClick={onGoConfig}>
          查看配置说明
        </Button>
      </section>
    </div>
  );
}
