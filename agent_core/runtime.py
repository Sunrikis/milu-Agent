"""实现命令行 Agent 的对话与工具循环。
Implement conversation and tool loops for the command-line Agent.
"""

from __future__ import annotations

from typing import Any

from .memory import MemoryCompactor, MemoryStore
from .presentation import ConsoleStreamRenderer
from .prompts import SystemPromptBuilder, build_runtime_context
from .telemetry import TokenUsageRecorder
from .tools import TOOL_DEFINITIONS, ToolExecutor, ToolResult


class AgentRuntime:
    def __init__(
        self,
        *,
        client: Any,
        model: str,
        max_tokens: int,
        memory_store: MemoryStore,
        memory_compactor: MemoryCompactor,
        token_recorder: TokenUsageRecorder,
        prompt_builder: SystemPromptBuilder,
        tool_executor: ToolExecutor,
        max_tool_rounds: int,
        max_tool_calls: int,
        thinking_enabled: bool,
        thinking_effort: str,
        show_thinking: bool,
        unlimited_tool_calls: bool,
    ):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.memory_store = memory_store
        self.memory_compactor = memory_compactor
        self.token_recorder = token_recorder
        self.prompt_builder = prompt_builder
        self.tool_executor = tool_executor
        self.max_tool_rounds = max_tool_rounds
        self.max_tool_calls = max_tool_calls
        self.thinking_enabled = thinking_enabled
        self.thinking_effort = thinking_effort
        self.show_thinking = show_thinking
        self.unlimited_tool_calls = unlimited_tool_calls
        self.history: list[dict] = self.memory_store.load_session()

    def run(self) -> None:
        resumed = f"；已恢复 {len(self.history)} 条短期消息" if self.history else ""
        print(
            "[记忆系统已启用；输入 /compact 手动整理记忆，输入 /quit 退出"
            f"{resumed}]"
        )
        while True:
            try:
                user_input = input("[你]: ").strip()
            except (EOFError, KeyboardInterrupt):
                self._sync_memory(
                    force_compaction=False,
                    announce_session=True,
                )
                return

            if not user_input:
                continue
            if user_input == "/quit":
                self._sync_memory(
                    force_compaction=False,
                    announce_session=True,
                )
                return
            if user_input == "/compact":
                print("\n[正在手动整理记忆]")
                self._sync_memory(
                    force_compaction=True,
                    announce_session=False,
                )
                continue

            try:
                self.process_turn(user_input)
            except Exception as exc:
                print(f"[Agent运行错误]: {exc}\n")

    def process_turn(self, user_input: str) -> None:
        self._record({"role": "user", "content": user_input})
        tool_rounds = 0
        tool_calls = 0

        while True:
            tool_rounds_remaining = (
                None if self.unlimited_tool_calls else self.max_tool_rounds - tool_rounds
            )
            tool_calls_remaining = (
                None if self.unlimited_tool_calls else self.max_tool_calls - tool_calls
            )
            message, has_text = self._stream_message(
                tools=TOOL_DEFINITIONS,
                tool_rounds_remaining=tool_rounds_remaining,
                tool_calls_remaining=tool_calls_remaining,
            )
            self._record({"role": "assistant", "content": message.content})

            tool_blocks = [
                block
                for block in message.content
                if getattr(block, "type", None) == "tool_use"
            ]

            if message.stop_reason != "tool_use" or not tool_blocks:
                if has_text:
                    print()
                self._sync_memory(
                    force_compaction=False,
                    announce_session=False,
                )
                return

            if has_text:
                print()

            available_calls = (
                len(tool_blocks)
                if self.unlimited_tool_calls
                else max(0, self.max_tool_calls - tool_calls)
            )
            executable_blocks = tool_blocks[:available_calls]
            rejected_blocks = tool_blocks[available_calls:]
            tool_results = [self._execute_tool(block) for block in executable_blocks]
            tool_results.extend(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Error: maximum tool calls reached for this user turn",
                    "is_error": True,
                }
                for block in rejected_blocks
            )
            self._record({"role": "user", "content": tool_results})
            tool_rounds += 1
            tool_calls += len(executable_blocks)

            if not self.unlimited_tool_calls and (
                tool_rounds >= self.max_tool_rounds
                or tool_calls >= self.max_tool_calls
                or rejected_blocks
            ):
                final_message, final_has_text = self._stream_message(
                    tools=None,
                    tool_rounds_remaining=max(0, self.max_tool_rounds - tool_rounds),
                    tool_calls_remaining=max(0, self.max_tool_calls - tool_calls),
                    final_instruction=(
                        "本轮工具预算已用完。请基于已有结果给出当前能完成的最佳答案；"
                        "明确区分已完成和未完成，不得再次请求工具，也不要让用户仅为了"
                        "重置工具次数而重复同一句指令。"
                    ),
                )
                self._record({"role": "assistant", "content": final_message.content})
                if final_has_text:
                    print()
                self._sync_memory(
                    force_compaction=False,
                    announce_session=False,
                )
                return

    def _sync_memory(
        self,
        *,
        force_compaction: bool,
        announce_session: bool,
    ) -> None:
        should_compact = force_compaction or self.memory_compactor.needs_compaction(self.history)
        if not should_compact:
            self.memory_store.save_session(self.history)
            if announce_session:
                print(
                    "[短期会话已保存；未超过记忆整理阈值]: "
                    f"messages={len(self.history)}"
                )
            return

        if should_compact and not force_compaction:
            print("[超过记忆整理阈值，开始记忆整理]")

        outcome = self.memory_compactor.compact(
            self.history,
            force=force_compaction,
        )
        self.history = outcome.history
        self.memory_store.save_session(self.history)
        if outcome.compacted:
            print(f"[记忆已整理]: archived={outcome.archived_messages}")
            if outcome.warning:
                print(f"[记忆整理警告]: {outcome.warning}")
        elif outcome.saved and (outcome.archive_path or outcome.warning):
            print("[原始记忆已保存；语义整理待后续重试]")
            if outcome.warning:
                print(f"[记忆整理警告]: {outcome.warning}")
        elif outcome.error:
            print(
                "[记忆整理失败；未压缩对话已保存，将在下次启动恢复]: "
                f"{outcome.error}"
            )

    def _record(self, message: dict) -> None:
        self.history.append(message)
        self.memory_store.append_history(message)
        self.memory_store.save_session(self.history)

    def _execute_tool(self, block: Any) -> dict:
        result = self.tool_executor.execute(block)
        if not isinstance(result, ToolResult):
            raise TypeError(
                "tool_executor.execute() must return ToolResult, "
                f"got {type(result).__name__}"
            )
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": result.content,
            "is_error": result.is_error,
        }

    def _stream_message(
        self,
        *,
        tools: list[dict] | None,
        tool_rounds_remaining: int | None = None,
        tool_calls_remaining: int | None = None,
        final_instruction: str | None = None,
    ) -> tuple[Any, bool]:
        environment_description = self.tool_executor.environment_description
        system_prompt = self.prompt_builder.build()
        system_prompt += build_runtime_context(
            environment_description=environment_description,
            tool_rounds_remaining=tool_rounds_remaining,
            tool_calls_remaining=tool_calls_remaining,
            final_instruction=final_instruction,
        )

        request = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "thinking": {
                "type": "enabled" if self.thinking_enabled else "disabled"
            },
            "system": system_prompt,
            "messages": self.history,
        }
        if self.thinking_enabled:
            request["output_config"] = {"effort": self.thinking_effort}
        if tools is not None:
            request["tools"] = tools

        renderer = ConsoleStreamRenderer(
            show_thinking=self.thinking_enabled and self.show_thinking,
            show_text=True,
            thinking_label="Agent思考",
            text_label="Agent回答",
        )
        try:
            with self.client.messages.stream(**request) as stream:
                for event in stream:
                    renderer.render(event)
                message = stream.get_final_message()
        except Exception as exc:
            renderer.finish()
            self.token_recorder.record_error(
                operation="conversation",
                requested_model=self.model,
                error=exc,
            )
            raise

        renderer.finish()
        self.token_recorder.record_response(
            message,
            operation="conversation",
            requested_model=self.model,
            history_messages=len(self.history),
            max_tokens=self.max_tokens,
            thinking_enabled=self.thinking_enabled,
            thinking_effort=self.thinking_effort if self.thinking_enabled else None,
        )
        return message, renderer.has_output
