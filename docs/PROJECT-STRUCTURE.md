# StoryClaw 项目目录说明

按 2026-10-25 当前源码核对。描述的是实际职责，不把规划当成已经实现。下列相对链接以 docs/ 为基准。`.env` 的值、密钥、依赖安装目录、缓存、测试运行输出不逐项展开。

## 项目整体结构

```text
StoryClaw/
├── frontend/           作者端 React 应用
├── admin-frontend/     运营中台 React 应用
├── backend/            FastAPI、业务数据、权限、任务和积分
├── packages/storyclaw/ AI Python 包：推理、图工作流、工具与知识检索
├── skills/             AI 写作技能提示与参考材料
├── configs/            模型、价格、会员 YAML 初始配置
├── docker/             容器镜像、Compose 和基础设施初始化
├── docs/               产品、架构、知识库、流程和本说明
├── novel-lab/          真实写作实验、恢复脚本、样书与任务回执
├── scripts/            开发启动及烟测脚本
└── _legacy/            历史归档，非当前主应用入口
```

| 根目录文件/辅助目录 | 用途 |
| --- | --- |
| README.md | 项目说明和启动入口 |
| Makefile | 常用开发、迁移和运行命令 |
| .env / .env.example | 本机环境设置 / 配置样例；不要提交真实密钥 |
| .dockerignore / .gitignore | 容器构建上下文与 Git 忽略规则 |
| .git/ | 版本控制元数据 |
| .venv/ | 本机 Python 环境，非业务源码 |
| .idea/、.DS_Store | IDE/系统元数据，非运行逻辑 |

## 两个前端和辅助目录

- frontend/src/main.tsx：React 挂载、全局样式及应用初始化；App.tsx：路由与页面组织。
- frontend/src/pages/：首页、工作台、社区、阅读、消息、会员、登录/注册和帮助等页面。
- frontend/src/components/：章纲、大纲、知识库、任务、设定卡、发布和编辑器等功能面板；ui/ 是基础控件。
- frontend/src/lib/：API、后台任务、流式消息及编辑正文等客户端工具；stores/：登录状态；styles/：工作台等视觉样式；types.ts：共享接口类型；tests/：前端回归。
- admin-frontend/src/：独立运营应用；pages/Admin.tsx 是管理页面，components/AdminPlatform.tsx、ProductOperations.tsx 组织平台配置和运营功能；lib/、stores/、ui 控件承担相应客户端基础职责。两个前端共用后端。
- configs/models.yaml、pricing.yaml、membership.yaml：模型目录、积分定价、会员初始配置；已有数据库平台配置可以覆盖默认值。
- docker/docker-compose.yml：编排作者端、中台、后端、PostgreSQL、Milvus、Neo4j 及 Milvus 所需 etcd/MinIO。三个 Dockerfile 构建两个前端和后端；nginx/nginx.conf 为代理配置；scripts/init-pg.sql 初始化 PostgreSQL。MinIO 在此主要支撑 Milvus，不能由此断言已实现图片素材中心。
- skills/：每个技能目录的 SKILL.md 是 AI 产品自身的技能说明，references/ 放写作方法材料。write-chapter、modify-chapter、outline-planning、consistency-check 等由 AI 包按需加载；不是 Python 服务，也不自动执行其中所有动作。
- scripts/dev-start.sh：本地开发启动；smoke_test.py、test_generate_book.py：通用烟测/生成实验。
- novel-lab/：run.py 等早期试验入口；serial_smoke.py 是逐章真实验收；repair_serial_sample.py 是本次样书专项修订，snapshot_serial_sample.py 只读导出，quality.py 做样本文本检查，status.py/launch.py 辅助运行，tests/ 与 integration/ 保存实验测试；runs/ 存正文、状态、报告、检索结果和任务回执，不是程序源码。
- docs/：NOVEL-WORKFLOW.md 是写作场景和依赖规则；KNOWLEDGE-DESIGN.md 是知识设计；IDEATION-WORKFLOW.md 是选题流程；其他计划文档记录改版与产品设计，可能包含尚待实现部分。
- _legacy/：历史资料，当前 Compose 不以其作为主应用入口；不因目录名而直接删除其中内容。

