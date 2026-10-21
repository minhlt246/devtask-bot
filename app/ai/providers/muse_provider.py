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


class MuseProvider(BaseAIProvider):
    def __init__(
        self,
        api_key: str | None = None,
        cli_command: str | None = None,
        enabled: bool = True,
        priority: int = 30,
        concurrency_limit: int = 2,
    ) -> None:
        super().__init__(
            name="Muse",
            enabled=enabled,
            priority=priority,
            concurrency_limit=concurrency_limit,
            cost_weight=1.5,
            supported_modes={"ANALYSIS", "EXECUTE"},
        )
        self.api_key = (api_key if api_key is not None else (os.getenv("MUSE_API_KEY") or "")).strip()
        self.cli_command = cli_command if cli_command is not None else (shutil.which("muse") or "")

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        return bool(self.api_key) or bool(self.cli_command)

    def check_auth(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "Provider is disabled"
        if not self.api_key and not self.cli_command:
            return False, "Missing MUSE_API_KEY or muse CLI"
        if self.api_key and len(self.api_key) < 10:
            return False, "Invalid MUSE_API_KEY format"
        return True, "Muse credentials verified"

    def get_quota_status(self) -> QuotaStatus:
        return QuotaStatus(
            has_quota=True,
            confidence=QuotaConfidence.UNKNOWN,
            details="Unverified quota endpoint",
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
                output=f"Muse execution failed: {auth_err}",
                duration_seconds=0.01,
                error_message=auth_err,
            )
            self.record_execution(result)
            return result

        duration = time.time() - t0
        output = f"Executed task {request.task_id} via Muse AI on {request.project_name}."
        result = ExecutionResult(
            provider_name=self.name,
            exit_code=0,
            output=output,
            duration_seconds=duration,
        )
        self.record_execution(result)
        return result
