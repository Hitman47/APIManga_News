from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    started_at: str
    counters: dict[str, int]
    ratios: dict[str, float]

    def model_dump(self) -> dict[str, Any]:
        return {
            'started_at': self.started_at,
            'counters': dict(self.counters),
            'ratios': dict(self.ratios),
        }


class MetricsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = datetime.now(UTC)
        self._counters: Counter[str] = Counter()

    def increment(self, key: str, value: int = 1) -> None:
        if value == 0:
            return
        with self._lock:
            self._counters[key] += value

    def record_response(self, status_code: int) -> None:
        self.increment('responses_total')
        bucket = f'responses_{status_code // 100}xx'
        self.increment(bucket)

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            counters = dict(self._counters)
        cache_hits = counters.get('cache_hits', 0)
        cache_stale_fallbacks = counters.get('cache_stale_fallbacks', 0)
        cache_misses = counters.get('cache_misses', 0)
        negative_cache_hits = counters.get('negative_cache_hits', 0)
        cache_lookups = cache_hits + cache_stale_fallbacks + cache_misses + negative_cache_hits
        upstream_total = counters.get('upstream_fetch_success', 0) + counters.get('upstream_fetch_errors', 0)
        ratios = {
            'cache_hit_ratio': round((cache_hits + cache_stale_fallbacks) / cache_lookups, 4) if cache_lookups else 0.0,
            'negative_cache_hit_ratio': round(negative_cache_hits / cache_lookups, 4) if cache_lookups else 0.0,
            'upstream_error_ratio': round(counters.get('upstream_fetch_errors', 0) / upstream_total, 4) if upstream_total else 0.0,
        }
        return MetricsSnapshot(
            started_at=self._started_at.isoformat(),
            counters=counters,
            ratios=ratios,
        )
