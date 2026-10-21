from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_GIT_SHORTSTAT_RE = re.compile(
    r"\d+ files? changed(?:, \d+ insertions?\(\+\))?(?:, \d+ deletions?\(-\))?"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def trim_report_for_storage(report: str, limit: int = 12000) -> str:
    """Giữ phần đầu report (header/kết quả) — không cắt mất vì đuôi là git dump dài."""
    text = report or ""
    if len(text) <= limit:
        return text
    shortstat = ""
    match = _GIT_SHORTSTAT_RE.search(text)
    if match:
        shortstat = "\n\n[GIT SUMMARY]\n" + match.group(0)
    marker = "\n\n…[truncated]…"
    budget = max(500, limit - len(shortstat) - len(marker))
    return text[:budget].rstrip() + marker + shortstat


class TaskDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        """Open one SQLite connection per operation and always commit/rollback/close it."""
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL,
                    project_key TEXT NOT NULL,
                    request_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'QUEUED',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error_text TEXT,
                    report_text TEXT,
                    status_chat_id INTEGER,
                    status_message_id INTEGER,
                    current_step TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_status_created
                    ON tasks(status, created_at);
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                CREATE TABLE IF NOT EXISTS user_preferences (
                    telegram_user_id INTEGER PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    project_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            # Backward-compatible migration for databases created by older bot versions.
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            if "status_chat_id" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN status_chat_id INTEGER")
            if "status_message_id" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN status_message_id INTEGER")
            if "current_step" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN current_step TEXT")

    def save_selected_project(
        self, telegram_user_id: int, project_key: str, project_name: str, project_path: str
    ) -> None:
        """Persist the user's current project so follow-up tasks survive restarts."""
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO user_preferences
                   (telegram_user_id, project_key, project_name, project_path, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(telegram_user_id) DO UPDATE SET
                     project_key=excluded.project_key,
                     project_name=excluded.project_name,
                     project_path=excluded.project_path,
                     updated_at=excluded.updated_at""",
                (telegram_user_id, project_key, project_name, project_path, now),
            )

    def get_selected_project(self, telegram_user_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT project_key, project_name, project_path, updated_at "
                "FROM user_preferences WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()
            return dict(row) if row else None

    def create_task(self, telegram_user_id: int, project_key: str, request_text: str) -> int:
        now = utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (telegram_user_id, project_key, request_text, status, created_at, updated_at) VALUES (?, ?, ?, 'QUEUED', ?, ?)",
                (telegram_user_id, project_key, request_text, now, now),
            )
            task_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO task_events (task_id, event_type, details, created_at) VALUES (?, 'CREATED', ?, ?)",
                (task_id, "Task đã được đưa vào hàng đợi", now),
            )
            return task_id

    def set_status_message(self, task_id: int, chat_id: int, message_id: int) -> None:
        """Save the Telegram message that must be edited throughout the task lifecycle."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET status_chat_id=?, status_message_id=? WHERE id=?",
                (chat_id, message_id, task_id),
            )

    def get_task(self, task_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row) if row else None

    def list_tasks(self, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in rows]

    def add_task_event(
        self, task_id: int, event_type: str, details: str = ""
    ) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_events
                    (task_id, event_type, details, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (task_id, event_type, details[-3000:], now),
            )
            conn.execute(
                "UPDATE tasks SET updated_at = ? WHERE id = ?",
                (now, task_id),
            )

    def update_task_progress(
        self, task_id: int, current_step: str, event_type: str = "", details: str = ""
    ) -> None:
        """Cập nhật bước hiện tại và (tuỳ chọn) ghi task_event — dùng khi worker chuyển giai đoạn."""
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET current_step = ?, updated_at = ? WHERE id = ?",
                (current_step[:500], now, task_id),
            )
            if event_type:
                conn.execute(
                    """
                    INSERT INTO task_events
                        (task_id, event_type, details, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (task_id, event_type, (details or current_step)[-3000:], now),
                )

    def reclaim_orphaned_running_tasks(self, reason: str) -> list[int]:
        """Khi worker khởi động lại: mọi task RUNNING bị coi là gián đoạn (không để treo mãi)."""
        now = utc_now()
        message = reason[-3000:]
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM tasks WHERE status = 'RUNNING' ORDER BY id ASC"
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            for task_id in ids:
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'FAILED',
                        updated_at = ?,
                        finished_at = ?,
                        current_step = ?,
                        error_text = ?,
                        report_text = COALESCE(report_text, ?)
                    WHERE id = ? AND status = 'RUNNING'
                    """,
                    (now, now, "Worker interrupted", message, message, task_id),
                )
                conn.execute(
                    """
                    INSERT INTO task_events
                        (task_id, event_type, details, created_at)
                    VALUES (?, 'FAILED', ?, ?)
                    """,
                    (task_id, message, now),
                )
            return ids

    def fail_stale_running_tasks(self, max_idle_seconds: int) -> list[int]:
        """Task RUNNING không cập nhật quá lâu → FAILED (worker treo / chết giữa chừng)."""
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat(timespec="seconds")
        failed: list[int] = []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, updated_at FROM tasks WHERE status = 'RUNNING'"
            ).fetchall()
            for row in rows:
                updated_raw = row["updated_at"] or ""
                try:
                    updated = datetime.fromisoformat(
                        updated_raw.replace("Z", "+00:00")
                        if updated_raw.endswith("Z")
                        else updated_raw
                    )
                except ValueError:
                    updated = None
                if updated is None:
                    continue
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                idle = (now_dt - updated).total_seconds()
                if idle < max_idle_seconds:
                    continue
                task_id = int(row["id"])
                message = (
                    f"Task marked FAILED: no progress for {int(idle)}s "
                    f"(limit {max_idle_seconds}s). Worker likely stalled or died."
                )
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'FAILED',
                        updated_at = ?,
                        finished_at = ?,
                        current_step = ?,
                        error_text = ?
                    WHERE id = ? AND status = 'RUNNING'
                    """,
                    (now, now, "Stale running task", message, task_id),
                )
                conn.execute(
                    """
                    INSERT INTO task_events
                        (task_id, event_type, details, created_at)
                    VALUES (?, 'FAILED', ?, ?)
                    """,
                    (task_id, message, now),
                )
                failed.append(task_id)
        return failed

    def list_task_events(
        self, task_id: int, limit: int = 20
    ) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_type, details, created_at
                FROM task_events
                WHERE task_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
            return [dict(row) for row in reversed(rows)]

    def cancel_task(self, task_id: int, telegram_user_id: int) -> str:
        now = utc_now()
        with self._connect() as conn:
            row = conn.execute("SELECT status, telegram_user_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return "NOT_FOUND"
            if int(row["telegram_user_id"]) != telegram_user_id:
                return "FORBIDDEN"
            if row["status"] != "QUEUED":
                return "NOT_QUEUED"
            conn.execute("UPDATE tasks SET status = 'CANCELLED', updated_at = ?, finished_at = ? WHERE id = ?", (now, now, task_id))
            conn.execute(
                "INSERT INTO task_events (task_id, event_type, details, created_at) VALUES (?, 'CANCELLED', ?, ?)",
                (task_id, "Đã hủy khi còn trong hàng đợi", now),
            )
            return "CANCELLED"

    def claim_next_task(self) -> dict | None:
        """Atomically move the oldest queued task to RUNNING."""
        now = utc_now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tasks WHERE status='QUEUED' ORDER BY id ASC LIMIT 1").fetchone()
            if row is None:
                return None
            task_id = int(row["id"])
            changed = conn.execute(
                """
                UPDATE tasks
                SET status='RUNNING', started_at=?, updated_at=?, current_step=?
                WHERE id=? AND status='QUEUED'
                """,
                (now, now, "Claimed by worker", task_id),
            ).rowcount
            if not changed:
                return None
            conn.execute(
                "INSERT INTO task_events (task_id,event_type,details,created_at) VALUES (?, 'STARTED', ?, ?)",
                (task_id, "Antigravity worker bắt đầu xử lý", now),
            )
            return dict(conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def finish_task(
        self,
        task_id: int,
        status: str,
        report: str,
        error: str = "",
        current_step: str = "Finished",
    ) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status=?, updated_at=?, finished_at=?, report_text=?, error_text=?, current_step=?
                WHERE id=?
                """,
                (
                    status,
                    now,
                    now,
                    trim_report_for_storage(report, 12000),
                    trim_report_for_storage(error, 4000) if error else None,
                    current_step[:500],
                    task_id,
                ),
            )
            # Event kết thúc dùng REPORT_FINISHED — tránh nhét status raw + dump git làm event_type.
            conn.execute(
                "INSERT INTO task_events (task_id,event_type,details,created_at) VALUES (?, ?, ?, ?)",
                (
                    task_id,
                    "REPORT_FINISHED",
                    f"Final status: {status}"[:500],
                    now,
                ),
            )
