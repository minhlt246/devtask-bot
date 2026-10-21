import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.ai_router import AIRouter, RouterPolicy
from app.ai.base_provider import ExecutionResult, TaskRequest
from app.ai.provider_registry import ProviderRegistry
from app.ai.providers.antigravity_provider import AntigravityProvider
from app.ai.providers.codex_provider import CodexProvider
from app.services.agent_worker import init_ai_router


def test_init_ai_router_default():
    settings = MagicMock()
    settings.agy_command = "echo 'mock agy'"
    settings.ai_router_policy = "balanced"
    settings.ai_fallback_enabled = True
    settings.openai_api_key = ""
    settings.anthropic_api_key = ""
    settings.muse_api_key = ""

    router = init_ai_router(settings)
    assert isinstance(router, AIRouter)
    assert router.policy == RouterPolicy.BALANCED
    assert router.fallback_enabled is True

    # Antigravity should be registered and available
    antigravity = router.registry.get("Antigravity")
    assert antigravity is not None
    assert antigravity.is_available() is True


def test_router_integration_selects_antigravity_when_others_unconfigured(tmp_path):
    settings = MagicMock()
    settings.agy_command = "echo 'mock agy'"
    settings.ai_router_policy = "latency_first"
    settings.ai_fallback_enabled = True
    settings.openai_api_key = ""
    settings.anthropic_api_key = ""
    settings.muse_api_key = ""

    router = init_ai_router(settings)
    req = TaskRequest(
        task_id=1,
        mode="EXECUTE",
        project_name="sample",
        project_path=tmp_path,
        user_request="write test",
    )
    decision = router.route_task(req)
    assert decision.selected_provider is not None
    assert decision.selected_provider.name == "Antigravity"
    assert decision.decision_latency_ms < 2.0


def test_router_integration_fallback_on_failure(tmp_path):
    reg = ProviderRegistry()
    p1 = AntigravityProvider(agy_command="echo 'mock'")
    p2 = CodexProvider(api_key="sk-mock-valid-key-for-test-1234567890", cli_command="")
    reg.register(p1)
    reg.register(p2)

    router = AIRouter(registry=reg, fallback_enabled=True)
    req = TaskRequest(1, "EXECUTE", "sample", tmp_path, "write test")

    # Initial route selects p1 or p2
    first_decision = router.route_task(req)
    chosen = first_decision.selected_provider.name

    # If first fails, fallback picks the other
    fallback = router.route_fallback(req, failed_providers={chosen})
    assert fallback is not None
    assert fallback.selected_provider is not None
    assert fallback.selected_provider.name != chosen
