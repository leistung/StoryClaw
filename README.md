# StoryClaw

React + FastAPI + LangChain / LangGraph 的 AI 小说创作平台，包含作者端和独立运营中台。支持选题、总纲、逐章规划、正文生成、审阅入库、旧稿接管、连续任务和投稿准备。

**当前是开发版本，尚未完成商业上线验收。** 在线支付、外站自动投稿和百万字真实生成质量未验收。具体实现与限制从 [00 阅读导航](docs/00-阅读导航.md) 开始了解。

## 启动

需要 Docker Engine 和 Compose；macOS 通常使用 Docker Desktop。在仓库根目录执行：

```bash
# 仅首次且不存在.env时复制，不覆盖已有配置
cp -n .env.example .env
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

- 作者端：<http://localhost:5173>
- 运营中台：<http://localhost:5174>
- API 文档：<http://localhost:8010/docs>

先注册账号，再按 [02 本地运行](docs/02-本地运行与配置.md) 设置管理员、文本模型、积分定价和Embedding。没有默认管理员或默认密码。端口以 `.env` 为准，平台模型配置优先读取数据库。

当前 Compose 启动9个服务，使用开发热更新。不是可直接用于正式运营的生产配置；不要为排错删除持久卷。

## 目录

```text
frontend/         React作者端
admin-frontend/   React运营中台
backend/          FastAPI应用、AI包、配置、测试与真实模型实验
deploy/           Docker、Nginx及启动配置
docs/             按00—13阅读的现行手册，archive保留历史资料
```

AI核心位于 `backend/packages/harness/storyclaw`；平台接口位于 `backend/app/gateway`。写作方法随AI包安装，不依赖仓库根目录的额外资源文件夹。

## 从哪里读起

| 目标 | 文档 |
| --- | --- |
| 理解项目现状 | [01 项目概览](docs/01-项目概览与实现现状.md) |
| 启动、注册、端口与热更新 | [02 本地运行](docs/02-本地运行与配置.md) |
| 阅读目录和每个后端/AI文件 | [03 源码导航](docs/03-源码目录与阅读路线.md) |
| 理解运行原理和AI机制 | [04 系统架构](docs/04-系统架构与运行原理.md)、[06 Agent与Skill](docs/06-Agent工作流与Skill原理.md) |
| 理解作者如何写小说 | [05 创作流程](docs/05-作者使用与小说创作流程.md)、[07 上下文记忆](docs/07-上下文记忆与三库设计.md) |
| 了解上线差距 | [11 部署](docs/11-部署运维与上线准备.md)、[13 限制与路线](docs/13-已知限制与后续路线.md) |

完整目录、推荐顺序和文档可信范围见 [00 阅读导航](docs/00-阅读导航.md)。旧方案与旧实验在 `docs/archive`，不作为当前配置或功能承诺。

## 开发检查

```bash
make test           # 离线AI包、后端单元、作者端测试；无付费模型调用
make docs-check     # 检查现行文档链接、编号及Git忽略规则
# 提供明确的隔离数据库DATABASE_URL后，才运行全量集成回归
make test-integration
```

最近一次代码验收（2026-10-26）：96项Python、4项作者端测试通过；包含模拟模型及隔离数据库，不代表真实文学质量或生产规模验收。本次文档维护只运行文档与忽略规则检查，不重复调用模型。

测试入口与费用边界见 [10 开发测试](docs/10-开发测试与文档维护.md)。真实模型实验放在 `backend/evaluations`，必须显式运行并控制预算；密钥和用户私密正文不进入仓库。
