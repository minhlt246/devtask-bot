from __future__ import annotations

import os
import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32" or os.name == "nt"


def is_root_dir(path: Path) -> bool:
    """Check if the path is the root directory of a filesystem (e.g. '/' or 'C:\\')."""
    try:
        resolved = path.resolve()
        return str(resolved) == str(resolved.anchor)
    except (OSError, ValueError):
        return False


def get_default_scan_roots(home: Path | None = None) -> list[Path]:
    """
    Return a list of common project directories under the user's home directory.
    Uses platform-aware candidates for Windows and macOS/Linux.
    """
    home = home or Path.home()
    if is_windows():
        candidates = [
            home / "Desktop",
            home / "Documents",
            home / "Downloads",
            home / "source",
            home / "Projects",
            home / "Developer",
            home / "Code",
            home / "dev",
            home / "repos",
            home / "workspace",
            home / "OneDrive",
            home / "OneDrive" / "Desktop",
            home / "OneDrive" / "Documents",
            home / "OneDrive" / "Downloads",
        ]
    else:
        candidates = [
            home / "Desktop",
            home / "Documents",
            home / "Downloads",
            home / "Projects",
            home / "Developer",
            home / "Code",
            home / "Work",
            home / "workspace",
            home / "dev",
            home / "source",
            home / "src",
            home / "repos",
        ]

    result: list[Path] = []
    seen: set[str] = set()

    for candidate in candidates:
        try:
            if candidate.is_dir():
                resolved = candidate.resolve()
                resolved_str = str(resolved)
                if resolved_str not in seen and not is_root_dir(resolved):
                    seen.add(resolved_str)
                    result.append(resolved)
        except (PermissionError, OSError):
            continue

    return result


def get_scan_roots(
    configured_root: Path | str | None = None, home: Path | None = None
) -> list[Path]:
    """
    Return scan roots based on explicit configuration or default auto-discovery.
    Protects against scanning entire disk roots.
    """
    if configured_root is not None:
        raw = str(configured_root).strip()
        if raw and raw != "__AUTO_DISCOVERY__":
            try:
                target = Path(raw).expanduser().resolve()
                if target.is_dir() and not is_root_dir(target):
                    return [target]
            except (PermissionError, OSError):
                pass

    return get_default_scan_roots(home)