## 先分清 backend 与 storyclaw

`backend` 是平台服务层：谁发请求、是否有权限、数据如何保存、任务怎么排队、扣多少积分、结果如何返回。

`packages/storyclaw` 是 AI 能力层：该问什么、参考什么、怎样规划和生成、调用什么工具、怎样检索小说上下文、怎样审核输出。

目前它们不是两个独立网络服务：后端进程安装并 import storyclaw 包，在启动时通过 deps.configure 注入模型/查库/工具适配器。两个前端走 HTTP 调后端，后端再通过 Python 调用 AI 包。包能连接向量库/图数据库，但不直接承担用户鉴权、业务 ORM 和积分账户管理。

## 后端入口与配置

| 文件 | 当前职责 |
| --- | --- |
| [requirements.txt](../backend/requirements.txt) | 后端 Python 依赖；AI 包依赖另见 packages/storyclaw/pyproject.toml。 |
| [alembic.ini](../backend/alembic.ini) | 数据库迁移工具入口配置。 |
| [app/__init__.py](../backend/app/__init__.py) | 将 app 声明为 Python 包。 |
| [app/main.py](../backend/app/main.py) | FastAPI 入口；注册路由、异常与跨域；启动时加载平台配置、向 AI 包注入数据适配器并启动任务消费者；开发期自动建表。 |
| [app/config.py](../backend/app/config.py) | 读取后端环境变量，定义数据库、鉴权、跨域等设置。 |
| [app/database.py](../backend/app/database.py) | 异步 SQLAlchemy 引擎、会话工厂、请求数据库依赖。 |
| [app/schemas.py](../backend/app/schemas.py) | 主要请求/响应 Pydantic 结构；部分新接口的结构就近定义在路由内。 |
| [app/admin_cli.py](../backend/app/admin_cli.py) | 管理员账号创建/权限设置的命令行入口；密码通过显式参数或标准输入提供。 |

## 后端 core/：公共 HTTP 基础能力

| 文件 | 当前职责 |
| --- | --- |
| [__init__.py](../backend/app/core/__init__.py) | 包标记。 |
| [admin.py](../backend/app/core/admin.py) | 管理员权限依赖；防止普通用户访问运营接口。 |
| [deps.py](../backend/app/core/deps.py) | 解析当前登录用户，供业务接口复用。 |
| [errors.py](../backend/app/core/errors.py) | 统一业务异常、错误码、标准错误响应结构。 |
| [logging.py](../backend/app/core/logging.py) | 结构化日志格式与请求耗时/状态日志中间件。 |
| [pagination.py](../backend/app/core/pagination.py) | 统一页码、每页数量及分页返回结构。 |
| [security.py](../backend/app/core/security.py) | 密码哈希与校验、JWT 签发解析、模型 API key 加解密。 |

## 后端 api/：HTTP 接口

