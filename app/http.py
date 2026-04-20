from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from app.exceptions import ResourceNotFound, UpstreamError
from app.logging_utils import log_event

logger = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(slots=True)
class FetchResult:
    text: str
    url: str


class AsyncFetcher:
    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float,
        *,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        log_json: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._log_json = log_json
        self._max_retries = max(0, max_retries)
        self._backoff_seconds = max(0.0, backoff_seconds)
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            transport=transport,
            headers={
                'User-Agent': user_agent,
                'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_text(self, url: str, params: dict | None = None) -> FetchResult:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            started = time.perf_counter()
            try:
                response = await self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                last_exc = exc
                retrying = attempt < self._max_retries
                log_event(
                    logger,
                    logging.WARNING if retrying else logging.ERROR,
                    'upstream_fetch_error',
                    json_mode=self._log_json,
                    url=url,
                    attempt=attempt + 1,
                    max_attempts=self._max_retries + 1,
                    duration_ms=duration_ms,
                    reason=str(exc),
                    retrying=retrying,
                )
                if retrying:
                    await asyncio.sleep(self._backoff_seconds * (2 ** attempt))
                    continue
                raise UpstreamError(f'Unable to reach Manga News: {exc}') from exc

            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            retrying = response.status_code in RETRYABLE_STATUS_CODES and attempt < self._max_retries
            if response.status_code == 404:
                log_event(
                    logger,
                    logging.INFO,
                    'upstream_fetch',
                    json_mode=self._log_json,
                    url=str(response.url),
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    attempt=attempt + 1,
                    max_attempts=self._max_retries + 1,
                )
                raise ResourceNotFound('Resource not found on Manga News.')
            if retrying:
                log_event(
                    logger,
                    logging.WARNING,
                    'upstream_fetch_retry',
                    json_mode=self._log_json,
                    url=str(response.url),
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    attempt=attempt + 1,
                    max_attempts=self._max_retries + 1,
                )
                await asyncio.sleep(self._backoff_seconds * (2 ** attempt))
                continue
            if response.status_code >= 400:
                log_event(
                    logger,
                    logging.ERROR,
                    'upstream_fetch',
                    json_mode=self._log_json,
                    url=str(response.url),
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    attempt=attempt + 1,
                    max_attempts=self._max_retries + 1,
                )
                raise UpstreamError(f'Manga News returned HTTP {response.status_code}.')
            if not response.text.strip():
                log_event(
                    logger,
                    logging.ERROR,
                    'upstream_fetch_empty',
                    json_mode=self._log_json,
                    url=str(response.url),
                    duration_ms=duration_ms,
                    attempt=attempt + 1,
                    max_attempts=self._max_retries + 1,
                )
                raise UpstreamError('Manga News returned an empty response.')
            log_event(
                logger,
                logging.INFO,
                'upstream_fetch',
                json_mode=self._log_json,
                url=str(response.url),
                status_code=response.status_code,
                duration_ms=duration_ms,
                attempt=attempt + 1,
                max_attempts=self._max_retries + 1,
            )
            return FetchResult(text=response.text, url=str(response.url))

        if last_exc is not None:
            raise UpstreamError(f'Unable to reach Manga News: {last_exc}') from last_exc
        raise UpstreamError('Unable to reach Manga News.')
