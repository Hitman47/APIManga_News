import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.run_v2_benchmarks import (
    Sample,
    Scenario,
    main,
    percentile,
    run_sequential_pass,
    selected_scenarios,
    summarize,
)


def test_benchmark_profiles_have_progressively_more_scenarios():
    quick = selected_scenarios('quick')
    standard = selected_scenarios('standard')
    stress = selected_scenarios('stress')

    assert len(quick) < len(standard) < len(stress)
    assert {item.group for item in standard} >= {
        'search_light',
        'volume_search_light',
        'search_enriched',
        'series_projection',
        'volume_projection',
        'news',
        'planning',
    }


def test_percentile_and_summary_are_deterministic():
    samples = [
        Sample('search', 'search_light', 1, 1, 10.0, 200, 100, False, False, True),
        Sample('search', 'search_light', 1, 2, 20.0, 200, 120, True, False, True),
        Sample('search', 'search_light', 1, 3, 30.0, 502, 80, False, False, False, 'HTTP 502'),
    ]

    assert percentile([10.0, 20.0, 30.0], 0.95) == 30.0
    rows = summarize(samples)
    assert rows == [
        {
            'pass_number': 1,
            'scenario': 'search',
            'group': 'search_light',
            'requests': 3,
            'successes': 2,
            'errors': 1,
            'cached_responses': 1,
            'avg_ms': 20.0,
            'p50_ms': 20.0,
            'p95_ms': 30.0,
            'max_ms': 30.0,
            'avg_bytes': 100.0,
        }
    ]


def test_sequential_pass_aborts_after_consecutive_unavailable_requests():
    class UnavailableClient:
        def request(self, scenario, *, pass_number, request_number):
            return Sample(
                scenario.name,
                scenario.group,
                pass_number,
                request_number,
                10.0,
                0,
                0,
                None,
                None,
                None,
                'timed out',
            )

    scenarios = [
        Scenario(f'scenario_{index}', 'test', '/test', {}, frozenset())
        for index in range(5)
    ]

    samples, aborted = run_sequential_pass(
        UnavailableClient(),
        scenarios,
        pass_number=1,
        repetitions=1,
        max_consecutive_unavailable=2,
    )

    assert aborted is True
    assert len(samples) == 2


def test_benchmark_runner_writes_reports_against_http_server(tmp_path, monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        counters = {
            'upstream_fetch_success': 0,
            'cache_hits': 0,
        }

        def do_GET(self):
            if self.path.startswith('/health/runtime'):
                payload = {
                    'ok': True,
                    'metrics': {'counters': dict(self.counters)},
                }
            elif self.path == '/health':
                payload = {'ok': True}
            else:
                self.counters['cache_hits'] += 1
                payload = {
                    'ok': True,
                    'found': True,
                    'cached': True,
                    'partial': False,
                    'data': {},
                }
            body = json.dumps(payload).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output_dir = tmp_path / 'benchmark'
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'run_v2_benchmarks.py',
            '--base-url',
            f'http://127.0.0.1:{server.server_port}',
            '--profile',
            'quick',
            '--passes',
            '1',
            '--skip-concurrency',
            '--output-dir',
            str(output_dir),
        ],
    )
    try:
        assert main() == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    report = json.loads((output_dir / 'report.json').read_text(encoding='utf-8'))
    assert report['metadata']['profile'] == 'quick'
    assert len(report['summary']) == len(selected_scenarios('quick'))
    assert (output_dir / 'summary.csv').is_file()
    assert (output_dir / 'samples.csv').is_file()


def test_benchmark_runner_can_select_one_scenario(tmp_path, monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = {'ok': True, 'metrics': {'counters': {}}}
            body = json.dumps(payload).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output_dir = tmp_path / 'single-scenario'
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'run_v2_benchmarks.py',
            '--base-url',
            f'http://127.0.0.1:{server.server_port}',
            '--scenario',
            'health',
            '--passes',
            '1',
            '--skip-concurrency',
            '--output-dir',
            str(output_dir),
        ],
    )
    try:
        assert main() == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    report = json.loads((output_dir / 'report.json').read_text(encoding='utf-8'))
    assert [row['scenario'] for row in report['summary']] == ['health']