| 文件 | 当前职责 |
| --- | --- |
| [__init__.py](../backend/app/api/__init__.py) | 路由包标记。 |
| [admin.py](../backend/app/api/admin.py) | 运营概览、用户数据、积分调整、日志、模型目录、向量模型和平台配置管理。 |
| [auth.py](../backend/app/api/auth.py) | 注册、登录、读取当前账号。 |
| [books.py](../backend/app/api/books.py) | 书籍 CRUD、统计、分卷接口、作品导出；卷接口也放在这里。 |
| [chapters.py](../backend/app/api/chapters.py) | 章节目录与正文 CRUD、正文版本历史、旧版本恢复；修改时触发索引/后文失效保护。 |
| [chat.py](../backend/app/api/chat.py) | AI 对话与流式响应、正文生成/修改、会话历史和反馈；负责鉴权、计费和写回，调用 AI runtime。 |
| [community.py](../backend/app/api/community.py) | 社区帖子、搜索、帖子书籍链接以及公开作品阅读接口。 |
| [config_entities.py](../backend/app/api/config_entities.py) | 世界观、角色、场景、物品、情节等设定卡 CRUD 与关联记忆查询；控制公开可操作的实体类型。 |
| [configs.py](../backend/app/api/configs.py) | 供前端读取模型目录、价格及可用状态。 |
| [ideation.py](../backend/app/api/ideation.py) | 开书前讨论与流式接口，持久化会话；方案不自动创建书籍。 |
| [jobs.py](../backend/app/api/jobs.py) | 后台任务提交、查询、取消与设计草案采用，包含章纲任务。 |
| [llm_configs.py](../backend/app/api/llm_configs.py) | 用户模型连接配置 CRUD；密钥处理依赖安全模块，实际是否使用取决于平台路由策略。 |
| [messages.py](../backend/app/api/messages.py) | 好友申请、同意/拒绝、好友列表、私信、未读统计。 |
| [outlines.py](../backend/app/api/outlines.py) | 大纲生成、读取、编辑及确认；保留直接调用接口，任务路径也复用相关逻辑。 |
| [product_ops.py](../backend/app/api/product_ops.py) | 点赞、评论、举报、钱包流水、会员订单及运营审核；当前多个产品域集中在一个文件。 |
| [publications.py](../backend/app/api/publications.py) | 作者发布状态、发布和撤回；公开阅读基于作品快照。 |
| [rag.py](../backend/app/api/rag.py) | 作者审阅后入库、知识检索、入库状态；真实切片/向量/图操作委托 AI 包。 |
| [reading_configs.py](../backend/app/api/reading_configs.py) | 阅读配置模板 CRUD 与 JSON 导入导出。 |
| [recharge.py](../backend/app/api/recharge.py) | 会员套餐读取、购买入口和充值历史；不等同于已接入真实支付渠道。 |
| [serial.py](../backend/app/api/serial.py) | 当前章纲读取、保存、确认，以及前文变更影响通知。 |
| [share.py](../backend/app/api/share.py) | 创建分享链接、读取分享内容；与正式社区发布是不同入口。 |
| [skills.py](../backend/app/api/skills.py) | 向前端提供写作 skill 元数据与说明。 |
| [writing.py](../backend/app/api/writing.py) | 润色、段内续写、批量写作兼容入口、分析、脑暴、标题、场景/对话增强、阅读配置生成、场景任务单。 |

## 后端 models/：PostgreSQL 数据模型

| 文件 | 当前职责 |
| --- | --- |
| [__init__.py](../backend/app/models/__init__.py) | 集中导出 ORM 模型，使建表和迁移能发现全部模型。 |
| [base.py](../backend/app/models/base.py) | SQLAlchemy 声明式基类。 |
| [user.py](../backend/app/models/user.py) | 账号、用户状态、平台相关用户字段。 |
| [book.py](../backend/app/models/book.py) | 书籍资料、作者归属、写作目标等。 |
| [volume.py](../backend/app/models/volume.py) | 书籍章节目录中的分卷记录；与大纲 JSON 的阶段规划不是同一种记录。 |
| [chapter.py](../backend/app/models/chapter.py) | 章节正文、排序、字数与入库状态等。 |
| [outline.py](../backend/app/models/outline.py) | 书籍大纲 JSON 与更新时间等。 |
| [config_entity.py](../backend/app/models/config_entity.py) | 设定实体与附加键值；当前内部章纲和影响状态也使用受限 workflow 类型记录。 |
| [credit.py](../backend/app/models/credit.py) | 用户 LLM 连接配置与积分流水。 |
| [message.py](../backend/app/models/message.py) | AI 对话消息；不是用户间私信表。 |
| [user_memory.py](../backend/app/models/user_memory.py) | 用户长期写作偏好，不是小说世界事实库。 |
| [ideation.py](../backend/app/models/ideation.py) | 开书讨论会话状态。 |
| [platform.py](../backend/app/models/platform.py) | 平台配置与操作/请求事件，不保存请求正文或明文密钥。 |
| [product.py](../backend/app/models/product.py) | 正文版本、持久任务、发布快照、帖子审核/评论/点赞/举报、会员订单和权益等。 |
| [post.py](../backend/app/models/post.py) | 社区帖子与帖子引用书籍的关联。 |
| [social.py](../backend/app/models/social.py) | 好友关系与用户间私信。 |
| [reading_config.py](../backend/app/models/reading_config.py) | 阅读样式/配置模板。 |
| [rag.py](../backend/app/models/rag.py) | SQL 中的章节切片、实体和关系记录结构；不要据此误判实时语义检索都在 PostgreSQL，主检索实现见 AI 包。 |

