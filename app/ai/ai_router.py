from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.ai.base_provider import BaseAIProvider, TaskRequest
from app.ai.provider_registry import ProviderRegistry, get_default_registry


class RouterPolicy(str, Enum):
    BALANCED = "balanced"
    LATENCY_FIRST = "latency_first"
    RELIABILITY_FIRST = "reliability_first"
    COST_FIRST = "cost_first"


@dataclass
class RouteDecision:
    selected_provider: BaseAIProvider | None
    provider_name: str | None
    score: float
    reason: str
    candidate_scores: dict[str, float] = field(default_factory=dict)
    rejections: dict[str, str] = field(default_factory=dict)
    decision_latency_ms: float = 0.0


class AIRouter:
    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        policy: RouterPolicy = RouterPolicy.BALANCED,
        fallback_enabled: bool = True,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self.registry = registry or get_default_registry()
        self.policy = policy
        self.fallback_enabled = fallback_enabled
        self.cooldown_seconds = cooldown_seconds

    def _calculate_score(self, provider: BaseAIProvider, now: float) -> float:
        metrics = provider.metrics
        median_lat = metrics.median_latency(default=1.0)
        err_rate = metrics.error_rate()

        # 1. Latency component (0 - 100)
        # 0.1s -> 91 pts, 1.0s -> 50 pts, 5.0s -> 16 pts
        latency_score = 100.0 / (1.0 + median_lat)

        # 2. Reliability component (0 - 100)
        reliability_score = max(0.0, 100.0 * (1.0 - err_rate))
        if metrics.last_error_time and (now - metrics.last_error_time < self.cooldown_seconds):
            elapsed = now - metrics.last_error_time
            # Penalty decays over cooldown period
            penalty = 50.0 * math.exp(-elapsed / (self.cooldown_seconds / 3.0))
            reliability_score = max(0.0, reliability_score - penalty)

        # 3. Priority component (0 - 100)
        priority_score = max(0.0, float(100 - min(provider.priority, 100)))

        # 4. Cost component (0 - 100)
        cost_score = max(0.0, 100.0 / (1.0 + max(0.1, provider.cost_weight)))

        if self.policy == RouterPolicy.LATENCY_FIRST:
            return 0.65 * latency_score + 0.25 * reliability_score + 0.10 * priority_score
        elif self.policy == RouterPolicy.RELIABILITY_FIRST:
            return 0.65 * reliability_score + 0.25 * latency_score + 0.10 * priority_score
        elif self.policy == RouterPolicy.COST_FIRST:
            return 0.50 * cost_score + 0.30 * reliability_score + 0.20 * latency_score
        else:  # BALANCED
            return 0.40 * latency_score + 0.40 * reliability_score + 0.20 * priority_score

    def route_task(
        self, request: TaskRequest, excluded_providers: set[str] | None = None
    ) -> RouteDecision:
        t0 = time.perf_counter()
        now = time.time()
        excluded = {p.lower() for p in (excluded_providers or set())}

        candidate_scores: dict[str, float] = {}
        rejections: dict[str, str] = {}
        best_provider: BaseAIProvider | None = None
        best_score = -1.0

        for provider in self.registry.list_providers():
            name = provider.name.lower()
            if name in excluded:
                rejections[provider.name] = "Excluded by caller or previous failure"
                continue

            can_accept, reason = provider.can_accept_task(request)
            if not can_accept:
                rejections[provider.name] = reason
                continue

            score = self._calculate_score(provider, now)
            candidate_scores[provider.name] = round(score, 3)

            if score > best_score:
                best_score = score
                best_provider = provider

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if best_provider:
            reason = (
                f"Selected {best_provider.name} (score: {best_score:.2f}, "
                f"p50 latency: {best_provider.metrics.median_latency():.2f}s, "
                f"error rate: {best_provider.metrics.error_rate():.1%})"
            )
            return RouteDecision(
                selected_provider=best_provider,
                provider_name=best_provider.name,
                score=best_score,
                reason=reason,
                candidate_scores=candidate_scores,
                rejections=rejections,
                decision_latency_ms=elapsed_ms,
            )
        else:
            return RouteDecision(
                selected_provider=None,
                provider_name=None,
                score=0.0,
                reason="No eligible AI provider available",
                candidate_scores=candidate_scores,
                rejections=rejections,
                decision_latency_ms=elapsed_ms,
            )

    def route_fallback(
        self, request: TaskRequest, failed_providers: set[str]
    ) -> RouteDecision | None:
        if not self.fallback_enabled:
            return None
        decision = self.route_task(request, excluded_providers=failed_providers)
        if decision.selected_provider is None:
            return None
        return decision
