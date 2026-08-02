"""根据整理内容长度自动选择思考强度并执行语义记忆整理。
Perform semantic memory compaction with thinking effort selected by input length.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..common import truncate_text
from ..presentation import ConsoleStreamRenderer
from ..telemetry import TokenUsageRecorder
from .formatting import (
    choose_compaction_split,
    extract_tag,
    messages_to_text,
    response_text,
)
from .datamodels import CompactionOutcome
from .store import MemoryStore


class MemoryCompactor:
    """在安全归档后让模型把旧对话转换为长期记忆。
    Convert old conversation into durable memory after safe archival.
    """

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        store: MemoryStore,
        token_recorder: TokenUsageRecorder,
        prompt_path: Path,
        compact_after_messages: int,
        recent_messages: int,
        max_tokens: int,
        retry_max_tokens: int,
        thinking_low_chars: int,
        thinking_high_chars: int,
        thinking_max_chars: int,
        show_thinking: bool,
        success_tool_result_max_chars: int,
        error_tool_result_max_chars: int,
        max_attempts: int,
    ):
        self.client = client
        self.model = model
        self.store = store
        self.token_recorder = token_recorder
        self.prompt_path = prompt_path
        self.compact_after_messages = compact_after_messages
        self.recent_messages = recent_messages
        self.max_tokens = max_tokens
        self.retry_max_tokens = retry_max_tokens
        self.thinking_low_chars = thinking_low_chars
        self.thinking_high_chars = thinking_high_chars
        self.thinking_max_chars = thinking_max_chars
        self.show_thinking = show_thinking
        self.success_tool_result_max_chars = success_tool_result_max_chars
        self.error_tool_result_max_chars = error_tool_result_max_chars
        self.max_attempts = max_attempts

    def needs_compaction(self, history: list[dict]) -> bool:
        return len(history) > self.compact_after_messages

    def compact(self, history: list[dict], *, force: bool = False) -> CompactionOutcome:
        if not history:
            return CompactionOutcome(history=history, compacted=False, saved=True)
        if not force and not self.needs_compaction(history):
            return CompactionOutcome(history=history, compacted=False, saved=True)

        if force:
            split_at = len(history)
        else:
            split_at = choose_compaction_split(history, self.recent_messages)
            if split_at == 0:
                return CompactionOutcome(
                    history=history,
                    compacted=False,
                    saved=True,
                    warning="No safe conversation boundary was found",
                )

        old_messages = history[:split_at]
        recent_messages = history[split_at:]
        try:
            archive_path = self.store.archive_messages(old_messages)
        except Exception as exc:
            return CompactionOutcome(
                history=history,
                compacted=False,
                saved=False,
                error=f"Could not archive messages: {exc}",
            )

        try:
            snapshot = self.store.snapshot()
            template = self.prompt_path.read_text(encoding="utf-8")
            prompt = template.format(
                old_conversation=messages_to_text(
                    old_messages,
                    success_tool_result_max_chars=self.success_tool_result_max_chars,
                    error_tool_result_max_chars=self.error_tool_result_max_chars,
                ),
                current_memory=snapshot.long_term,
                current_user=snapshot.user_profile,
                today_episode=snapshot.today_episode,
                now_hhmm=datetime.now().strftime("%H:%M"),
            )
            episode, updated_memory, updated_user, warning = self._generate_memory(
                prompt,
                current_user=snapshot.user_profile,
            )
        except Exception as exc:
            return CompactionOutcome(
                history=history,
                compacted=False,
                saved=True,
                archive_path=archive_path,
                warning=(
                    "语义整理未完成，但原始消息已安全归档并保留在短期会话中："
                    f"{type(exc).__name__}: {exc}"
                ),
            )

        try:
            self.store.apply_compaction(
                episode=episode,
                updated_memory=updated_memory,
                updated_user=updated_user,
            )
        except Exception as exc:
            return CompactionOutcome(
                history=history,
                compacted=False,
                saved=True,
                archive_path=archive_path,
                warning=(
                    "语义结果写入失败，但原始消息已安全归档并保留在短期会话中："
                    f"{type(exc).__name__}: {exc}"
                ),
            )

        return CompactionOutcome(
            history=recent_messages,
            compacted=True,
            saved=True,
            archived_messages=len(old_messages),
            archive_path=archive_path,
            warning=warning,
        )

    def _generate_memory(
        self,
        prompt: str,
        *,
        current_user: str,
    ) -> tuple[str, str, str, str | None]:
        request_prompt = prompt
        thinking_effort = self._select_thinking_effort(len(prompt))
        best_core: tuple[str, str] | None = None
        last_missing: list[str] = []
        last_stop_reason: str | None = None
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                message = self._request_compaction(
                    request_prompt,
                    attempt=attempt,
                    thinking_effort=thinking_effort,
                )
            except Exception as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    continue
                break

            text = response_text(message)
            episode = extract_tag(text, "episode")
            updated_memory = extract_tag(text, "updated_memory")
            updated_user = extract_tag(text, "updated_user")
            last_stop_reason = getattr(message, "stop_reason", None)
            last_missing = [
                tag
                for tag, value in (
                    ("episode", episode),
                    ("updated_memory", updated_memory),
                    ("updated_user", updated_user),
                )
                if not value
            ]

            if not last_missing:
                return episode, updated_memory, updated_user, None
            if episode and updated_memory:
                best_core = (episode, updated_memory)
            if attempt < self.max_attempts:
                request_prompt = self._repair_prompt(
                    original_prompt=prompt,
                    invalid_output=text,
                    missing=last_missing,
                    stop_reason=last_stop_reason,
                )

        if best_core is not None:
            episode, updated_memory = best_core
            reason = "updated_user 缺失，已保留原 USER.md"
            if last_error is not None:
                reason += f"；重试失败：{type(last_error).__name__}"
            return episode, updated_memory, current_user, reason

        details = f"missing={','.join(last_missing) or 'all'}"
        if last_stop_reason:
            details += f", stop_reason={last_stop_reason}"
        if last_error is not None:
            details += f", retry_error={type(last_error).__name__}"
        raise ValueError(
            "Compaction response is missing required XML sections after "
            f"{self.max_attempts} attempt(s): {details}"
        )

    def _select_thinking_effort(self, input_chars: int) -> str | None:
        if input_chars >= self.thinking_max_chars:
            return "max"
        if input_chars >= self.thinking_high_chars:
            return "high"
        if input_chars >= self.thinking_low_chars:
            return "low"
        return None

    @staticmethod
    def _repair_prompt(
        *,
        original_prompt: str,
        invalid_output: str,
        missing: list[str],
        stop_reason: str | None,
    ) -> str:
        previous = truncate_text(invalid_output, 8000)
        return f"""{original_prompt}

