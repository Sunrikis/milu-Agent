"""提供 Unicode 安全的目录和文档读取能力。
Provide Unicode-safe directory and document reading capabilities.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from ..common import format_text_segment, truncate_text
from .encoding import decode_bytes


_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_WORD_PARAGRAPH = f"{{{_WORD_NAMESPACE}}}p"
_WORD_TEXT = f"{{{_WORD_NAMESPACE}}}t"
_WORD_TAB = f"{{{_WORD_NAMESPACE}}}tab"
_WORD_BREAKS = {
    f"{{{_WORD_NAMESPACE}}}br",
    f"{{{_WORD_NAMESPACE}}}cr",
}


class FileToolbox:
    def __init__(self, *, project_root: Path, max_output_chars: int):
        self.project_root = project_root
        self.max_output_chars = max_output_chars

    def list_directory(
        self,
        path: str,
        *,
        pattern: str,
        recursive: bool,
        max_entries: int,
    ) -> str:
        directory = self._resolve(path)
        if not directory.exists():
            raise FileNotFoundError(f"directory does not exist: {directory}")
        if not directory.is_dir():
            raise NotADirectoryError(f"not a directory: {directory}")

        max_entries = max(1, min(int(max_entries), 1000))
        iterator = directory.rglob(pattern) if recursive else directory.glob(pattern)
        entries = sorted(iterator, key=lambda item: str(item).casefold())
        visible = entries[:max_entries]

        lines = [f"directory: {directory}", f"matched: {len(entries)}"]
        for item in visible:
            relative = item.relative_to(directory)
            if item.is_dir():
                lines.append(f"[dir]  {relative}")
            else:
                try:
                    size = item.stat().st_size
                except OSError:
                    size = -1
                lines.append(f"[file] {relative} ({size} bytes)")
        if len(entries) > len(visible):
            lines.append(f"... {len(entries) - len(visible)} more entries omitted")
        return truncate_text("\n".join(lines), self.max_output_chars)

    def read_file(
        self,
        path: str,
        *,
        start_char: int,
        max_chars: int,
    ) -> str:
        file_path = self._resolve(path)
        text, _, _ = self._read_content(file_path)
        limit = max(1, min(int(max_chars), self.max_output_chars))
        return format_text_segment(
            str(file_path),
            text,
            start_char=start_char,
            max_chars=limit,
        )

    def read_files(self, requests: list[dict[str, Any]]) -> str:
        if not requests:
            raise ValueError("files must contain at least one request")
        if len(requests) > 10:
            raise ValueError("at most 10 files can be read in one call")

        parts: list[str] = []
        per_file_budget = max(500, (self.max_output_chars // len(requests)) - 200)
        for index, request in enumerate(requests, start=1):
            if not isinstance(request, dict) or not request.get("path"):
                parts.append(f"## file {index}\nError: path is required")
                continue
            try:
                result = self.read_file(
                    str(request["path"]),
                    start_char=int(request["start_char"]),
                    max_chars=min(
                        int(request["max_chars"]),
                        per_file_budget,
                    ),
                )
            except Exception as exc:
                result = f"Error: {type(exc).__name__}: {exc}"
            parts.append(f"## file {index}\n{result}")
        return truncate_text("\n\n".join(parts), self.max_output_chars)

    def _resolve(self, path: str) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        return candidate.resolve()

    @staticmethod
    def _read_content(path: Path) -> tuple[str, str, str]:
        if not path.exists():
            raise FileNotFoundError(f"file does not exist: {path}")
        if not path.is_file():
            raise IsADirectoryError(f"not a file: {path}")
        if path.suffix.lower() == ".docx":
            return FileToolbox._read_docx(path), "docx", "Open XML"

        raw = path.read_bytes()
        text, encoding = decode_bytes(raw)
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalized, "text", encoding

    @staticmethod
    def _read_docx(path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                document_xml = archive.read("word/document.xml")
        except (KeyError, zipfile.BadZipFile) as exc:
            raise ValueError(f"invalid .docx file: {path}") from exc

        try:
            root = ET.fromstring(document_xml)
        except ET.ParseError as exc:
            raise ValueError(f"invalid Word XML in: {path}") from exc

        paragraphs: list[str] = []
        for paragraph in root.iter(_WORD_PARAGRAPH):
            parts: list[str] = []
            for node in paragraph.iter():
                if node.tag == _WORD_TEXT and node.text:
                    parts.append(node.text)
                elif node.tag == _WORD_TAB:
                    parts.append("\t")
                elif node.tag in _WORD_BREAKS:
                    parts.append("\n")
            paragraphs.append("".join(parts))
        return "\n".join(paragraphs)
