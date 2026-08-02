"""可靠解码子进程和本地文件产生的字节。
Reliably decode bytes produced by subprocesses and local files.
"""

from __future__ import annotations

import locale
from collections.abc import Iterable


def _unique_encodings(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        normalized = value.lower().replace("_", "-")
        if normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result


def decode_bytes(data: bytes, *, preferred: str | None = None) -> tuple[str, str]:
    """返回解码后的文本和实际成功使用的编码。
    Return decoded text and the encoding that succeeded.
    """

    if not data:
        return "", preferred or "utf-8"
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"

    # 没有 BOM 的 UTF-16 输出通常包含大量空字节。
    # UTF-16 output without a BOM normally contains many NUL bytes.
    if data.count(b"\x00") > max(2, len(data) // 8):
        for encoding in ("utf-16-le", "utf-16-be"):
            try:
                return data.decode(encoding), encoding
            except UnicodeDecodeError:
                pass

    # 先尝试 UTF-8，避免把 Python UTF-8 输出误解码为 Windows 传统编码。
    # Try UTF-8 first so Python UTF-8 output is not decoded as legacy Windows text.
    candidates = _unique_encodings(
        (
            "utf-8",
            preferred,
            locale.getpreferredencoding(False),
            "oem",
            "mbcs",
            "gb18030",
        )
    )
    for encoding in candidates:
        try:
            return data.decode(encoding), encoding
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"
