"""发现 Skill 并渐进式加载其正文。
Discover skills and progressively load their full content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    name: str
    description: str
    body: str
    path: Path
    metadata: dict


class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills: dict[str, SkillDefinition] = {}
        self.warnings: list[str] = []
        self.reload()

    def reload(self) -> None:
        self.skills.clear()
        self.warnings.clear()
        if not self.skills_dir.exists():
            return

        for path in sorted(self.skills_dir.rglob("SKILL.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                self.warnings.append(f"Could not read {path}: {exc}")
                continue

            metadata, body = self._parse_frontmatter(text, path)
            name = str(metadata.get("name") or path.parent.name)
            description = str(metadata.get("description") or "No description")
            if name in self.skills:
                self.warnings.append(
                    f"Duplicate skill name {name!r}; using {path} instead of "
                    f"{self.skills[name].path}"
                )

            self.skills[name] = SkillDefinition(
                name=name,
                description=description,
                body=body,
                path=path,
                metadata=metadata,
            )

    def _parse_frontmatter(self, text: str, path: Path) -> tuple[dict, str]:
        match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", text, re.DOTALL)
        if not match:
            self.warnings.append(f"Missing or invalid frontmatter: {path}")
            return {}, text.strip()

        try:
            metadata = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            self.warnings.append(f"Invalid YAML frontmatter in {path}: {exc}")
            return {}, match.group(2).strip()

        if not isinstance(metadata, dict):
            self.warnings.append(f"Frontmatter must be a mapping: {path}")
            metadata = {}
        return metadata, match.group(2).strip()

    def get_descriptions(self) -> str:
        if not self.skills:
            return "(no skills available)"
        return "\n".join(
            f"  - {skill.name}: {skill.description}"
            for skill in self.skills.values()
        )

    def get_content(self, name: str) -> str:
        skill = self.skills.get(name)
        if skill is None:
            available = ", ".join(self.skills) or "(none)"
            return f"Error: Unknown skill {name!r}. Available: {available}"
        skill_name = escape(skill.name, quote=True)
        source_path = escape(str(skill.path.resolve()), quote=True)
        return (
            f'<skill name="{skill_name}" source_path="{source_path}">\n'
            f"{skill.body}\n"
            "</skill>"
        )
