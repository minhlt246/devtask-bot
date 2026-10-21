"""Kiểm thử lifecycle /status — đọc từ SQLite, không bịa tiến độ."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent_worker import _decide_execute_status, worker_loop
from app.services.task_status import (
    format_task_status,
    normalize_status,
    parse_task_id,
)
from app.storage.database import TaskDatabase


@pytest.fixture
def db(tmp_path: Path) -> TaskDatabase:
    return TaskDatabase(tmp_path / "test.sqlite3")


def _make_request(name: str = "devtask-bot", mode: str = "EXECUTE") -> str:
    return (
        f"[Project: {name} | Path: /tmp/demo]\n"
        f"[Mode: {mode}]\n"
        "Làm gì đó hữu ích"
    )


def test_parse_task_id_numeric_and_prefixed():
    assert parse_task_id("14") == 14
    assert parse_task_id("TASK-0014") == 14
    assert parse_task_id("task-14") == 14
    assert parse_task_id("abc") is None
    assert parse_task_id("") is None


def test_normalize_legacy_statuses():
    assert normalize_status("SUCCEEDED") == "COMPLETED"
    assert normalize_status("COMPLETED_WITH_WARNINGS") == "PARTIAL"
    assert normalize_status("QUEUED") == "QUEUED"


def test_status_queued(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request())
    task = db.get_task(task_id)
    events = db.list_task_events(task_id)
    text = format_task_status(task, events)
    assert "🟡 QUEUED" in text
    assert "Project analysis — PENDING" in text
    assert "Waiting to be claimed" in text
    assert "Not available" in text or "Not recorded" in text


def test_status_running_with_current_step(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request())
    claimed = db.claim_next_task()
    assert claimed is not None
    db.update_task_progress(
        task_id, "Task execution", "EXECUTION_STARTED", "running agent"
    )
    task = db.get_task(task_id)
    events = db.list_task_events(task_id, limit=50)
    text = format_task_status(task, events)
    assert "🔵 RUNNING" in text
    assert "Step        Task execution" in text
    assert "Task execution — RUNNING" in text
    assert "Updated" in text


def test_status_completed(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request())
    db.claim_next_task()
    db.update_task_progress(task_id, "Task execution", "EXECUTION_STARTED")
    db.update_task_progress(task_id, "done", "EXECUTION_COMPLETED", "ok")
    db.update_task_progress(task_id, "tests", "TESTING_STARTED")
    db.update_task_progress(task_id, "tests done", "TESTING_FINISHED", "Exit code: 0\nok")
    db.update_task_progress(task_id, "audit", "AUDIT_STARTED")
    db.update_task_progress(task_id, "audit done", "AUDIT_FINISHED", "verified by audit")
    db.finish_task(
        task_id,
        "COMPLETED",
        "KẾT QUẢ TRIỂN KHAI:\nall good\n\nKIỂM THỬ:\nExit code: 0\n\n"
        "POST-TASK AUDIT (READ-ONLY):\nverified by audit\n",
        "",
    )
    db.update_task_progress(task_id, "Finished", "REPORT_DELIVERED", "sent")
    task = db.get_task(task_id)
    text = format_task_status(task, db.list_task_events(task_id, limit=80))
    assert "🟢 COMPLETED" in text
    assert "Exit code: 0" in text
    assert "verified by audit" in text
    assert "Final report delivery — COMPLETED" in text


def test_status_failed_shows_error(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request())
    db.claim_next_task()
    db.finish_task(task_id, "FAILED", "boom report", "Concrete failure: disk full")
    task = db.get_task(task_id)
    text = format_task_status(task, db.list_task_events(task_id))
    assert "🔴 FAILED" in text
    assert "Concrete failure: disk full" in text


def test_status_partial_and_blocked(db: TaskDatabase):
    partial_id = db.create_task(1, "demo", _make_request())
    db.finish_task(
        partial_id,
        "PARTIAL",
        "KẾT QUẢ TRIỂN KHAI:\npartial\n\nKIỂM THỬ:\nexit code: 1\n\n"
        "POST-TASK AUDIT (READ-ONLY):\nnot verified\n",
        "tests failed",
    )
    partial_text = format_task_status(
        db.get_task(partial_id), db.list_task_events(partial_id)
    )
    assert "🟠 PARTIAL" in partial_text

    blocked_id = db.create_task(1, "demo", _make_request())
    db.finish_task(
        blocked_id,
        "BLOCKED",
        "permission denied by headless mode",
        "Blocked: auto-denied tool",
    )
    blocked_text = format_task_status(
        db.get_task(blocked_id), db.list_task_events(blocked_id)
    )
    assert "⚪ BLOCKED" in blocked_text
    assert "Blocked: auto-denied tool" in blocked_text


def test_status_both_syntaxes_same_task(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request("devtask-bot"))
    task = db.get_task(task_id)
    assert parse_task_id(str(task_id)) == task_id
    assert parse_task_id(f"TASK-{task_id:04d}") == task_id
    text = format_task_status(task, db.list_task_events(task_id))
    assert f"TASK-{task_id:04d}" in text
    assert "devtask-bot" in text


def test_status_missing_task(db: TaskDatabase):
    assert db.get_task(99999) is None


def test_files_changed_preserved(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request())
    db.add_task_event(
        task_id,
        "PROGRESS",
        "📝 Phát hiện file thay đổi: app/services/task_status.py\n"
        "📄 Phát hiện file mới: tests/test_task_status.py",
    )
    db.finish_task(task_id, "COMPLETED", "done", "")
    text = format_task_status(db.get_task(task_id), db.list_task_events(task_id))
    assert "app/services/task_status.py" in text
    assert "tests/test_task_status.py" in text


def test_no_fake_progress_percent(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request())
    text = format_task_status(db.get_task(task_id), db.list_task_events(task_id))
    progress_line = next(line for line in text.splitlines() if line.startswith("Progress"))
    assert "%" not in progress_line


def test_decide_execute_status_not_completed_on_empty_success():
    assert _decide_execute_status(0, "short", "ok", "ok") == "FAILED"
    assert (
        _decide_execute_status(
            0,
            "x" * 40,
            "Exit code: 0",
            "audit status: fail",
        )
        == "PARTIAL"
    )
    assert (
        _decide_execute_status(
            1,
            "Agent không hoàn thành yêu cầu.\nauto-denied\n" + ("y" * 40),
            "",
            "",
        )
        == "BLOCKED"
    )
    assert (
        _decide_execute_status(0, "done work " * 5, "Exit code: 0\npass", "all verified ok")
        == "COMPLETED"
    )


def test_reclaim_orphaned_running(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request())
    db.claim_next_task()
    assert db.get_task(task_id)["status"] == "RUNNING"
    reclaimed = db.reclaim_orphaned_running_tasks("worker died")
    assert task_id in reclaimed
    task = db.get_task(task_id)
    assert task["status"] == "FAILED"
    assert "worker died" in (task["error_text"] or "")
    text = format_task_status(task, db.list_task_events(task_id))
    assert "🔴 FAILED" in text
    status_line = next(line for line in text.splitlines() if line.startswith("Status"))
    assert "RUNNING" not in status_line


def test_fail_stale_running(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request())
    db.claim_next_task()
    with db._connect() as conn:
        conn.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", task_id),
        )
    failed = db.fail_stale_running_tasks(max_idle_seconds=60)
    assert task_id in failed
    assert db.get_task(task_id)["status"] == "FAILED"


def test_legacy_succeeded_displays_as_completed(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request())
    db.finish_task(task_id, "SUCCEEDED", "old success report", "")
    task = db.get_task(task_id)
    view = dict(task)
    view["status"] = normalize_status(task["status"])
    text = format_task_status(view, db.list_task_events(task_id))
    assert "🟢 COMPLETED" in text


def test_report_delivery_failure_marks_partial(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request())
    db.finish_task(
        task_id,
        "COMPLETED",
        "KẾT QUẢ TRIỂN KHAI:\nok\n\nKIỂM THỬ:\nExit code: 0\n\n"
        "POST-TASK AUDIT (READ-ONLY):\nverified\n",
        "",
    )
    db.update_task_progress(
        task_id,
        "Report delivery failed",
        "REPORT_FAILED",
        "Telegram delivery failed: RuntimeError: telegram down",
    )
    db.finish_task(
        task_id,
        "PARTIAL",
        "report\n\nTELEGRAM DELIVERY ERROR: telegram down",
        "Telegram delivery failed: telegram down",
        current_step="Report delivery failed",
    )
    task = db.get_task(task_id)
    events = db.list_task_events(task_id, limit=80)
    text = format_task_status(task, events)
    assert "🟠 PARTIAL" in text
    assert "REPORT_FAILED" in {e["event_type"] for e in events}
    assert "telegram down" in text.casefold()


def test_worker_loop_reclaims_running_on_start(db: TaskDatabase):
    task_id = db.create_task(1, "demo", _make_request())
    db.claim_next_task()
    application = SimpleNamespace(
        bot_data={
            "database": db,
            "settings": SimpleNamespace(agent_timeout_seconds=30),
            "agent_enabled": False,
        }
    )

    async def stop_soon(*_args, **_kwargs):
        raise asyncio.CancelledError()

    async def run():
        with patch("app.services.agent_worker.asyncio.sleep", side_effect=stop_soon):
            await worker_loop(application)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())
    assert db.get_task(task_id)["status"] == "FAILED"


def test_handler_status_message_content(db: TaskDatabase):
    from app.handlers import task_commands

    task_id = db.create_task(1, "demo", _make_request("devtask-bot"))
    db.finish_task(task_id, "FAILED", "report", "boom error")

    reply = AsyncMock()
    update = SimpleNamespace(
        effective_message=SimpleNamespace(reply_text=reply),
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(
        args=[f"TASK-{task_id:04d}"],
        application=SimpleNamespace(
            bot_data={
                "database": db,
                "settings": SimpleNamespace(allowed_user_ids={1}),
            }
        ),
    )

    async def run():
        with patch.object(
            task_commands, "reject_unauthorized", AsyncMock(return_value=False)
        ):
            await task_commands.task_status(update, context)

    asyncio.run(run())
    assert reply.await_count == 1
    sent = reply.await_args.args[0]
    assert "🔴 FAILED" in sent
    assert "boom error" in sent
    assert f"TASK-{task_id:04d}" in sent


def test_handler_numeric_status_syntax(db: TaskDatabase):
    from app.handlers import task_commands

    task_id = db.create_task(1, "demo", _make_request())

    reply = AsyncMock()
    update = SimpleNamespace(
        effective_message=SimpleNamespace(reply_text=reply),
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(
        args=[str(task_id)],
        application=SimpleNamespace(bot_data={"database": db}),
    )

    async def run():
        with patch.object(
            task_commands, "reject_unauthorized", AsyncMock(return_value=False)
        ):
            await task_commands.task_status(update, context)

    asyncio.run(run())
    sent = reply.await_args.args[0]
    assert "🟡 QUEUED" in sent


def test_handler_missing_task(db: TaskDatabase):
    from app.handlers import task_commands

    reply = AsyncMock()
    update = SimpleNamespace(
        effective_message=SimpleNamespace(reply_text=reply),
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(
        args=["TASK-9999"],
        application=SimpleNamespace(bot_data={"database": db}),
    )

    async def run():
        with patch.object(
            task_commands, "reject_unauthorized", AsyncMock(return_value=False)
        ):
            await task_commands.task_status(update, context)

    asyncio.run(run())
    assert "Không tìm thấy task" in reply.await_args.args[0]


def test_status_summarizes_git_dump_instead_of_wall_of_paths(db: TaskDatabase):
    """Report chỉ còn dump git --stat phải được tóm tắt, không in hàng trăm dòng path."""
    from app.storage.database import trim_report_for_storage

    git_wall = "\n".join(
        [f"?? test/file_{i}.dart" for i in range(40)]
        + [f" lib/a_{i}.dart | {i} +-" for i in range(80)]
        + [" 957 files changed, 8511 insertions(+), 132545 deletions(-)"]
    )
    # Giả lập DB cũ: chỉ giữ đuôi report (mất header KẾT QUẢ).
    report = ("x" * 100) + "\n" + git_wall
    task_id = db.create_task(1, "demo", _make_request("Food"))
    db.finish_task(task_id, "COMPLETED_WITH_WARNINGS", report, report[-3000:])
    task = db.get_task(task_id)
    text = format_task_status(task, db.list_task_events(task_id))

    assert "🟠 PARTIAL" in text
    assert "957 files changed" in text
    assert "lib/a_50.dart" not in text  # không đổ cả bảng diff-stat
    assert text.count("?? test/file_") <= 3
    assert "\\n" not in text
    # trim storage phải giữ đầu + shortstat, không chỉ cắt đuôi mù.
    trimmed = trim_report_for_storage("HEAD_MARKER\n" + ("y" * 15000) + "\n" + git_wall)
    assert trimmed.startswith("HEAD_MARKER")
    assert "957 files changed" in trimmed


def test_unescape_literal_newlines_in_status():
    from app.services.task_status import _readable_body

    raw = "Line one\\nLine two\\nBÁO CÁO CUỐI:\\nok"
    out = _readable_body(raw, limit=200)
    assert "\\n" not in out
    assert "Line one" in out and "Line two" in out
