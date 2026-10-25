"""结构化日志配置。

使用标准库 logging + 自定义 Formatter，输出为 key=value 单行（类 logfmt），
便于 grep / 日志采集。所有请求通过 add_request_logging(app) 挂载中间件记录
method/path/status/duration/user_id。

示例输出：
    2026-08-26 10:00:00 INFO req method=GET path=/api/v1/books status=200 duration_ms=12 user_id=27
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

_CONFIGURED = False


class LogfmtFormatter(logging.Formatter):
    """把记录转成 key=value 单行；message 作为 msg=... 字段。"""

    def format(self, record: logging.LogRecord) -> str:
        base = f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} {record.levelname} {record.name}"
        extra = getattr(record, "data", None)
        if extra:
            parts = " ".join(f"{k}={_safe(v)}" for k, v in extra.items())
            base += f" {parts}"
        return f"{base} msg={_safe(record.getMessage())}"


def _safe(v: Any) -> str:
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, ensure_ascii=False, default=str)
        except Exception:
            return str(v)
    return str(v)


def setup_logging(level: str = "INFO", fmt: logging.Formatter | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler()
    handler.setFormatter(fmt or LogfmtFormatter())
    root.addHandler(handler)
    # 避免第三方库刷屏
    for noisy in ("uvicorn.access", "httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


def add_request_logging(app: FastAPI) -> None:
    """挂载请求日志中间件（记录耗时 / 状态码 / 路径）。"""

    class _RequestLoggingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            start = time.perf_counter()
            response = await call_next(request)
            route = request.scope.get("route")
            safe_path = getattr(route, "path", "<unmatched>")
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger = logging.getLogger("storyclaw.req")
            data: dict[str, Any] = {
                "method": request.method,
                "path": safe_path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            }
            if request.scope.get("user"):
                data["user_id"] = request.scope["user"]
            logger.info("request", extra={"data": data})
            if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/v1/admin/logs"):
                try:
                    from app.database import AsyncSessionLocal
                    from app.models.platform import PlatformEvent
                    async with AsyncSessionLocal() as db:
                        db.add(PlatformEvent(kind="request", actor_id=request.scope.get("user"),
                            action=request.method, target=safe_path[:255],
                            details={"status": response.status_code, "duration_ms": duration_ms}))
                        await db.commit()
                except Exception:
                    logger.warning("request metadata persistence failed")
            return response

    app.add_middleware(_RequestLoggingMiddleware)
