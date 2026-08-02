"""把模型工具调用分派到具体本地实现。
Dispatch model tool calls to concrete local implementations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..common import limit_text_segment
from ..memory.store import MemoryStore
from ..skills import SkillLoader
from .command import CommandRunner
from .files import FileToolbox
from .types import ToolResult
from .web import web_fetch


class ToolExecutor:
    def __init__(
        self,
        *,
        project_root: Path,
        skill_loader: SkillLoader,
        memory_store: MemoryStore,
        command_timeout_seconds: int,
        max_output_chars: int,
    ):
        self.project_root = project_root
        self.skill_loader = skill_loader
        self.memory_store = memory_store
        self.command_timeout_seconds = command_timeout_seconds
        self.max_output_chars = max_output_chars
        self.command_runner = CommandRunner(
            project_root=project_root,
            timeout_seconds=command_timeout_seconds,
            max_output_chars=max_output_chars,
        )
        self.file_toolbox = FileToolbox(
            project_root=project_root,
            max_output_chars=max_output_chars,
        )

    @property
    def environment_description(self) -> str:
        return (
            f"default_shell={self.command_runner.default_shell}"
        )

    def execute(self, block: Any) -> ToolResult:
        try:
            result = self._execute(block)
        except Exception as exc:
            result = ToolResult(
                f"Error executing tool {getattr(block, 'name', '?')!r}: "
                f"{type(exc).__name__}: {exc}",
                True,
            )
        if getattr(block, "name", None) == "load_skill":
            return result
        return ToolResult(
            limit_text_segment(result.content, self.max_output_chars),
            result.is_error,
        )

    def _execute(self, block: Any) -> ToolResult:
        if block.name == "web_fetch":
            url = block.input["url"]
            mode = block.input["extract_mode"]
            start_char = block.input["start_char"]
            max_chars = min(block.input["max_chars"], self.max_output_chars)
            print(f"[网页获取]: {url} start_char={start_char}")
            result = web_fetch(url, mode, start_char, max_chars)
            return ToolResult(result, result.startswith("Error"))

        if block.name == "run_command":
            command = block.input["command"]
            shell = block.input["shell"]
            print(f"[执行命令/{shell}]: {command}")
            result = self.command_runner.run(command, shell)
            return result

        if block.name == "run_python_script":
            script_path = block.input["script_path"]
            args = block.input["args"]
            print(f"[执行 Python 脚本]: {script_path} args={args}")
            result = self.command_runner.run_python_script(script_path, args)
            return result

        if block.name == "list_directory":
            path = block.input["path"]
            print(f"[列出目录]: {path}")
            content = self.file_toolbox.list_directory(
                path,
                pattern=block.input["pattern"],
                recursive=block.input["recursive"],
                max_entries=block.input["max_entries"],
            )
            return ToolResult(content)

        if block.name == "read_file":
            path = block.input["path"]
            print(f"[读取文件]: {path}")
            content = self.file_toolbox.read_file(
                path,
                start_char=block.input["start_char"],
                max_chars=min(block.input["max_chars"], self.max_output_chars),
            )
            return ToolResult(content)

        if block.name == "read_files":
            files = block.input["files"]
            print(f"[批量读取文件]: count={len(files)}")
            content = self.file_toolbox.read_files(files)
            return ToolResult(content)

        if block.name == "read_daily_memory":
            query_type = block.input["query_type"]
            max_chars = min(block.input["max_chars"], self.max_output_chars)
            print(f"[读取日期记忆]: type={query_type} input={block.input}")
            content = self.memory_store.query_daily_memory(
                query_type=query_type,
                date_value=block.input.get("date"),
                days_ago=block.input.get("days_ago"),
                start_date=block.input.get("start_date"),
                end_date=block.input.get("end_date"),
                recent_days=block.input.get("recent_days"),
                max_chars=max_chars,
            )
            return ToolResult(content)

        if block.name == "load_skill":
            skill_name = block.input["skill_name"]
            print(f"[加载技能]: {skill_name}")
            content = self.skill_loader.get_content(skill_name)
            return ToolResult(content, content.startswith("Error"))

        return ToolResult(f"Error: Unknown tool {block.name!r}", True)
