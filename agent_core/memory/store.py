"""持久化长期记忆、用户档案、会话检查点与原始归档。
Persist long-term memory, user profiles, session checkpoints, and raw archives.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from ..common import json_safe, truncate_text
from .datamodels import MemorySnapshot


MAX_DAILY_MEMORY_RANGE_DAYS = 31
ATOMIC_WRITE_RETRIES = 6
ATOMIC_WRITE_RETRY_DELAY_SECONDS = 0.05


class MemoryStore:
    """管理运行时记忆文件。
    Manage runtime memory files.
    """

    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir
        self.memory_file = memory_dir / "MEMORY.md"
        self.user_file = memory_dir / "USER.md"
        self.history_file = memory_dir / "history.jsonl"
        self.session_file = memory_dir / "session.json"
        self.archive_dir = memory_dir / "archives"

    def ensure_files(self) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        if not self.memory_file.exists():
            self._atomic_write(self.memory_file, "# Long-term Memory\n\n")
        if not self.user_file.exists():
            self._atomic_write(self.user_file, "# User Profile\n\n")
        if not self.history_file.exists():
            self.history_file.touch()
        if not self.session_file.exists():
            self._atomic_write(self.session_file, "[]\n")

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
                file.write(text)
                file.flush()
                os.fsync(file.fileno())
            for attempt in range(ATOMIC_WRITE_RETRIES):
                try:
                    os.replace(temp, path)
                    return
                except PermissionError:
                    if attempt + 1 >= ATOMIC_WRITE_RETRIES:
                        raise
                    time.sleep(ATOMIC_WRITE_RETRY_DELAY_SECONDS * (attempt + 1))
        finally:
            temp.unlink(missing_ok=True)

    def append_history(self, message: dict) -> None:
        self.ensure_files()
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "role": message.get("role"),
            "content": json_safe(message.get("content")),
        }
        with self.history_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load_session(self) -> list[dict]:
        self.ensure_files()
        try:
            value = json.loads(self.session_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[短期会话恢复警告]: {exc}")
            return []
        if not isinstance(value, list) or not all(
            isinstance(message, dict) for message in value
        ):
            print("[短期会话恢复警告]: session.json 格式无效")
            return []
        return value

    def save_session(self, history: list[dict]) -> None:
        self.ensure_files()
        payload = json.dumps(json_safe(history), ensure_ascii=False, indent=2)
        self._atomic_write(self.session_file, payload + "\n")

    def archive_messages(self, messages: list[dict]) -> str:
        self.ensure_files()
        safe_messages = json_safe(messages)
        canonical = json.dumps(
            safe_messages,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
        day_dir = self.archive_dir / f"{datetime.now():%Y-%m-%d}"
        archive_file = day_dir / f"{digest}.json"
        if not archive_file.exists():
            payload = {
                "version": 1,
                "archived_at": datetime.now().isoformat(timespec="seconds"),
                "message_count": len(messages),
                "messages": safe_messages,
            }
            self._atomic_write(
                archive_file,
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            )
        return archive_file.relative_to(self.memory_dir).as_posix()

    def snapshot(self) -> MemorySnapshot:
        self.ensure_files()
        episode_file = self.memory_dir / f"{datetime.now():%Y-%m-%d}.md"
        return MemorySnapshot(
            long_term=self.memory_file.read_text(encoding="utf-8"),
            user_profile=self.user_file.read_text(encoding="utf-8"),
            today_episode=(
                episode_file.read_text(encoding="utf-8")
                if episode_file.exists()
                else ""
            ),
        )

    @staticmethod
    def _parse_iso_date(value: str | None, field_name: str) -> date:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} is required and must use YYYY-MM-DD")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} must use YYYY-MM-DD: {value!r}") from exc
        if parsed.isoformat() != value:
            raise ValueError(f"{field_name} must use YYYY-MM-DD: {value!r}")
        return parsed

    def query_daily_memory(
        self,
        *,
        query_type: str,
        date_value: str | None,
        days_ago: int | None,
        start_date: str | None,
        end_date: str | None,
        recent_days: int | None,
        max_chars: int,
    ) -> str:
        """按明确日期或相对范围读取每日情景记忆。
        Read daily episodic memory by exact date or relative range.
        """

        start, end = self._resolve_daily_memory_range(
            query_type=query_type,
            date_value=date_value,
            days_ago=days_ago,
            start_date=start_date,
            end_date=end_date,
            recent_days=recent_days,
        )
        if isinstance(max_chars, bool) or not isinstance(max_chars, int):
            raise ValueError("max_chars must be an integer")
        if not 1 <= max_chars <= 50000:
            raise ValueError("max_chars must be between 1 and 50000")

        requested_days = (end - start).days + 1
        found: list[tuple[date, str]] = []
        missing: list[str] = []
        for offset in range(requested_days):
            current = start + timedelta(days=offset)
            episode_file = self.memory_dir / f"{current.isoformat()}.md"
            if episode_file.is_file():
                found.append(
                    (current, episode_file.read_text(encoding="utf-8").strip())
                )
            else:
                missing.append(current.isoformat())

        if query_type == "date":
            target = start.isoformat()
            if found:
                content = found[0][1] or "(该日期的记忆文件为空)"
                result = (
                    "query_type: date\n"
                    f"date: {target}\n"
                    "status: found\n"
                    "content:\n"
                    f"{content}"
                )
            else:
                result = (
                    "query_type: date\n"
                    f"date: {target}\n"
                    "status: missing\n"
                    "content:\n"
                    "(该日期没有每日记忆文件)"
                )
            return truncate_text(result, max_chars)

        sections = [
            f"## {memory_date.isoformat()}\n{content or '(该日期的记忆文件为空)'}"
            for memory_date, content in found
        ]
        result = (
            "query_type: range\n"
            f"start_date: {start.isoformat()}\n"
            f"end_date: {end.isoformat()}\n"
            f"requested_days: {requested_days}\n"
            f"found_days: {len(found)}\n"
            f"missing_dates: {', '.join(missing) if missing else '(none)'}\n"
            "content:\n"
            + ("\n\n".join(sections) if sections else "(范围内没有每日记忆文件)")
        )
        return truncate_text(result, max_chars)

    def _resolve_daily_memory_range(
        self,
        *,
        query_type: str,
        date_value: str | None,
        days_ago: int | None,
        start_date: str | None,
        end_date: str | None,
        recent_days: int | None,
    ) -> tuple[date, date]:
        """校验查询参数并解析为闭区间日期。
        Validate query arguments and resolve them to an inclusive date range.
        """

        if query_type == "date":
            if any(value is not None for value in (start_date, end_date, recent_days)):
                raise ValueError(
                    "date queries cannot include start_date, end_date, or recent_days"
                )
            selectors = int(date_value is not None) + int(days_ago is not None)
            if selectors != 1:
                raise ValueError(
                    "date queries require exactly one of date or days_ago"
                )
            if date_value is not None:
                target = self._parse_iso_date(date_value, "date")
            else:
                if (
                    isinstance(days_ago, bool)
                    or not isinstance(days_ago, int)
                    or days_ago < 0
                    or days_ago > 36500
                ):
                    raise ValueError("days_ago must be an integer between 0 and 36500")
                target = datetime.now().date() - timedelta(days=days_ago)
            return target, target

        if query_type != "range":
            raise ValueError("query_type must be date or range")
        if date_value is not None or days_ago is not None:
            raise ValueError("range queries cannot include date or days_ago")

        has_explicit_range = start_date is not None or end_date is not None
        has_recent_range = recent_days is not None
        if has_explicit_range == has_recent_range:
            raise ValueError(
                "range queries require start_date/end_date or recent_days, but not both"
            )
        if has_recent_range:
            if (
                isinstance(recent_days, bool)
                or not isinstance(recent_days, int)
                or not 1 <= recent_days <= MAX_DAILY_MEMORY_RANGE_DAYS
            ):
                raise ValueError(
                    "recent_days must be an integer between 1 and "
                    f"{MAX_DAILY_MEMORY_RANGE_DAYS}"
                )
            end = datetime.now().date()
            start = end - timedelta(days=recent_days - 1)
            return start, end

        start = self._parse_iso_date(start_date, "start_date")
        end = self._parse_iso_date(end_date, "end_date")
        if start > end:
            raise ValueError("start_date cannot be later than end_date")
        requested_days = (end - start).days + 1
        if requested_days > MAX_DAILY_MEMORY_RANGE_DAYS:
            raise ValueError(
                f"date range cannot exceed {MAX_DAILY_MEMORY_RANGE_DAYS} days"
            )
        return start, end

    def apply_compaction(
        self,
        *,
        episode: str,
        updated_memory: str,
        updated_user: str,
    ) -> None:
        self.ensure_files()
        episode_file = self.memory_dir / f"{datetime.now():%Y-%m-%d}.md"
        previous_episode = (
            episode_file.read_text(encoding="utf-8") if episode_file.exists() else None
        )
        if previous_episode is None:
            next_episode = f"# Daily Memory {datetime.now():%Y-%m-%d}\n"
        else:
            next_episode = previous_episode.rstrip() + "\n"
        next_episode += "\n" + episode.strip() + "\n"

        updates = {
            self.memory_file: updated_memory.strip() + "\n",
            self.user_file: updated_user.strip() + "\n",
            episode_file: next_episode,
        }

        previous = {
            path: path.read_text(encoding="utf-8") if path.exists() else None
            for path in updates
        }
        try:
            for path, content in updates.items():
                self._atomic_write(path, content)
        except OSError:
            for path, old_content in previous.items():
                rollback_attempt = 0
                while True:
                    try:
                        if old_content is None:
                            path.unlink(missing_ok=True)
                        else:
                            self._atomic_write(path, old_content)
                        break
                    except OSError as rollback_error:
                        rollback_attempt += 1
                        if rollback_attempt == 1 or rollback_attempt % 10 == 0:
                            print(
                                "[记忆回滚重试]: "
                                f"path={path} attempt={rollback_attempt} "
                                f"error={rollback_error}"
                            )
                        delay = ATOMIC_WRITE_RETRY_DELAY_SECONDS * min(
                            rollback_attempt,
                            ATOMIC_WRITE_RETRIES,
                        )
                        time.sleep(delay)
            raise
