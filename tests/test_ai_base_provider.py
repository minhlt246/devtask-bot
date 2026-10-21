import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from app.ai.base_provider import (
    BaseAIProvider,
    ExecutionResult,
    ProviderMetrics,
    QuotaConfidence,
    QuotaStatus,
    TaskCapability,
    TaskRequest,
)


class DummyProvider(BaseAIProvider):
    def __init__(self, name="dummy", enabled=True, auth_ok=True, quota_ok=True, concurrency_limit=2):
        super().__init__(
            name=name,
            enabled=enabled,
            concurrency_limit=concurrency_limit,
            supported_modes={"ANALYSIS", "EXECUTE"},
        )
        self._auth_ok = auth_ok
        self._quota_ok = quota_ok

    def is_available(self) -> bool:
        return self.enabled

    def check_auth(self) -> tuple[bool, str]:
        return (True, "OK") if self._auth_ok else (False, "Auth failed")

    def get_quota_status(self) -> QuotaStatus:
        return QuotaStatus(has_quota=self._quota_ok, confidence=QuotaConfidence.EXACT)

    async def execute_task(self, request: TaskRequest, on_progress=None) -> ExecutionResult:
        return ExecutionResult(
            provider_name=self.name,
            exit_code=0,
            output="Done",
            duration_seconds=1.2,
        )


def test_task_request_creation():
    req = TaskRequest(
        task_id=1,
        mode="EXECUTE",
        project_name="test_proj",
        project_path=Path("/tmp"),
        user_request="fix bug",
    )
    assert req.task_id == 1
    assert req.mode == "EXECUTE"
    assert req.project_name == "test_proj"


def test_provider_metrics_tracking():
    m = ProviderMetrics()
    assert m.total_calls == 0
    assert m.error_rate() == 0.0

    m.add_latency(1.0)
    m.add_latency(2.0)
    m.add_latency(3.0)
    assert m.median_latency() == 2.0

    # Add 25 samples, maxlen=20
    for i in range(25):
        m.add_latency(float(i))
    assert len(m.latency_samples) == 20


def test_provider_can_accept_task():
    p = DummyProvider()
    req = TaskRequest(1, "EXECUTE", "test", Path("/tmp"), "work")
    ok, reason = p.can_accept_task(req)
    assert ok is True

    # Disabled
    p_dis = DummyProvider(enabled=False)
    ok, reason = p_dis.can_accept_task(req)
    assert ok is False
    assert "disabled" in reason.lower()

    # Auth failed
    p_auth = DummyProvider(auth_ok=False)
    ok, reason = p_auth.can_accept_task(req)
    assert ok is False
    assert "auth" in reason.lower()

    # Quota exhausted
    p_quota = DummyProvider(quota_ok=False)
    ok, reason = p_quota.can_accept_task(req)
    assert ok is False
    assert "quota" in reason.lower()


def test_concurrency_control():
    p = DummyProvider(concurrency_limit=1)
    req = TaskRequest(1, "EXECUTE", "test", Path("/tmp"), "work")
    assert p.acquire_concurrency() is True
    assert p.metrics.active_concurrency == 1

    # Limit reached
    assert p.acquire_concurrency() is False
    ok, reason = p.can_accept_task(req)
    assert ok is False
    assert "concurrency" in reason.lower()

    # Release
    p.release_concurrency()
    assert p.metrics.active_concurrency == 0
    assert p.acquire_concurrency() is True
    p.release_concurrency()


def test_record_execution():
    p = DummyProvider()
    res = ExecutionResult("dummy", exit_code=0, output="pass", duration_seconds=0.8)
    p.record_execution(res)
    assert p.metrics.total_calls == 1
    assert p.metrics.successful_calls == 1
    assert p.metrics.median_latency() == 0.8

    # Record error
    res_err = ExecutionResult("dummy", exit_code=1, output="err", duration_seconds=1.5, error_message="fail")
    p.record_execution(res_err)
    assert p.metrics.total_calls == 2
    assert p.metrics.failed_calls == 1
    assert p.metrics.error_rate() == 0.5
