"""创作方法资源加载：旧名兼容、版本哈希和受限参考读取。

SKILL.md / references 只提供方法，不执行脚本或授予业务权限。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from storyclaw.config.settings import settings

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
    """编译当前任务的方法，不把整套参考材料塞入每次模型调用。"""
    sections = read_skill_sections(name, ("parameters", "method", "constraints", "output"))
    result = "\n\n".join(f"[{key}]\n{value}" for key, value in sections.items() if value)
    meta = describe_skill(name)
    refs = meta.get('reference_files', [])
    routes = meta.get('instruction_references', {})
    # 沿用旧名识别修订、续写和对白模式；同一方法不意味着同一份任务参考。
    preferred={'modify-chapter':'references/revise.md','write-chapter':'references/write.md',
        'continue-writing':'references/continue.md','polish-chapter':'references/polish.md',
        'scene-enhance':'references/scene.md','dialogue-polish':'references/dialogue.md'}.get(name)
    selected = routes.get(name, routes.get('default'))
    if selected is None:  # 没有新路由字段的自定义 Skill 保持原有加载行为。
        selected = [preferred] if preferred and preferred in refs else refs[:1]
    for reference in dict.fromkeys(selected):
        if reference not in refs:
            raise ValueError(f'Skill 注入参考未登记：{name}/{reference}')
        text = read_skill_reference(name, reference)
        if not text:
            raise ValueError(f'Skill 注入参考不可读取：{name}/{reference}')
        result += f'\n\n[创作参考：{reference}]\n{text}'
    return result


def _method_hash(path: Path) -> str:
    digest=hashlib.sha256()
    for resource in sorted(path.parent.rglob('*')):
        if resource.is_file() and resource.suffix in ('.md','.json') and resource.resolve().is_relative_to(path.parent.resolve()):
            digest.update(str(resource.relative_to(path.parent)).encode());digest.update(resource.read_bytes())
    return digest.hexdigest()


def read_skill_reference(name: str, relative: str) -> str:
    path=_find_skill_path(name)
    if path is None or not relative.startswith('references/'):return ''
    resource=(path.parent/relative).resolve()
    if not resource.is_relative_to(path.parent.resolve()) or not resource.is_relative_to((path.parent/'references').resolve()) or not resource.is_file() or resource.suffix!='.md':return ''
    return resource.read_text()[:6000]


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
                  content_hash=_method_hash(path), kind="method",
                  compatible_capabilities=manifest.get("compatible_capabilities",[]),
                  reference_files=manifest.get("reference_files",[]),
                  instruction_references=manifest.get("instruction_references",{}))
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
    "parameters": ("parameters", "参数", "输入"),
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
