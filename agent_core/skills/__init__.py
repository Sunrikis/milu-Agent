"""Skill 发现与按需加载的公开入口。
Public entry point for skill discovery and lazy loading.
"""

from .loader import SkillDefinition, SkillLoader

__all__ = ["SkillDefinition", "SkillLoader"]
