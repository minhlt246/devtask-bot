# Plan: Automatic Multi-AI Router System

Date: 2026-10-21
Spec: docs/supergraph/plans/sdd_multi_ai_router.md

## Wave 1: Core Provider Abstraction & Router Engine

### Task 1: Base Provider and Data Models
Wave: 1
Status: pending
Risk: low
Dependencies: none
Model: inherit

Files:
- Create: `app/ai/__init__.py`
- Create: `app/ai/base_provider.py`
- Test: `tests/test_ai_base_provider.py`

Acceptance:
- `TaskCapability`, `TaskRequest`, `ExecutionResult`, `QuotaStatus`, `ProviderMetrics` defined.
- `BaseAIProvider` base class provides common metrics tracking, latency sliding window, concurrency control, and abstract execution methods.

### Task 2: Provider Registry & AI Router Decision Engine
Wave: 1
Status: pending
Risk: medium
Dependencies: Task 1
Model: inherit

Files:
- Create: `app/ai/provider_registry.py`
- Create: `app/ai/ai_router.py`
- Test: `tests/test_ai_router.py`

Acceptance:
- `AIRouter.route_task(request)` evaluates candidates in memory under 2 ms.
- Filters out unauthenticated, disabled, over-capacity, and quota-exhausted providers.
- Computes rank scores based on latency, error rates, and policy.
- Supports `route_fallback(request, failed_providers)`.

## Wave 2: AI Provider Adapters

### Task 3: Antigravity Provider Adapter
Wave: 2
Status: pending
Risk: low
Dependencies: Task 1
Model: inherit

Files:
- Create: `app/ai/providers/__init__.py`
- Create: `app/ai/providers/antigravity_provider.py`
- Test: `tests/test_providers.py`

Acceptance:
- Adapts existing `AGY_COMMAND` execution with streaming logs and activity detection.
- Reports verified status and real metrics.

### Task 4: External Providers (Codex, Claude, Muse)
Wave: 2
Status: pending
Risk: low
Dependencies: Task 1
Model: inherit

Files:
- Create: `app/ai/providers/codex_provider.py`
- Create: `app/ai/providers/claude_provider.py`
- Create: `app/ai/providers/muse_provider.py`
- Test: `tests/test_providers.py`

Acceptance:
- Validates credentials safely without logging secrets.
- Accurately reports `is_available()=False` when API keys/CLIs are not configured.
- Structured execution and error mapping when configured.

## Wave 3: Worker Integration & Settings

### Task 5: Integrate Router into Config and Agent Worker
Wave: 3
Status: pending
Risk: medium
Dependencies: Task 2, Task 3, Task 4
Model: inherit

Files:
- Modify: `app/config.py`
- Modify: `.env.example`
- Modify: `app/services/agent_worker.py`
- Test: `tests/test_worker_router_integration.py`

Acceptance:
- Worker routes task via `AIRouter` before execution.
- Telegram status reflects selected provider name.
- Safe fallback triggered if primary provider fails early with recoverable error.

## Wave 4: Benchmark, Verification & Documentation

### Task 6: Latency Benchmark & Full Regression Test
Wave: 4
Status: pending
Risk: low
Dependencies: Task 5
Model: inherit

Files:
- Create: `tests/benchmark_ai_router.py`
- Modify: `README.md`

Acceptance:
- Benchmark measures p50, p95, p99 decision latency and asserts < 2 ms.
- Full test suite passes.
- Documentation updated with multi-AI configuration and latency statistics.
