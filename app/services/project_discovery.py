from __future__ import annotations
import os
from pathlib import Path

from app.services.platform_support import iter_preferred_scan_roots

PROJECT_MARKERS = {
    ".git", "pyproject.toml", "requirements.txt", "Pipfile",
    "package.json", "pnpm-workspace.yaml", "yarn.lock", "package-lock.json",
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    "Cargo.toml", "go.mod", "composer.json", "Gemfile", "CMakeLists.txt",
    "Makefile", "pubspec.yaml", "mix.exs", "manage.py", "deno.json",
    "deno.jsonc", "bun.lockb", "bun.lock",
}
SKIP_DIRS = {
    "org.eclipse", ".metadata", ".settings", ".replit", ".terraform", ".svn", ".hg",
    "Library", "Applications", "System", "Volumes", "private", "dev",
    ".Trash", ".Trashes", ".Spotlight-V100", ".fseventsd",
    "node_modules", "vendor", ".venv", "venv", "__pycache__",
    ".next", ".nuxt", "dist", "build", "target", ".gradle",
    ".idea", ".vscode", "Pods", "DerivedData", ".cache", ".npm",
    ".pnpm-store", ".cargo", ".rustup", ".local", "Parallels", "Docker",
    "Caches",
}

def _has_marker(directory: Path) -> bool:
    try:
        entries = list(directory.iterdir())
    except (PermissionError, OSError):
        return False
    names = {p.name for p in entries}
    if names.intersection(PROJECT_MARKERS):
        return True
    return any(p.is_file() and p.suffix in {".sln", ".csproj", ".fsproj"}
               for p in entries)

def default_scan_roots() -> list[Path]:
    home = Path.home()
    roots = list(iter_preferred_scan_roots(home))
    try:
        for child in home.iterdir():
            if not child.is_dir() or child.name.startswith(".") or child.name in SKIP_DIRS:
                continue
            if child not in roots:
                roots.append(child)
    except (PermissionError, OSError):
        pass
    result, seen = [], set()
    for p in roots:
        try:
            resolved = str(p.resolve())
        except OSError:
            continue
        if resolved not in seen:
            seen.add(resolved)
            result.append(Path(resolved))
    return result

def discover_projects(roots: list[Path] | None = None, max_depth: int = 12,
                      max_projects: int = 1000) -> list[dict[str, str]]:
    if roots is None:
        roots = default_scan_roots()
    found, seen = [], set()
    for root in roots:
        try:
            root = root.expanduser().resolve()
        except OSError:
            continue
        if not root.exists() or not root.is_dir():
            continue
        for current, dirs, _files in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            try:
                depth = len(current_path.relative_to(root).parts)
            except ValueError:
                dirs[:] = []
                continue
            dirs[:] = sorted(
                d for d in dirs
                if d not in SKIP_DIRS
                and not d.startswith(".")
                and not d.startswith("org.eclipse.")
                and d not in {"bin", "out", "obj", "coverage", "htmlcov"}
            )
            # Do not treat a scan root (e.g. Desktop or /Users/min) as a project.
            if current_path != root and _has_marker(current_path):
                try:
                    canonical = str(current_path.resolve())
                except OSError:
                    dirs[:] = []
                    continue
                if canonical not in seen:
                    seen.add(canonical)
                    found.append({"key": f"p{len(found)+1:04d}",
                                  "name": current_path.name, "path": canonical})
                dirs[:] = []
            if depth >= max_depth:
                dirs[:] = []
            if len(found) >= max_projects:
                return found
    return found