## 后端 services/：业务服务与 AI 数据适配

| 文件 | 当前职责 |
| --- | --- |
| [__init__.py](../backend/app/services/__init__.py) | 包标记。 |
| [agent_tools.py](../backend/app/services/agent_tools.py) | 实现 AI 只读工具的数据访问：查设定、记忆、大纲、前章、开书资料；工具定义和调用循环在 AI 包。 |
| [book_bootstrap.py](../backend/app/services/book_bootstrap.py) | 旧的自动开书初始化兼容钩子，已退役；不再无追踪地自动生成全部内容。 |
| [configs.py](../backend/app/services/configs.py) | 读取 models/pricing/membership YAML 默认配置。 |
| [content.py](../backend/app/services/content.py) | 清理允许的 HTML 标签，供正文阅读和社区输出使用。 |
| [creative_jobs.py](../backend/app/services/creative_jobs.py) | 角色、世界观等设计任务的 SQL/积分适配；实际设计推理调用 AI 包 design.py。 |
| [credits.py](../backend/app/services/credits.py) | 通过原子 SQL 扣减积分。 |
| [embedding_config.py](../backend/app/services/embedding_config.py) | 从平台配置解析向量模型连接；当前不从用户个人模型配置选择。 |
| [ideation_format.py](../backend/app/services/ideation_format.py) | 兼容导入转发，真正格式解析在 storyclaw/ideation/format.py。 |
| [ideation_workflow.py](../backend/app/services/ideation_workflow.py) | 兼容导入转发，真正讨论工作流在 storyclaw/ideation/。 |
| [jobs.py](../backend/app/services/jobs.py) | 持久任务执行、SQL 领取、心跳与消费者循环；当前由 API 进程启动，不是独立 Celery 服务；不会自动重试付费生成。 |
| [llm.py](../backend/app/services/llm.py) | 查平台/用户模型设置、解密密钥并选择模型；客户端协议构建由 AI 包 llm.py 实现。 |
| [memory.py](../backend/app/services/memory.py) | 读写用户写作偏好 SQL 记录；纯偏好编码和合并在 AI 包。 |
| [planning.py](../backend/app/services/planning.py) | 校验已确认总纲、规划编辑条件、前文章节正文和记忆是否就绪。 |
| [platform.py](../backend/app/services/platform.py) | 平台配置持久化与运行时刷新；数据库配置优先，YAML 是初始默认。 |
| [pricing.py](../backend/app/services/pricing.py) | 按模型价格和 token 用量计算平台积分；不是完整支付结算系统。 |
| [revisions.py](../backend/app/services/revisions.py) | 正文哈希、版本快照、编辑互斥与生成写回前版本检查。 |
| [scene_plan.py](../backend/app/services/scene_plan.py) | 兼容导入 AI 包场景单结构；没有独立场景推理实现。 |
| [serial.py](../backend/app/services/serial.py) | 章纲及其依赖指纹的 SQL 保存/确认、生成任务适配、后文失效和影响通知、索引复核解除通知。 |
| [setting_sync.py](../backend/app/services/setting_sync.py) | 旧的自动同步设定兼容钩子；不再自动用模型覆盖作者设定卡。 |
| [skill_loader.py](../backend/app/services/skill_loader.py) | 读取有权限的书籍、大纲、章纲、设定和历史正文；把普通数据交给 AI 包组合上下文。 |

