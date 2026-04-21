from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode, urlparse

import feedparser

from app.cache import SQLiteCache
from app.config import Settings
from app.exceptions import ParseError, ResourceNotFound
from app.http import AsyncFetcher
from app.models import (
    Envelope,
    NewsItem,
    RelatedLinks,
    ResolveData,
    ResolveResult,
    SearchResult,
    SeriesEditionsBlock,
    SeriesEditionsData,
    SeriesRelatedData,
)
from app.manga_news.parsers import (
    parse_news_page,
    parse_planning_page,
    parse_search_page,
    parse_series_editions_page,
    parse_series_page,
    parse_volume_page,
)
from app.utils import clean_ws, fingerprint_data, is_manga_news_url, make_cache_key, normalize_text, now_utc, parse_french_date, score_match

logger = logging.getLogger(__name__)

SERIES_BLOCKS = {
    'identity': ['title', 'title_vo', 'translated_title', 'source_url'],
    'staff': ['authors_story', 'authors_art', 'translators'],
    'publishing': ['publisher_fr', 'publisher_vo', 'collection', 'type', 'genres', 'prepublication', 'origin', 'advisory_age'],
    'presentation': ['summary', 'illustration', 'illustration_details', 'cover_image', 'themes', 'strengths'],
    'editions': ['vf', 'vo', 'last_release_date', 'next_release_date'],
    'stats': ['stats'],
    'related': ['related'],
    'raw': ['raw_sections'],
    'raw_sections': ['raw_sections'],
}
VOLUME_BLOCKS = {
    'identity': ['title', 'series_title', 'number', 'number_int', 'edition_label', 'is_special', 'is_one_shot', 'title_vo', 'translated_title', 'source_url'],
    'staff': ['authors_story', 'authors_art', 'translators'],
    'publishing': ['publisher_fr', 'publisher_vo', 'collection', 'type', 'genres', 'prepublication', 'origin', 'advisory_age'],
    'presentation': ['summary', 'illustration', 'illustration_details', 'cover_image'],
    'release': ['publication_date', 'isbn_ean', 'price_code'],
    'scores': ['editorial_score', 'reader_score'],
    'related': ['related'],
    'raw': ['raw_sections'],
    'raw_sections': ['raw_sections'],
}

CACHE_KEY_SCHEMA_VERSION = '2026-04-21-vf-vo-counters-v2'


def _make_cache_key(*parts: str) -> str:
    return make_cache_key(CACHE_KEY_SCHEMA_VERSION, *parts)


def _split_csv_param(value: str | None) -> list[str]:
    if not value:
        return []
    parts: list[str] = []
    for raw in value.split(','):
        cleaned = clean_ws(raw)
        if cleaned:
            parts.append(cleaned)
    return parts



def _has_path(data: dict[str, Any], path: str) -> bool:
    current: Any = data
    for part in path.split('.'):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True



def _get_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split('.'):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current



def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    current = target
    parts = path.split('.')
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = deepcopy(value)



def project_resource_payload(
    payload: dict[str, Any],
    *,
    resource: Literal['series', 'volume'],
    blocks: list[str] | None = None,
    fields: list[str] | None = None,
    include_raw_sections: bool = False,
) -> dict[str, Any]:
    full_data = deepcopy(payload)
    if not include_raw_sections:
        full_data.pop('raw_sections', None)

    blocks = blocks or []
    fields = fields or []
    if not blocks and not fields and not include_raw_sections:
        return full_data

    if 'all' in [normalize_text(block) for block in blocks]:
        return payload if include_raw_sections else full_data

    mapping = SERIES_BLOCKS if resource == 'series' else VOLUME_BLOCKS
    selected_paths: list[str] = []
    for block in blocks:
        normalized = slugify_block_name(block)
        if normalized not in mapping:
            raise ParseError(f'Unknown {resource} block: {block}')
        selected_paths.extend(mapping[normalized])
    selected_paths.extend(fields)
    if include_raw_sections and 'raw_sections' not in selected_paths:
        selected_paths.append('raw_sections')

    if not selected_paths:
        return payload if include_raw_sections else full_data

    projected: dict[str, Any] = {}
    source_data = payload if include_raw_sections else full_data
    for path in selected_paths:
        if not _has_path(source_data, path):
            raise ParseError(f'Unknown {resource} field path: {path}')
        _set_path(projected, path, _get_path(source_data, path))
    return projected



