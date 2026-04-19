from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.exceptions import ResourceNotFound, UpstreamError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FetchResult:
    text: str
    url: str


class AsyncFetcher:
    def __init__(self, user_agent: str, timeout_seconds: float):
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
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise UpstreamError(f'Unable to reach Manga News: {exc}') from exc

        if response.status_code == 404:
            raise ResourceNotFound('Resource not found on Manga News.')
        if response.status_code >= 400:
            raise UpstreamError(f'Manga News returned HTTP {response.status_code}.')
        if not response.text.strip():
            raise UpstreamError('Manga News returned an empty response.')
        logger.debug('Fetched %s', response.url)
        return FetchResult(text=response.text, url=str(response.url))
