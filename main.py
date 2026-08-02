"""组装依赖并提供命令行入口。
Compose dependencies and provide the command-line entry point.
"""

from __future__ import annotations

import anthropic

from agent_core.config import Settings
from agent_core.memory import MemoryCompactor, MemoryStore
from agent_core.presentation import configure_console_utf8
from agent_core.prompts import SystemPromptBuilder
from agent_core.runtime import AgentRuntime
from agent_core.skills import SkillLoader
from agent_core.tools import ToolExecutor
from agent_core.telemetry import TokenUsageRecorder


def create_runtime(settings: Settings | None = None) -> AgentRuntime:
    settings = settings or Settings.from_env()
    client = anthropic.Anthropic(
        api_key=settings.api_key,
        base_url=settings.base_url,
    )

    skill_loader = SkillLoader(settings.skills_dir)
    for warning in skill_loader.warnings:
        print(f"[Skill警告]: {warning}")

    memory_store = MemoryStore(settings.memory_dir)
    prompt_builder = SystemPromptBuilder(
        memory_store=memory_store,
        skill_loader=skill_loader,
        soul_path=settings.soul_path,
    )

    tool_executor = ToolExecutor(
        project_root=settings.project_root,
        skill_loader=skill_loader,
        memory_store=memory_store,
        command_timeout_seconds=settings.command_timeout_seconds,
        max_output_chars=settings.tool_output_max_chars,
    )

    token_recorder = TokenUsageRecorder(settings.memory_dir)
    memory_compactor = MemoryCompactor(
        client=client,
        model=settings.model,
        store=memory_store,
        token_recorder=token_recorder,
        prompt_path=settings.compact_prompt_path,
        compact_after_messages=settings.compact_after_messages,
        recent_messages=settings.recent_messages,
        max_tokens=settings.compaction_max_tokens,
        retry_max_tokens=settings.compaction_retry_max_tokens,
        thinking_low_chars=settings.memory_thinking_low_chars,
        thinking_high_chars=settings.memory_thinking_high_chars,
        thinking_max_chars=settings.memory_thinking_max_chars,
        show_thinking=settings.memory_show_thinking,
        success_tool_result_max_chars=settings.success_tool_result_max_chars,
        error_tool_result_max_chars=settings.error_tool_result_max_chars,
        max_attempts=settings.compaction_attempts,
    )

    return AgentRuntime(
        client=client,
        model=settings.model,
        max_tokens=settings.max_tokens,
        memory_store=memory_store,
        memory_compactor=memory_compactor,
        token_recorder=token_recorder,
        prompt_builder=prompt_builder,
        tool_executor=tool_executor,
        max_tool_rounds=settings.max_tool_rounds,
        max_tool_calls=settings.max_tool_calls,
        thinking_enabled=settings.conversation_thinking_enabled,
        thinking_effort=settings.conversation_thinking_effort,
        show_thinking=settings.conversation_show_thinking,
        unlimited_tool_calls=settings.unlimited_tool_calls,
    )


def main() -> None:
    configure_console_utf8()
    create_runtime().run()


if __name__ == "__main__":
    main()