def slugify_block_name(block: str) -> str:
    return normalize_text(block).replace(' ', '_').replace('-', '_')


class MangaNewsService:
    def __init__(self, settings: Settings, fetcher: AsyncFetcher, cache: SQLiteCache):
        self.settings = settings
        self.fetcher = fetcher
        self.cache = cache
        self.base_url = settings.manga_news_base_url.rstrip('/')

    def _negative_cache_exception(self, entry):
        if entry.error_code == ResourceNotFound.code:
            return ResourceNotFound(entry.detail)
        return ParseError(entry.detail, debug_dump_path=entry.debug_dump_path)

    def _dump_debug_html(self, *, html: str, source_url: str, cache_key: str, resource_kind: str, error: ParseError) -> str | None:
        if not getattr(self.settings, 'debug_capture_html_on_error', False):
            return None
        dump_dir = Path(getattr(self.settings, 'debug_html_dump_dir', Path('/tmp/manga-news-debug-html')))
        dump_dir.mkdir(parents=True, exist_ok=True)
        stamp = now_utc().strftime('%Y%m%dT%H%M%S%fZ')
        prefix = f'{resource_kind}-{cache_key[:12]}-{stamp}'
        html_path = dump_dir / f'{prefix}.html'
        meta_path = dump_dir / f'{prefix}.json'
        html_path.write_text(html, encoding='utf-8')
        meta_payload = {
            'resource_kind': resource_kind,
            'source_url': source_url,
            'cache_key': cache_key,
            'error_code': error.code,
            'detail': error.detail,
            'saved_at': now_utc().isoformat(),
        }
        meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return str(html_path)

    def _with_debug_dump(self, *, error: ParseError, html: str, source_url: str, cache_key: str, resource_kind: str) -> ParseError:
        dump_path = self._dump_debug_html(
            html=html,
            source_url=source_url,
            cache_key=cache_key,
            resource_kind=resource_kind,
            error=error,
        )
        if not dump_path:
            return error
        detail = error.detail
        if 'Debug HTML saved to' not in detail:
            detail = f'{detail} Debug HTML saved to {dump_path}'
        return ParseError(detail, debug_dump_path=dump_path)

    async def _cached_payload(self, *, cache_key: str, ttl_seconds: int, loader, namespace: str | None = None, resource_url: str | None = None):
        entry = self.cache.get(cache_key)
        if entry and entry.is_fresh:
            repaired_payload = self._repair_cached_payload(entry.payload)
            if repaired_payload is not entry.payload:
                entry = self.cache.set(
                    cache_key=cache_key,
                    payload=repaired_payload,
                    ttl_seconds=ttl_seconds,
                    stale_grace_seconds=self.settings.cache_stale_grace_seconds,
                    namespace=namespace,
                    resource_url=repaired_payload.get('source_url') or resource_url,
                )
            return repaired_payload, entry, True, False, []

        if getattr(self.settings, 'negative_cache_enabled', True):
            negative_entry = self.cache.get_negative(cache_key)
            if negative_entry and negative_entry.is_fresh:
                raise self._negative_cache_exception(negative_entry)

        try:
            payload, source_url = await loader()
            self.cache.clear_negative(cache_key)
            cached_entry = self.cache.set(
                cache_key=cache_key,
                payload={'data': payload, 'source_url': source_url},
                ttl_seconds=ttl_seconds,
                stale_grace_seconds=self.settings.cache_stale_grace_seconds,
                namespace=namespace,
                resource_url=source_url or resource_url,
            )
            return cached_entry.payload, cached_entry, False, False, []
        except (ParseError, ResourceNotFound) as exc:
            if getattr(self.settings, 'negative_cache_enabled', True):
                self.cache.set_negative(
                    cache_key=cache_key,
                    error_code=exc.code,
                    detail=str(exc),
                    ttl_seconds=getattr(self.settings, 'negative_cache_ttl_seconds', 120),
                    namespace=namespace,
                    resource_url=getattr(exc, 'resource_url', None) or resource_url,
                    debug_dump_path=getattr(exc, 'debug_dump_path', None),
                )
            if entry and entry.is_stale_usable:
                warning = f'Using stale cached data because the upstream fetch failed: {exc}'
                logger.warning(warning)
                return entry.payload, entry, True, True, [warning]
            raise
        except Exception as exc:
            if entry and entry.is_stale_usable:
                warning = f'Using stale cached data because the upstream fetch failed: {exc}'
                logger.warning(warning)
                return entry.payload, entry, True, True, [warning]
            raise

    def _repair_cached_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get('data')
        if not isinstance(data, dict):
            return payload

        repaired = deepcopy(payload)
        repaired_data = repaired.get('data') or {}
        changed = False
        for field in ('vf', 'vo'):
            if field not in repaired_data:
                repaired_data[field] = None
                changed = True
        return repaired if changed else payload


    def _envelope(self, payload: dict, entry, *, cached: bool, partial: bool, warnings: list[str], found: bool | None = None) -> Envelope:
        data = payload.get('data')
        if found is None:
            found = data not in (None, [], {})
        return Envelope(
            schema_version='1.0',
            ok=True,
            found=found,
            source='manga_news',
            source_url=payload.get('source_url'),
            cached=cached,
            fetched_at=entry.fetched_at.isoformat() if entry else now_utc().isoformat(),
            cache_expires_at=entry.expires_at.isoformat() if entry else None,
            partial=partial,
            warnings=warnings,
            fingerprint=fingerprint_data(data),
            data=data,
        )

    async def _enrich_search_results(self, results: list[Any]) -> list[SearchResult]:
        enriched: list[SearchResult] = []
        for item in results:
            payload = item.model_dump() if hasattr(item, 'model_dump') else dict(item)
            try:
                if payload.get('kind') == 'series' and payload.get('slug'):
                    series_payload, *_ = await self._get_series_payload(slug=payload['slug'])
                    data = series_payload.get('data', {}) or {}
                    payload['title_vo'] = data.get('title_vo')
                    payload['translated_title'] = data.get('translated_title')
                elif payload.get('kind') == 'volume' and payload.get('series_slug') and payload.get('volume_slug'):
                    volume_payload, *_ = await self._get_volume_payload(series_slug=payload['series_slug'], volume_slug=payload['volume_slug'])
                    data = volume_payload.get('data', {}) or {}
                    payload['title_vo'] = data.get('title_vo')
                    payload['translated_title'] = data.get('translated_title')
            except Exception as exc:  # pragma: no cover - best-effort enrichment
                logger.debug('Search result title enrichment failed for %s: %s', payload.get('url'), exc)
            enriched.append(SearchResult.model_validate(payload))
        return enriched

    async def resolve_search(self, query: str, kind: Literal['series', 'volume', 'all'], limit: int) -> Envelope:
        search_response = await self.search(query=query, kind=kind, mode='all', limit=limit)
        candidates = [ResolveResult.model_validate(item) for item in (search_response.data or [])]
        best = candidates[0] if candidates else None
        if not best:
            confidence = 'none'
        elif best.score >= 90:
            confidence = 'high'
        elif best.score >= max(75, self.settings.search_score_threshold):
            confidence = 'medium'
        else:
            confidence = 'low'
        data = ResolveData(
            query=query,
            kind_requested=kind,
            confidence=confidence,
            best=best,
            candidates=candidates,
        )
        return Envelope(
            schema_version='1.0',
            ok=True,
            found=best is not None,
            source='manga_news',
            source_url=search_response.source_url,
            cached=search_response.cached,
            fetched_at=search_response.fetched_at,
            cache_expires_at=search_response.cache_expires_at,
            partial=search_response.partial,
            warnings=search_response.warnings,
            fingerprint=fingerprint_data(data.model_dump()),
            data=data.model_dump(),
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
        cache_key = _make_cache_key('search', query, kind, mode, str(limit), *search_urls)

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
            deduped: dict[str, object] = {}
            for item in aggregated:
                existing = deduped.get(item.url)
                if existing is None or item.score > existing.score:
                    deduped[item.url] = item
            results = sorted(deduped.values(), key=lambda item: item.score, reverse=True)
            if mode == 'best' and results:
                results = [results[0]]
            results = results[:limit]
            enriched = await self._enrich_search_results(results)
            return [item.model_dump() for item in enriched], search_urls[0] if search_urls else self.base_url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_search_seconds,
            loader=loader,
        )
        found = bool(payload.get('data'))
        return Envelope(
            schema_version='1.0',
            ok=True,
            found=found,
            source='manga_news',
            source_url=payload.get('source_url'),
            cached=cached,
            fetched_at=entry.fetched_at.isoformat(),
            cache_expires_at=entry.expires_at.isoformat(),
            partial=partial,
            warnings=warnings,
            fingerprint=fingerprint_data(payload.get('data', [])),
            data=payload.get('data', []),
        )

    async def _get_series_payload(self, *, slug: str | None = None, url: str | None = None):
        target_url = self._resolve_series_url(slug=slug, url=url)
        cache_key = _make_cache_key('series', target_url)

        async def loader():
            result = await self.fetcher.get_text(target_url)
            try:
                parsed = parse_series_page(result.text, result.url)
            except ParseError as exc:
                raise self._with_debug_dump(
                    error=exc,
                    html=result.text,
                    source_url=result.url,
                    cache_key=cache_key,
                    resource_kind='series',
                ) from exc
            return parsed.model_dump(), result.url

        return await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_series_seconds,
            loader=loader,
            namespace='series',
            resource_url=target_url,
        )

    async def _get_volume_payload(self, *, series_slug: str | None = None, volume_slug: str | None = None, url: str | None = None):
        target_url = self._resolve_volume_url(series_slug=series_slug, volume_slug=volume_slug, url=url)
        cache_key = _make_cache_key('volume', target_url)

        async def loader():
            result = await self.fetcher.get_text(target_url)
            try:
                parsed = parse_volume_page(result.text, result.url)
            except ParseError as exc:
                raise self._with_debug_dump(
                    error=exc,
                    html=result.text,
                    source_url=result.url,
                    cache_key=cache_key,
                    resource_kind='volume',
                ) from exc
            return parsed.model_dump(), result.url

        return await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_volume_seconds,
            loader=loader,
            namespace='volume',
            resource_url=target_url,
        )

    async def get_series(
        self,
        *,
        slug: str | None = None,
        url: str | None = None,
        blocks: str | None = None,
        fields: str | None = None,
        include_raw_sections: bool = False,
    ) -> Envelope:
        payload, entry, cached, partial, warnings = await self._get_series_payload(slug=slug, url=url)
        projected = project_resource_payload(
            payload.get('data', {}) or {},
            resource='series',
            blocks=_split_csv_param(blocks),
            fields=_split_csv_param(fields),
            include_raw_sections=include_raw_sections,
        )
        return self._envelope({'data': projected, 'source_url': payload.get('source_url')}, entry, cached=cached, partial=partial, warnings=warnings)

    async def get_volume(
        self,
        *,
        series_slug: str | None = None,
        volume_slug: str | None = None,
        url: str | None = None,
        blocks: str | None = None,
        fields: str | None = None,
        include_raw_sections: bool = False,
    ) -> Envelope:
        payload, entry, cached, partial, warnings = await self._get_volume_payload(series_slug=series_slug, volume_slug=volume_slug, url=url)
        projected = project_resource_payload(
            payload.get('data', {}) or {},
            resource='volume',
            blocks=_split_csv_param(blocks),
            fields=_split_csv_param(fields),
            include_raw_sections=include_raw_sections,
        )
        return self._envelope({'data': projected, 'source_url': payload.get('source_url')}, entry, cached=cached, partial=partial, warnings=warnings)

    async def get_series_related(self, *, slug: str | None = None, url: str | None = None) -> Envelope:
        payload, entry, cached, partial, warnings = await self._get_series_payload(slug=slug, url=url)
        data = payload.get('data', {}) or {}
        related_data = SeriesRelatedData(
            title=data.get('title'),
            related=RelatedLinks.model_validate(data.get('related') or {}),
            source_url=payload.get('source_url'),
        )
        return self._envelope({'data': related_data.model_dump(), 'source_url': payload.get('source_url')}, entry, cached=cached, partial=partial, warnings=warnings)

    async def get_series_editions(self, *, slug: str | None = None, url: str | None = None, edition: Literal['all', 'vf', 'vo'] = 'all') -> Envelope:
        target_url = self._resolve_series_url(slug=slug, url=url)
        target_slug = self._extract_series_slug(target_url)
        cache_key = _make_cache_key('series-editions', target_url, edition)

        async def loader():
            series_result = await self.fetcher.get_text(target_url)
            series_payload = parse_series_page(series_result.text, series_result.url)
            data = SeriesEditionsData(title=series_payload.title, series_slug=target_slug, source_url=series_result.url)
            editions_to_fetch = ['vf', 'vo'] if edition == 'all' else [edition]
            for current in editions_to_fetch:
                current_url = f'{self.base_url}/index.php/serie/{"editionsVo" if current == "vo" else "editions"}/{target_slug}'
                try:
                    result = await self.fetcher.get_text(current_url)
                    parsed = parse_series_editions_page(result.text, result.url, self.base_url, current)
                except ResourceNotFound:
                    parsed = SeriesEditionsBlock(edition=current, source_url=current_url, total=0, items=[])
                if current == 'vf':
                    data.vf = parsed
                else:
                    data.vo = parsed
            return data.model_dump(), series_result.url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_series_seconds,
            loader=loader,
            namespace='series-editions',
            resource_url=target_url,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings)

    async def get_global_news(self, *, limit: int) -> Envelope:
        rss_url = f'{self.base_url}/index.php/feed/news'
        cache_key = _make_cache_key('news-global', rss_url, str(limit))

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
            namespace='news-global',
            resource_url=rss_url,
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
        cache_key = _make_cache_key('planning', target_url)

        async def loader():
            result = await self.fetcher.get_text(target_url)
            parsed = parse_planning_page(result.text, result.url, self.base_url)
            parsed.page = page
            return parsed.model_dump(), result.url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_planning_seconds,
            loader=loader,
            namespace='planning',
            resource_url=target_url,
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
            schema_version='1.0',
            ok=True,
            found=bool(items),
            source='manga_news',
            source_url=payload.get('source_url'),
            cached=cached,
            fetched_at=entry.fetched_at.isoformat(),
            cache_expires_at=entry.expires_at.isoformat(),
            partial=partial,
            warnings=warnings,
            fingerprint=fingerprint_data(data),
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
        cache_key = _make_cache_key(cache_namespace, target_url, str(limit))

        async def loader():
            result = await self.fetcher.get_text(target_url)
            parsed = parse_news_page(result.text, result.url, self.base_url, limit=limit)
            return [item.model_dump() for item in parsed], result.url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=ttl,
            loader=loader,
            namespace=cache_namespace,
            resource_url=target_url,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings)

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

    def _extract_series_slug(self, series_url: str) -> str:
        path_parts = [part for part in urlparse(series_url).path.split('/') if part]
        if not path_parts:
            raise ParseError('Unable to infer the series slug from the provided URL.')
        return path_parts[-1]
