"""按平台执行命令并稳定捕获 Unicode 输出。
Execute commands by platform and capture Unicode output deterministically.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..common import truncate_text
from .encoding import decode_bytes
from .types import ToolResult


class CommandRunner:
    def __init__(
        self,
        *,
        project_root: Path,
        timeout_seconds: int,
        max_output_chars: int,
    ):
        self.project_root = project_root
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    @property
    def default_shell(self) -> str:
        return "powershell" if os.name == "nt" else "sh"

    @property
    def python_executable(self) -> str:
        return sys.executable

    def run(self, command: str, shell: str) -> ToolResult:
        if not isinstance(command, str) or not command.strip():
            return ToolResult("Error: command must be a non-empty string", True)

        try:
            argv, shell_name, encoding_hint = self._build_command(command, shell)
        except ValueError as exc:
            return ToolResult(f"Error: {exc}", True)

        return self._run_process(
            argv,
            runtime_name=shell_name,
            encoding_hint=encoding_hint,
        )

    def run_python_script(
        self,
        script_path: str,
        args: list[str],
    ) -> ToolResult:
        if not isinstance(script_path, str) or not script_path.strip():
            return ToolResult("Error: script_path must be a non-empty string", True)
        if not isinstance(args, list) or not all(
            isinstance(argument, str) for argument in args
        ):
            return ToolResult("Error: args must be an array of strings", True)

        project_root = self.project_root.resolve()
        candidate = Path(script_path)
        if not candidate.is_absolute():
            candidate = project_root / candidate
        script = candidate.resolve()
        try:
            script.relative_to(project_root)
        except ValueError:
            return ToolResult(
                "Error: Python scripts must be inside the project directory",
                True,
            )
        if script.suffix.lower() != ".py":
            return ToolResult("Error: script_path must point to a .py file", True)
        if not script.is_file():
            return ToolResult(f"Error: Python script does not exist: {script}", True)

        return self._run_process(
            [self.python_executable, "-B", str(script), *args],
            runtime_name=f"python ({self.python_executable})",
            encoding_hint="utf-8",
        )

    def _run_process(
        self,
        argv: list[str],
        *,
        runtime_name: str,
        encoding_hint: str,
    ) -> ToolResult:

        try:
            completed = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=False,
                cwd=str(self.project_root),
                timeout=self.timeout_seconds,
                env=self._subprocess_environment(),
            )
        except subprocess.TimeoutExpired as exc:
            stdout, stdout_encoding = decode_bytes(
                exc.stdout or b"", preferred=encoding_hint
            )
            stderr, stderr_encoding = decode_bytes(
                exc.stderr or b"", preferred=encoding_hint
            )
            details = self._format_output(
                shell_name=runtime_name,
                exit_code=None,
                stdout=stdout,
                stderr=stderr,
                stdout_encoding=stdout_encoding,
                stderr_encoding=stderr_encoding,
            )
            return ToolResult(
                f"Error: command timed out after {self.timeout_seconds}s\n{details}",
                True,
            )
        except OSError as exc:
            return ToolResult(f"Error: could not start {runtime_name}: {exc}", True)

        stdout, stdout_encoding = decode_bytes(
            completed.stdout, preferred=encoding_hint
        )
        stderr, stderr_encoding = decode_bytes(
            completed.stderr, preferred=encoding_hint
        )
        output = self._format_output(
            shell_name=runtime_name,
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            stdout_encoding=stdout_encoding,
            stderr_encoding=stderr_encoding,
        )
        return ToolResult(
            truncate_text(output, self.max_output_chars),
            is_error=completed.returncode != 0,
        )

    @staticmethod
    def _subprocess_environment() -> dict[str, str]:
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        return environment

    def _build_command(self, command: str, shell: str) -> tuple[list[str], str, str]:
        requested = shell.lower()
        if requested == "auto":
            requested = self.default_shell

        if os.name == "nt":
            if requested == "powershell":
                executable = self._find_executable("pwsh", "powershell")
                if executable is None:
                    raise ValueError("PowerShell was not found")
                utf8_prelude = (
                    "$agentUtf8 = New-Object System.Text.UTF8Encoding($false); "
                    "[Console]::InputEncoding = $agentUtf8; "
                    "[Console]::OutputEncoding = $agentUtf8; "
                    "$OutputEncoding = $agentUtf8; "
                )
                return (
                    [
                        executable,
                        "-NoLogo",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        utf8_prelude + command,
                    ],
                    "powershell",
                    "utf-8",
                )
            if requested == "cmd":
                executable = os.environ.get("COMSPEC") or self._find_executable(
                    "cmd.exe"
                )
                if executable is None:
                    raise ValueError("cmd.exe was not found")
                return [executable, "/d", "/s", "/c", command], "cmd", "oem"
            raise ValueError("on Windows, shell must be auto, powershell, or cmd")

        if requested not in {"sh", "bash"}:
            raise ValueError("on this platform, shell must be auto, sh, or bash")
        executable = self._find_executable(requested)
        if executable is None:
            raise ValueError(f"{requested} was not found")
        return [executable, "-lc", command], requested, "utf-8"

    @staticmethod
    def _find_executable(*commands: str) -> str | None:
        """按顺序查找可执行文件并返回普通字符串路径。
        Find an executable in order and return its path as a plain string.
        """
        for command in commands:
            executable = shutil.which(command)
            if executable is not None:
                return str(executable)
        return None

    @staticmethod
    def _format_output(
        *,
        shell_name: str,
        exit_code: int | None,
        stdout: str,
        stderr: str,
        stdout_encoding: str,
        stderr_encoding: str,
    ) -> str:
        sections = [f"shell: {shell_name}", f"exit_code: {exit_code}"]
        if stdout:
            sections.append(f"stdout ({stdout_encoding}):\n{stdout.rstrip()}")
        if stderr:
            sections.append(f"stderr ({stderr_encoding}):\n{stderr.rstrip()}")
        if not stdout and not stderr:
            sections.append("output: (empty)")
        return "\n".join(sections)
