"""通用辅助函数的公开入口。
Public entry point for shared helpers.
"""

from .serialization import json_safe
from .text import format_text_segment, limit_text_segment, truncate_text

__all__ = [
    "format_text_segment",
    "json_safe",
    "limit_text_segment",
    "truncate_text",
]
