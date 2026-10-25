# 自动化测试

| 位置 | 测试对象 | 是否连接实际服务 |
| --- | --- | --- |
| `backend/packages/harness/tests/` | AI 门面、上下文、模型适配、方法资源等纯逻辑 | 模型使用模拟，无费用 |
| `backend/tests/unit/` | 平台数据契约、配置、边界与文本质量 | 不连接数据库或模型 |
| `backend/tests/integration/` | 权限、配置、账务、Run、来源与索引状态 | 仅隔离 PostgreSQL，模型使用模拟 |
| `backend/tests/e2e/test_*.py` | 完整 API 与逐章写作流程 | 仅隔离 PostgreSQL，模型使用模拟 |
| `backend/tests/e2e/architecture_smoke.py` | 现有平台的接口、方法与 Worker 领取 | 显式执行，不调用模型，不修改正文 |
| `backend/evaluations/` | 真实模型写作质量与长篇实验 | 显式执行，可能产生费用 |

在仓库根目录运行：

```bash
make test                   # AI包、后端单元和作者端测试；不调用模型
make test-backend           # 仅离线 Python 测试
# 全量回归必须显式指定一次性测试数据库，拒绝生产数据库名
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/storyclaw_refactor_test \
  make test-integration
```

统一 Python 入口是 `backend/scripts/test.py`，支持 `--suite offline|integration|all`、`--pattern`；不会创建、删除生产数据，不会自动启动付费实验。集成测试库需预先创建，测试会在其中创建表和测试数据。

两个前端各自保留测试或构建入口：作者端 `frontend/tests`，管理端当前使用 TypeScript 与构建检查，尚无独立自动化用例，不新建空测试目录。