## 后端数据库迁移

| 文件 | 当前职责 |
| --- | --- |
| [env.py](../backend/alembic/env.py) | 加载应用模型与数据库设置，运行迁移环境。 |
| [script.py.mako](../backend/alembic/script.py.mako) | 生成新迁移脚本时使用的模板。 |
| [versions/0001_init_tables.py](../backend/alembic/versions/0001_init_tables.py) | 初始业务表迁移。 |
| [versions/0002_user_memories.py](../backend/alembic/versions/0002_user_memories.py) | 用户长期偏好表迁移。 |
| [versions/0003_rag_tables.py](../backend/alembic/versions/0003_rag_tables.py) | RAG 相关 SQL 表迁移。 |
| [versions/0004_config_tables.py](../backend/alembic/versions/0004_config_tables.py) | 设定实体及附加配置表迁移。 |
| [versions/0005_reading_configs.py](../backend/alembic/versions/0005_reading_configs.py) | 阅读配置表迁移。 |
| [versions/0006_posts.py](../backend/alembic/versions/0006_posts.py) | 社区帖子及关联表迁移。 |
| [versions/0007_admin_social.py](../backend/alembic/versions/0007_admin_social.py) | 管理员/社交相关迁移。 |
| [versions/0008_platform.py](../backend/alembic/versions/0008_platform.py) | 平台配置与审计相关迁移。 |
| [versions/0009_product.py](../backend/alembic/versions/0009_product.py) | 任务、版本、发布、互动、订单权益等产品数据迁移。 |
| [versions/0010_ideation.py](../backend/alembic/versions/0010_ideation.py) | 开书讨论持久化迁移。 |

## 后端 tests/：自动化回归

| 文件 | 当前职责 |
| --- | --- |
| [test_model_adapter.py](../backend/tests/test_model_adapter.py) | 模型客户端适配相关测试。 |
| [test_llm_json_mode.py](../backend/tests/test_llm_json_mode.py) | 模型 JSON 输出模式相关测试。 |
| [test_embedding.py](../backend/tests/test_embedding.py) | 向量模型调用及行为相关测试。 |
| [test_platform.py](../backend/tests/test_platform.py) | 平台配置、用户权限及运营相关测试。 |
| [test_product.py](../backend/tests/test_product.py) | 任务、发布、互动和产品数据相关测试。 |
| [test_ideation.py](../backend/tests/test_ideation.py) | 选题讨论基础接口相关测试。 |
| [test_guided_ideation.py](../backend/tests/test_guided_ideation.py) | 引导式选题流程相关测试。 |
| [test_ideation_choices.py](../backend/tests/test_ideation_choices.py) | 可点击问题/答案选择相关测试。 |
| [test_ideation_format.py](../backend/tests/test_ideation_format.py) | 模型选题输出格式解析相关测试。 |
| [test_ideation_stream.py](../backend/tests/test_ideation_stream.py) | 选题流式数据相关测试。 |
| [test_ideation_workflow.py](../backend/tests/test_ideation_workflow.py) | 有限问答与方案流程相关测试。 |
| [test_novel_pipeline.py](../backend/tests/test_novel_pipeline.py) | 小说生成和入库流程相关测试。 |
| [test_novel_workflow.py](../backend/tests/test_novel_workflow.py) | 作者确认与写作依赖规则相关测试。 |
| [test_serial_workflow.py](../backend/tests/test_serial_workflow.py) | 逐章规划、确认门槛、改前章使后文过期及复核恢复的隔离集成测试。 |
| [test_continuity.py](../backend/tests/test_continuity.py) | 跨章复用检测、完整上章参考与审核修订相关测试。 |

## AI 包根目录与核心模块

