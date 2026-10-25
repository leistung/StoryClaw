.RECIPEPREFIX := >
.PHONY: help up down up-all health logs build migrate backend-shell frontend-dev

help:
>@echo "StoryClaw dev commands:"
>@echo "  make up          启动核心服务 (postgres milvus neo4j backend frontend admin-frontend)"
>@echo "  make up-all      启动全部所需服务"
>@echo "  make down        停止全部服务"
>@echo "  make health      健康检查"
>@echo "  make logs        查看日志 (Ctrl+C 退出)"
>@echo "  make build       构建镜像"
>@echo "  make migrate     执行数据库迁移"
>@echo "  make backend-shell  进入 backend 容器"
>@echo "  make frontend-dev   前端本地开发 (npm run dev)"

COMPOSE := docker compose --env-file .env -f docker/docker-compose.yml

up:
>$(COMPOSE) up -d postgres milvus neo4j backend frontend admin-frontend

up-all:
>$(COMPOSE) up -d

down:
>$(COMPOSE) down

health:
>@echo "Checking services..."
>$(COMPOSE) exec -T backend curl -sf http://localhost:8000/health
>$(COMPOSE) exec -T frontend wget -q --spider http://localhost:5173
>$(COMPOSE) exec -T admin-frontend wget -q --spider http://localhost:5174
>$(COMPOSE) ps

logs:
>$(COMPOSE) logs -f --tail=200

build:
>$(COMPOSE) build

migrate:
>$(COMPOSE) exec backend alembic upgrade head

backend-shell:
>$(COMPOSE) exec backend bash

frontend-dev:
>cd frontend && npm run dev
