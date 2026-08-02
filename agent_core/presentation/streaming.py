"""渲染普通回答与可选的思考内容。
Render regular answers and optional thinking content.
"""

from __future__ import annotations

import sys
from typing import Any


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def configure_console_utf8() -> None:
    """将可配置的终端文本流切换到 UTF-8。
    Configure supported terminal text streams to use UTF-8.
    """

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (LookupError, OSError, ValueError):
            continue


class ConsoleStreamRenderer:
    """按内容类型实时输出模型流事件。
    Render model stream events live according to content type.
    """

    def __init__(
        self,
        *,
        show_thinking: bool,
        show_text: bool,
        thinking_label: str,
        text_label: str,
    ):
        self.show_thinking = show_thinking
        self.show_text = show_text
        self.thinking_label = thinking_label
        self.text_label = text_label
        self.has_output = False
        self._active_label: str | None = None

    def render(self, event: Any) -> None:
        if _field(event, "type") != "content_block_delta":
            return
        delta = _field(event, "delta")
        delta_type = _field(delta, "type")
        if delta_type == "thinking_delta" and self.show_thinking:
            self._write(self.thinking_label, str(_field(delta, "thinking", "")))
        elif delta_type == "text_delta" and self.show_text:
            self._write(self.text_label, str(_field(delta, "text", "")))

    def finish(self) -> None:
        if self._active_label is not None:
            print()
            self._active_label = None

    def _write(self, label: str, content: str) -> None:
        if not content:
            return
        if self._active_label != label:
            if self._active_label is not None:
                print()
            print(f"[{label}]: ", end="", flush=True)
            self._active_label = label
        print(content, end="", flush=True)
        self.has_output = True
