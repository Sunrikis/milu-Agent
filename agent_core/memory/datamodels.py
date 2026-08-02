"""定义记忆系统使用的数据模型。
Define data models used by the memory system.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    long_term: str
    user_profile: str
    today_episode: str


@dataclass(frozen=True, slots=True)
class CompactionOutcome:
    history: list[dict]
    compacted: bool
    saved: bool = False
    archived_messages: int = 0
    archive_path: str | None = None
    error: str | None = None
    warning: str | None = None
