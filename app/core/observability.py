"""Dependency-light tracing, metrics, and alert evaluation for Phase 7."""

import contextvars
import statistics
import time
import uuid
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, Optional

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")


def start_trace(incoming_trace_id: Optional[str] = None) -> str:
    trace_id = incoming_trace_id or str(uuid.uuid4())
    trace_id_var.set(trace_id)
    return trace_id


def current_trace_id() -> str:
    return trace_id_var.get()


class MetricsRegistry:
    """Bounded in-memory metric registry, exportable in Prometheus text format."""
    def __init__(self, max_samples: int = 4096):
        self.max_samples = max_samples
        self.counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self.latencies: Dict[tuple[str, tuple[tuple[str, str], ...]], Deque[float]] = defaultdict(lambda: deque(maxlen=max_samples))

    @staticmethod
    def _key(name: str, labels: Optional[Dict[str, str]] = None):
        return name, tuple(sorted((labels or {}).items()))

    def increment(self, name: str, labels: Optional[Dict[str, str]] = None, value: int = 1) -> None:
        self.counters[self._key(name, labels)] += value

    def observe(self, name: str, seconds: float, labels: Optional[Dict[str, str]] = None) -> None:
        self.latencies[self._key(name, labels)].append(max(0.0, seconds))

    def percentiles(self, name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        samples = sorted(self.latencies.get(self._key(name, labels), ()))
        if not samples:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        def percentile(p: float) -> float:
            return samples[min(len(samples) - 1, int((len(samples) - 1) * p))]
        return {"p50": percentile(.50), "p95": percentile(.95), "p99": percentile(.99)}

    def prometheus(self) -> str:
        lines: list[str] = []
        def label_text(labels: tuple[tuple[str, str], ...]) -> str:
            return ",".join(f'{key}="{value}"' for key, value in labels)
        for (name, labels), value in self.counters.items():
            suffix = "" if not labels else "{" + label_text(labels) + "}"
            lines.append(f"polaris_{name}{suffix} {value}")
        for (name, labels), samples in self.latencies.items():
            suffix = "" if not labels else "{" + label_text(labels) + "}"
            for quantile, value in self.percentiles(name, dict(labels)).items():
                quantile_labels = (("quantile", quantile),) + labels
                lines.append(f"polaris_{name}_seconds{{{label_text(quantile_labels)}}} {value}")
            lines.append(f"polaris_{name}_seconds_count{suffix} {len(samples)}")
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class Alert:
    name: str
    severity: str
    owner: str
    message: str


class AlertEvaluator:
    def __init__(self, metrics: MetricsRegistry):
        self.metrics = metrics

    def evaluate(self) -> list[Alert]:
        alerts: list[Alert] = []
        for (name, labels), count in self.metrics.counters.items():
            label_map = dict(labels)
            if name == "workflow_failures_total" and count >= 1:
                alerts.append(Alert("workflow_failure", "critical", "platform-oncall", "Workflow failure detected."))
            if name == "session_version_conflicts_total" and count >= 5:
                alerts.append(Alert("version_conflicts", "warning", "platform-oncall", "High optimistic-concurrency conflict rate."))
            if name == "hitl_interruptions_total" and count >= 5:
                alerts.append(Alert("stuck_interruptions", "warning", "workflow-owner", "Repeated HITL interruptions require review."))
        for (name, labels), _ in self.metrics.latencies.items():
            p95 = self.metrics.percentiles(name, dict(labels))["p95"]
            if name in {"api_request", "workflow"} and p95 > 2.0:
                alerts.append(Alert("high_latency", "warning", "platform-oncall", f"{name} p95 exceeds 2 seconds."))
        return alerts


metrics = MetricsRegistry()
alerts = AlertEvaluator(metrics)
