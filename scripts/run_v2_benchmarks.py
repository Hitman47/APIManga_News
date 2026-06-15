#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    group: str
    path: str
    params: dict[str, Any]
    profiles: frozenset[str]


@dataclass(slots=True)
class Sample:
    scenario: str
    group: str
    pass_number: int
    request_number: int
    duration_ms: float
    status: int
    response_bytes: int
    cached: bool | None
    partial: bool | None
    found: bool | None
    error: str | None = None


SCENARIOS = [
    Scenario('health', 'health', '/health', {}, frozenset({'quick', 'standard', 'stress'})),
    Scenario('search_one_piece_light', 'search_light', '/search', {'q': 'one piece', 'kind': 'series', 'mode': 'best', 'limit': 1}, frozenset({'quick', 'standard', 'stress'})),
    Scenario('search_naruto_light', 'search_light', '/search', {'q': 'naruto', 'kind': 'series', 'mode': 'best', 'limit': 1}, frozenset({'standard', 'stress'})),
    Scenario('search_berserk_light', 'search_light', '/search', {'q': 'berserk', 'kind': 'series', 'mode': 'best', 'limit': 1}, frozenset({'standard', 'stress'})),
    Scenario('search_one_piece_t110_light', 'volume_search_light', '/search', {'q': 'one piece tome 110', 'kind': 'volume', 'mode': 'best', 'limit': 1}, frozenset({'quick', 'standard', 'stress'})),
    Scenario('search_naruto_t72_light', 'volume_search_light', '/search', {'q': 'naruto tome 72', 'kind': 'volume', 'mode': 'best', 'limit': 1}, frozenset({'standard', 'stress'})),
    Scenario('search_berserk_t42_light', 'volume_search_light', '/search', {'q': 'berserk tome 42', 'kind': 'volume', 'mode': 'best', 'limit': 1}, frozenset({'standard', 'stress'})),
    Scenario('search_one_piece_enriched', 'search_enriched', '/search', {'q': 'one piece', 'kind': 'series', 'mode': 'best', 'limit': 1, 'enrich': 'true', 'include_editions': 'true'}, frozenset({'quick', 'standard', 'stress'})),
    Scenario('search_naruto_enriched', 'search_enriched', '/search', {'q': 'naruto', 'kind': 'series', 'mode': 'best', 'limit': 1, 'enrich': 'true', 'include_editions': 'true'}, frozenset({'standard', 'stress'})),
    Scenario('search_berserk_enriched', 'search_enriched', '/search', {'q': 'berserk', 'kind': 'series', 'mode': 'best', 'limit': 1, 'enrich': 'true', 'include_editions': 'true'}, frozenset({'standard', 'stress'})),
    Scenario('search_one_piece_t110_enriched', 'volume_search_enriched', '/search', {'q': 'one piece tome 110', 'kind': 'volume', 'mode': 'best', 'limit': 1, 'enrich': 'true', 'include_editions': 'true'}, frozenset({'standard', 'stress'})),
    Scenario('search_naruto_t72_enriched', 'volume_search_enriched', '/search', {'q': 'naruto tome 72', 'kind': 'volume', 'mode': 'best', 'limit': 1, 'enrich': 'true', 'include_editions': 'true'}, frozenset({'stress'})),
    Scenario('series_one_piece_projection', 'series_projection', '/series/One-piece-Edition-originale', {'fields': 'title,title_vo,publisher_fr,vf.volumes,next_release_date'}, frozenset({'quick', 'standard', 'stress'})),
    Scenario('series_naruto_projection', 'series_projection', '/series/Naruto', {'fields': 'title,title_vo,publisher_fr,vf.volumes,next_release_date'}, frozenset({'standard', 'stress'})),
    Scenario('series_berserk_projection', 'series_projection', '/series/Berserk-2Ed', {'fields': 'title,title_vo,publisher_fr,vf.volumes,next_release_date'}, frozenset({'standard', 'stress'})),
    Scenario('volume_one_piece_91_projection', 'volume_projection', '/volume/One-Piece/vol-91', {'fields': 'title,number,publication_date,isbn_ean,publisher_fr'}, frozenset({'quick', 'standard', 'stress'})),
    Scenario('volume_naruto_72_projection', 'volume_projection', '/volume/Naruto/vol-72', {'fields': 'title,number,publication_date,isbn_ean,publisher_fr'}, frozenset({'standard', 'stress'})),
    Scenario('volume_berserk_42_projection', 'volume_projection', '/volume/Berserk/vol-42', {'fields': 'title,number,publication_date,isbn_ean,publisher_fr'}, frozenset({'standard', 'stress'})),
    Scenario('volume_one_piece_91_parent_editions', 'volume_enriched', '/volume/One-Piece/vol-91', {'include_parent_editions': 'true', 'fields': 'title,number,vf.volumes,vo.volumes'}, frozenset({'standard', 'stress'})),
    Scenario('series_one_piece_editions', 'series_editions', '/series/One-piece-Edition-originale/editions', {'edition': 'all'}, frozenset({'stress'})),
    Scenario('news_global', 'news', '/news/global', {'limit': 10}, frozenset({'standard', 'stress'})),
    Scenario('news_one_piece', 'news', '/news/series/One-piece-Edition-originale', {'limit': 10}, frozenset({'stress'})),
    Scenario('planning_vf', 'planning', '/planning', {'section': 'manga-vf', 'sort': 'date_asc', 'limit': 25}, frozenset({'standard', 'stress'})),
]


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


