# StoryClaw

React + FastAPI + LangChain / LangGraph 的 AI 小说创作平台，目前处于 Demo 重构阶段。
包括作品与章节、AI 写作、知识库、社区、会员及积分页面。充值接口的模拟支付默认关闭，尚未接入真实支付渠道。

## 本地运行

启动 Docker Desktop，在项目根目录执行：

```bash
# 仅首次且不存在 .env 时执行，已有配置不要覆盖
cp -n .env.example .env
docker compose --env-file .env -f docker/docker-compose.yml up -d --build
```

创作站 http://localhost:5173，独立运营中台 http://localhost:5174，后端文档 http://localhost:8010/docs。
在 `.env` 中设置 `BACKEND_HOST_PORT`、`FRONTEND_HOST_PORT` 可改变宿主机映射端口；容器内部保持 8000、5173。
只改变后端宿主机端口时，Docker 前端代理无需修改。
改变前端端口时同步检查 `.env` 的 `CORS_ORIGINS`。
本机直接运行前端时使用 `VITE_PROXY_TARGET=http://localhost:8010 npm run dev`（在 frontend 目录执行）。

```bash
docker compose --env-file .env -f docker/docker-compose.yml ps
docker compose --env-file .env -f docker/docker-compose.yml logs -f --tail=100 backend
docker compose --env-file .env -f docker/docker-compose.yml down
```

首次到 `/register` 注册。账号统一使用平台模型；启动不会自动创建管理员。
现有 Compose 使用热重载和开发服务器，生产部署方案见重构文档。
已有数据库的部署不要更换项目名或删除数据卷；`down` 不加 `-v`。

## 创作流程与架构

主文档：[小说工作流与 AI 架构](docs/NOVEL-WORKFLOW.md)。包含开书所需档案、生成依赖、人工确认、逐章上下文、向量/图谱入库、异常处理及实现边界。索引细节见 [三库设计](docs/KNOWLEDGE-DESIGN.md)。

## 目录与后续方案

- `frontend/`：创作站 React 页面、组件、状态及 API。
- `admin-frontend/`：独立运营中台，拥有自己的依赖、构建、登录状态及 Docker 服务。
- `backend/`：FastAPI、业务模型、接口及 Alembic 迁移。
- `packages/storyclaw/`：Agent 图、工具、上下文及 RAG。
- `skills/`：写作技能；`configs/`：模型、定价及会员配置。
- `docker/`：容器编排；`scripts/`：测试脚本。

完整目标架构、实施顺序、验收及迁移方式见 [平台重构方案](docs/REFACTOR-PLAN.md)。

## 统一平台与运营中台

注册后前往登录页，登录后进入工作台。模型由管理员统一配置，不再提供本地版选择。
旧账号及作品保留，启动会将账号版本归一为平台版本；旧个人模型记录不会自动转换为平台密钥。

先注册自己的账号，再将它设为管理员：

```bash
docker compose --env-file .env -f docker/docker-compose.yml exec backend python -m app.admin_cli 你的用户名
```

运营中台位于独立的 `admin-frontend/` React 应用，在 http://localhost:5174 单独登录，可管理模型、向量模型、定价和会员，查询用户数据、调整积分、查看日志。创作站不再包含后台页面，旧 `/admin` 地址会跳转到独立中台。
模型先保存，再在定价中配置对应平台编号的积分价格；没有有效定价的模型不允许调用。
新增表在当前 Demo 启动时自动创建；已有 Alembic 管理的数据库可使用 `0008_platform` 迁移，未建立迁移基线的旧库不要直接盲目执行全量迁移。

模拟支付默认禁用，真实支付尚未接入；当前会员套餐管理不等于已实现支付及会员到期权益闭环。
数据库仍使用 PostgreSQL + Milvus + Neo4j；见 [小说上下文与三库设计](docs/KNOWLEDGE-DESIGN.md)。

## 开发热更新

首次或依赖变更时构建一次：

```bash
docker compose --env-file .env -f docker/docker-compose.yml up -d --build
```

之后直接改本机文件：React/样式由 Vite 更新；后端和 Agent Python 代码、技能 Markdown 变更会触发 Uvicorn 自动重载。
Docker Desktop 使用轮询检测文件变化。后端重载会短暂重启应用进程，正在进行的生成请求可能中断。
`.env` / Compose 改动需重新 `up -d`；Python/npm 依赖改动需重新构建。数据库表结构变更仍需迁移。

也可以创建一个新的开发管理员（密码通过交互输入，不写入源码）：

```bash
docker compose --env-file .env -f docker/docker-compose.yml exec backend python -m app.admin_cli admin --create
```


## Docker 服务精简与双前端

目前共 8 个服务：frontend、admin-frontend、backend、postgres、milvus、neo4j、etcd、minio。
已移除未使用的 Redis，以及开发环境未使用的可选 Nginx 服务。
保留 etcd 和 MinIO 是因为当前 Milvus standalone 使用它们存储元数据与对象数据，不能单独删除。
本次精简不删除业务数据库及知识库卷，也不执行全局 Docker prune。

创作站与中台通过各自的 `/api` 代理访问同一 FastAPI，所有管理接口仍校验管理员权限。
两站登录互相独立（中台使用 `sc_admin_token`），不会在跨站跳转时传递 Token；退出其中一个不会退出另一个。
网站分开部署本身不是权限隔离，后端的管理员校验仍是最终边界。

`.env` 配置：

```dotenv
FRONTEND_HOST_PORT=5173
ADMIN_HOST_PORT=5174
ADMIN_PUBLIC_URL=http://localhost:5174
WRITER_PUBLIC_URL=http://localhost:5173
```

`*_HOST_PORT` 改变 Docker 映射，`*_PUBLIC_URL` 改变站点跳转链接；更换端口或域名时同步更新。
两个前端都支持代码和样式热更新。新建中台或修改依赖时执行：

```bash
docker compose --env-file .env -f docker/docker-compose.yml up -d --build --remove-orphans
```

本地单独开发中台：在 `admin-frontend/` 执行 `npm ci` 和 `npm run dev`，默认代理到 localhost:8010。

智谱 GLM-5.1 / Embedding-3 的接入与开发积分说明见 [GLM 接入说明](docs/GLM-INTEGRATION.md)。

## 长篇小说实测

`novel-lab/` 包含原创小说设定、功能设计、API 测试与可恢复的40章生成脚本。参阅 [实验说明](novel-lab/README.md)、[设计](novel-lab/DESIGN.md) 与 [已核实的样章结果](novel-lab/VALIDATION.md)。运行状态以实验报告为准。
