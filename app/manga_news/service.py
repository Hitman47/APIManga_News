from __future__ import annotations

import asyncio
import json
import logging
import time
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
    parse_series_search_meta_page,
    parse_volume_page,
)
from app.utils import clean_ws, fingerprint_data, is_manga_news_url, make_cache_key, normalize_text, now_utc, parse_french_date, score_match

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = '2026-04-22-search-meta-rawhtml-1'

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
    'editions': ['vf', 'vo'],
    'release': ['publication_date', 'isbn_ean', 'price_code'],
    'scores': ['editorial_score', 'reader_score'],
    'related': ['related'],
    'raw': ['raw_sections'],
    'raw_sections': ['raw_sections'],
}


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


def versioned_cache_key(*parts: str) -> str:
    return make_cache_key(CACHE_SCHEMA_VERSION, *parts)


class MangaNewsService:
    def __init__(self, settings: Settings, fetcher: AsyncFetcher, cache: SQLiteCache):
        self.settings = settings
        self.fetcher = fetcher
        self.cache = cache
        self.base_url = settings.manga_news_base_url.rstrip('/')
        self._search_fetch_concurrency = max(1, int(getattr(settings, 'search_fetch_concurrency', 4)))
        self._search_enrich_concurrency = max(1, int(getattr(settings, 'search_enrich_concurrency', 4)))
        self._search_default_enrich = bool(getattr(settings, 'search_default_enrich', False))
        self._search_default_include_editions = bool(getattr(settings, 'search_default_include_editions', True))
        self._volume_default_include_parent_editions = bool(getattr(settings, 'volume_default_include_parent_editions', False))
        self._inflight_lock = asyncio.Lock()
        self._inflight_loads: dict[str, asyncio.Future] = {}

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

    def _is_compatible_cache_payload(self, payload: dict[str, Any]) -> bool:
        return payload.get('_schema_version') == CACHE_SCHEMA_VERSION

    async def _cached_payload(self, *, cache_key: str, ttl_seconds: int, loader, namespace: str | None = None, resource_url: str | None = None):
        entry = self.cache.get(cache_key)
        if entry and not self._is_compatible_cache_payload(entry.payload):
            entry = None
        if entry and entry.is_fresh:
            return entry.payload, entry, True, False, []

        if getattr(self.settings, 'negative_cache_enabled', True):
            negative_entry = self.cache.get_negative(cache_key)
            if negative_entry and negative_entry.is_fresh:
                raise self._negative_cache_exception(negative_entry)

        leader = False
        async with self._inflight_lock:
            in_flight = self._inflight_loads.get(cache_key)
            if in_flight is None:
                in_flight = asyncio.get_running_loop().create_future()
                self._inflight_loads[cache_key] = in_flight
                leader = True

        if not leader:
            return await in_flight

        try:
            try:
                payload, source_url = await loader()
                self.cache.clear_negative(cache_key)
                cached_entry = self.cache.set(
                    cache_key=cache_key,
                    payload={'_schema_version': CACHE_SCHEMA_VERSION, 'data': payload, 'source_url': source_url},
                    ttl_seconds=ttl_seconds,
                    stale_grace_seconds=self.settings.cache_stale_grace_seconds,
                    namespace=namespace,
                    resource_url=source_url or resource_url,
                )
                result = (cached_entry.payload, cached_entry, False, False, [])
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
                    result = (entry.payload, entry, True, True, [warning])
                else:
                    raise
            except Exception as exc:
                if entry and entry.is_stale_usable:
                    warning = f'Using stale cached data because the upstream fetch failed: {exc}'
                    logger.warning(warning)
                    result = (entry.payload, entry, True, True, [warning])
                else:
                    raise
            in_flight.set_result(result)
            return result
        except Exception as exc:
            in_flight.set_exception(exc)
            raise
        finally:
            async with self._inflight_lock:
                current = self._inflight_loads.get(cache_key)
                if current is in_flight:
                    self._inflight_loads.pop(cache_key, None)

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


    async def _run_with_limit(self, items: list[Any], worker, *, concurrency: int) -> list[Any]:
        if not items:
            return []
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _runner(item: Any):
            async with semaphore:
                return await worker(item)

        return await asyncio.gather(*[_runner(item) for item in items])

    def _projection_requests_parent_editions(self, *, blocks: str | None, fields: str | None) -> bool:
        requested_blocks = {slugify_block_name(block) for block in _split_csv_param(blocks)}
        if 'editions' in requested_blocks:
            return True
        for path in _split_csv_param(fields):
            if path == 'vf' or path == 'vo' or path.startswith('vf.') or path.startswith('vo.'):
                return True
        return False

    def _log_perf(self, event: str, **fields: Any) -> None:
        logger.info('%s %s', event, ' '.join(f'{key}={value!r}' for key, value in sorted(fields.items())))

    def _build_search_urls(self, *, query: str, kind: Literal['series', 'volume', 'all']) -> list[str]:
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
        return search_urls

    async def _get_search_candidates_payload(self, *, query: str, kind: Literal['series', 'volume', 'all']):
        search_urls = self._build_search_urls(query=query, kind=kind)
        raw_limit = max(1, int(self.settings.max_limit))
        cache_key = versioned_cache_key(
            'search-source',
            query,
            kind,
            str(raw_limit),
            str(self.settings.search_score_threshold),
            *search_urls,
        )

        async def loader():
            started = time.perf_counter()

            async def _fetch_search_page(url: str):
                result = await self.fetcher.get_text(url)
                parsed = parse_search_page(
                    html=result.text,
                    page_url=result.url,
                    base_url=self.base_url,
                    query=query,
                    kind=kind,
                    score_threshold=self.settings.search_score_threshold,
                    limit=raw_limit,
                )
                return result.url, parsed

            fetched_pages = await self._run_with_limit(
                search_urls,
                _fetch_search_page,
                concurrency=self._search_fetch_concurrency,
            )
            aggregated = [item for _, parsed in fetched_pages for item in parsed]
            deduped: dict[str, object] = {}
            for item in aggregated:
                existing = deduped.get(item.url)
                if existing is None or item.score > existing.score:
                    deduped[item.url] = item
            results = sorted(deduped.values(), key=lambda item: item.score, reverse=True)[:raw_limit]
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            self._log_perf(
                'search_source_perf',
                query=query,
                kind=kind,
                search_pages=len(search_urls),
                aggregated_hits=len(aggregated),
                deduped_hits=len(deduped),
                cached_candidates=len(results),
                duration_ms=duration_ms,
            )
            return [item.model_dump() for item in results], search_urls[0] if search_urls else self.base_url

        return await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_search_seconds,
            loader=loader,
            namespace='search-source',
            resource_url=search_urls[0] if search_urls else self.base_url,
        )

    async def _fetch_search_series_data_map(self, base_payloads: list[dict[str, Any]], *, include_volume_parents: bool) -> tuple[dict[str, dict[str, Any]], int]:
        unique_series_slugs = sorted({
            payload.get('slug') for payload in base_payloads
            if payload.get('kind') == 'series' and payload.get('slug')
        } | ({
            payload.get('series_slug') for payload in base_payloads
            if payload.get('kind') == 'volume' and payload.get('series_slug')
        } if include_volume_parents else set()))

        async def _fetch_series(slug: str):
            try:
                payload, *_ = await self._get_series_search_meta_payload(slug=slug)
                return slug, payload.get('data', {}) or {}
            except Exception as exc:  # pragma: no cover - best-effort enrichment
                logger.debug('Search series enrichment failed for %s: %s', slug, exc)
                return slug, {}

        series_data_map = {
            slug: data
            for slug, data in await self._run_with_limit(
                unique_series_slugs,
                _fetch_series,
                concurrency=self._search_enrich_concurrency,
            )
        }
        return series_data_map, len(unique_series_slugs)

    async def _attach_search_edition_counters(self, results: list[Any]) -> tuple[list[SearchResult], dict[str, int]]:
        perf = {
            'input_results': len(results),
            'unique_series_fetches': 0,
            'unique_volume_fetches': 0,
        }
        if not results:
            return [], perf

        base_payloads = [item.model_dump() if hasattr(item, 'model_dump') else dict(item) for item in results]
        series_data_map, perf['unique_series_fetches'] = await self._fetch_search_series_data_map(
            base_payloads,
            include_volume_parents=True,
        )

        enriched: list[SearchResult] = []
        for payload in base_payloads:
            current = deepcopy(payload)
            series_key = current.get('slug') if current.get('kind') == 'series' else current.get('series_slug')
            if series_key:
                series_data = series_data_map.get(series_key, {})
                current['vf'] = series_data.get('vf')
                current['vo'] = series_data.get('vo')
            enriched.append(SearchResult.model_validate(current))
        return enriched, perf

    async def _enrich_search_results(self, results: list[Any], *, include_editions: bool) -> tuple[list[SearchResult], dict[str, int]]:
        perf = {
            'input_results': len(results),
            'unique_series_fetches': 0,
            'unique_volume_fetches': 0,
        }
        if not results:
            return [], perf

        base_payloads = [item.model_dump() if hasattr(item, 'model_dump') else dict(item) for item in results]
        series_data_map, perf['unique_series_fetches'] = await self._fetch_search_series_data_map(
            base_payloads,
            include_volume_parents=include_editions,
        )

        unique_volume_keys = sorted({
            (payload.get('series_slug'), payload.get('volume_slug'))
            for payload in base_payloads
            if payload.get('kind') == 'volume' and payload.get('series_slug') and payload.get('volume_slug')
        })
        perf['unique_volume_fetches'] = len(unique_volume_keys)

        async def _fetch_volume(key: tuple[str, str]):
            series_slug, volume_slug = key
            try:
                payload, *_ = await self._get_volume_payload(series_slug=series_slug, volume_slug=volume_slug)
                return key, payload.get('data', {}) or {}
            except Exception as exc:  # pragma: no cover - best-effort enrichment
                logger.debug('Search volume enrichment failed for %s/%s: %s', series_slug, volume_slug, exc)
                return key, {}

        volume_data_map = {
            key: data
            for key, data in await self._run_with_limit(
                unique_volume_keys,
                _fetch_volume,
                concurrency=self._search_enrich_concurrency,
            )
        }

        enriched: list[SearchResult] = []
        for payload in base_payloads:
            current = deepcopy(payload)
            if current.get('kind') == 'series' and current.get('slug'):
                series_data = series_data_map.get(current['slug'], {})
                current['title_vo'] = series_data.get('title_vo')
                current['translated_title'] = series_data.get('translated_title')
                if include_editions:
                    current['vf'] = series_data.get('vf')
                    current['vo'] = series_data.get('vo')
            elif current.get('kind') == 'volume' and current.get('series_slug') and current.get('volume_slug'):
                key = (current['series_slug'], current['volume_slug'])
                volume_data = volume_data_map.get(key, {})
                current['title_vo'] = volume_data.get('title_vo')
                current['translated_title'] = volume_data.get('translated_title')
                current['number'] = volume_data.get('number')
                current['number_int'] = volume_data.get('number_int')
                current['edition_label'] = volume_data.get('edition_label')
                current['is_special'] = volume_data.get('is_special')
                current['is_one_shot'] = volume_data.get('is_one_shot')
                if include_editions:
                    series_data = series_data_map.get(current['series_slug'], {})
                    current['vf'] = series_data.get('vf')
                    current['vo'] = series_data.get('vo')
            enriched.append(SearchResult.model_validate(current))
        return enriched, perf

    async def resolve_search(self, query: str, kind: Literal['series', 'volume', 'all'], limit: int, enrich: bool | None = None, include_editions: bool | None = None) -> Envelope:
        search_response = await self.search(query=query, kind=kind, mode='all', limit=limit, enrich=enrich, include_editions=include_editions)
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

    async def search(self, query: str, kind: Literal['series', 'volume', 'all'], mode: Literal['best', 'all'], limit: int, enrich: bool | None = None, include_editions: bool | None = None) -> Envelope:
        query = clean_ws(query)
        if not query:
            raise ParseError('The search query cannot be empty.')
        enrich = self._search_default_enrich if enrich is None else enrich
        include_editions = self._search_default_include_editions if include_editions is None else include_editions
        search_urls = self._build_search_urls(query=query, kind=kind)
        cache_key = versioned_cache_key(
            'search',
            query,
            kind,
            mode,
            str(limit),
            str(bool(enrich)),
            str(bool(include_editions)),
            str(self.settings.max_limit),
            str(self.settings.search_score_threshold),
        )

        async def loader():
            started = time.perf_counter()
            source_payload, *_ = await self._get_search_candidates_payload(query=query, kind=kind)
            source_results = [
                SearchResult.model_validate(item)
                for item in (source_payload.get('data', []) or [])
            ]
            results: list[SearchResult] = source_results
            if mode == 'best' and results:
                results = [results[0]]
            results = results[:limit]
            enrichment_perf = {'input_results': len(results), 'unique_series_fetches': 0, 'unique_volume_fetches': 0}
            final_results: list[SearchResult]
            if enrich:
                final_results, enrichment_perf = await self._enrich_search_results(results, include_editions=include_editions)
            elif include_editions:
                final_results, enrichment_perf = await self._attach_search_edition_counters(results)
            else:
                final_results = [
                    SearchResult.model_validate(item.model_dump() if hasattr(item, 'model_dump') else dict(item))
                    for item in results
                ]
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            self._log_perf(
                'search_perf',
                query=query,
                kind=kind,
                mode=mode,
                enrich=enrich,
                include_editions=include_editions,
                source_candidates=len(source_results),
                returned_hits=len(final_results),
                unique_series_fetches=enrichment_perf['unique_series_fetches'],
                unique_volume_fetches=enrichment_perf['unique_volume_fetches'],
                duration_ms=duration_ms,
            )
            return [item.model_dump() for item in final_results], search_urls[0] if search_urls else self.base_url

        payload, entry, cached, partial, warnings = await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_search_seconds,
            loader=loader,
            namespace='search',
            resource_url=search_urls[0] if search_urls else self.base_url,
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
        cache_key = versioned_cache_key('series', target_url)

        async def loader():
            html_payload, *_ = await self._get_raw_html_payload(
                target_url=target_url,
                ttl_seconds=self.settings.cache_ttl_series_seconds,
                resource_kind='series',
            )
            html = html_payload.get('data', {}).get('html', '')
            source_url = html_payload.get('source_url') or target_url
            try:
                parsed = parse_series_page(html, source_url)
            except ParseError as exc:
                raise self._with_debug_dump(
                    error=exc,
                    html=html,
                    source_url=source_url,
                    cache_key=cache_key,
                    resource_kind='series',
                ) from exc
            return parsed.model_dump(), source_url

        return await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_series_seconds,
            loader=loader,
            namespace='series',
            resource_url=target_url,
        )

    async def _get_series_search_meta_payload(self, *, slug: str | None = None, url: str | None = None):
        target_url = self._resolve_series_url(slug=slug, url=url)
        cache_key = versioned_cache_key('series-search-meta', target_url)

        async def loader():
            html_payload, *_ = await self._get_raw_html_payload(
                target_url=target_url,
                ttl_seconds=self.settings.cache_ttl_series_seconds,
                resource_kind='series',
            )
            html = html_payload.get('data', {}).get('html', '')
            source_url = html_payload.get('source_url') or target_url
            try:
                parsed = parse_series_search_meta_page(html, source_url)
            except ParseError as exc:
                raise self._with_debug_dump(
                    error=exc,
                    html=html,
                    source_url=source_url,
                    cache_key=cache_key,
                    resource_kind='series-search-meta',
                ) from exc
            return parsed.model_dump(), source_url

        return await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_series_seconds,
            loader=loader,
            namespace='series-search-meta',
            resource_url=target_url,
        )

    async def _get_volume_payload(self, *, series_slug: str | None = None, volume_slug: str | None = None, url: str | None = None):
        target_url = self._resolve_volume_url(series_slug=series_slug, volume_slug=volume_slug, url=url)
        cache_key = versioned_cache_key('volume', target_url)

        async def loader():
            html_payload, *_ = await self._get_raw_html_payload(
                target_url=target_url,
                ttl_seconds=self.settings.cache_ttl_volume_seconds,
                resource_kind='volume',
            )
            html = html_payload.get('data', {}).get('html', '')
            source_url = html_payload.get('source_url') or target_url
            try:
                parsed = parse_volume_page(html, source_url)
            except ParseError as exc:
                raise self._with_debug_dump(
                    error=exc,
                    html=html,
                    source_url=source_url,
                    cache_key=cache_key,
                    resource_kind='volume',
                ) from exc
            return parsed.model_dump(), source_url

        return await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_volume_seconds,
            loader=loader,
            namespace='volume',
            resource_url=target_url,
        )

    async def _get_raw_html_payload(self, *, target_url: str, ttl_seconds: int, resource_kind: Literal['series', 'volume']):
        cache_key = versioned_cache_key('raw-html', resource_kind, target_url)

        async def loader():
            result = await self.fetcher.get_text(target_url)
            return {'html': result.text}, result.url

        return await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=ttl_seconds,
            loader=loader,
            namespace=f'raw-html-{resource_kind}',
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
        include_parent_editions: bool | None = None,
    ) -> Envelope:
        payload, entry, cached, partial, warnings = await self._get_volume_payload(series_slug=series_slug, volume_slug=volume_slug, url=url)
        data = deepcopy(payload.get('data', {}) or {})
        should_include_parent_editions = self._volume_default_include_parent_editions if include_parent_editions is None else include_parent_editions
        if not should_include_parent_editions:
            should_include_parent_editions = self._projection_requests_parent_editions(blocks=blocks, fields=fields)
        target_series_slug = series_slug or self._extract_series_slug_from_volume_url(payload.get('source_url') or url or '')
        if should_include_parent_editions and target_series_slug:
            started = time.perf_counter()
            try:
                series_payload, *_ = await self._get_series_search_meta_payload(slug=target_series_slug)
                series_data = series_payload.get('data', {}) or {}
                data['vf'] = series_data.get('vf')
                data['vo'] = series_data.get('vo')
            except Exception as exc:  # pragma: no cover - best-effort enrichment
                logger.debug('Volume enrichment failed for %s: %s', payload.get('source_url'), exc)
            finally:
                self._log_perf(
                    'volume_perf',
                    source_url=payload.get('source_url'),
                    include_parent_editions=should_include_parent_editions,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
        projected = project_resource_payload(
            data,
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

    async def _get_series_editions_block_payload(self, *, slug: str, edition: Literal['vf', 'vo']):
        target_url = f'{self.base_url}/index.php/serie/{"editionsVo" if edition == "vo" else "editions"}/{slug}'
        cache_key = versioned_cache_key('series-editions-block', target_url, edition)

        async def loader():
            try:
                result = await self.fetcher.get_text(target_url)
                parsed = parse_series_editions_page(result.text, result.url, self.base_url, edition)
                return parsed.model_dump(), result.url
            except ResourceNotFound:
                parsed = SeriesEditionsBlock(edition=edition, source_url=target_url, total=0, items=[])
                return parsed.model_dump(), target_url

        return await self._cached_payload(
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_series_seconds,
            loader=loader,
            namespace='series-editions-block',
            resource_url=target_url,
        )

    async def get_series_editions(self, *, slug: str | None = None, url: str | None = None, edition: Literal['all', 'vf', 'vo'] = 'all') -> Envelope:
        target_url = self._resolve_series_url(slug=slug, url=url)
        target_slug = self._extract_series_slug(target_url)
        cache_key = versioned_cache_key('series-editions', target_url, edition)

        async def loader():
            started = time.perf_counter()
            series_payload, *_ = await self._get_series_search_meta_payload(slug=target_slug)
            series_data = series_payload.get('data', {}) or {}
            data = SeriesEditionsData(title=series_data.get('title'), series_slug=target_slug, source_url=series_payload.get('source_url'))
            editions_to_fetch = ['vf', 'vo'] if edition == 'all' else [edition]

            async def _load_block(current: Literal['vf', 'vo']):
                block_payload, *_ = await self._get_series_editions_block_payload(slug=target_slug, edition=current)
                block_data = block_payload.get('data', {}) or {}
                return current, SeriesEditionsBlock.model_validate(block_data)

            for current, block in await self._run_with_limit(
                editions_to_fetch,
                _load_block,
                concurrency=min(len(editions_to_fetch), 2),
            ):
                if current == 'vf':
                    data.vf = block
                else:
                    data.vo = block

            self._log_perf(
                'series_editions_perf',
                slug=target_slug,
                edition=edition,
                blocks=len(editions_to_fetch),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return data.model_dump(), series_payload.get('source_url')

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
        cache_key = versioned_cache_key('news-global', rss_url, str(limit))

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
        cache_key = versioned_cache_key('planning', target_url)

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
        cache_key = versioned_cache_key(cache_namespace, target_url, str(limit))

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

    def _extract_series_slug_from_volume_url(self, volume_url: str) -> str | None:
        if not volume_url:
            return None
        path_parts = [part for part in urlparse(volume_url).path.split('/') if part]
        if 'manga' in path_parts:
            idx = path_parts.index('manga')
            if len(path_parts) > idx + 1:
                return path_parts[idx + 1]
        return None

    def _extract_series_slug(self, series_url: str) -> str:
        path_parts = [part for part in urlparse(series_url).path.split('/') if part]
        if not path_parts:
            raise ParseError('Unable to infer the series slug from the provided URL.')
        return path_parts[-1]
