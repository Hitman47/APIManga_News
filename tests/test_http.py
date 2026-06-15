import asyncio

import httpx

from app.exceptions import ResourceNotFound, UpstreamError
from app.http import AsyncFetcher
from app.metrics import MetricsStore


async def _run_retry_scenario():
    calls = {'count': 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls['count'] += 1
        if calls['count'] < 3:
            return httpx.Response(503, text='temporary failure', request=request)
        return httpx.Response(200, text='ok', request=request)

    fetcher = AsyncFetcher('test-agent', 2.0, max_retries=2, backoff_seconds=0, transport=httpx.MockTransport(handler))
    try:
        result = await fetcher.get_text('https://example.test/resource')
        return result, calls['count']
    finally:
        await fetcher.close()


async def _run_not_found_scenario():
    calls = {'count': 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls['count'] += 1
        return httpx.Response(404, text='not found', request=request)

    fetcher = AsyncFetcher('test-agent', 2.0, max_retries=3, backoff_seconds=0, transport=httpx.MockTransport(handler))
    try:
        try:
            await fetcher.get_text('https://example.test/missing')
        except ResourceNotFound:
            return calls['count']
        raise AssertionError('ResourceNotFound was not raised')
    finally:
        await fetcher.close()


async def _run_network_failure_scenario():
    calls = {'count': 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls['count'] += 1
        raise httpx.ConnectError('boom', request=request)

    fetcher = AsyncFetcher('test-agent', 2.0, max_retries=1, backoff_seconds=0, transport=httpx.MockTransport(handler))
    try:
        try:
            await fetcher.get_text('https://example.test/unreachable')
        except UpstreamError:
            return calls['count']
        raise AssertionError('UpstreamError was not raised')
    finally:
        await fetcher.close()


def test_async_fetcher_retries_retryable_statuses():
    result, call_count = asyncio.run(_run_retry_scenario())
    assert result.text == 'ok'
    assert result.url == 'https://example.test/resource'
    assert call_count == 3



def test_async_fetcher_does_not_retry_on_404():
    call_count = asyncio.run(_run_not_found_scenario())
    assert call_count == 1



def test_async_fetcher_retries_network_errors_until_exhausted():
    call_count = asyncio.run(_run_network_failure_scenario())
    assert call_count == 2


async def _run_concurrency_scenario():
    active = 0
    maximum_active = 0
    lock = asyncio.Lock()
    metrics = MetricsStore()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, maximum_active
        async with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.02)
        async with lock:
            active -= 1
        return httpx.Response(200, text='ok', request=request)

    fetcher = AsyncFetcher(
        'test-agent',
        2.0,
        max_retries=0,
        max_concurrency=2,
        metrics=metrics,
        transport=httpx.MockTransport(handler),
    )
    try:
        await asyncio.gather(*(fetcher.get_text(f'https://example.test/{index}') for index in range(6)))
        return maximum_active, metrics.snapshot()
    finally:
        await fetcher.close()


def test_async_fetcher_limits_global_upstream_concurrency_and_records_timings():
    maximum_active, snapshot = asyncio.run(_run_concurrency_scenario())

    assert maximum_active == 2
    assert snapshot.timings['upstream.fetch']['count'] == 6
