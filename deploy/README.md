# 部署与本地运行

从仓库根目录执行：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
# 或 make up-all
```

当前 Compose 是支持热更新的开发编排。正式生产镜像、HTTPS、备份等仍需单独配置，不能将开发服务直接当成生产验收结果。

Worker默认按可见CPU和内存估算WorkJob并发，可通过`WORKER_JOB_CONCURRENCY`覆盖；`WORKER_GLOBAL_JOB_CONCURRENCY=0`表示没有额外集群总量上限。支持`docker compose --env-file .env -f deploy/docker-compose.yml up -d --scale worker=2 worker`增加副本，资源配额、SQL连接和供应商容量需同时规划，见[配置说明](../docs/02-本地运行与配置.md)。这不影响作品归属权限，也不允许共同编辑他人的书。

- `docker-compose.yml`：API、Worker、两个前端及数据库依赖。
- `backend.Dockerfile`：安装独立 Harness，再安装平台代码。
- `frontend.Dockerfile`、`admin-frontend.Dockerfile`：两个前端的开发镜像。
- `nginx/`：代理参考配置。
- `scripts/init-pg.sql`：首次创建空数据库卷时的初始化脚本。
- `dev-start.sh`：从任意工作目录启动开发服务。

Compose项目名仍为 `storyclaw`，持久卷名称不变。目录改名不需要清库或运行 `down -v`。后端初始配置位于 `backend/config`；AI写作方法位于 Harness 的 `storyclaw/skills/resources`，由包自身加载。
