from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from app.exceptions import ResourceNotFound, UpstreamError
from app.logging_utils import log_event

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FetchResult:
    text: str
    url: str


class AsyncFetcher:
    def __init__(self, user_agent: str, timeout_seconds: float, *, log_json: bool = False):
        self._log_json = log_json
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={
                'User-Agent': user_agent,
                'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_text(self, url: str, params: dict | None = None) -> FetchResult:
        started = time.perf_counter()
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            log_event(logger, logging.ERROR, 'upstream_fetch_error', json_mode=self._log_json, url=url, reason=str(exc))
            raise UpstreamError(f'Unable to reach Manga News: {exc}') from exc

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        if response.status_code == 404:
            log_event(logger, logging.INFO, 'upstream_fetch', json_mode=self._log_json, url=str(response.url), status_code=response.status_code, duration_ms=duration_ms)
            raise ResourceNotFound('Resource not found on Manga News.')
        if response.status_code >= 400:
            log_event(logger, logging.ERROR, 'upstream_fetch', json_mode=self._log_json, url=str(response.url), status_code=response.status_code, duration_ms=duration_ms)
            raise UpstreamError(f'Manga News returned HTTP {response.status_code}.')
        if not response.text.strip():
            log_event(logger, logging.ERROR, 'upstream_fetch_empty', json_mode=self._log_json, url=str(response.url), duration_ms=duration_ms)
            raise UpstreamError('Manga News returned an empty response.')
        log_event(logger, logging.INFO, 'upstream_fetch', json_mode=self._log_json, url=str(response.url), status_code=response.status_code, duration_ms=duration_ms)
        return FetchResult(text=response.text, url=str(response.url))
