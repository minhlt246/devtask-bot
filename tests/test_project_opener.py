from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.project_opener import open_project


def test_open_project_missing_path_raises_filenotfound(tmp_path: Path):
    missing = tmp_path / "does_not_exist"
    with pytest.raises(FileNotFoundError, match="Project directory does not exist"):
        open_project(missing)


def test_open_project_macos_with_cursor_cli(tmp_path: Path):
    project = tmp_path / "my_project"
    project.mkdir()

    with (
        patch("app.services.project_opener.is_macos", return_value=True),
        patch("app.services.project_opener.is_windows", return_value=False),
        patch("shutil.which", return_value="/usr/local/bin/cursor"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        open_project(project)

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args == ["/usr/local/bin/cursor", str(project.resolve())]


def test_open_project_macos_fallback_open_a(tmp_path: Path):
    project = tmp_path / "my_project"
    project.mkdir()

    with (
        patch("app.services.project_opener.is_macos", return_value=True),
        patch("app.services.project_opener.is_windows", return_value=False),
        patch("shutil.which", return_value=None),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        open_project(project)

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args == ["open", "-a", "Cursor", str(project.resolve())]


def test_open_project_windows_with_cursor_cli(tmp_path: Path):
    project = tmp_path / "my_project"
    project.mkdir()

    with (
        patch("app.services.project_opener.is_macos", return_value=False),
        patch("app.services.project_opener.is_windows", return_value=True),
        patch("shutil.which", return_value=r"C:\Users\User\AppData\Local\Programs\cursor\cursor.cmd"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        open_project(project)

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == r"C:\Users\User\AppData\Local\Programs\cursor\cursor.cmd"
    assert args[1] == str(project.resolve())


def test_open_project_windows_missing_cursor_cli_raises_filenotfound(tmp_path: Path):
    project = tmp_path / "my_project"
    project.mkdir()

    with (
        patch("app.services.project_opener.is_macos", return_value=False),
        patch("app.services.project_opener.is_windows", return_value=True),
        patch("shutil.which", return_value=None),
    ):
        with pytest.raises(FileNotFoundError, match="Cannot find Cursor CLI"):
            open_project(project)


def test_open_project_subprocess_failure_raises_oserror(tmp_path: Path):
    project = tmp_path / "my_project"
    project.mkdir()

    with (
        patch("app.services.project_opener.is_macos", return_value=True),
        patch("app.services.project_opener.is_windows", return_value=False),
        patch("shutil.which", return_value="/usr/local/bin/cursor"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Could not connect to display")
        with pytest.raises(OSError, match="failed: Could not connect to display"):
            open_project(project)
