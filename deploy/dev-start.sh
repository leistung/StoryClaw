#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build --wait
printf '%s\n' 'StoryClaw 服务已启动。端口以 .env 和 docker compose ps 为准：'
docker compose --env-file .env -f deploy/docker-compose.yml ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
