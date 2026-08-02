"""从环境变量加载应用配置。
Load application configuration from environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _positive_int_env(name: str) -> int:
    raw = os.environ.get(name)
    if not raw:
        raise RuntimeError(f"Missing required environment variable: {name}")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got: {raw!r}") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than 0, got: {value}")
    return value


def _binary_flag_env(name: str) -> bool:
    """读取只能为零或一的布尔环境变量。
    Read a Boolean environment variable restricted to zero or one.
    """

    raw = _required_env(name)
    if raw not in {"0", "1"}:
        raise RuntimeError(f"{name} must be 0 or 1, got: {raw!r}")
    return raw == "1"


def _thinking_effort_env(name: str) -> str:
    """读取 DeepSeek 支持的思考强度。
    Read a thinking effort supported by DeepSeek.
    """

    value = _required_env(name).strip().lower()
    if value not in {"high", "max"}:
        raise RuntimeError(f"{name} must be high or max, got: {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path
    skills_dir: Path
    memory_dir: Path
    soul_path: Path
    compact_prompt_path: Path
    api_key: str
    base_url: str
    model: str
    max_tokens: int
    conversation_thinking_enabled: bool
    conversation_thinking_effort: str
    conversation_show_thinking: bool
    compact_after_messages: int
    recent_messages: int
    compaction_max_tokens: int
    compaction_retry_max_tokens: int
    memory_thinking_low_chars: int
    memory_thinking_high_chars: int
    memory_thinking_max_chars: int
    memory_show_thinking: bool
    success_tool_result_max_chars: int
    error_tool_result_max_chars: int
    command_timeout_seconds: int
    max_tool_rounds: int
    compaction_attempts: int
    tool_output_max_chars: int
    max_tool_calls: int
    unlimited_tool_calls: bool

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "Settings":
        """加载运行配置。
        Load runtime settings.
        """
        load_dotenv()

        root = (project_root or Path(__file__).resolve().parents[1]).resolve()
        recent_messages = _positive_int_env("AGENT_MEMORY_RECENT_MESSAGES")
        compact_after = _positive_int_env("AGENT_MEMORY_COMPACT_AFTER")
        if compact_after <= recent_messages:
            raise RuntimeError(
                "AGENT_MEMORY_COMPACT_AFTER must be greater than AGENT_MEMORY_RECENT_MESSAGES"
            )
        memory_thinking_low_chars = _positive_int_env("AGENT_MEMORY_THINKING_LOW_CHARS")
        memory_thinking_high_chars = _positive_int_env("AGENT_MEMORY_THINKING_HIGH_CHARS")
        memory_thinking_max_chars = _positive_int_env("AGENT_MEMORY_THINKING_MAX_CHARS")
        if not (memory_thinking_low_chars < memory_thinking_high_chars < memory_thinking_max_chars):
            raise RuntimeError(
                "Memory thinking thresholds must satisfy "
                "AGENT_MEMORY_THINKING_LOW_CHARS < "
                "AGENT_MEMORY_THINKING_HIGH_CHARS < "
                "AGENT_MEMORY_THINKING_MAX_CHARS"
            )
        compaction_max_tokens = _positive_int_env("AGENT_MEMORY_COMPACTION_MAX_TOKENS")
        compaction_retry_max_tokens = _positive_int_env("AGENT_MEMORY_COMPACTION_RETRY_MAX_TOKENS")
        if compaction_retry_max_tokens < compaction_max_tokens:
            raise RuntimeError(
                "AGENT_MEMORY_COMPACTION_RETRY_MAX_TOKENS must be greater than "
                "or equal to AGENT_MEMORY_COMPACTION_MAX_TOKENS"
            )

        return cls(
            project_root=root,
            skills_dir=root / "skills",
            memory_dir=root / "memory",
            soul_path=root / "templates" / "SOUL.md",
            compact_prompt_path=root / "templates" / "agent" / "compact_prompt.md",
            api_key=_required_env("DEEPSEEK_API_KEY"),
            base_url=_required_env("DEEPSEEK_BASE_URL"),
            model=_required_env("DEEPSEEK_MODEL"),
            max_tokens=_positive_int_env("DEEPSEEK_MAX_TOKENS"),
            conversation_thinking_enabled=_binary_flag_env("AGENT_CONVERSATION_THINKING_ENABLED"),
            conversation_thinking_effort=_thinking_effort_env("AGENT_CONVERSATION_THINKING_EFFORT"),
            conversation_show_thinking=_binary_flag_env("AGENT_CONVERSATION_SHOW_THINKING"),
            compact_after_messages=compact_after,
            recent_messages=recent_messages,
            compaction_max_tokens=compaction_max_tokens,
            compaction_retry_max_tokens=compaction_retry_max_tokens,
            memory_thinking_low_chars=memory_thinking_low_chars,
            memory_thinking_high_chars=memory_thinking_high_chars,
            memory_thinking_max_chars=memory_thinking_max_chars,
            memory_show_thinking=_binary_flag_env("AGENT_MEMORY_SHOW_THINKING"),
            success_tool_result_max_chars=_positive_int_env("SUCCESS_TOOL_RESULT_MAX_CHARS"),
            error_tool_result_max_chars=_positive_int_env("ERROR_TOOL_RESULT_MAX_CHARS"),
            compaction_attempts=_positive_int_env("AGENT_MEMORY_COMPACTION_ATTEMPTS"),
            command_timeout_seconds=_positive_int_env("AGENT_COMMAND_TIMEOUT_SECONDS"),
            tool_output_max_chars=_positive_int_env("AGENT_TOOL_OUTPUT_MAX_CHARS"),
            max_tool_rounds=_positive_int_env("AGENT_MAX_TOOL_ROUNDS"),
            max_tool_calls=_positive_int_env("AGENT_MAX_TOOL_CALLS"),
            unlimited_tool_calls=_binary_flag_env("AGENT_UNLIMITED_TOOL_CALLS"),
        )