上一次输出未通过校验。缺少：{', '.join(missing)}；stop_reason={stop_reason or 'unknown'}。
请重新输出完整的三段 XML，不要解释、不要使用 Markdown 代码围栏。

<previous_invalid_output>
{previous}
</previous_invalid_output>
"""

    def _request_compaction(
        self,
        prompt: str,
        *,
        attempt: int,
        thinking_effort: str | None,
    ) -> Any:
        output_budget = (
            min(
                self.max_tokens * (2 ** (attempt - 1)),
                self.retry_max_tokens,
            )
        )
        thinking_enabled = thinking_effort is not None
        renderer = ConsoleStreamRenderer(
            show_thinking=thinking_enabled and self.show_thinking,
            show_text=False,
            thinking_label="记忆整理思考",
            text_label="记忆整理结果",
        )
        request = {
            "model": self.model,
            "max_tokens": output_budget,
            "thinking": {
                "type": "enabled" if thinking_enabled else "disabled"
            },
            "system": "你是记忆整理员。严格按要求输出 XML，不要输出额外解释。",
            "messages": [{"role": "user", "content": prompt}],
        }
        if thinking_enabled:
            request["output_config"] = {"effort": thinking_effort}
        try:
            with self.client.messages.stream(**request) as stream:
                for event in stream:
                    renderer.render(event)
                message = stream.get_final_message()
        except Exception as exc:
            renderer.finish()
            self.token_recorder.record_error(
                operation="memory_compaction",
                requested_model=self.model,
                error=exc,
                thinking_enabled=thinking_enabled,
                thinking_effort=thinking_effort,
                max_tokens=output_budget,
                attempt=attempt,
            )
            raise

        renderer.finish()
        self.token_recorder.record_response(
            message,
            operation="memory_compaction",
            requested_model=self.model,
            thinking_enabled=thinking_enabled,
            thinking_effort=thinking_effort,
            max_tokens=output_budget,
            attempt=attempt,
        )
        return message
