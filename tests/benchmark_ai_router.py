import statistics
import time
from pathlib import Path

from app.ai.ai_router import AIRouter, RouterPolicy
from app.ai.base_provider import TaskRequest
from app.ai.provider_registry import ProviderRegistry
from app.ai.providers.antigravity_provider import AntigravityProvider
from app.ai.providers.claude_provider import ClaudeProvider
from app.ai.providers.codex_provider import CodexProvider
from app.ai.providers.muse_provider import MuseProvider


def run_benchmark(iterations: int = 1000) -> dict[str, float]:
    registry = ProviderRegistry()
    registry.register(AntigravityProvider(agy_command="echo 'mock'"))
    registry.register(CodexProvider(api_key="sk-mock-valid-key-for-test-1234567890", cli_command=""))
    registry.register(ClaudeProvider(api_key="sk-ant-mock-valid-key-1234567890", cli_command=""))
    registry.register(MuseProvider(api_key="muse-mock-valid-key-12345", cli_command=""))

    router = AIRouter(registry=registry, policy=RouterPolicy.BALANCED)
    req = TaskRequest(
        task_id=999,
        mode="EXECUTE",
        project_name="benchmark_project",
        project_path=Path("/tmp"),
        user_request="benchmark task routing",
    )

    # Warmup
    for _ in range(50):
        router.route_task(req)

    latencies_ms: list[float] = []
    for _ in range(iterations):
        decision = router.route_task(req)
        latencies_ms.append(decision.decision_latency_ms)

    sorted_lats = sorted(latencies_ms)
    p50 = statistics.median(sorted_lats)
    p95 = sorted_lats[int(len(sorted_lats) * 0.95)]
    p99 = sorted_lats[int(len(sorted_lats) * 0.99)]

    return {
        "iterations": float(iterations),
        "p50_ms": round(p50, 4),
        "p95_ms": round(p95, 4),
        "p99_ms": round(p99, 4),
        "mean_ms": round(statistics.mean(sorted_lats), 4),
    }


def test_ai_router_decision_latency_benchmark():
    stats = run_benchmark(iterations=1000)
    print("\n[AI ROUTER LATENCY BENCHMARK RESULT]")
    print(f"Iterations: {int(stats['iterations'])}")
    print(f"p50:  {stats['p50_ms']:.4f} ms")
    print(f"p95:  {stats['p95_ms']:.4f} ms")
    print(f"p99:  {stats['p99_ms']:.4f} ms")
    print(f"Mean: {stats['mean_ms']:.4f} ms")

    # Assert p95 < 2.0 ms strictly
    assert stats["p95_ms"] < 2.0, f"p95 latency {stats['p95_ms']} ms exceeds 2.0 ms target!"
    assert stats["p50_ms"] < 1.0, f"p50 latency {stats['p50_ms']} ms exceeds 1.0 ms target!"


if __name__ == "__main__":
    results = run_benchmark(iterations=5000)
    print("=== AI Router Benchmark Results (5,000 iterations) ===")
    print(f"p50:  {results['p50_ms']} ms")
    print(f"p95:  {results['p95_ms']} ms")
    print(f"p99:  {results['p99_ms']} ms")
    print(f"Mean: {results['mean_ms']} ms")
