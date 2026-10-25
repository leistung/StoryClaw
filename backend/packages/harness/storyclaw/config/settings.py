"""storyclaw 包级配置（环境变量驱动）。

backend 负责注入数据层依赖（见 deps.py）；本模块只负责 agent 自身需要的
基础设施配置：skills 目录、Milvus / Neo4j 连接、Embedding 兜底。
"""
from __future__ import annotations

import os
from pathlib import Path


class StoryClawSettings:
    def __init__(self) -> None:
        # Built-in methods ship with the wheel; SKILLS_DIR optionally overrides them.
        self.skills_dir = self._first_existing(self._skills_candidates())
        # ---- Milvus ----
        self.milvus_uri = os.getenv("MILVUS_URI", "").strip()          # 可选完整 URI
        self.milvus_host = os.getenv("MILVUS_HOST", "localhost")
        self.milvus_port = int(os.getenv("MILVUS_PORT", "19530") or 19530)
        self.milvus_dim = int(os.getenv("MILVUS_VECTOR_DIM", "1024") or 1024)
        # ---- Neo4j ----
        self.neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", "storyclaw_neo4j_pwd")
        # ---- Embedding / LLM 兜底 ----
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "bge-base-zh")
        self.llm_default_base_url = os.getenv("LLM_DEFAULT_BASE_URL", "")
        self.llm_default_api_key = os.getenv("LLM_DEFAULT_API_KEY", "")
        self.llm_default_model = os.getenv("LLM_DEFAULT_MODEL", "gpt-4o-mini")

    @property
    def skills_path(self) -> Path:
        return Path(self.skills_dir) if self.skills_dir else Path("/nonexistent")

    @staticmethod
    def _first_existing(candidates: list[str]) -> str:
        for c in candidates:
            if c and Path(c).exists():
                return c
        return candidates[0] if candidates else ""

    @staticmethod
    def _skills_candidates() -> list[str]:
        """Resolve package-owned resources independently of the working directory."""
        builtin = Path(__file__).resolve().parents[1] / "skills" / "resources"
        return [os.getenv("SKILLS_DIR", "").strip(), str(builtin)]



settings = StoryClawSettings()