| 文件 | 当前职责 |
| --- | --- |
| [pyproject.toml](../packages/storyclaw/pyproject.toml) | 可安装 Python 包的名称、版本、依赖及构建配置；src 是源码布局层，真正 import 名是 storyclaw。 |
| [src/storyclaw/__init__.py](../packages/storyclaw/src/storyclaw/__init__.py) | 包入口与导出组织。 |
| [src/storyclaw/config.py](../packages/storyclaw/src/storyclaw/config.py) | AI 包环境设置：skills、Milvus、Neo4j、向量模型等基础设施配置。 |
| [src/storyclaw/deps.py](../packages/storyclaw/src/storyclaw/deps.py) | 依赖注入契约：模型工厂、用户偏好、写作上下文、向量配置、检查点、工具执行；也保存请求级流式回调。 |
| [src/storyclaw/llm.py](../packages/storyclaw/src/storyclaw/llm.py) | 构建 OpenAI Chat、Anthropic、OpenAI Responses 协议客户端；优先使用后端注入工厂。 |
| [src/storyclaw/runtime.py](../packages/storyclaw/src/storyclaw/runtime.py) | 统一 run_agent/stream_agent 入口、请求状态初始化、图访问和流式事件处理。 |
| [src/storyclaw/graph.py](../packages/storyclaw/src/storyclaw/graph.py) | LangGraph 主图与大纲子图：意图路由、写作、审核与有限回写循环；注入检查点后可重建图。 |
| [src/storyclaw/state.py](../packages/storyclaw/src/storyclaw/state.py) | AgentState、OutlineState 等图状态结构。 |
| [src/storyclaw/checkpointer.py](../packages/storyclaw/src/storyclaw/checkpointer.py) | 构建 PostgreSQL 检查点，条件不足时用内存；检查点不同于任务表和正文版本。 |
| [src/storyclaw/prompts.py](../packages/storyclaw/src/storyclaw/prompts.py) | 集中系统提示词和部分用户提示构造。 |
| [src/storyclaw/_util.py](../packages/storyclaw/src/storyclaw/_util.py) | 模型调用/流式公共封装、输出段落处理、token 使用信息和代码围栏处理。 |
| [src/storyclaw/budget.py](../packages/storyclaw/src/storyclaw/budget.py) | 近似 token 估算、上下文窗口预算和裁剪保护，不是积分账户。 |
| [src/storyclaw/tracing.py](../packages/storyclaw/src/storyclaw/tracing.py) | 图节点耗时、状态、token 等日志包装。 |
| [src/storyclaw/context.py](../packages/storyclaw/src/storyclaw/context.py) | 字数统计、前章尾部截取、大纲节点定位；通过注入回调加载业务数据。 |
| [src/storyclaw/writing_context.py](../packages/storyclaw/src/storyclaw/writing_context.py) | 将普通书籍/设定/历史数据组成写作参考，混合召回与来源边界、完整上章参考和记忆工具查询。 |
| [src/storyclaw/workflow.py](../packages/storyclaw/src/storyclaw/workflow.py) | 总纲确认哈希、历史入库等纯工作流规则，无 HTTP/SQL。 |
| [src/storyclaw/serial.py](../packages/storyclaw/src/storyclaw/serial.py) | 连载总方向/阶段/单章情节结构、AI 生成框架和本章章纲、依赖指纹计算。 |
| [src/storyclaw/outline.py](../packages/storyclaw/src/storyclaw/outline.py) | 大纲规划、结构校验、定稿模式兼容与连载分支；不能仅凭结构校验判断文学质量。 |
| [src/storyclaw/scene_plan.py](../packages/storyclaw/src/storyclaw/scene_plan.py) | 确认章纲后的本章场景任务单：场景目标、地点、人物和建议字数等。 |
| [src/storyclaw/design.py](../packages/storyclaw/src/storyclaw/design.py) | 生成角色、世界观等结构化设计草案；不隐式写业务数据库。 |
| [src/storyclaw/continuity.py](../packages/storyclaw/src/storyclaw/continuity.py) | 有限文字复用检测与证据，不是完整语义矛盾检测器。 |
| [src/storyclaw/memory.py](../packages/storyclaw/src/storyclaw/memory.py) | 用户写作偏好默认值、合并、编码/解码，通过注入实现读写。 |
| [src/storyclaw/skills.py](../packages/storyclaw/src/storyclaw/skills.py) | 发现 skills 目录、解析 SKILL.md、列出技能索引、加载技能正文与参考。 |

