"""定义所有本地工具共享的结果类型。
Define the result type shared by all local tools.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolResult:
    content: str
    is_error: bool = False
