"""格式化记忆整理输入并解析模型输出。
Format memory-compaction input and parse model output.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..common import json_safe, truncate_text


_ASSISTANT_THINKING_BLOCK_TYPES = {"thinking", "redacted_thinking"}


def _content_for_compaction(message: dict) -> Any:
    content = json_safe(message.get("content"))
    if message.get("role") != "assistant":
        return content
    if isinstance(content, list):
        return [
            block
            for block in content
            if not (
                isinstance(block, dict)
                and block.get("type") in _ASSISTANT_THINKING_BLOCK_TYPES
            )
        ]
    if (
        isinstance(content, dict)
        and content.get("type") in _ASSISTANT_THINKING_BLOCK_TYPES
    ):
        return []
    return content


def _truncate_tool_result_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    return truncate_text(text, max_chars)[:max_chars]


def _truncate_tool_results(
    content: Any,
    *,
    success_max_chars: int,
    error_max_chars: int,
) -> Any:
    blocks = content if isinstance(content, list) else [content]
    transformed: list[Any] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            copied = dict(block)
            max_chars = (
                error_max_chars
                if copied.get("is_error") is True
                else success_max_chars
            )
            value = copied.get("content")
            full_text = (
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False)
            )
            copied["content"] = _truncate_tool_result_text(full_text, max_chars)
            block = copied
        transformed.append(block)
    if isinstance(content, list):
        return transformed
    return transformed[0]


def messages_to_text(
    messages: list[dict],
    *,
    success_tool_result_max_chars: int,
    error_tool_result_max_chars: int,
) -> str:
    lines: list[str] = []
    success_limit = max(0, int(success_tool_result_max_chars))
    error_limit = max(0, int(error_tool_result_max_chars))
    for message in messages:
        role = message.get("role", "?")
        content = _truncate_tool_results(
            _content_for_compaction(message),
            success_max_chars=success_limit,
            error_max_chars=error_limit,
        )
        lines.append(f"{role}: {json.dumps(content, ensure_ascii=False)}")
    return "\n".join(lines)


def extract_tag(text: str, tag: str) -> str:
    match = re.search(
        rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>",
        text,
        re.DOTALL
    )
    return match.group(1).strip() if match else ""


def _is_conversation_boundary(message: dict) -> bool:
    return message.get("role") == "user" and isinstance(message.get("content"), str)


def choose_compaction_split(history: list[dict], recent_messages: int) -> int:
    target = max(0, len(history) - recent_messages)
    for index in range(target, 0, -1):
        if _is_conversation_boundary(history[index]):
            return index
    for index in range(target + 1, len(history)):
        if _is_conversation_boundary(history[index]):
            return index
    return 0


def response_text(message: Any) -> str:
    parts: list[str] = []
    for block in getattr(message, "content", []):
        block_type = getattr(block, "type", None)
        if block_type == "text":
            parts.append(getattr(block, "text", ""))
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "\n".join(part for part in parts if part)
