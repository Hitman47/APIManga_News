from __future__ import annotations

import threading
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from typing import Any


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    started_at: str
    counters: dict[str, int]
    ratios: dict[str, float]
    timings: dict[str, dict[str, float | int]]
    recent_requests: list[dict[str, Any]]
    recent_events: list[dict[str, Any]]

    def model_dump(self) -> dict[str, Any]:
        return {
            'started_at': self.started_at,
            'counters': dict(self.counters),
            'ratios': dict(self.ratios),
            'timings': dict(self.timings),
            'recent_requests': list(self.recent_requests),
            'recent_events': list(self.recent_events),
        }


class MetricsStore:
    def __init__(self, *, recent_limit: int = 100, sample_limit: int = 200) -> None:
        self._lock = threading.Lock()
        self._started_at = datetime.now(UTC)
        self._counters: Counter[str] = Counter()
        self._recent_limit = max(10, int(recent_limit))
        self._sample_limit = max(20, int(sample_limit))
        self._recent_requests: deque[dict[str, Any]] = deque(maxlen=self._recent_limit)
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=self._recent_limit)
        self._duration_samples: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=self._sample_limit))
        self._duration_totals: dict[str, dict[str, float | int | None]] = defaultdict(
            lambda: {'count': 0, 'sum_ms': 0.0, 'min_ms': None, 'max_ms': None}
        )

    def increment(self, key: str, value: int = 1) -> None:
        if value == 0:
            return
        with self._lock:
            self._counters[key] += value

    def record_response(self, status_code: int) -> None:
        self.increment('responses_total')
        bucket = f'responses_{status_code // 100}xx'
        self.increment(bucket)

    def _record_duration(self, scope: str, duration_ms: float) -> None:
        stats = self._duration_totals[scope]
        stats['count'] = int(stats['count']) + 1
        stats['sum_ms'] = float(stats['sum_ms']) + float(duration_ms)
        stats['min_ms'] = duration_ms if stats['min_ms'] is None else min(float(stats['min_ms']), duration_ms)
        stats['max_ms'] = duration_ms if stats['max_ms'] is None else max(float(stats['max_ms']), duration_ms)
        self._duration_samples[scope].append(float(duration_ms))

    def record_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        request_id: str | None = None,
    ) -> None:
        with self._lock:
            self._record_duration('http.request', float(duration_ms))
            self._recent_requests.append(
                {
                    'timestamp': datetime.now(UTC).isoformat(),
                    'method': method,
                    'path': path,
                    'status_code': status_code,
                    'duration_ms': round(float(duration_ms), 2),
                    'request_id': request_id,
                }
            )
        self.record_response(status_code)

    def record_operation(self, scope: str, *, duration_ms: float, event: str | None = None, **fields: Any) -> None:
        clean_fields = {key: value for key, value in fields.items() if value is not None}
        with self._lock:
            self._record_duration(scope, float(duration_ms))
            self._recent_events.append(
                {
                    'timestamp': datetime.now(UTC).isoformat(),
                    'scope': scope,
                    'event': event or scope,
                    'duration_ms': round(float(duration_ms), 2),
                    **clean_fields,
                }
            )

    def _build_timing_snapshot(self) -> dict[str, dict[str, float | int]]:
        timings: dict[str, dict[str, float | int]] = {}
        for scope, stats in self._duration_totals.items():
            count = int(stats['count'])
            if count <= 0:
                continue
            samples = sorted(self._duration_samples.get(scope, []))
            p95_ms = 0.0
            if samples:
                index = max(0, min(len(samples) - 1, ceil(len(samples) * 0.95) - 1))
                p95_ms = float(samples[index])
            timings[scope] = {
                'count': count,
                'avg_ms': round(float(stats['sum_ms']) / count, 2),
                'min_ms': round(float(stats['min_ms'] or 0.0), 2),
                'max_ms': round(float(stats['max_ms'] or 0.0), 2),
                'p95_ms': round(p95_ms, 2),
            }
        return timings

    def snapshot(self, *, include_recent: bool = True) -> MetricsSnapshot:
        with self._lock:
            counters = dict(self._counters)
            recent_requests = list(self._recent_requests) if include_recent else []
            recent_events = list(self._recent_events) if include_recent else []
            timings = self._build_timing_snapshot()
        cache_hits = counters.get('cache_hits', 0)
        cache_stale_fallbacks = counters.get('cache_stale_fallbacks', 0)
        cache_misses = counters.get('cache_misses', 0)
        negative_cache_hits = counters.get('negative_cache_hits', 0)
        cache_lookups = cache_hits + cache_stale_fallbacks + cache_misses + negative_cache_hits
        upstream_total = counters.get('upstream_fetch_success', 0) + counters.get('upstream_fetch_errors', 0)
        singleflight_total = counters.get('singleflight_creations', 0) + counters.get('singleflight_shared', 0)
        ratios = {
            'cache_hit_ratio': round((cache_hits + cache_stale_fallbacks) / cache_lookups, 4) if cache_lookups else 0.0,
            'negative_cache_hit_ratio': round(negative_cache_hits / cache_lookups, 4) if cache_lookups else 0.0,
            'upstream_error_ratio': round(counters.get('upstream_fetch_errors', 0) / upstream_total, 4) if upstream_total else 0.0,
            'singleflight_share_ratio': round(counters.get('singleflight_shared', 0) / singleflight_total, 4) if singleflight_total else 0.0,
        }
        return MetricsSnapshot(
            started_at=self._started_at.isoformat(),
            counters=counters,
            ratios=ratios,
            timings=timings,
            recent_requests=recent_requests,
            recent_events=recent_events,
        )