## AI nodes/：主图节点

| 文件 | 当前职责 |
| --- | --- |
| [__init__.py](../packages/storyclaw/src/storyclaw/nodes/__init__.py) | 集中导出节点。 |
| [supervisor.py](../packages/storyclaw/src/storyclaw/nodes/supervisor.py) | 结合当前对话识别意图，选择写作、修改、分析、辅助或普通对话等路径。 |
| [writer.py](../packages/storyclaw/src/storyclaw/nodes/writer.py) | 首次写章、改章、段内续写、选中润色；读取确认章纲/历史，调用技能和工具。 |
| [reviewer.py](../packages/storyclaw/src/storyclaw/nodes/reviewer.py) | 正文长度、修改要求及跨章复用检查；按有限轮数请求 writer 修订，不代表全自动文学验收。 |
| [tools.py](../packages/storyclaw/src/storyclaw/nodes/tools.py) | 工具 JSON schema 与有限工具调用循环；实际业务查库委托后端注入的只读 executor。 |
| [analyst.py](../packages/storyclaw/src/storyclaw/nodes/analyst.py) | 大纲、情节、角色发展、一致性检查、前情摘要等分析技能。 |
| [assistant.py](../packages/storyclaw/src/storyclaw/nodes/assistant.py) | 脑暴、标题、场景增强、对话润色、阅读配置生成等辅助技能。 |
| [chat.py](../packages/storyclaw/src/storyclaw/nodes/chat.py) | 普通多轮对话及 skill 发现/加载；模型不支持工具时有兼容路径。 |
| [researcher.py](../packages/storyclaw/src/storyclaw/nodes/researcher.py) | 当前是模型直答型节点，没有在此实现联网搜索；小说知识检索主要在 writing_context、工具和 rag 子系统。 |

## AI ideation/：开书前讨论

| 文件 | 当前职责 |
| --- | --- |
| [__init__.py](../packages/storyclaw/src/storyclaw/ideation/__init__.py) | 独立讨论领域包标记。 |
| [models.py](../packages/storyclaw/src/storyclaw/ideation/models.py) | 用户消息、选择答案、问题卡、书籍方案及讨论输出结构。 |
| [workflow.py](../packages/storyclaw/src/storyclaw/ideation/workflow.py) | 有限 LangGraph 引导流程；分组采集偏好/故事信息后形成方案或修订，不无限追问，不自动建书。 |
| [brief.py](../packages/storyclaw/src/storyclaw/ideation/brief.py) | 已知题材判断和开书方案提示构造。 |
| [engine.py](../packages/storyclaw/src/storyclaw/ideation/engine.py) | 讨论模型推理、提示组装、流式解码和输出校验。 |
| [format.py](../packages/storyclaw/src/storyclaw/ideation/format.py) | 修复表层 JSON 格式、提取流式部分回复；不编造模型缺失的必要字段。 |
| [session.py](../packages/storyclaw/src/storyclaw/ideation/session.py) | 领域会话状态转换；调用方负责原子持久化。 |

## AI rag/：小说知识库

