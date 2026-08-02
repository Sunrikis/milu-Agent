"""为每次模型 API 调用追加记录 Token 用量。
Append token usage for every model API request.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from ..common import json_safe


def _token_count(usage: dict, field: str) -> int:
    value = usage.get(field, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


class TokenUsageRecorder:
    """每次模型请求成功或失败时写入一条 JSONL 记录。
    Write one JSONL record for every successful or failed model request.
    """

    def __init__(self, memory_dir: Path):
        self.path = memory_dir / "tokens.jsonl"
        self._lock = Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def record_response(
        self,
        response: Any,
        *,
        operation: str,
        requested_model: str,
        **request_metadata: Any,
    ) -> bool:
        raw_usage = json_safe(getattr(response, "usage", None))
        usage = raw_usage if isinstance(raw_usage, dict) else {}
        input_tokens = _token_count(usage, "input_tokens")
        output_tokens = _token_count(usage, "output_tokens")
        cache_creation_tokens = _token_count(usage, "cache_creation_input_tokens")
        cache_read_tokens = _token_count(usage, "cache_read_input_tokens")

        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "operation": operation,
            "status": "success",
            "requested_model": requested_model,
            "response_model": getattr(response, "model", None),
            "stop_reason": getattr(response, "stop_reason", None),
            "input_tokens": input_tokens,
            "cache_creation_input_tokens": cache_creation_tokens,
            "cache_read_input_tokens": cache_read_tokens,
            "output_tokens": output_tokens,
        }
        if request_metadata:
            record["request_metadata"] = json_safe(request_metadata)
        return self._append(record)

    def record_error(
        self,
        *,
        operation: str,
        requested_model: str,
        error: Exception,
        **request_metadata: Any,
    ) -> bool:
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "operation": operation,
            "status": "error",
            "requested_model": requested_model,
            "response_model": None,
            "error_type": type(error).__name__,
            "usage_available": False,
        }
        if request_metadata:
            record["request_metadata"] = json_safe(request_metadata)
        return self._append(record)

    def _append(self, record: dict) -> bool:
        try:
            with self._lock:
                self._ensure_file()
                with self.path.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(f"[Token记录失败]: {exc}")
            return False
        return True
