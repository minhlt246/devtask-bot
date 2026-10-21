from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import InlineKeyboardMarkup

from app.handlers import task_commands


@pytest.fixture
def mock_projects(tmp_path: Path) -> list[dict[str, str]]:
    proj_a = tmp_path / "project_alpha"
    proj_a.mkdir()
    proj_b = tmp_path / "project_beta"
    proj_b.mkdir()
    return [
        {"key": "p0001", "name": "project_alpha", "path": str(proj_a.resolve())},
        {"key": "p0002", "name": "project_beta", "path": str(proj_b.resolve())},
    ]


def test_open_command_returns_inline_keyboard(mock_projects):
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_message=SimpleNamespace(reply_text=reply),
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(
        args=[],
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(allowed_user_ids={1}, project_scan_root=""),
            }
        ),
    )

    async def run():
        with (
            patch.object(task_commands, "reject_unauthorized", AsyncMock(return_value=False)),
            patch.object(task_commands, "_discover", return_value=mock_projects),
        ):
            await task_commands.open_project_start(update, context)

    asyncio.run(run())

    assert reply.await_count == 1
    call_args = reply.await_args
    sent_text = call_args.args[0]
    markup = call_args.kwargs.get("reply_markup")

    assert "MỞ DỰ ÁN TRONG IDE" in sent_text
    assert isinstance(markup, InlineKeyboardMarkup)
    # Check buttons
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    data_values = [b.callback_data for b in buttons]
    assert "open_project:p0001" in data_values
    assert "open_project:p0002" in data_values
    assert "open_refresh" in data_values
    assert "open_project:__cancel__" in data_values


def test_click_project_button_opens_project(mock_projects):
    edit_text = AsyncMock()
    answer = AsyncMock()
    query = SimpleNamespace(
        data="open_project:p0001",
        answer=answer,
        edit_message_text=edit_text,
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=1),
    )
    mock_db = MagicMock()
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(allowed_user_ids={1}, code_editor="Cursor"),
                "database": mock_db,
            }
        ),
    )

    opened_paths = []

    def fake_open(path, editor="Cursor"):
        opened_paths.append((str(path), editor))

    async def run():
        with (
            patch.object(task_commands, "reject_unauthorized", AsyncMock(return_value=False)),
            patch.object(task_commands, "_discover", return_value=mock_projects),
            patch.object(task_commands, "open_project", side_effect=fake_open),
        ):
            await task_commands.open_project_callback(update, context)

    asyncio.run(run())

    assert answer.await_count == 1
    assert len(opened_paths) == 1
    assert opened_paths[0][0] == mock_projects[0]["path"]
    assert edit_text.await_count == 1
    confirmation = edit_text.await_args.args[0]
    assert "project_alpha" in confirmation


def test_user_can_switch_from_project_a_to_project_b(mock_projects):
    opened_paths = []

    def fake_open(path, editor="Cursor"):
        opened_paths.append(str(path))

    async def run():
        with (
            patch.object(task_commands, "reject_unauthorized", AsyncMock(return_value=False)),
            patch.object(task_commands, "_discover", return_value=mock_projects),
            patch.object(task_commands, "open_project", side_effect=fake_open),
        ):
            # Select A
            query_a = SimpleNamespace(
                data="open_project:p0001",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
            )
            update_a = SimpleNamespace(callback_query=query_a, effective_user=SimpleNamespace(id=1))
            context_a = SimpleNamespace(
                application=SimpleNamespace(
                    bot_data={
                        "settings": SimpleNamespace(allowed_user_ids={1}, code_editor="Cursor"),
                        "database": MagicMock(),
                    }
                ),
            )
            await task_commands.open_project_callback(update_a, context_a)

            # Select B
            query_b = SimpleNamespace(
                data="open_project:p0002",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
            )
            update_b = SimpleNamespace(callback_query=query_b, effective_user=SimpleNamespace(id=1))
            context_b = SimpleNamespace(
                application=SimpleNamespace(
                    bot_data={
                        "settings": SimpleNamespace(allowed_user_ids={1}, code_editor="Cursor"),
                        "database": MagicMock(),
                    }
                ),
            )
            await task_commands.open_project_callback(update_b, context_b)

    asyncio.run(run())

    assert len(opened_paths) == 2
    assert opened_paths[0] == mock_projects[0]["path"]
    assert opened_paths[1] == mock_projects[1]["path"]
    assert opened_paths[0] != opened_paths[1]


def test_open_callback_missing_or_invalid_project(mock_projects):
    edit_text = AsyncMock()
    query = SimpleNamespace(
        data="open_project:p9999",
        answer=AsyncMock(),
        edit_message_text=edit_text,
    )
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(allowed_user_ids={1}, code_editor="Cursor"),
                "database": MagicMock(),
            }
        ),
    )

    mock_opener = MagicMock()
    async def run():
        with (
            patch.object(task_commands, "reject_unauthorized", AsyncMock(return_value=False)),
            patch.object(task_commands, "_discover", return_value=mock_projects),
            patch.object(task_commands, "open_project", mock_opener),
        ):
            await task_commands.open_project_callback(update, context)

    asyncio.run(run())

    mock_opener.assert_not_called()
    assert edit_text.await_count == 1
    assert "Không còn tìm thấy" in edit_text.await_args.args[0]


def test_open_callback_cancel(mock_projects):
    edit_text = AsyncMock()
    query = SimpleNamespace(
        data="open_project:__cancel__",
        answer=AsyncMock(),
        edit_message_text=edit_text,
    )
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(allowed_user_ids={1}),
                "database": MagicMock(),
            }
        ),
    )

    async def run():
        with patch.object(task_commands, "reject_unauthorized", AsyncMock(return_value=False)):
            await task_commands.open_project_callback(update, context)

    asyncio.run(run())

    assert edit_text.await_count == 1
    assert "Đã hủy" in edit_text.await_args.args[0]


def test_open_command_no_projects_found():
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_message=SimpleNamespace(reply_text=reply),
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(
        args=[],
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(allowed_user_ids={1}, project_scan_root="/custom/path"),
            }
        ),
    )

    async def run():
        with (
            patch.object(task_commands, "reject_unauthorized", AsyncMock(return_value=False)),
            patch.object(task_commands, "_discover", return_value=[]),
        ):
            await task_commands.open_project_start(update, context)

    asyncio.run(run())

    assert reply.await_count == 1
    msg = reply.await_args.args[0]
    assert "Chưa tìm thấy dự án nào" in msg
    assert "PROJECT_SCAN_ROOT" in msg


def test_open_direct_argument(mock_projects):
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_message=SimpleNamespace(reply_text=reply),
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(
        args=["1"],
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(allowed_user_ids={1}, code_editor="Cursor"),
                "database": MagicMock(),
            }
        ),
    )

    opened = []
    async def run():
        with (
            patch.object(task_commands, "reject_unauthorized", AsyncMock(return_value=False)),
            patch.object(task_commands, "_discover", return_value=mock_projects),
            patch.object(task_commands, "open_project", side_effect=lambda p, e: opened.append(str(p))),
        ):
            await task_commands.open_project_start(update, context)

    asyncio.run(run())

    assert len(opened) == 1
    assert opened[0] == mock_projects[0]["path"]
    assert reply.await_count == 1
    assert "project_alpha" in reply.await_args.args[0]
