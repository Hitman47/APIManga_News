from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal
from urllib.parse import urlencode, urlparse

import feedparser

from app.cache import SQLiteCache
from app.config import Settings
from app.exceptions import ParseError
from app.http import AsyncFetcher
from app.models import (
    ComparisonData,
    ComparisonDiff,
    Envelope,
    MachineSeriesSummaryData,
    MachineVolumeSummaryData,
    NewsItem,
    SeriesNewsSummaryData,
    SeriesReleaseSummaryData,
)
from app.manga_news.parsers import parse_news_page, parse_planning_page, parse_search_page, parse_series_page, parse_volume_page
from app.utils import (
    clean_ws,
    flatten_for_compare,
    is_manga_news_url,
    make_cache_key,
    normalize_text,
    now_utc,
    parse_fields_param,
    parse_french_date,
    project_dict_fields,
    score_match,
)

logger = logging.getLogger(__name__)

SERIES_COMPARISON_FIELDS = [
    'title',
    'title_vo',
    'translated_title',
    'publisher_fr',
    'publisher_vo',
    'collection',
    'type',
    'genres',
    'prepublication',
    'origin',
    'illustration',
    'advisory_age',
    'vf.volumes',
    'vf.status',
    'vo.volumes',
    'vo.status',
    'last_release_date',
    'next_release_date',
    'themes',
]
VOLUME_COMPARISON_FIELDS = [
    'title',
    'series_title',
    'title_vo',
    'translated_title',
    'publisher_fr',
    'publisher_vo',
    'collection',
    'type',
    'genres',
    'publication_date',
    'isbn_ean',
    'price_code',
    'editorial_score',
    'reader_score',
    'illustration',
    'origin',
]


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

    def _envelope(self, payload: dict, entry, *, cached: bool, partial: bool, warnings: list[str], found: bool = True) -> Envelope:
        return Envelope(
            ok=True,
            found=found,
            source='manga_news',
            source_url=payload.get('source_url'),
            cached=cached,
            fetched_at=entry.fetched_at.isoformat() if entry else now_utc().isoformat(),
            cache_expires_at=entry.expires_at.isoformat() if entry else None,
            partial=partial,
            warnings=warnings,
            data=payload.get('data'),
        )

    async def search(self, query: str, kind: Literal['series', 'volume', 'all'], mode: Literal['best', 'all'], limit: int) -> Envelope:
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
        cache_key = make_cache_key('search', query, kind, mode, str(limit), *search_urls)

        async def loader():
            aggregated = []
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
            deduped: dict[str, Any] = {}
            for item in aggregated:
                existing = deduped.get(item.url)
                if existing is None or item.score > existing.score:
                    deduped[item.url] = item
            results = sorted(deduped.values(), key=lambda item: item.score, reverse=True)
            if mode == 'best' and results:
                results = [results[0]]
            results = results[:limit]
            return [item.model_dump() for item in results], search_urls[0] if search_urls else self.base_url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_search_seconds,
            loader=loader,
        )
        found = bool(payload.get('data'))
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings, found=found)

    async def get_series(self, *, slug: str | None = None, url: str | None = None) -> Envelope:
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
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings)

    async def select_series_fields(self, *, slug: str | None = None, url: str | None = None, fields: str | None = None) -> Envelope:
        target_url = self._resolve_series_url(slug=slug, url=url)
        selected_fields = parse_fields_param(fields)
        if not selected_fields:
            raise ParseError('fields is required for the series projection endpoint.')
        cache_key = make_cache_key('series-select', target_url, *selected_fields)

        async def loader():
            envelope = await self.get_series(url=target_url)
            data = envelope.data or {}
            return project_dict_fields(data, selected_fields), target_url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_series_seconds,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings, found=bool(payload.get('data')))

    async def get_series_summary(self, *, slug: str | None = None, url: str | None = None) -> Envelope:
        target_url = self._resolve_series_url(slug=slug, url=url)
        cache_key = make_cache_key('series-summary', target_url)

        async def loader():
            envelope = await self.get_series(url=target_url)
            data = envelope.data or {}
            summary = MachineSeriesSummaryData(
                slug=self._series_slug_from_url(target_url),
                title=data.get('title', ''),
                title_vo=data.get('title_vo'),
                publisher_fr=data.get('publisher_fr'),
                vf=data.get('vf'),
                vo=data.get('vo'),
                last_release_date=data.get('last_release_date'),
                next_release_date=data.get('next_release_date'),
                source_url=data.get('source_url') or target_url,
            )
            return summary.model_dump(), target_url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_series_seconds,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings)

    async def get_series_release_summary(self, *, slug: str | None = None, url: str | None = None) -> Envelope:
        target_url = self._resolve_series_url(slug=slug, url=url)
        cache_key = make_cache_key('series-release-summary', target_url)

        async def loader():
            envelope = await self.get_series(url=target_url)
            data = envelope.data or {}
            summary = SeriesReleaseSummaryData(
                slug=self._series_slug_from_url(target_url),
                title=data.get('title', ''),
                vf=data.get('vf'),
                vo=data.get('vo'),
                last_release_date=data.get('last_release_date'),
                next_release_date=data.get('next_release_date'),
                has_upcoming_release=bool(data.get('next_release_date')),
                publisher_fr=data.get('publisher_fr'),
                source_url=data.get('source_url') or target_url,
            )
            return summary.model_dump(), target_url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_series_seconds,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings)

    async def get_series_news_summary(self, *, slug: str | None = None, url: str | None = None, limit: int = 20) -> Envelope:
        target_url = self._resolve_series_url(slug=slug, url=url)
        series_slug = self._series_slug_from_url(target_url)
        cache_key = make_cache_key('series-news-summary', series_slug, str(limit))

        async def loader():
            envelope = await self.get_series_news(slug=series_slug, limit=limit)
            items = envelope.data or []
            latest = items[0] if items else None
            summary = SeriesNewsSummaryData(
                slug=series_slug,
                total_items=len(items),
                latest=latest,
                categories=sorted({item.get('category') for item in items if item.get('category')}),
                source_url=envelope.source_url or f'{self.base_url}/index.php/serie/news/{series_slug}',
            )
            return summary.model_dump(), summary.source_url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_news_series_seconds,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings)

    async def get_volume(self, *, series_slug: str | None = None, volume_slug: str | None = None, url: str | None = None) -> Envelope:
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
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings)

    async def select_volume_fields(
        self,
        *,
        series_slug: str | None = None,
        volume_slug: str | None = None,
        url: str | None = None,
        fields: str | None = None,
    ) -> Envelope:
        target_url = self._resolve_volume_url(series_slug=series_slug, volume_slug=volume_slug, url=url)
        selected_fields = parse_fields_param(fields)
        if not selected_fields:
            raise ParseError('fields is required for the volume projection endpoint.')
        cache_key = make_cache_key('volume-select', target_url, *selected_fields)

        async def loader():
            envelope = await self.get_volume(url=target_url)
            data = envelope.data or {}
            return project_dict_fields(data, selected_fields), target_url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_volume_seconds,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings, found=bool(payload.get('data')))

    async def get_volume_summary(self, *, series_slug: str | None = None, volume_slug: str | None = None, url: str | None = None) -> Envelope:
        target_url = self._resolve_volume_url(series_slug=series_slug, volume_slug=volume_slug, url=url)
        cache_key = make_cache_key('volume-summary', target_url)

        async def loader():
            envelope = await self.get_volume(url=target_url)
            data = envelope.data or {}
            resolved_series_slug, resolved_volume_slug = self._volume_slugs_from_url(target_url)
            summary = MachineVolumeSummaryData(
                series_slug=resolved_series_slug,
                volume_slug=resolved_volume_slug,
                title=data.get('title', ''),
                series_title=data.get('series_title'),
                publication_date=data.get('publication_date'),
                isbn_ean=data.get('isbn_ean'),
                publisher_fr=data.get('publisher_fr'),
                editorial_score=data.get('editorial_score'),
                reader_score=data.get('reader_score'),
                source_url=data.get('source_url') or target_url,
            )
            return summary.model_dump(), target_url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_volume_seconds,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings)

    async def compare_series(
        self,
        *,
        left_slug: str | None = None,
        right_slug: str | None = None,
        left_url: str | None = None,
        right_url: str | None = None,
    ) -> Envelope:
        left_target = self._resolve_series_url(slug=left_slug, url=left_url)
        right_target = self._resolve_series_url(slug=right_slug, url=right_url)
        cache_key = make_cache_key('compare-series', left_target, right_target)

        async def loader():
            left = await self.get_series(url=left_target)
            right = await self.get_series(url=right_target)
            comparison = self._build_comparison(
                kind='series',
                left_data=left.data or {},
                right_data=right.data or {},
                left_source_url=left.source_url,
                right_source_url=right.source_url,
                fields=SERIES_COMPARISON_FIELDS,
            )
            return comparison.model_dump(), left_target

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_series_seconds,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings)

    async def compare_volume(
        self,
        *,
        left_series_slug: str | None = None,
        left_volume_slug: str | None = None,
        right_series_slug: str | None = None,
        right_volume_slug: str | None = None,
        left_url: str | None = None,
        right_url: str | None = None,
    ) -> Envelope:
        left_target = self._resolve_volume_url(series_slug=left_series_slug, volume_slug=left_volume_slug, url=left_url)
        right_target = self._resolve_volume_url(series_slug=right_series_slug, volume_slug=right_volume_slug, url=right_url)
        cache_key = make_cache_key('compare-volume', left_target, right_target)

        async def loader():
            left = await self.get_volume(url=left_target)
            right = await self.get_volume(url=right_target)
            comparison = self._build_comparison(
                kind='volume',
                left_data=left.data or {},
                right_data=right.data or {},
                left_source_url=left.source_url,
                right_source_url=right.source_url,
                fields=VOLUME_COMPARISON_FIELDS,
            )
            return comparison.model_dump(), left_target

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_volume_seconds,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings)

    async def get_global_news(self, *, limit: int) -> Envelope:
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
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings)

    async def get_series_news(self, *, slug: str, limit: int) -> Envelope:
        target_url = f'{self.base_url}/index.php/serie/news/{slug}'
        return await self._get_news_page(target_url=target_url, cache_namespace='news-series', ttl=self.settings.cache_ttl_news_series_seconds, limit=limit)

    async def get_volume_news(self, *, series_slug: str | None = None, volume_slug: str | None = None, url: str | None = None, limit: int) -> Envelope:
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
    ) -> Envelope:
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
            items = [
                item for item in items
                if normalized_publisher in normalize_text(item.get('publisher'))
            ]

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
        data = {
            'section': planning.get('section') or section,
            'year': planning.get('year') or year,
            'month': planning.get('month') or month,
            'page': planning.get('page') or page,
            'filters': {
                'publisher': publisher,
                'query': query,
                'date_from': date_from,
                'date_to': date_to,
            },
            'sort': sort,
            'total_items': total_items,
            'items': items,
        }

        return Envelope(
            ok=True,
            found=bool(items),
            source='manga_news',
            source_url=payload.get('source_url'),
            cached=cached,
            fetched_at=entry.fetched_at.isoformat(),
            cache_expires_at=entry.expires_at.isoformat(),
            partial=partial,
            warnings=warnings,
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

    async def _get_news_page(self, *, target_url: str, cache_namespace: str, ttl: int, limit: int) -> Envelope:
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
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings, found=bool(payload.get('data')))

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

    def _series_slug_from_url(self, url: str) -> str:
        parsed_path = [part for part in urlparse(url).path.split('/') if part]
        if parsed_path:
            return parsed_path[-1]
        raise ParseError('Unable to infer the series slug from the URL.')

    def _volume_slugs_from_url(self, url: str) -> tuple[str | None, str | None]:
        parsed_path = [part for part in urlparse(url).path.split('/') if part]
        if len(parsed_path) >= 4 and parsed_path[-3] == 'manga':
            return parsed_path[-2], parsed_path[-1]
        return None, None

    def _build_comparison(
        self,
        *,
        kind: Literal['series', 'volume'],
        left_data: dict,
        right_data: dict,
        left_source_url: str | None,
        right_source_url: str | None,
        fields: list[str],
    ) -> ComparisonData:
        left_projection = project_dict_fields(left_data, fields)
        right_projection = project_dict_fields(right_data, fields)
        left_flat = flatten_for_compare(left_projection)
        right_flat = flatten_for_compare(right_projection)
        compared_fields = sorted(set(left_flat) | set(right_flat))
        equal_fields: list[str] = []
        differing_fields: list[ComparisonDiff] = []
        for field in compared_fields:
            left_value = left_flat.get(field)
            right_value = right_flat.get(field)
            if left_value == right_value:
                equal_fields.append(field)
            else:
                differing_fields.append(ComparisonDiff(field=field, left=left_value, right=right_value))
        total = len(compared_fields)
        similarity_score = int((len(equal_fields) / total) * 100) if total else 100
        return ComparisonData(
            kind=kind,
            left_source_url=left_source_url,
            right_source_url=right_source_url,
            compared_fields_count=total,
            equal_fields=equal_fields,
            differing_fields=differing_fields,
            similarity_score=similarity_score,
        )
