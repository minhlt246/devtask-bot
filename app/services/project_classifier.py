from __future__ import annotations

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_RULES_PATH = ROOT_DIR / "config" / "project_colors.json"


def load_rules(path: Path | None = None) -> list[dict]:
    """Load user-editable project technology/color rules."""
    rules_path = path or DEFAULT_RULES_PATH
    try:
        data = json.loads(rules_path.read_text(encoding="utf-8"))
        rules = data.get("rules", [])
        return rules if isinstance(rules, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def classify_project(project: dict[str, str], rules: list[dict] | None = None) -> dict[str, str]:
    """Classify using project root markers, a bounded file sample, then project name."""
    project_path = Path(project.get("path", ""))
    try:
        root_names = {item.name for item in project_path.iterdir()}
    except OSError:
        root_names = set()

    # Collect a bounded sample; do not traverse dependency/build/cache directories.
    extensions: set[str] = set()
    skip = {"node_modules", "vendor", ".git", ".venv", "venv", "build", "dist", "target", "Pods", "Library"}
    visited = 0
    try:
        for current, dirs, files in __import__("os").walk(project_path, topdown=True, followlinks=False):
            dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
            for filename in files:
                extensions.add(Path(filename).suffix.lower())
                visited += 1
                if visited >= 2500:
                    break
            if visited >= 2500:
                break
    except OSError:
        pass

    name = project.get("name", "").casefold()
    for rule in (rules if rules is not None else load_rules()):
        markers = set(rule.get("markers", []))
        rule_exts = {str(ext).lower() for ext in rule.get("extensions", [])}
        name_terms = [str(term).casefold() for term in rule.get("name_contains", [])]
        marker_match = bool(markers.intersection(root_names))
        extension_match = bool(rule_exts.intersection(extensions))
        name_match = any(term and term in name for term in name_terms)
        if marker_match or extension_match or name_match:
            # Distinguish TypeScript before JavaScript and Flutter before generic Dart/PHP rules.
            return {
                "technology": str(rule.get("label", "Chưa xác định")),
                "emoji": str(rule.get("emoji", "⚪")),
                "color": str(rule.get("color", "#777777")),
                "rule_id": str(rule.get("id", "generic")),
            }
    fallback = next((r for r in (rules if rules is not None else load_rules()) if r.get("id") == "generic"), {})
    return {
        "technology": str(fallback.get("label", "Chưa xác định")),
        "emoji": str(fallback.get("emoji", "⚪")),
        "color": str(fallback.get("color", "#777777")),
        "rule_id": str(fallback.get("id", "generic")),
    }
