from __future__ import annotations

import statistics
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine


class TaskCapability(str, Enum):
    ANALYSIS = "ANALYSIS"
    EXECUTE = "EXECUTE"
    AUDIT = "AUDIT"


class QuotaConfidence(str, Enum):
    EXACT = "exact"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


@dataclass
class TaskRequest:
    task_id: int
    mode: str
    project_name: str
    project_path: Path
    user_request: str
    prompt: str = ""
    timeout_seconds: int = 1800
    allow_code_mutation: bool = True


@dataclass
class QuotaStatus:
    has_quota: bool = True
    confidence: QuotaConfidence = QuotaConfidence.UNKNOWN
    details: str = ""
    reset_time: float | None = None
    remaining_tokens: int | None = None
    remaining_cost: float | None = None


@dataclass
class ExecutionResult:
    provider_name: str
    exit_code: int
    output: str
    duration_seconds: float
    is_blocked: bool = False
    rate_limited: bool = False
    error_message: str | None = None
    tokens_used: int | None = None


@dataclass
class ProviderMetrics:
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    timeout_calls: int = 0
    rate_limit_calls: int = 0
    latency_samples: list[float] = field(default_factory=list)
    last_error: str | None = None
    last_error_time: float | None = None
    last_success_time: float | None = None
    active_concurrency: int = 0
    max_latency_samples: int = 20

    def add_latency(self, seconds: float) -> None:
        self.latency_samples.append(max(0.001, float(seconds)))
        if len(self.latency_samples) > self.max_latency_samples:
            self.latency_samples.pop(0)

    def median_latency(self, default: float = 1.0) -> float:
        if not self.latency_samples:
            return default
        return float(statistics.median(self.latency_samples))

    def error_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.failed_calls / self.total_calls


class BaseAIProvider(ABC):
    def __init__(
        self,
        name: str,
        enabled: bool = True,
        priority: int = 100,
        concurrency_limit: int = 2,
        cost_weight: float = 1.0,
        supported_modes: set[str] | None = None,
    ) -> None:
        self.name = name
        self.enabled = enabled
        self.priority = priority
        self.concurrency_limit = concurrency_limit
        self.cost_weight = cost_weight
        self.supported_modes = supported_modes or {"ANALYSIS", "EXECUTE"}
        self.metrics = ProviderMetrics()

    @abstractmethod
    def is_available(self) -> bool:
        """Kiểm tra provider có khả dụng trên máy (đã cài đặt CLI/SDK/môi trường)."""
        ...

    @abstractmethod
    def check_auth(self) -> tuple[bool, str]:
        """Kiểm tra credentials/API key hợp lệ mà không làm lộ secret."""
        ...

    @abstractmethod
    def get_quota_status(self) -> QuotaStatus:
        """Lấy thông tin quota khả dụng (nếu provider hỗ trợ chính thức)."""
        ...

    def supports_mode(self, mode: str) -> bool:
        return mode.upper() in self.supported_modes

    def can_accept_task(self, request: TaskRequest) -> tuple[bool, str]:
        if not self.enabled:
            return False, f"Provider {self.name} is disabled"
        if not self.is_available():
            return False, f"Provider {self.name} is not available on this host"
        auth_ok, auth_err = self.check_auth()
        if not auth_ok:
            return False, f"Provider {self.name} auth failed: {auth_err}"
        if not self.supports_mode(request.mode):
            return False, f"Provider {self.name} does not support mode {request.mode}"
        quota = self.get_quota_status()
        if not quota.has_quota:
            return False, f"Provider {self.name} out of quota: {quota.details}"
        if self.metrics.active_concurrency >= self.concurrency_limit:
            return False, f"Provider {self.name} concurrency limit reached ({self.metrics.active_concurrency}/{self.concurrency_limit})"
        return True, "OK"

    def acquire_concurrency(self) -> bool:
        if self.metrics.active_concurrency >= self.concurrency_limit:
            return False
        self.metrics.active_concurrency += 1
        return True

    def release_concurrency(self) -> None:
        self.metrics.active_concurrency = max(0, self.metrics.active_concurrency - 1)

    def record_execution(self, result: ExecutionResult) -> None:
        now = time.time()
        self.metrics.total_calls += 1
        self.metrics.add_latency(result.duration_seconds)

        if result.exit_code == 0 and not result.is_blocked and not result.rate_limited:
            self.metrics.successful_calls += 1
            self.metrics.last_success_time = now
        else:
            self.metrics.failed_calls += 1
            self.metrics.last_error = result.error_message or "Execution failed"
            self.metrics.last_error_time = now
            if result.rate_limited:
                self.metrics.rate_limit_calls += 1
            if result.exit_code == 124 or "timeout" in (result.error_message or "").lower():
                self.metrics.timeout_calls += 1

    @abstractmethod
    async def execute_task(
        self,
        request: TaskRequest,
        on_progress: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ) -> ExecutionResult:
        """Thực thi task với streaming output và kết quả cấu trúc."""
        ...
