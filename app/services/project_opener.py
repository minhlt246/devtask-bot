from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32" or os.name == "nt"


def is_macos() -> bool:
    return sys.platform == "darwin"


def open_project(project_path: str | Path, editor: str = "Cursor") -> None:
    """
    Open a project directory in Cursor (or configured editor) on macOS or Windows.
    Raises FileNotFoundError if directory does not exist or CLI launcher is missing on Windows.
    Raises OSError if subprocess fails.
    """
    path = Path(project_path).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(f"Project directory does not exist: {path}")

    editor_name = (editor or "Cursor").strip() or "Cursor"
    is_cursor = editor_name.casefold() in {"cursor", "cursor.cmd", "cursor.exe"}

    cursor = shutil.which("cursor") or shutil.which("cursor.cmd") or shutil.which("cursor.exe")

    if is_macos():
        if cursor and is_cursor:
            command = [cursor, str(path)]
        else:
            app_name = "Cursor" if is_cursor else editor_name
            command = ["open", "-a", app_name, str(path)]
    elif is_windows():
        if is_cursor:
            if cursor:
                command = [cursor, str(path)]
            else:
                raise FileNotFoundError(
                    "Cannot find Cursor CLI. Install Cursor and enable its command-line launcher, then retry."
                )
        else:
            cli = shutil.which(editor_name) or shutil.which(f"{editor_name}.cmd") or shutil.which(f"{editor_name}.exe")
            if cli:
                command = [cli, str(path)]
            else:
                raise FileNotFoundError(
                    f"Cannot find editor CLI for '{editor_name}' on Windows PATH."
                )
    else:
        # Linux and other POSIX systems
        if cursor and is_cursor:
            command = [cursor, str(path)]
        else:
            cli = shutil.which(editor_name) if not is_cursor else None
            if cli:
                command = [cli, str(path)]
            else:
                xdg = shutil.which("xdg-open")
                if xdg:
                    command = [xdg, str(path)]
                else:
                    raise FileNotFoundError(
                        f"Cannot find '{editor_name}' CLI or 'xdg-open' on PATH."
                    )

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Required opener command not found: {exc.filename or command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise OSError(f"Timed out while launching editor: {exc}") from exc

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Editor process exited with non-zero code").strip()
        raise OSError(f"Command {' '.join(command)} failed: {err}")
