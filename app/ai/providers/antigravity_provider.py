from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Coroutine

from app.ai.base_provider import (
    BaseAIProvider,
    ExecutionResult,
    QuotaConfidence,
    QuotaStatus,
    TaskRequest,
)
from app.services.platform_support import default_agy_command, resolve_argv, split_command

log = logging.getLogger(__name__)


class AntigravityProvider(BaseAIProvider):
    def __init__(
        self,
        agy_command: str | None = None,
        enabled: bool = True,
        priority: int = 10,
        concurrency_limit: int = 2,
    ) -> None:
        super().__init__(
            name="Antigravity",
            enabled=enabled,
            priority=priority,
            concurrency_limit=concurrency_limit,
            cost_weight=1.0,
            supported_modes={"ANALYSIS", "EXECUTE", "AUDIT"},
        )
        self.agy_command = (agy_command or os.getenv("AGY_COMMAND") or default_agy_command()).strip()

    def is_available(self) -> bool:
        if not self.enabled or not self.agy_command:
            return False
        parts = split_command(self.agy_command)
        if not parts:
            return False
        binary = parts[0]
        # Direct file path or on PATH
        if Path(binary).is_file():
            return True
        return shutil.which(binary) is not None

    def check_auth(self) -> tuple[bool, str]:
        if not self.is_available():
            return False, f"Antigravity CLI ({self.agy_command}) not found on PATH"
        return True, "Antigravity CLI verified"

    def get_quota_status(self) -> QuotaStatus:
        # CLI headless mode uses local binary; no remote quota REST API published.
        return QuotaStatus(
            has_quota=True,
            confidence=QuotaConfidence.UNKNOWN,
            details="CLI mode (quota managed via host login/account)",
        )

    async def execute_task(
        self,
        request: TaskRequest,
        on_progress: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ) -> ExecutionResult:
        t0 = time.time()
        cmd_parts = split_command(self.agy_command)
        prompt = request.prompt or request.user_request
        full_args = cmd_parts + ["-p", prompt]
        cmd = resolve_argv(full_args)

        chunks: list[str] = []
        is_blocked = False
        rate_limited = False
        exit_code = 0
        error_msg = None

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(request.project_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            async def _read_stream():
                last_report = 0.0
                while True:
                    try:
                        raw = await asyncio.wait_for(proc.stdout.readline(), timeout=2.0)
                    except asyncio.TimeoutError:
                        raw = None
                    if raw == b"":
                        break
                    if raw:
                        line = raw.decode(errors="replace")
                        chunks.append(line)
                        now = time.time()
                        if on_progress and (now - last_report >= 4.0 or "error" in line.lower()):
                            try:
                                await on_progress("".join(chunks)[-2500:])
                            except Exception:
                                pass
                            last_report = now

            await asyncio.wait_for(_read_stream(), timeout=request.timeout_seconds)
            await asyncio.wait_for(proc.wait(), timeout=10)
            exit_code = proc.returncode or 0

        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            exit_code = 124
            error_msg = f"Task timed out after {request.timeout_seconds}s"
            chunks.append(f"\n[TIMEOUT] {error_msg}")
        except Exception as exc:
            exit_code = 1
            error_msg = str(exc)
            chunks.append(f"\n[ERROR] {exc}")

        duration = time.time() - t0
        output = "".join(chunks)
        lowered = output.casefold()

        if any(marker in lowered for marker in ("permission that headless mode", "auto-denied", "cannot prompt for")):
            is_blocked = True

        if any(marker in lowered for marker in ("rate limit", "429", "quota exceeded")):
            rate_limited = True

        result = ExecutionResult(
            provider_name=self.name,
            exit_code=exit_code,
            output=output,
            duration_seconds=duration,
            is_blocked=is_blocked,
            rate_limited=rate_limited,
            error_message=error_msg,
        )
        self.record_execution(result)
        return result
