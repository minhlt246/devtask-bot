"""Helpers tách hành vi phụ thuộc hệ điều hành — giữ logic nghiệp vụ dùng chung."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def default_agy_command() -> str:
    """Đường dẫn mặc định tới CLI `agy` theo từng nền tảng (có thể ghi đè bằng AGY_COMMAND)."""
    found = shutil.which("agy")
    if found:
        return found

    home = Path.home()
    candidates: list[Path] = []
    if is_windows():
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        candidates.extend(
            [
                local / "agy" / "bin" / "agy.exe",
                local / "agy" / "bin" / "agy.cmd",
                local / "agy" / "bin" / "agy",
                home / "AppData" / "Local" / "agy" / "bin" / "agy.exe",
            ]
        )
    else:
        candidates.extend(
            [
                home / ".local" / "bin" / "agy",
                Path("/usr/local/bin/agy"),
            ]
        )

    for path in candidates:
        if path.is_file():
            return str(path)

    # Để worker báo lỗi rõ nếu thiếu CLI; người dùng đặt AGY_COMMAND khi cần.
    return "agy"


def split_command(command: str) -> list[str]:
    """Tách lệnh cấu hình thành argv — posix=False trên Windows để giữ đường dẫn có khoảng trắng."""
    text = (command or "").strip()
    if not text:
        return []
    # Một đường dẫn file duy nhất (kể cả có khoảng trắng) — không cần tách.
    if Path(text).is_file():
        return [text]
    parts = shlex.split(text, posix=not is_windows())
    if is_windows():
        # shlex posix=False có thể giữ dấu ngoặc kép quanh token — gỡ để subprocess nhận path thật.
        cleaned: list[str] = []
        for part in parts:
            if len(part) >= 2 and part[0] == part[-1] == '"':
                cleaned.append(part[1:-1])
            else:
                cleaned.append(part)
        return cleaned
    return parts


def resolve_executable(name: str) -> str:
    """Tìm executable thật (hữu ích trên Windows với .cmd/.bat của npm/go)."""
    if not name:
        return name
    # Đường dẫn tuyệt đối / tương đối đã chỉ rõ file.
    as_path = Path(name)
    if as_path.is_file():
        return str(as_path)

    found = shutil.which(name)
    if found:
        return found

    if is_windows() and not name.lower().endswith((".exe", ".cmd", ".bat", ".com")):
        for suffix in (".cmd", ".bat", ".exe"):
            found = shutil.which(name + suffix)
            if found:
                return found
    return name


def resolve_argv(args: list[str]) -> list[str]:
    if not args:
        return args
    resolved = list(args)
    resolved[0] = resolve_executable(resolved[0])
    return resolved


def preferred_scan_dir_parts() -> tuple[tuple[str, ...], ...]:
    """Các đoạn đường dẫn ưu tiên dưới home — bổ sung OneDrive* trên Windows."""
    base: tuple[tuple[str, ...], ...] = (
        ("Desktop",),
        ("Documents",),
        ("Downloads",),
        ("Projects",),
        ("Developer",),
        ("Code",),
        ("Work",),
        ("workspace",),
        ("dev",),
        ("source",),
        ("src",),
        ("repos",),
    )
    if is_windows():
        return base + (
            ("OneDrive",),
            ("OneDrive", "Desktop"),
            ("OneDrive", "Documents"),
            ("OneDrive", "Downloads"),
        )
    return base


def iter_preferred_scan_roots(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    roots: list[Path] = []
    for parts in preferred_scan_dir_parts():
        path = home.joinpath(*parts)
        if path.is_dir():
            roots.append(path)
    return roots


def open_path_in_editor(path: Path, editor: str) -> tuple[bool, str]:
    """
    Mở thư mục dự án trong IDE theo nền tảng.
    Trả về (ok, message). Không ném exception cho lỗi subprocess thông thường.
    """
    target = path.expanduser().resolve()
    if not target.is_dir():
        return False, "Project directory does not exist."

    editor_name = (editor or "Cursor").strip() or "Cursor"
    key = editor_name.casefold()

    try:
        if is_macos():
            app_map = {
                "cursor": "Cursor",
                "code": "Visual Studio Code",
                "vscode": "Visual Studio Code",
                "visual studio code": "Visual Studio Code",
                "sublime": "Sublime Text",
                "sublime text": "Sublime Text",
            }
            app = app_map.get(key, editor_name)
            result = subprocess.run(
                ["open", "-a", app, str(target)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "open failed").strip()
                return False, f"Could not open with {app}: {err}"
            return True, f"Opened with {app}: {target}"

        if is_windows():
            cli_candidates = {
                "cursor": ("cursor", "cursor.cmd"),
                "code": ("code", "code.cmd"),
                "vscode": ("code", "code.cmd"),
                "visual studio code": ("code", "code.cmd"),
            }.get(key, (editor_name, editor_name + ".cmd", editor_name + ".exe"))

            for candidate in cli_candidates:
                exe = shutil.which(candidate)
                if not exe:
                    continue
                result = subprocess.run(
                    [exe, str(target)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                if result.returncode == 0:
                    return True, f"Opened with {exe}: {target}"
                err = (result.stderr or result.stdout or "").strip()
                return False, f"Could not open with {exe}: {err or 'non-zero exit'}"

            # Fallback: mở thư mục trong Explorer — không giả lập IDE.
            os.startfile(str(target))  # type: ignore[attr-defined]
            return True, (
                f"Editor CLI '{editor_name}' not found on PATH; "
                f"opened folder in Explorer: {target}"
            )

        # Linux / other: xdg-open or editor CLI if present.
        for candidate in (editor_name, "xdg-open"):
            exe = shutil.which(candidate)
            if not exe:
                continue
            result = subprocess.run(
                [exe, str(target)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode == 0:
                return True, f"Opened with {exe}: {target}"
        return False, (
            f"No supported opener found for editor '{editor_name}' on {sys.platform}."
        )
    except FileNotFoundError as exc:
        return False, f"Required opener missing: {exc.filename or exc}"
    except subprocess.TimeoutExpired:
        return False, "Timed out while opening the editor."
    except OSError as exc:
        return False, f"OS error while opening editor: {exc}"
