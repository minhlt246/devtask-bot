import asyncio
import os
import sys
from pathlib import Path
import pytest

from app.ai.base_provider import TaskRequest, ExecutionResult
from app.ai.providers.antigravity_provider import AntigravityProvider
from app.ai.providers.codex_provider import CodexProvider
from app.ai.providers.claude_provider import ClaudeProvider
from app.ai.providers.muse_provider import MuseProvider


def test_antigravity_provider_available_and_auth():
    p = AntigravityProvider(agy_command="echo 'mock agy'")
    assert p.is_available() is True
    ok, msg = p.check_auth()
    assert ok is True
    assert p.supports_mode("ANALYSIS") is True
    assert p.supports_mode("EXECUTE") is True


def test_codex_provider_unconfigured():
    # Pass empty api_key and empty cli_command to simulate totally unconfigured host
    p = CodexProvider(api_key="", cli_command="")
    assert p.is_available() is False
    ok, msg = p.check_auth()
    assert ok is False
    assert "OPENAI_API_KEY" in msg


def test_codex_provider_configured():
    p = CodexProvider(api_key="sk-mock-valid-key-for-test-1234567890", cli_command="")
    assert p.is_available() is True
    ok, msg = p.check_auth()
    assert ok is True


def test_claude_provider_unconfigured():
    p = ClaudeProvider(api_key="", cli_command="")
    assert p.is_available() is False
    ok, msg = p.check_auth()
    assert ok is False
    assert "ANTHROPIC_API_KEY" in msg


def test_claude_provider_configured():
    p = ClaudeProvider(api_key="sk-ant-mock-valid-key-1234567890", cli_command="")
    assert p.is_available() is True
    ok, msg = p.check_auth()
    assert ok is True


def test_muse_provider_unconfigured():
    p = MuseProvider(api_key="", cli_command="")
    assert p.is_available() is False
    ok, msg = p.check_auth()
    assert ok is False
    assert "MUSE_API_KEY" in msg


def test_muse_provider_configured():
    p = MuseProvider(api_key="muse-mock-valid-key-12345", cli_command="")
    assert p.is_available() is True
    ok, msg = p.check_auth()
    assert ok is True


def test_antigravity_execute_mock(tmp_path):
    async def run():
        script = "import sys; print('ANTIGRAVITY REPORT OK'); sys.exit(0)"
        p = AntigravityProvider(agy_command=f"{sys.executable} -c \"{script}\"")
        req = TaskRequest(
            task_id=1,
            mode="EXECUTE",
            project_name="test_proj",
            project_path=tmp_path,
            user_request="test request",
            prompt="run dummy",
            timeout_seconds=10,
        )
        res = await p.execute_task(req)
        assert res.exit_code == 0
        assert "ANTIGRAVITY REPORT OK" in res.output
        assert res.provider_name == "Antigravity"
        assert p.metrics.total_calls == 1
        assert p.metrics.successful_calls == 1

    asyncio.run(run())
