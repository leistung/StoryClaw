from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import admin, auth, books, chapters, chat, community, config_entities, configs as api_configs, messages, outlines, rag, reading_configs, recharge, share, skills, writing
from .config import settings
from .core.errors import APIError, error_body
from .core.logging import add_request_logging, setup_logging
from .database import AsyncSessionLocal, engine
from .models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 开发期：自动建表（生产用 `make migrate` 走 alembic）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        from .services.platform import refresh_configs
        from sqlalchemy import update
        from .models import User
        await db.execute(update(User).where(User.version != "business").values(version="business"))
        await db.commit()
        await refresh_configs(db)
    # 注入 agent 数据层依赖到 packages/storyclaw（llm/memory/context/rag/checkpointer）
    try:
        from storyclaw.deps import configure as sc_configure
        from storyclaw.graph import rebuild_graph
        from storyclaw.checkpointer import build_checkpointer

        from .services import llm as llm_svc
        from .services.embedding_config import resolve_embedding_config
        from .services.memory import load_user_memory, save_user_memory
        from .services.skill_loader import build_write_context


        async def _load_memory_cb(user_id: int) -> dict:
            async with AsyncSessionLocal() as db:
                return await load_user_memory(user_id, db)


        async def _save_memory_cb(user_id: int, key: str, value) -> None:
            async with AsyncSessionLocal() as db:
                await save_user_memory(user_id, key, value, db)


        async def _load_context_cb(db, user_id: int, book_id: int, chapter_id: int) -> dict:
            return await build_write_context(user_id, book_id, chapter_id, db)


        async def _tool_executor_cb(name: str, args: dict, user_id: int,
                                    book_id: int, chapter_id: int | None) -> str:
            from .services.agent_tools import execute_writer_tool
            return await execute_writer_tool(name, args, user_id, book_id, chapter_id)


        saver = await build_checkpointer(getattr(settings, "database_url", None))
        sc_configure(
            llm_factory=llm_svc.build_llm_from_choice,
            load_memory=_load_memory_cb,
            save_memory=_save_memory_cb,
            load_context=_load_context_cb,
            embedding_resolver=resolve_embedding_config,
            checkpointer=saver,
            tool_executor=_tool_executor_cb,
        )
        rebuild_graph()  # 用真实 checkpointer 重新编译 agent 图
    except Exception as e:
        # 容错：storyclaw 包未安装时仍可启动基础 API
        import logging
        logging.getLogger("storyclaw").warning(f"storyclaw configure skipped: {e}")
    import asyncio
    from .services.jobs import queue_loop
    consumer=asyncio.create_task(queue_loop())
    try:
        yield
    finally:
        consumer.cancel()
        try:await consumer
        except asyncio.CancelledError:pass


setup_logging(getattr(settings, "log_level", "INFO"))

app = FastAPI(title="StoryClaw Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== 统一错误响应 =====
@app.exception_handler(APIError)
async def _api_error_handler(request: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.details),
    )


@app.exception_handler(HTTPException)
async def _http_error_handler(request: Request, exc: HTTPException):
    # 尽量把 FastAPI 自带异常映射成稳定错误码
    code_map = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
    }
    code = code_map.get(exc.status_code, f"http_{exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, str(exc.detail)),
    )


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_error",
            "请求参数校验失败",
            jsonable_encoder(exc.errors()),
        ),
    )


@app.exception_handler(Exception)
async def _unhandled_error_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger("storyclaw").exception(
        "unhandled error",
        extra={"data": {"method": request.method, "path": request.url.path}},
    )
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "服务器内部错误"),
    )


add_request_logging(app)

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(api_configs.router, prefix=API_PREFIX)
app.include_router(books.router, prefix=API_PREFIX)
app.include_router(chapters.router, prefix=API_PREFIX)
app.include_router(outlines.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(rag.router, prefix=API_PREFIX)
app.include_router(share.router, prefix=API_PREFIX)
app.include_router(skills.router, prefix=API_PREFIX)
app.include_router(writing.router, prefix=API_PREFIX)
app.include_router(config_entities.router, prefix=API_PREFIX)
app.include_router(reading_configs.router, prefix=API_PREFIX)
app.include_router(community.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
app.include_router(recharge.router, prefix=API_PREFIX)
app.include_router(messages.router, prefix=API_PREFIX)
from .api import jobs, publications, product_ops
app.include_router(jobs.router, prefix=API_PREFIX)
app.include_router(publications.router, prefix=API_PREFIX)
app.include_router(product_ops.router, prefix=API_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok"}

from .api import ideation
app.include_router(ideation.router, prefix=API_PREFIX)

from .api import serial
app.include_router(serial.router,prefix=API_PREFIX)

from .api import agent
app.include_router(agent.router,prefix=API_PREFIX)
