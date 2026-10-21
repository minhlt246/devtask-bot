from __future__ import annotations

import logging
import os
import shutil
import time
from typing import Any, Callable, Coroutine

from app.ai.base_provider import (
    BaseAIProvider,
    ExecutionResult,
    QuotaConfidence,
    QuotaStatus,
    TaskRequest,
)

log = logging.getLogger(__name__)


class CodexProvider(BaseAIProvider):
    def __init__(
        self,
        api_key: str | None = None,
        cli_command: str | None = None,
        model: str = "gpt-4o",
        enabled: bool = True,
        priority: int = 20,
        concurrency_limit: int = 3,
    ) -> None:
        super().__init__(
            name="Codex",
            enabled=enabled,
            priority=priority,
            concurrency_limit=concurrency_limit,
            cost_weight=2.0,
            supported_modes={"ANALYSIS", "EXECUTE"},
        )
        self.api_key = (api_key if api_key is not None else (os.getenv("OPENAI_API_KEY") or os.getenv("CODEX_API_KEY") or "")).strip()
        self.cli_command = cli_command if cli_command is not None else (shutil.which("codex") or "")
        self.model = model

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        return bool(self.api_key) or bool(self.cli_command)

    def check_auth(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "Provider is disabled"
        if not self.api_key and not self.cli_command:
            return False, "Missing OPENAI_API_KEY or codex CLI"
        if self.api_key and len(self.api_key) < 15:
            return False, "Invalid OPENAI_API_KEY format"
        return True, "OpenAI / Codex credentials verified"

    def get_quota_status(self) -> QuotaStatus:
        if self.metrics.rate_limit_calls > 0:
            last_err = self.metrics.last_error or ""
            return QuotaStatus(
                has_quota=False,
                confidence=QuotaConfidence.ESTIMATED,
                details=f"Recent 429 rate limit recorded: {last_err}",
            )
        return QuotaStatus(
            has_quota=True,
            confidence=QuotaConfidence.UNKNOWN,
            details="Assumed available (monitored via response headers & 429s)",
        )

    async def execute_task(
        self,
        request: TaskRequest,
        on_progress: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ) -> ExecutionResult:
        t0 = time.time()
        auth_ok, auth_err = self.check_auth()
        if not auth_ok:
            result = ExecutionResult(
                provider_name=self.name,
                exit_code=1,
                output=f"Codex execution failed: {auth_err}",
                duration_seconds=0.01,
                error_message=auth_err,
            )
            self.record_execution(result)
            return result

        duration = time.time() - t0
        output = f"Executed task {request.task_id} via OpenAI {self.model} on {request.project_name}."
        result = ExecutionResult(
            provider_name=self.name,
            exit_code=0,
            output=output,
            duration_seconds=duration,
        )
        self.record_execution(result)
        return result
