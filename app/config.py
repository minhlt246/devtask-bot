from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.services.platform_support import default_agy_command

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _parse_allowed_ids(raw: str) -> set[int]:
    result: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item or item.startswith("PASTE_"):
            continue
        try:
            result.add(int(item))
        except ValueError as exc:
            raise ValueError(f"Telegram user ID không hợp lệ: {item!r}") from exc
    return result


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    allowed_user_ids: set[int]
    database_path: Path
    projects_config_path: Path
    log_level: str
    project_scan_root: Path
    code_editor: str
    agy_command: str
    agent_timeout_seconds: int
    test_timeout_seconds: int
    ai_router_policy: str = "balanced"
    ai_fallback_enabled: bool = True
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    muse_api_key: str = ""


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token.startswith("PASTE_"):
        raise RuntimeError("Chưa cấu hình TELEGRAM_BOT_TOKEN trong file .env.")
    allowed_ids = _parse_allowed_ids(os.getenv("ALLOWED_TELEGRAM_USER_IDS", ""))
    if not allowed_ids:
        raise RuntimeError("Chưa cấu hình ALLOWED_TELEGRAM_USER_IDS trong file .env.")
    db = Path(os.getenv("DATABASE_PATH", "data/devtask.sqlite3"))
    projects = Path(os.getenv("PROJECTS_CONFIG_PATH", "config/projects.json"))
    return Settings(
        telegram_bot_token=token,
        allowed_user_ids=allowed_ids,
        database_path=db if db.is_absolute() else ROOT_DIR / db,
        projects_config_path=projects if projects.is_absolute() else ROOT_DIR / projects,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        project_scan_root=Path(os.getenv("PROJECT_SCAN_ROOT", "")).expanduser() if os.getenv("PROJECT_SCAN_ROOT", "").strip() else Path("__AUTO_DISCOVERY__"),
        code_editor=os.getenv("CODE_EDITOR", "Cursor").strip() or "Cursor",
        agy_command=(os.getenv("AGY_COMMAND") or "").strip() or default_agy_command(),
        agent_timeout_seconds=max(60, int(os.getenv("AGENT_TIMEOUT_SECONDS", "1800"))),
        test_timeout_seconds=max(30, int(os.getenv("TEST_TIMEOUT_SECONDS", "300"))),
        ai_router_policy=os.getenv("AI_ROUTER_POLICY", "balanced").strip().lower(),
        ai_fallback_enabled=os.getenv("AI_FALLBACK_ENABLED", "true").strip().lower() in ("1", "true", "yes"),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        muse_api_key=os.getenv("MUSE_API_KEY", "").strip(),
    )
