"""Skill 发现与加载（DeerFlow 风格）。

统一结构（skills/<skill-name>/）：
    SKILL.md           # 说明书（核心）
    scripts/           # 可执行脚本
    references/        # 参考文档
    assets/            # 静态资源

Agent 通过 `describe_skill(name)` 获取元数据，再把 SKILL.md 全文注入 prompt 或工具。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import settings

# Legacy names resolve methods, never executable workflows.
SKILL_ALIASES = {
    "write-chapter": "chapter-craft", "modify-chapter": "chapter-craft",
    "continue-writing": "prose-editing", "polish-chapter": "prose-editing",
    "outline-planning": "framework-design", "plot-planning": "plot-design",
    "character-development": "character-arc", "consistency-check": "continuity-review",
    "book-summary": "story-summarization", "brainstorm": "idea-generation",
    "title-generation": "naming", "scene-enhance": "scene-and-dialogue",
    "dialogue-polish": "scene-and-dialogue",
}
RETIRED_SKILLS = {"continue-chapter": "chapter.write", "write-multi-chapters": "serial.advance",
                  "reading-config-gen": "reading presets", "skill-creator": "private method proposals (planned)"}

def canonical_skill(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name):
        return ""
    return SKILL_ALIASES.get(name, name)


def method_instructions(name: str) -> str:
    sections = read_skill_sections(name, ("method", "constraints"))
    return "\n\n".join(f"[{key}]\n{value}" for key,value in sections.items() if value)



def describe_skill(skill_name: str) -> dict[str, Any]:
    """读取 skills/<skill_name>/SKILL.md 并解析元数据。

    Returns {"name","description","parameters","output"}；SKILL.md 缺失时 description 标记。
    """
    path = _find_skill_path(skill_name)
    if not path:
        return {"name": skill_name, "available": False, "replacement": RETIRED_SKILLS.get(skill_name), "description": "该名称不是活跃创作方法"}
    text = path.read_text(encoding="utf-8")
    result = _parse_skill_md(path.parent.name, text)
    manifest_path = path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    result.update(available=True, requested_name=skill_name, version=manifest.get("version", 1),
                  content_hash=hashlib.sha256(text.encode()).hexdigest(), kind="method")
    return result


def read_skill_doc(skill_name: str) -> str:
    """返回 SKILL.md 全文（Agent 加载完整说明书用）。"""
    path = _find_skill_path(skill_name)
    if not path:
        return ""
    return path.read_text(encoding="utf-8")


# section 别名映射（中英文），用于把 SKILL.md 指定章节注入 system prompt
_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "workflow": ("method", "方法", "workflow", "流程", "步骤", "运行流程"),
    "method": ("method", "方法"),
    "constraints": ("constraints", "约束", "注意事项", "规则"),
    "output": ("output", "输出", "输出格式"),
    "description": ("description", "描述", "简介"),
}


def read_skill_sections(skill_name: str, wanted: tuple[str, ...] = ("workflow", "constraints", "output")) -> dict[str, str]:
    """提取 SKILL.md 指定 section 的文本，供节点注入 system prompt。

    返回形如 {"workflow": "...", "constraints": "..."}；不存在的 section 缺失。
    """
    text = read_skill_doc(skill_name)
    if not text:
        return {}
    # 先把全文按 '## ' 分块
    blocks: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for ln in text.splitlines():
        if ln.startswith("## "):
            if current:
                blocks[current] = "\n".join(buf).strip()
            current = ln[3:].strip()
            buf = []
        elif ln.startswith("# ") or ln.startswith("### "):
            continue
        else:
            if current is not None:
                buf.append(ln)
    if current:
        blocks[current] = "\n".join(buf).strip()

    result: dict[str, str] = {}
    for w in wanted:
        key = w.lower()
        for canonical, aliases in _SECTION_ALIASES.items():
            if key == canonical or key in aliases:
                # 精确匹配 canonical 或其别名
                for name, content in blocks.items():
                    if name.strip().lower() in aliases or name.strip().lower() == canonical:
                        result[canonical] = content
                break
    return result


def list_skill_index() -> list[dict[str, str]]:
    """扫描 skills/ 目录，返回所有 skill 的 {name, description} 列表。

    用于注入 chat 系统提示的 <skill_index>，让 Agent 知道有哪些可用能力。
    """
    base = settings.skills_path
    if not base.exists():
        return []
    out: list[dict[str, str]] = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            meta = describe_skill(d.name)
            out.append({"name": d.name, "description": meta.get("description", "")[:80]})
    return out


def list_skills(skills_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """枚举 skills/ 下所有 skill 元数据（供 /api/skills 接口使用）。"""
    base = Path(skills_dir) if skills_dir else settings.skills_path
    out: list[dict[str, Any]] = []
    if not base.exists():
        return out
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            out.append(describe_skill(d.name))
    return out


def _find_skill_path(skill_name: str) -> Path | None:
    base = settings.skills_path
    name = canonical_skill(skill_name)
    if not name or name in RETIRED_SKILLS:
        return None
    p = (base / name / "SKILL.md").resolve()
    if not p.is_relative_to(base.resolve()):
        return None
    return p if p.is_file() else None


def _parse_skill_md(name: str, text: str) -> dict[str, Any]:
    sections: dict[str, str] = {"description": "", "parameters": "", "output": ""}
    aliases = {
        "description": ("description", "描述", "简介"),
        "parameters": ("parameters", "参数"),
        "output": ("output", "输出", "输出格式"),
    }
    section = ""
    buf: list[str] = []
    for ln in text.splitlines():
        if ln.startswith("## "):
            if section:
                s = "\n".join(buf).strip()
                for k, aliases_k in aliases.items():
                    if section in aliases_k:
                        sections[k] = s
                        break
            section = ln[3:].strip().lower()
            buf = []
        else:
            buf.append(ln)
    if section:
        s = "\n".join(buf).strip()
        for k, aliases_k in aliases.items():
            if section in aliases_k:
                sections[k] = s
                break
    return {
        "name": name,
        "description": sections["description"] or text[:200],
        "parameters": sections["parameters"],
        "output": sections["output"],
    }
