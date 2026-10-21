import time
from pathlib import Path
import pytest

from app.ai.base_provider import BaseAIProvider, ExecutionResult, QuotaConfidence, QuotaStatus, TaskRequest
from app.ai.provider_registry import ProviderRegistry
from app.ai.ai_router import AIRouter, RouteDecision, RouterPolicy


class MockProvider(BaseAIProvider):
    def __init__(
        self,
        name: str,
        enabled: bool = True,
        auth_ok: bool = True,
        quota_ok: bool = True,
        concurrency_limit: int = 2,
        priority: int = 100,
        median_lat: float = 1.0,
    ):
        super().__init__(
            name=name,
            enabled=enabled,
            priority=priority,
            concurrency_limit=concurrency_limit,
            supported_modes={"ANALYSIS", "EXECUTE"},
        )
        self._auth_ok = auth_ok
        self._quota_ok = quota_ok
        if median_lat > 0:
            self.metrics.add_latency(median_lat)

    def is_available(self) -> bool:
        return self.enabled

    def check_auth(self) -> tuple[bool, str]:
        return (True, "OK") if self._auth_ok else (False, "Bad key")

    def get_quota_status(self) -> QuotaStatus:
        return QuotaStatus(has_quota=self._quota_ok, confidence=QuotaConfidence.EXACT)

    async def execute_task(self, request: TaskRequest, on_progress=None) -> ExecutionResult:
        return ExecutionResult(self.name, 0, "OK", 0.5)


def test_router_selects_fastest_eligible_provider():
    reg = ProviderRegistry()
    p_fast = MockProvider("fast", median_lat=0.2)
    p_slow = MockProvider("slow", median_lat=2.0)
    reg.register(p_fast)
    reg.register(p_slow)

    router = AIRouter(registry=reg, policy=RouterPolicy.LATENCY_FIRST)
    req = TaskRequest(1, "EXECUTE", "test", Path("/tmp"), "fix")

    decision = router.route_task(req)
    assert decision.selected_provider is not None
    assert decision.selected_provider.name == "fast"
    assert decision.decision_latency_ms < 2.0  # Must be fast in-memory


def test_router_excludes_ineligible_providers():
    reg = ProviderRegistry()
    p_bad_auth = MockProvider("bad_auth", auth_ok=False, median_lat=0.1)
    p_no_quota = MockProvider("no_quota", quota_ok=False, median_lat=0.1)
    p_disabled = MockProvider("disabled", enabled=False, median_lat=0.1)
    p_valid = MockProvider("valid", median_lat=1.5)

    reg.register(p_bad_auth)
    reg.register(p_no_quota)
    reg.register(p_disabled)
    reg.register(p_valid)

    router = AIRouter(registry=reg)
    req = TaskRequest(1, "EXECUTE", "test", Path("/tmp"), "fix")

    decision = router.route_task(req)
    assert decision.selected_provider is not None
    assert decision.selected_provider.name == "valid"
    assert "bad_auth" in decision.rejections
    assert "no_quota" in decision.rejections
    assert "disabled" in decision.rejections


def test_router_error_rate_penalty():
    reg = ProviderRegistry()
    p1 = MockProvider("p1", median_lat=0.5)
    p2 = MockProvider("p2", median_lat=0.6)

    # p1 has high error rate
    for _ in range(5):
        p1.record_execution(ExecutionResult("p1", exit_code=1, output="err", duration_seconds=0.5, error_message="fail"))

    reg.register(p1)
    reg.register(p2)

    router = AIRouter(registry=reg, policy=RouterPolicy.BALANCED)
    req = TaskRequest(1, "EXECUTE", "test", Path("/tmp"), "fix")

    decision = router.route_task(req)
    # p2 should win because p1 has 100% error rate
    assert decision.selected_provider.name == "p2"


def test_router_fallback():
    reg = ProviderRegistry()
    p_primary = MockProvider("primary", median_lat=0.5)
    p_secondary = MockProvider("secondary", median_lat=1.0)
    reg.register(p_primary)
    reg.register(p_secondary)

    router = AIRouter(registry=reg)
    req = TaskRequest(1, "EXECUTE", "test", Path("/tmp"), "fix")

    decision = router.route_fallback(req, failed_providers={"primary"})
    assert decision is not None
    assert decision.selected_provider.name == "secondary"

    # When all failed
    decision_none = router.route_fallback(req, failed_providers={"primary", "secondary"})
    assert decision_none is None or decision_none.selected_provider is None