class BenchmarkClient:
    def __init__(self, base_url: str, token: str | None, timeout: float):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout

    def request(self, scenario: Scenario, *, pass_number: int, request_number: int) -> Sample:
        query = urllib.parse.urlencode(scenario.params)
        url = f'{self.base_url}{scenario.path}'
        if query:
            url = f'{url}?{query}'
        headers = {'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        request = urllib.request.Request(url, headers=headers, method='GET')
        started = time.perf_counter()
        status = 0
        body = b''
        error = None
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                body = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read()
            error = f'HTTP {exc.code}'
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error = str(exc)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        payload: dict[str, Any] = {}
        if body:
            try:
                decoded = json.loads(body.decode('utf-8'))
                if isinstance(decoded, dict):
                    payload = decoded
            except (UnicodeDecodeError, json.JSONDecodeError):
                if error is None:
                    error = 'invalid JSON response'
        return Sample(
            scenario=scenario.name,
            group=scenario.group,
            pass_number=pass_number,
            request_number=request_number,
            duration_ms=duration_ms,
            status=status,
            response_bytes=len(body),
            cached=payload.get('cached'),
            partial=payload.get('partial'),
            found=payload.get('found'),
            error=error,
        )

    def runtime_snapshot(self) -> dict[str, Any]:
        scenario = Scenario('runtime', 'runtime', '/health/runtime', {'include_recent': 'false'}, frozenset())
        query = urllib.parse.urlencode(scenario.params)
        request = urllib.request.Request(
            f'{self.base_url}{scenario.path}?{query}',
            headers={'Accept': 'application/json', **({'Authorization': f'Bearer {self.token}'} if self.token else {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode('utf-8'))
                return payload if isinstance(payload, dict) else {}
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
            return {}


def counter(snapshot: dict[str, Any], name: str) -> int:
    return int((((snapshot.get('metrics') or {}).get('counters') or {}).get(name) or 0))


def counter_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    names = [
        'upstream_fetch_success',
        'upstream_fetch_errors',
        'upstream_fetch_retries',
        'cache_hits',
        'cache_misses',
        'cache_stale_fallbacks',
        'singleflight_creations',
        'singleflight_shared',
    ]
    return {name: counter(after, name) - counter(before, name) for name in names}


def selected_scenarios(profile: str) -> list[Scenario]:
    return [scenario for scenario in SCENARIOS if profile in scenario.profiles]


def run_sequential_pass(
    client: BenchmarkClient,
    scenarios: Iterable[Scenario],
    *,
    pass_number: int,
    repetitions: int,
    max_consecutive_unavailable: int,
) -> tuple[list[Sample], bool]:
    samples: list[Sample] = []
    consecutive_unavailable = 0
    for scenario in scenarios:
        for request_number in range(1, repetitions + 1):
            sample = client.request(scenario, pass_number=pass_number, request_number=request_number)
            samples.append(sample)
            marker = 'OK' if sample.status == 200 and not sample.error else 'FAIL'
            cache_label = ' cache' if sample.cached is True else ''
            print(f'[{marker}] pass={pass_number} {scenario.name}: {sample.duration_ms:.2f} ms status={sample.status}{cache_label}')
            if sample.status == 0:
                consecutive_unavailable += 1
            else:
                consecutive_unavailable = 0
            if consecutive_unavailable >= max_consecutive_unavailable:
                print(
                    f'[ABORT] API unavailable for {consecutive_unavailable} consecutive requests; '
                    'skipping the remaining scenarios.',
                    file=sys.stderr,
                )
                return samples, True
    return samples, False


def run_concurrent_workload(
    client: BenchmarkClient,
    scenarios: list[Scenario],
    *,
    concurrency: int,
    total_requests: int,
    pass_number: int,
) -> list[Sample]:
    samples: list[Sample] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        for request_number in range(1, total_requests + 1):
            scenario = scenarios[(request_number - 1) % len(scenarios)]
            futures.append(
                executor.submit(
                    client.request,
                    scenario,
                    pass_number=pass_number,
                    request_number=request_number,
                )
            )
        for future in as_completed(futures):
            samples.append(future.result())
    return samples


def summarize(samples: list[Sample]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str], list[Sample]] = {}
    for sample in samples:
        grouped.setdefault((sample.pass_number, sample.scenario), []).append(sample)
    rows = []
    for (pass_number, scenario), current in sorted(grouped.items()):
        durations = [sample.duration_ms for sample in current]
        successful = [sample for sample in current if sample.status == 200 and not sample.error]
        cached = [sample for sample in current if sample.cached is True]
        rows.append(
            {
                'pass_number': pass_number,
                'scenario': scenario,
                'group': current[0].group,
                'requests': len(current),
                'successes': len(successful),
                'errors': len(current) - len(successful),
                'cached_responses': len(cached),
                'avg_ms': round(statistics.fmean(durations), 2),
                'p50_ms': round(percentile(durations, 0.50), 2),
                'p95_ms': round(percentile(durations, 0.95), 2),
                'max_ms': round(max(durations), 2),
                'avg_bytes': round(statistics.fmean(sample.response_bytes for sample in current), 1),
            }
        )
    return rows


def write_reports(
    output_dir: Path,
    *,
    args: argparse.Namespace,
    samples: list[Sample],
    summary: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        'generated_at': datetime.now(UTC).isoformat(),
        'base_url': args.base_url,
        'profile': args.profile,
        'passes': args.passes,
        'repetitions': args.repetitions,
        'concurrency': args.concurrency,
        'concurrent_requests': args.concurrent_requests,
    }
    (output_dir / 'report.json').write_text(
        json.dumps(
            {
                'metadata': metadata,
                'metrics_by_pass': metrics,
                'summary': summary,
                'samples': [asdict(sample) for sample in samples],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    with (output_dir / 'summary.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()) if summary else ['scenario'])
        writer.writeheader()
        writer.writerows(summary)
    with (output_dir / 'samples.csv').open('w', encoding='utf-8', newline='') as handle:
        sample_rows = [asdict(sample) for sample in samples]
        writer = csv.DictWriter(handle, fieldnames=list(sample_rows[0].keys()) if sample_rows else ['scenario'])
        writer.writeheader()
        writer.writerows(sample_rows)


def print_summary(summary: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    print()
    print('Summary')
    print('-------')
    print(f"{'Pass':>4}  {'Scenario':42} {'Req':>4} {'OK':>4} {'Avg ms':>9} {'P95 ms':>9} {'Cache':>5}")
    for row in summary:
        print(
            f"{row['pass_number']:>4}  {row['scenario'][:42]:42} "
            f"{row['requests']:>4} {row['successes']:>4} "
            f"{row['avg_ms']:>9.2f} {row['p95_ms']:>9.2f} {row['cached_responses']:>5}"
        )
    print()
    print('Runtime metric deltas')
    print('---------------------')
    for item in metrics:
        delta = item['delta']
        print(
            f"pass {item['pass_number']}: upstream_ok={delta['upstream_fetch_success']} "
            f"upstream_errors={delta['upstream_fetch_errors']} retries={delta['upstream_fetch_retries']} "
            f"cache_hits={delta['cache_hits']} cache_misses={delta['cache_misses']} "
            f"singleflight_shared={delta['singleflight_shared']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Benchmark the Manga News API V2 with cold-ish and warm-cache passes.')
    parser.add_argument('--base-url', default=os.getenv('BASE_URL', 'http://localhost:8017'))
    parser.add_argument('--token', default=os.getenv('API_TOKEN') or os.getenv('TOKEN'))
    parser.add_argument('--profile', choices=('quick', 'standard', 'stress'), default='standard')
    parser.add_argument(
        '--scenario',
        action='append',
        choices=tuple(scenario.name for scenario in SCENARIOS),
        help='Run only this scenario; repeat the option to select several scenarios.',
    )
    parser.add_argument('--passes', type=int, default=2, help='Pass 1 measures current cache state; later passes measure warm cache.')
    parser.add_argument('--repetitions', type=int, default=1, help='Sequential requests per scenario and pass.')
    parser.add_argument('--timeout', type=float, default=60.0)
    parser.add_argument(
        '--max-consecutive-unavailable',
        type=int,
        default=2,
        help='Abort after this many consecutive connection failures or timeouts.',
    )
    parser.add_argument('--concurrency', type=int, default=8, help='Workers for the optional concurrent workload.')
    parser.add_argument('--concurrent-requests', type=int, default=24, help='Requests in the optional concurrent workload.')
    parser.add_argument('--skip-concurrency', action='store_true')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--list-scenarios', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenarios = selected_scenarios(args.profile)
    if args.scenario:
        selected_names = set(args.scenario)
        scenarios = [scenario for scenario in SCENARIOS if scenario.name in selected_names]
    if args.list_scenarios:
        for scenario in scenarios:
            print(f'{scenario.name}: {scenario.path} {scenario.params}')
        return 0
    if args.passes < 1 or args.repetitions < 1:
        raise SystemExit('--passes and --repetitions must be >= 1')
    if args.concurrency < 1 or args.concurrent_requests < 1:
        raise SystemExit('--concurrency and --concurrent-requests must be >= 1')
    if args.max_consecutive_unavailable < 1:
        raise SystemExit('--max-consecutive-unavailable must be >= 1')

    output_dir = args.output_dir or (
        Path('benchmark-results') / datetime.now().strftime('%Y%m%d-%H%M%S')
    )
    client = BenchmarkClient(args.base_url, args.token, args.timeout)

    health = client.request(
        Scenario('startup_health', 'health', '/health', {}, frozenset()),
        pass_number=0,
        request_number=1,
    )
    if health.status != 200:
        print(f'API unavailable at {args.base_url}: status={health.status} error={health.error}', file=sys.stderr)
        return 2

    all_samples: list[Sample] = []
    metric_deltas: list[dict[str, Any]] = []
    for pass_number in range(1, args.passes + 1):
        print()
        print(f'Pass {pass_number}/{args.passes}')
        print('----------------')
        before = client.runtime_snapshot()
        sequential_samples, api_unavailable = run_sequential_pass(
            client,
            scenarios,
            pass_number=pass_number,
            repetitions=args.repetitions,
            max_consecutive_unavailable=args.max_consecutive_unavailable,
        )
        all_samples.extend(sequential_samples)
        if not args.skip_concurrency and not api_unavailable:
            concurrent_scenarios = [
                scenario for scenario in scenarios
                if scenario.group in {'search_light', 'volume_search_light', 'series_projection', 'volume_projection'}
            ]
            concurrent_samples = run_concurrent_workload(
                client,
                concurrent_scenarios,
                concurrency=args.concurrency,
                total_requests=args.concurrent_requests,
                pass_number=pass_number,
            )
            all_samples.extend(concurrent_samples)
            durations = [sample.duration_ms for sample in concurrent_samples]
            success_count = sum(sample.status == 200 and not sample.error for sample in concurrent_samples)
            print(
                f'[LOAD] concurrency={args.concurrency} requests={len(concurrent_samples)} '
                f'ok={success_count} avg={statistics.fmean(durations):.2f} ms '
                f'p95={percentile(durations, 0.95):.2f} ms'
            )
        after = client.runtime_snapshot()
        metric_deltas.append(
            {
                'pass_number': pass_number,
                'before': before,
                'after': after,
                'delta': counter_delta(before, after),
            }
        )
        if api_unavailable:
            break

    summary = summarize(all_samples)
    write_reports(
        output_dir,
        args=args,
        samples=all_samples,
        summary=summary,
        metrics=metric_deltas,
    )
    print_summary(summary, metric_deltas)
    print()
    print(f'Reports: {output_dir.resolve()}')
    failures = [sample for sample in all_samples if sample.status != 200 or sample.error]
    if failures:
        print(f'Completed with {len(failures)} failed requests.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
