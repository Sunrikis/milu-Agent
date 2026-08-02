"""提供跨模块使用的文本处理函数。
Provide text helpers shared across modules.
"""

from __future__ import annotations


def format_text_segment(
    source: str,
    text: str,
    *,
    start_char: int,
    max_chars: int,
) -> str:
    start = min(len(text), max(0, int(start_char)))
    limit = max(1, int(max_chars))
    end = min(len(text), start + limit)
    header = [
        f"source: {source}",
        f"total_chars: {len(text)}",
        f"range: {start}:{end}",
        f"has_more: {str(end < len(text)).lower()}",
    ]
    return "\n".join(header) + "\n\n" + text[start:end]


def truncate_text(text: str, max_chars: int) -> str:
    limit = max(0, int(max_chars))
    if len(text) <= limit:
        return text
    if limit == 0:
        return ""
    marker = f"\n... [中间省略 {len(text) - limit} 个字符] ...\n"
    if len(marker) >= limit:
        return text[:limit]
    available = limit - len(marker)
    head = (available * 2) // 3
    tail = available - head
    return text[:head] + marker + (text[-tail:] if tail else "")


def limit_text_segment(text: str, max_chars: int) -> str:
    """限制工具输出并保持分段游标连续有效。
    Limit tool output while keeping segmented cursors contiguous and valid.
    """

    limit = max(0, int(max_chars))
    if len(text) <= limit:
        return text

    header, separator, body = text.partition("\n\n")
    lines = header.splitlines()
    if not separator or len(lines) != 4:
        return truncate_text(text, limit)
    if not (
        lines[0].startswith("source: ")
        and lines[1].startswith("total_chars: ")
        and lines[2].startswith("range: ")
        and lines[3].startswith("has_more: ")
    ):
        return truncate_text(text, limit)

    try:
        total_chars = int(lines[1].removeprefix("total_chars: "))
        range_value = lines[2].removeprefix("range: ")
        start_char, end_char = (int(value) for value in range_value.split(":", 1))
    except ValueError:
        return truncate_text(text, limit)
    if not (
        0 <= start_char <= end_char <= total_chars
        and len(body) == end_char - start_char
    ):
        return truncate_text(text, limit)

    best: str | None = None
    lower = 0
    upper = len(body)
    while lower <= upper:
        body_chars = (lower + upper) // 2
        limited_end = start_char + body_chars
        candidate_header = "\n".join(
            [
                lines[0],
                lines[1],
                f"range: {start_char}:{limited_end}",
                f"has_more: {str(limited_end < total_chars).lower()}",
            ]
        )
        candidate = candidate_header + "\n\n" + body[:body_chars]
        if len(candidate) <= limit:
            best = candidate
            lower = body_chars + 1
        else:
            upper = body_chars - 1

    if best is not None:
        return best
    return truncate_text(text, limit)
