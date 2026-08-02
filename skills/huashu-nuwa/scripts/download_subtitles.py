"""下载优先级最高的人工或自动字幕。
Download the highest-priority manual or automatic subtitles.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


CHINESE_LANGUAGES = ("zh-Hans", "zh-CN", "zh-Hant", "zh-TW", "zh")
ENGLISH_LANGUAGES = ("en", "en-US", "en-GB")
SUPPORTED_OUTPUT_SUFFIXES = {".srt", ".vtt"}


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    """描述准备下载的一条字幕轨道。
    Describe one subtitle track selected for download.
    """

    language: str
    automatic: bool


def _load_yt_dlp() -> Any:
    """延迟加载 yt-dlp 并给出可执行的安装提示。
    Load yt-dlp lazily and provide an actionable installation hint.
    """

    try:
        import yt_dlp
    except ModuleNotFoundError as exc:
        if exc.name != "yt_dlp":
            raise
        raise RuntimeError(
            "缺少 yt-dlp；请使用 Agent 的 Python 执行 "
            "-m pip install --upgrade 'yt-dlp[default]'"
        ) from exc
    return yt_dlp


def _select_language(
    catalogue: Mapping[str, Any],
    preferred: Sequence[str],
) -> str | None:
    """按精确匹配和地区变体顺序选择语言。
    Select a language by exact match and then regional variants.
    """

    normalized = {language.casefold(): language for language in catalogue}
    for preferred_language in preferred:
        exact = normalized.get(preferred_language.casefold())
        if exact:
            return exact
    for preferred_language in preferred:
        prefix = preferred_language.casefold() + "-"
        for language in catalogue:
            if language.casefold().startswith(prefix):
                return language
    return None


def select_subtitle_track(info: Mapping[str, Any]) -> SubtitleTrack | None:
    """按照中文人工、英文人工、中文自动、英文自动的顺序选择字幕。
    Select subtitles in Chinese-manual, English-manual, Chinese-auto, English-auto order.
    """

    manual = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    choices = (
        (manual, CHINESE_LANGUAGES, False),
        (manual, ENGLISH_LANGUAGES, False),
        (automatic, CHINESE_LANGUAGES, True),
        (automatic, ENGLISH_LANGUAGES, True),
    )
    for catalogue, preferred, is_automatic in choices:
        language = _select_language(catalogue, preferred)
        if language:
            return SubtitleTrack(language=language, automatic=is_automatic)
    return None


def _subtitle_snapshot(directory: Path) -> dict[Path, tuple[int, int]]:
    """记录目录中可清洗字幕文件的修改状态。
    Record modification state for cleanable subtitle files in a directory.
    """

    snapshot: dict[Path, tuple[int, int]] = {}
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_OUTPUT_SUFFIXES:
            continue
        stat = path.stat()
        snapshot[path.resolve()] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _changed_subtitles(
    directory: Path,
    before: Mapping[Path, tuple[int, int]],
) -> list[Path]:
    """返回本次下载新建或修改的字幕文件。
    Return subtitle files created or modified by the current download.
    """

    changed: list[Path] = []
    for path, state in _subtitle_snapshot(directory).items():
        if before.get(path) != state:
            changed.append(path)
    return sorted(changed, key=lambda path: path.stat().st_mtime_ns, reverse=True)


def download_subtitles(url: str, output_directory: Path) -> list[Path]:
    """提取字幕清单并下载优先级最高的可用轨道。
    Extract subtitle metadata and download the highest-priority available track.
    """

    yt_dlp = _load_yt_dlp()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    inspect_options = {
        "skip_download": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(inspect_options) as downloader:
        info = downloader.extract_info(url, download=False)
    if not isinstance(info, Mapping):
        raise RuntimeError("yt-dlp 未返回有效的视频信息")

    track = select_subtitle_track(info)
    if track is None:
        raise RuntimeError("没有找到中文或英文的人工/自动字幕")

    before = _subtitle_snapshot(output_directory)
    download_options = {
        "skip_download": True,
        "noplaylist": True,
        "writesubtitles": not track.automatic,
        "writeautomaticsub": track.automatic,
        "subtitleslangs": [track.language],
        "subtitlesformat": "srt/vtt/best",
        "outtmpl": str(output_directory / "%(title)s.%(ext)s"),
    }
    kind = "自动字幕" if track.automatic else "人工字幕"
    print(f"[字幕选择] {kind}，语言={track.language}")
    with yt_dlp.YoutubeDL(download_options) as downloader:
        downloader.extract_info(url, download=True)

    downloaded = _changed_subtitles(output_directory, before)
    if not downloaded:
        raise RuntimeError(
            "yt-dlp 没有生成新的 SRT/VTT；可能只提供了其他字幕格式"
        )
    return downloaded


def _build_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。
    Build the command-line argument parser.
    """

    parser = argparse.ArgumentParser(description="下载 YouTube 人工或自动字幕")
    parser.add_argument("url", help="YouTube 视频 URL")
    parser.add_argument(
        "output_directory",
        nargs="?",
        default=".",
        help="字幕输出目录，默认为当前目录",
    )
    return parser


def main() -> int:
    """执行字幕下载命令并返回进程退出码。
    Run the subtitle download command and return its process exit code.
    """

    arguments = _build_parser().parse_args()
    try:
        downloaded = download_subtitles(
            arguments.url,
            Path(arguments.output_directory),
        )
    except Exception as exc:
        print(f"[字幕下载失败] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    for path in downloaded:
        print(f"[字幕下载成功] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
