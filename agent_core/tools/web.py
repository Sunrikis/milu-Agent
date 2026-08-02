"""获取网页并按需提取可读文本。
Fetch web pages and optionally extract readable text.
"""

from __future__ import annotations

import re
import urllib.request
from functools import lru_cache
from html.parser import HTMLParser
from urllib.parse import urlsplit

from ..common import format_text_segment
from .encoding import decode_bytes


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        if tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4"):
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self._parts)).strip()


@lru_cache(maxsize=32)
def _fetch_web_content(url: str, extract_mode: str) -> str:
    """下载并缓存完整网页的已提取文本。
    Download and cache the complete extracted web content.
    """

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = response.read()
        charset = response.headers.get_content_charset()
        raw, _ = decode_bytes(payload, preferred=charset)

    if extract_mode == "raw":
        return raw

    parser = _TextExtractor()
    parser.feed(raw)
    return parser.get_text()


def web_fetch(
    url: str,
    extract_mode: str,
    start_char: int,
    max_chars: int,
) -> str:
    """按字符范围读取缓存的完整网页内容。
    Read cached complete web content by character range.
    """

    scheme = urlsplit(url).scheme.lower()
    if scheme not in {"http", "https"}:
        return "Error: web_fetch only supports HTTP and HTTPS URLs"
    if extract_mode not in {"text", "raw"}:
        return "Error: extract_mode must be text or raw"

    try:
        text = _fetch_web_content(url, extract_mode)
    except Exception as exc:
        return f"Error fetching {url}: {exc}"

    limit = max(1, min(int(max_chars), 50000))
    return format_text_segment(
        url,
        text,
        start_char=start_char,
        max_chars=limit,
    )