| 文件 | 当前职责 |
| --- | --- |
| [__init__.py](../packages/storyclaw/src/storyclaw/rag/__init__.py) | 知识检索子包标记。 |
| [service.py](../packages/storyclaw/src/storyclaw/rag/service.py) | 审阅正文入库的总流程：切片、embedding、向量写入、实体关系提取、图写入；也组织混合查询和状态。 |
| [chunker.py](../packages/storyclaw/src/storyclaw/rag/chunker.py) | 去 HTML、按段落分片、长段分割和重叠；纯文本处理。 |
| [embedding.py](../packages/storyclaw/src/storyclaw/rag/embedding.py) | 调用兼容 embeddings 接口、批量向量化及相似度工具；真实失败应显式呈现，不能把测试向量当生产成果。 |
| [milvus_store.py](../packages/storyclaw/src/storyclaw/rag/milvus_store.py) | Milvus 片段向量存储、相似检索、章节替换/状态等；按用户与书籍隔离。 |
| [neo4j_store.py](../packages/storyclaw/src/storyclaw/rag/neo4j_store.py) | Neo4j 实体、关系、章节来源的写入与查询。 |
| [memory_store.py](../packages/storyclaw/src/storyclaw/rag/memory_store.py) | 进程内存备用存储，重启丢失；是否允许备用受运行配置约束，不等于持久知识库。 |

相关目标方案：[StoryClaw Agent 统一设计](STORYCLAW-AGENT-DESIGN.md)与[用户场景和验收目录](STORYCLAW-AGENT-SCENARIOS.md)（待评审，区分现有代码与目标设计）。

## 主要调用链

### 生成一个章节

1. 前端提交后台任务到 api/jobs.py。
2. 后端检查用户归属、总纲确认、当前章纲确认和历史记忆是否就绪，保存 WorkJob。
3. services/jobs.py 领取任务，services/skill_loader.py 读业务数据，AI 包 writing_context.py 整理参考。
4. runtime.py 调 graph.py，supervisor 路由到 writer，writer 按需调用 tools，后端 agent_tools.py 执行只读查询。
5. reviewer 检查并可能有限次返回 writer 修订。
6. 后端检查参考版本和正文哈希，保存正文/版本/消息，记录积分和任务结果；前端查询任务获得结果。
7. 作者审阅后另行确认入库：rag.py 调 storyclaw/rag/service.py 写向量和图，成功后更新状态。正文保存不等于已入库。

### 改前章以后

chapters.py → revisions.py / serial.py：保留版本，当前与后续相关记忆 pending，章纲依赖 stale，产生影响通知。作者核对后重新确认计划/索引，不能把“重建索引”理解成“自动修好了后文”。

### 开书前讨论

api/ideation.py → storyclaw/ideation/session.py → workflow.py / engine.py。返回可点击问题或书籍方案；用户确认后才由创建书籍接口落库。

## 同名文件为什么不重复

| 后端文件 | AI 包文件 | 分工 |
| --- | --- | --- |
| services/llm.py | llm.py | 后端查配置解密，AI 包构造模型客户端 |
| services/memory.py | memory.py | 后端保存偏好，AI 包定义偏好格式/合并 |
| services/serial.py | serial.py | 后端存章纲和依赖状态，AI 包生成规划并计算纯指纹 |
| services/skill_loader.py | writing_context.py | 后端读有权限的原始数据，AI 包组合参考和检索 |
| services/agent_tools.py | nodes/tools.py | 后端查业务数据，AI 包定义工具并决定调用 |
| api/rag.py | rag/service.py | 后端审阅/鉴权/状态写回，AI 包做切片、向量、图处理 |

## 当前边界与后续整理点

- API 中仍有产品业务编排，不能说 backend 已经只有路由转发；AI 相关核心推理已集中在包中。
- services/ideation_format.py、ideation_workflow.py、scene_plan.py 等兼容文件不代表重复实现；book_bootstrap.py、setting_sync.py 的旧自动副作用已退役。
- product_ops.py、schemas.py、models/product.py 等文件覆盖多个业务域，后续可按任务/社区/会员拆分。
- researcher 不是联网爬虫；reviewer 不是完整文学质量裁判；向量库也不能保证全文每个事实都被召回。
- 数据库迁移文件记录历史结构；开发自动 create_all 不会替代生产迁移。
- 当前第四章样书索引因上游 embedding 额度不足停止，目录说明不把这种外部失败描述为入库成功。
