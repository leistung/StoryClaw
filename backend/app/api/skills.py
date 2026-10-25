"""Skill 系统元数据 API（薄网关）。

skill 发现/解析统一在 packages/storyclaw/src/storyclaw/skills.py。
"""
from fastapi import APIRouter, Depends, HTTPException

from storyclaw.skills import describe_skill, list_skills

from ..core.deps import get_current_user
from ..models import User

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("")
async def list_all(u: User = Depends(get_current_user)):
    """列出所有可用 skill 的元数据。"""
    try:
        return list_skills()
    except Exception as e:
        raise HTTPException(500, f"加载 skills 失败: {e}")


@router.get("/{name}")
async def describe(name: str, u: User = Depends(get_current_user)):
    """返回单个 skill 的元数据。"""
    try:
        meta = describe_skill(name)
    except Exception as e:
        raise HTTPException(500, f"加载 skill 失败: {e}")
    if not meta or not meta.get("available",True):
        raise HTTPException(404, "skill 不存在")
    return meta
