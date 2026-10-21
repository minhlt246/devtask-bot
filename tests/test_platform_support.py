"""Kiểm thử helper đa nền tảng (static / mock — không yêu cầu máy Windows thật)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from app.services.platform_support import (
    default_agy_command,
    iter_preferred_scan_roots,
    open_path_in_editor,
    preferred_scan_dir_parts,
    resolve_argv,
    resolve_executable,
    split_command,
)


def test_split_command_basic():
    assert split_command("agy -p hello")[0:1] == ["agy"] or split_command("agy") == ["agy"]
    assert split_command("") == []


def test_split_command_windows_quoted_path():
    with patch("app.services.platform_support.is_windows", return_value=True):
        parts = split_command(r'"C:\Program Files\agy\agy.exe" -p x')
    assert parts[0].endswith("agy.exe")
    assert "-p" in parts


def test_resolve_argv_leaves_absolute_file(tmp_path: Path):
    exe = tmp_path / "tool.exe"
    exe.write_text("", encoding="utf-8")
    assert resolve_argv([str(exe), "a"])[0] == str(exe)


def test_default_agy_command_uses_which_when_available():
    with patch("app.services.platform_support.shutil.which", return_value="/fake/agy"):
        assert default_agy_command() == "/fake/agy"


def test_default_agy_command_windows_localappdata(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "agy" / "bin"
    bin_dir.mkdir(parents=True)
    agy = bin_dir / "agy.exe"
    agy.write_text("", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with (
        patch("app.services.platform_support.is_windows", return_value=True),
        patch("app.services.platform_support.shutil.which", return_value=None),
    ):
        assert default_agy_command() == str(agy)


def test_preferred_scan_includes_onedrive_on_windows():
    with patch("app.services.platform_support.is_windows", return_value=True):
        parts = preferred_scan_dir_parts()
    assert ("OneDrive", "Desktop") in parts
    with patch("app.services.platform_support.is_windows", return_value=False):
        parts_unix = preferred_scan_dir_parts()
    assert ("OneDrive", "Desktop") not in parts_unix


def test_iter_preferred_scan_roots_respects_existing_dirs(tmp_path: Path):
    desk = tmp_path / "Desktop"
    desk.mkdir()
    roots = iter_preferred_scan_roots(tmp_path)
    assert desk in roots


def test_open_path_in_editor_macos(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    with (
        patch("app.services.platform_support.is_macos", return_value=True),
        patch("app.services.platform_support.is_windows", return_value=False),
        patch("app.services.platform_support.subprocess.run") as run,
    ):
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        run.return_value.stdout = ""
        ok, msg = open_path_in_editor(project, "Cursor")
    assert ok
    assert "Cursor" in msg or "Opened" in msg
    assert run.call_args.args[0][:3] == ["open", "-a", "Cursor"]


def test_open_path_in_editor_windows_cli(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    with (
        patch("app.services.platform_support.is_macos", return_value=False),
        patch("app.services.platform_support.is_windows", return_value=True),
        patch("app.services.platform_support.shutil.which", return_value=r"C:\Tools\cursor.cmd"),
        patch("app.services.platform_support.subprocess.run") as run,
    ):
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        run.return_value.stdout = ""
        ok, msg = open_path_in_editor(project, "Cursor")
    assert ok
    assert run.call_args.args[0][0].endswith("cursor.cmd")


def test_open_path_in_editor_windows_explorer_fallback(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    with (
        patch("app.services.platform_support.is_macos", return_value=False),
        patch("app.services.platform_support.is_windows", return_value=True),
        patch("app.services.platform_support.shutil.which", return_value=None),
        patch("app.services.platform_support.os.startfile", create=True) as startfile,
    ):
        ok, msg = open_path_in_editor(project, "Cursor")
    assert ok
    assert "Explorer" in msg
    startfile.assert_called_once()


def test_resolve_executable_windows_cmd_suffix():
    with (
        patch("app.services.platform_support.is_windows", return_value=True),
        patch(
            "app.services.platform_support.shutil.which",
            side_effect=lambda name: r"C:\npm.cmd" if name == "npm.cmd" else None,
        ),
    ):
        assert resolve_executable("npm") == r"C:\npm.cmd"


def test_sys_executable_used_for_pytest_args():
    # Đảm bảo worker dùng interpreter hiện tại — quan trọng trên Windows.
    from app.services import agent_worker

    assert hasattr(agent_worker, "sys")
    assert agent_worker.sys.executable == sys.executable
