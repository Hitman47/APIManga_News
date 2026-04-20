from __future__ import annotations

import logging
from datetime import date
from typing import Literal
from urllib.parse import urlencode

import feedparser

from app.cache import SQLiteCache
from app.config import Settings
from app.exceptions import ParseError
from app.http import AsyncFetcher
from app.models import (
    BaseEnvelope,
    NewsItem,
    NewsResponse,
    PlanningData,
    PlanningFilters,
    PlanningResponse,
    ResolveData,
    ResolveResponse,
    SCHEMA_VERSION,
    SearchResponse,
    SearchResult,
    SeriesResponse,
    VolumeResponse,
)
from app.manga_news.parsers import parse_news_page, parse_planning_page, parse_search_page, parse_series_page, parse_volume_page
from app.utils import clean_ws, is_manga_news_url, make_cache_key, normalize_text, now_utc, parse_french_date, score_match

logger = logging.getLogger(__name__)


class MangaNewsService:
    def __init__(self, settings: Settings, fetcher: AsyncFetcher, cache: SQLiteCache):
        self.settings = settings
        self.fetcher = fetcher
        self.cache = cache
        self.base_url = settings.manga_news_base_url.rstrip('/')

    async def _cached_payload(self, *, cache_key: str, ttl_seconds: int, loader):
        entry = self.cache.get(cache_key)
        if entry and entry.is_fresh:
            return entry.payload, entry, True, False, []
        try:
            payload, source_url = await loader()
            cached_entry = self.cache.set(
                cache_key=cache_key,
                payload={'data': payload, 'source_url': source_url},
                ttl_seconds=ttl_seconds,
                stale_grace_seconds=self.settings.cache_stale_grace_seconds,
            )
            return cached_entry.payload, cached_entry, False, False, []
        except Exception as exc:
            if entry and entry.is_stale_usable:
                warning = f'Using stale cached data because the upstream fetch failed: {exc}'
                logger.warning(warning)
                return entry.payload, entry, True, True, [warning]
            raise

    def _base_envelope_kwargs(self, payload: dict, entry, *, cached: bool, partial: bool, warnings: list[str], found: bool = True) -> dict:
        return {
            'schema_version': SCHEMA_VERSION,
            'ok': True,
            'found': found,
            'source': 'manga_news',
            'source_url': payload.get('source_url'),
            'cached': cached,
            'fetched_at': entry.fetched_at.isoformat() if entry else now_utc().isoformat(),
            'cache_expires_at': entry.expires_at.isoformat() if entry else None,
            'partial': partial,
            'warnings': warnings,
        }

    async def _search_results(self, query: str, kind: Literal['series', 'volume', 'all'], limit: int) -> tuple[list[SearchResult], str]:
        query = clean_ws(query)
        if not query:
            raise ParseError('The search query cannot be empty.')
        search_urls: list[str] = []
        if kind in {'series', 'all'}:
            search_urls.extend([
                f'{self.base_url}/index.php/recherche/?cat=manga-serie-vf&q={query}',
                f'{self.base_url}/index.php/recherche/?cat=manga-serie-vo&q={query}',
            ])
        if kind in {'volume', 'all'}:
            search_urls.extend([
                f'{self.base_url}/index.php/recherche/?cat=manga-volume-vf&q={query}',
                f'{self.base_url}/index.php/recherche/?cat=manga-volume-vo&q={query}',
            ])
        aggregated: list[SearchResult] = []
        for url in search_urls:
            result = await self.fetcher.get_text(url)
            aggregated.extend(
                parse_search_page(
                    html=result.text,
                    page_url=result.url,
                    base_url=self.base_url,
                    query=query,
                    kind=kind,
                    score_threshold=self.settings.search_score_threshold,
                    limit=max(limit, self.settings.max_limit),
                )
            )
        deduped: dict[str, SearchResult] = {}
        for item in aggregated:
            existing = deduped.get(item.url)
            if existing is None or item.score > existing.score:
                deduped[item.url] = item
        results = sorted(deduped.values(), key=lambda item: item.score, reverse=True)
        return results[:limit], search_urls[0] if search_urls else self.base_url

    async def search(self, query: str, kind: Literal['series', 'volume', 'all'], mode: Literal['best', 'all'], limit: int) -> SearchResponse:
        query = clean_ws(query)
        if not query:
            raise ParseError('The search query cannot be empty.')
        cache_key = make_cache_key('search', query, kind, mode, str(limit))

        async def loader():
            results, source_url = await self._search_results(query=query, kind=kind, limit=max(limit, self.settings.max_limit))
            if mode == 'best' and results:
                results = [results[0]]
            return [item.model_dump() for item in results[:limit]], source_url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_search_seconds,
            loader=loader,
        )
        data = [SearchResult.model_validate(item) for item in payload.get('data', [])]
        return SearchResponse(
            **self._base_envelope_kwargs(payload, entry, cached=cached, partial=partial, warnings=warnings, found=bool(data)),
            data=data,
        )

    async def resolve_search(self, query: str, kind: Literal['series', 'volume', 'all']) -> ResolveResponse:
        query = clean_ws(query)
        if not query:
            raise ParseError('The search query cannot be empty.')
        cache_key = make_cache_key('search-resolve', query, kind)

        async def loader():
            results, source_url = await self._search_results(query=query, kind=kind, limit=self.settings.max_limit)
            best = results[0] if results else None
            if best is None:
                confidence = 'none'
            elif best.score >= 90:
                confidence = 'high'
            elif best.score >= 75:
                confidence = 'medium'
            else:
                confidence = 'low'
            data = ResolveData(
                query=query,
                result=best,
                confidence=confidence,
                alternatives_count=max(len(results) - 1, 0),
            )
            return data.model_dump(), source_url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_search_seconds,
            loader=loader,
        )
        data = ResolveData.model_validate(payload.get('data', {}))
        return ResolveResponse(
            **self._base_envelope_kwargs(payload, entry, cached=cached, partial=partial, warnings=warnings, found=data.result is not None),
            data=data,
        )

    async def get_series(self, *, slug: str | None = None, url: str | None = None) -> SeriesResponse:
        target_url = self._resolve_series_url(slug=slug, url=url)
        cache_key = make_cache_key('series', target_url)

        async def loader():
            result = await self.fetcher.get_text(target_url)
            parsed = parse_series_page(result.text, result.url)
            return parsed.model_dump(), result.url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_series_seconds,
            loader=loader,
        )
        return SeriesResponse(
            **self._base_envelope_kwargs(payload, entry, cached=cached, partial=partial, warnings=warnings),
            data=payload.get('data'),
        )

    async def get_volume(self, *, series_slug: str | None = None, volume_slug: str | None = None, url: str | None = None) -> VolumeResponse:
        target_url = self._resolve_volume_url(series_slug=series_slug, volume_slug=volume_slug, url=url)
        cache_key = make_cache_key('volume', target_url)

        async def loader():
            result = await self.fetcher.get_text(target_url)
            parsed = parse_volume_page(result.text, result.url)
            return parsed.model_dump(), result.url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_volume_seconds,
            loader=loader,
        )
        return VolumeResponse(
            **self._base_envelope_kwargs(payload, entry, cached=cached, partial=partial, warnings=warnings),
            data=payload.get('data'),
        )

    async def get_global_news(self, *, limit: int) -> NewsResponse:
        rss_url = f'{self.base_url}/index.php/feed/news'
        cache_key = make_cache_key('news-global', rss_url, str(limit))

        async def loader():
            result = await self.fetcher.get_text(rss_url)
            feed = feedparser.parse(result.text)
            items: list[NewsItem] = []
            for entry in feed.entries[:limit]:
                items.append(
                    NewsItem(
                        title=clean_ws(entry.get('title')),
                        url=entry.get('link'),
                        published_at=parse_french_date(clean_ws(entry.get('published'))),
                        excerpt=clean_ws(entry.get('summary')) or None,
                        category=clean_ws(entry.tags[0].term) if getattr(entry, 'tags', None) else None,
                    )
                )
            return [item.model_dump() for item in items], result.url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_news_global_seconds,
            loader=loader,
        )
        data = [NewsItem.model_validate(item) for item in payload.get('data', [])]
        return NewsResponse(
            **self._base_envelope_kwargs(payload, entry, cached=cached, partial=partial, warnings=warnings, found=bool(data)),
            data=data,
        )

    async def get_series_news(self, *, slug: str, limit: int) -> NewsResponse:
        target_url = f'{self.base_url}/index.php/serie/news/{slug}'
        return await self._get_news_page(target_url=target_url, cache_namespace='news-series', ttl=self.settings.cache_ttl_news_series_seconds, limit=limit)

    async def get_volume_news(self, *, series_slug: str | None = None, volume_slug: str | None = None, url: str | None = None, limit: int) -> NewsResponse:
        target_url = self._resolve_volume_url(series_slug=series_slug, volume_slug=volume_slug, url=url)
        if '/index.php/manga/' not in target_url:
            raise ParseError('The provided volume URL is not a Manga News volume page.')
        parts = target_url.split('/index.php/manga/', 1)[1].strip('/').split('/')
        if len(parts) < 2:
            raise ParseError('Unable to infer the volume route from the provided URL.')
        news_url = f'{self.base_url}/index.php/manga/news/{parts[0]}/{parts[1]}'
        return await self._get_news_page(target_url=news_url, cache_namespace='news-volume', ttl=self.settings.cache_ttl_news_series_seconds, limit=limit)

    async def get_planning(
        self,
        *,
        section: Literal['manga-vf', 'manga-vo'],
        year: int | None,
        month: int | None,
        page: int,
        publisher: str | None,
        query: str | None,
        date_from: str | None,
        date_to: str | None,
        sort: Literal['date_asc', 'date_desc', 'title_asc', 'title_desc'],
        limit: int,
    ) -> PlanningResponse:
        path = '/index.php/planning/' if section == 'manga-vf' else '/index.php/planning/mangas-vo'
        params: dict[str, object] = {}
        if year is not None:
            params['p_year'] = year
        if month is not None:
            params['p_month'] = month
        if page > 1:
            params['page'] = page
        query_string = urlencode(params)
        target_url = f'{self.base_url}{path}'
        if query_string:
            target_url = f'{target_url}?{query_string}'
        cache_key = make_cache_key('planning', target_url)

        async def loader():
            result = await self.fetcher.get_text(target_url)
            parsed = parse_planning_page(result.text, result.url, self.base_url)
            parsed.page = page
            return parsed.model_dump(), result.url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_planning_seconds,
            loader=loader,
        )

        planning = payload.get('data', {}) or {}
        items = list(planning.get('items', []))

        if publisher:
            normalized_publisher = normalize_text(publisher)
            items = [item for item in items if normalized_publisher in normalize_text(item.get('publisher'))]

        if query:
            normalized_query = clean_ws(query)
            items = [
                item for item in items
                if score_match(
                    normalized_query,
                    ' '.join([
                        item.get('title', ''),
                        ' / '.join(item.get('authors', [])),
                        item.get('publisher', '') or '',
                    ]),
                ) >= self.settings.search_score_threshold
            ]

        parsed_date_from = self._parse_iso_date(date_from, 'date_from')
        parsed_date_to = self._parse_iso_date(date_to, 'date_to')
        if parsed_date_from or parsed_date_to:
            filtered_items = []
            for item in items:
                raw_date = item.get('release_date')
                if not raw_date:
                    continue
                release_date = date.fromisoformat(raw_date)
                if parsed_date_from and release_date < parsed_date_from:
                    continue
                if parsed_date_to and release_date > parsed_date_to:
                    continue
                filtered_items.append(item)
            items = filtered_items

        if sort == 'date_asc':
            items.sort(key=lambda item: (item.get('release_date') or '9999-99-99', normalize_text(item.get('title'))))
        elif sort == 'date_desc':
            items.sort(key=lambda item: (item.get('release_date') or '0000-00-00', normalize_text(item.get('title'))), reverse=True)
        elif sort == 'title_asc':
            items.sort(key=lambda item: normalize_text(item.get('title')))
        elif sort == 'title_desc':
            items.sort(key=lambda item: normalize_text(item.get('title')), reverse=True)

        total_items = len(items)
        items = items[:limit]
        data = PlanningData(
            section=planning.get('section') or section,
            year=planning.get('year') or year,
            month=planning.get('month') or month,
            page=planning.get('page') or page,
            filters=PlanningFilters(
                publisher=publisher,
                query=query,
                date_from=date_from,
                date_to=date_to,
            ),
            sort=sort,
            total_items=total_items,
            items=items,
        )

        return PlanningResponse(
            **self._base_envelope_kwargs(payload, entry, cached=cached, partial=partial, warnings=warnings, found=bool(items)),
            data=data,
        )

    def _parse_iso_date(self, value: str | None, field_name: str) -> date | None:
        if value is None:
            return None
        parsed = parse_french_date(value)
        if not parsed:
            raise ParseError(f'{field_name} must be a valid date.')
        try:
            return date.fromisoformat(parsed)
        except ValueError as exc:
            raise ParseError(f'{field_name} must be a valid date.') from exc

    async def _get_news_page(self, *, target_url: str, cache_namespace: str, ttl: int, limit: int) -> NewsResponse:
        cache_key = make_cache_key(cache_namespace, target_url, str(limit))

        async def loader():
            result = await self.fetcher.get_text(target_url)
            parsed = parse_news_page(result.text, result.url, self.base_url, limit=limit)
            return [item.model_dump() for item in parsed], result.url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=ttl,
            loader=loader,
        )
        data = [NewsItem.model_validate(item) for item in payload.get('data', [])]
        return NewsResponse(
            **self._base_envelope_kwargs(payload, entry, cached=cached, partial=partial, warnings=warnings, found=bool(data)),
            data=data,
        )

    def _resolve_series_url(self, *, slug: str | None, url: str | None) -> str:
        if url:
            if not is_manga_news_url(url, self.base_url):
                raise ParseError('The provided URL does not belong to Manga News.')
            return url
        if not slug:
            raise ParseError('A series slug or URL is required.')
        return f'{self.base_url}/index.php/serie/{slug}'

    def _resolve_volume_url(self, *, series_slug: str | None, volume_slug: str | None, url: str | None) -> str:
        if url:
            if not is_manga_news_url(url, self.base_url):
                raise ParseError('The provided URL does not belong to Manga News.')
            return url
        if not series_slug or not volume_slug:
            raise ParseError('series_slug and volume_slug are required when no direct URL is provided.')
        return f'{self.base_url}/index.php/manga/{series_slug}/{volume_slug}'
