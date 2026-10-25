# 重构验收

后端流程测试只允许数据库名 `storyclaw_refactor_test`。先创建一个隔离 PostgreSQL 和该数据库，再运行：

```sh
DATABASE_URL='postgresql+asyncpg://postgres:测试密码@127.0.0.1:55432/storyclaw_refactor_test' .venv/bin/python novel-lab/refactor_acceptance.py
```

不读取项目 `.env`，不清空用户库。模型调用被模拟，覆盖12章滚动生成/入库、500万字合成文本拆章、旧稿接管/分支、预算/版本保护等。测试数据留在隔离库，不写当前小说。

运行中容器只读烟测（密码通过环境变量提供）：

```sh
STORYCLAW_PASSWORD='本地账号密码' python3 novel-lab/architecture_smoke.py
```

前端检查：

```sh
npm test --prefix frontend
npx --prefix frontend tsc --noEmit -p frontend/tsconfig.json
npm run build --prefix frontend
```

真实模型小说试写要另行记录模型版本、用量、逐章审阅和上下文证据。模拟测试不等于真实模型质量、真实Milvus/Neo4j故障恢复或商业收入证明。详见 docs/AGENT-REFACTOR-STATUS.md。
