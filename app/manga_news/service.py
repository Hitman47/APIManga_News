from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal
from urllib.parse import urlencode

import feedparser

from app.cache import SQLiteCache
from app.config import Settings
from app.exceptions import ParseError
from app.http import AsyncFetcher
from app.logging_utils import log_event
from app.models import Envelope, NewsItem
from app.manga_news.parsers import parse_news_page, parse_planning_page, parse_search_page, parse_series_page, parse_volume_page
from app.utils import clean_ws, is_manga_news_url, make_cache_key, make_fingerprint, normalize_text, now_utc, parse_french_date, score_match

logger = logging.getLogger(__name__)


class MangaNewsService:
    def __init__(self, settings: Settings, fetcher: AsyncFetcher, cache: SQLiteCache):
        self.settings = settings
        self.fetcher = fetcher
        self.cache = cache
        self.base_url = settings.manga_news_base_url.rstrip('/')
        self._json_logs = settings.log_format.lower() == 'json'

    async def _cached_payload(self, *, namespace: str, cache_key: str, ttl_seconds: int, loader):
        entry = self.cache.get(cache_key)
        if entry and entry.is_fresh:
            log_event(logger, logging.INFO, 'cache_hit', json_mode=self._json_logs, namespace=namespace, cache_key=cache_key, resource_url=entry.resource_url)
            return entry.payload, entry, True, False, [], 'fresh_hit'
        try:
            payload, source_url = await loader()
            cached_entry = self.cache.set(
                cache_key=cache_key,
                payload={'data': payload, 'source_url': source_url},
                ttl_seconds=ttl_seconds,
                stale_grace_seconds=self.settings.cache_stale_grace_seconds,
                namespace=namespace,
                resource_url=source_url,
            )
            log_event(logger, logging.INFO, 'cache_refresh', json_mode=self._json_logs, namespace=namespace, cache_key=cache_key, resource_url=source_url)
            return cached_entry.payload, cached_entry, False, False, [], 'refreshed'
        except Exception as exc:
            if entry and entry.is_stale_usable:
                warning = f'Using stale cached data because the upstream fetch failed: {exc}'
                log_event(
                    logger,
                    logging.WARNING,
                    'cache_stale_fallback',
                    json_mode=self._json_logs,
                    namespace=namespace,
                    cache_key=cache_key,
                    resource_url=entry.resource_url,
                    reason=str(exc),
                )
                return entry.payload, entry, True, True, [warning], 'stale_fallback'
            raise

    def _assess_parse(self, resource_kind: str, data: Any) -> tuple[bool, list[str], list[str]]:
        missing_fields: list[str] = []
        warnings: list[str] = []

        if resource_kind == 'series' and isinstance(data, dict):
            important = ['title', 'summary', 'cover_image', 'publisher_fr']
            missing_fields = [field for field in important if not data.get(field)]
        elif resource_kind == 'volume' and isinstance(data, dict):
            important = ['title', 'publication_date', 'cover_image', 'isbn_ean']
            missing_fields = [field for field in important if not data.get(field)]
        elif resource_kind == 'planning' and isinstance(data, dict):
            items = data.get('items', []) or []
            malformed = [item for item in items if not item.get('title') or not item.get('release_date')]
            if malformed:
                missing_fields.append('items[*].title/release_date')
                warnings.append(f'{len(malformed)} planning item(s) are missing a title or release date.')
        elif resource_kind == 'news' and isinstance(data, list):
            malformed = [item for item in data if not item.get('title') or not item.get('published_at')]
            if malformed:
                missing_fields.append('items[*].title/published_at')
                warnings.append(f'{len(malformed)} news item(s) are missing a title or publication date.')
        elif resource_kind == 'search' and isinstance(data, list):
            malformed = [item for item in data if not item.get('title') or not item.get('url')]
            if malformed:
                missing_fields.append('items[*].title/url')
                warnings.append(f'{len(malformed)} search result(s) are missing a title or URL.')

        partial = bool(missing_fields)
        if partial and resource_kind in {'series', 'volume'}:
            warnings.append('Some important fields are missing. The upstream page layout may have changed or the resource is incomplete.')
        return partial, missing_fields, warnings

    def _envelope(
        self,
        payload: dict,
        entry,
        *,
        cached: bool,
        partial: bool,
        warnings: list[str],
        cache_state: str,
        resource_kind: str,
        found: bool = True,
    ) -> Envelope:
        data = payload.get('data')
        parse_partial, missing_fields, parse_warnings = self._assess_parse(resource_kind, data)
        combined_partial = partial or parse_partial
        combined_warnings = warnings + [warning for warning in parse_warnings if warning not in warnings]
        return Envelope(
            ok=True,
            found=found,
            source='manga_news',
            source_url=payload.get('source_url'),
            cached=cached,
            cache_state=cache_state,
            fetched_at=entry.fetched_at.isoformat() if entry else now_utc().isoformat(),
            cache_expires_at=entry.expires_at.isoformat() if entry else None,
            partial=combined_partial,
            parse_status='partial' if combined_partial else 'complete',
            missing_fields=missing_fields,
            fingerprint=make_fingerprint(data),
            warnings=combined_warnings,
            data=data,
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
            deduped: dict[str, object] = {}
            for item in aggregated:
                existing = deduped.get(item.url)
                if existing is None or item.score > existing.score:
                    deduped[item.url] = item
            results = sorted(deduped.values(), key=lambda item: item.score, reverse=True)
            if mode == 'best' and results:
                results = [results[0]]
            results = results[:limit]
            return [item.model_dump() for item in results], search_urls[0] if search_urls else self.base_url

        payload, entry, cached, partial, warnings, cache_state = await self._cached_payload(
            namespace='search',
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_search_seconds,
            loader=loader,
        )
        found = bool(payload.get('data'))
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings, cache_state=cache_state, resource_kind='search', found=found)

    async def get_series(self, *, slug: str | None = None, url: str | None = None) -> Envelope:
        target_url = self._resolve_series_url(slug=slug, url=url)
        cache_key = make_cache_key('series', target_url)

        async def loader():
            result = await self.fetcher.get_text(target_url)
            parsed = parse_series_page(result.text, result.url)
            return parsed.model_dump(), result.url

        payload, entry, cached, partial, warnings, cache_state = await self._cached_payload(
            namespace='series',
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_series_seconds,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings, cache_state=cache_state, resource_kind='series')

    async def get_volume(self, *, series_slug: str | None = None, volume_slug: str | None = None, url: str | None = None) -> Envelope:
        target_url = self._resolve_volume_url(series_slug=series_slug, volume_slug=volume_slug, url=url)
        cache_key = make_cache_key('volume', target_url)

        async def loader():
            result = await self.fetcher.get_text(target_url)
            parsed = parse_volume_page(result.text, result.url)
            return parsed.model_dump(), result.url

        payload, entry, cached, partial, warnings, cache_state = await self._cached_payload(
            namespace='volume',
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_volume_seconds,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings, cache_state=cache_state, resource_kind='volume')

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

        payload, entry, cached, partial, warnings, cache_state = await self._cached_payload(
            namespace='news-global',
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_news_global_seconds,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings, cache_state=cache_state, resource_kind='news')

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

    async def _load_planning_source(self, *, section: Literal['manga-vf', 'manga-vo'], year: int | None, month: int | None, page: int):
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

        return await self._cached_payload(
            namespace='planning',
            cache_key=cache_key,
            ttl_seconds=self.settings.cache_ttl_planning_seconds,
            loader=loader,
        )

    def _filter_planning_items(
        self,
        planning: dict[str, Any],
        *,
        publisher: str | None,
        query: str | None,
        date_from: str | None,
        date_to: str | None,
        sort: Literal['date_asc', 'date_desc', 'title_asc', 'title_desc'],
    ) -> list[dict[str, Any]]:
        items = list(planning.get('items', []) or [])

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
        return items

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
        payload, entry, cached, partial, warnings, cache_state = await self._load_planning_source(section=section, year=year, month=month, page=page)
        planning = payload.get('data', {}) or {}
        full_items = self._filter_planning_items(planning, publisher=publisher, query=query, date_from=date_from, date_to=date_to, sort=sort)
        total_items = len(full_items)
        limited_items = full_items[:limit]
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
            'items': limited_items,
        }
        return self._envelope(
            {'data': data, 'source_url': payload.get('source_url')},
            entry,
            cached=cached,
            partial=partial,
            warnings=warnings,
            cache_state=cache_state,
            resource_kind='planning',
            found=bool(full_items),
        )

    async def get_planning_watch(
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
        watch_id: str | None,
        previous_fingerprint: str | None,
        commit_snapshot: bool,
        preview_limit: int,
    ) -> Envelope:
        payload, entry, cached, partial, warnings, cache_state = await self._load_planning_source(section=section, year=year, month=month, page=page)
        planning = payload.get('data', {}) or {}
        full_items = self._filter_planning_items(planning, publisher=publisher, query=query, date_from=date_from, date_to=date_to, sort=sort)
        full_items = full_items[:limit]
        current_fingerprint = make_fingerprint(full_items)
        scope = {
            'section': section,
            'year': year,
            'month': month,
            'page': page,
            'publisher': publisher,
            'query': query,
            'date_from': date_from,
            'date_to': date_to,
            'sort': sort,
            'limit': limit,
        }
        scope_hash = make_fingerprint(scope)

        previous_items: list[dict[str, Any]] = []
        has_previous_snapshot = False
        scope_changed = False
        prior_fingerprint = previous_fingerprint

        if watch_id:
            snapshot = self.cache.get_watch_snapshot(f'planning:{watch_id}')
            if snapshot:
                if snapshot.scope_hash == scope_hash:
                    has_previous_snapshot = True
                    previous_items = list(snapshot.payload.get('items', []))
                    prior_fingerprint = snapshot.fingerprint
                else:
                    scope_changed = True
                    prior_fingerprint = snapshot.fingerprint
            if commit_snapshot:
                self.cache.upsert_watch_snapshot(
                    f'planning:{watch_id}',
                    scope_hash=scope_hash,
                    payload={'items': full_items, 'scope': scope},
                    fingerprint=current_fingerprint,
                )

        previous_index = {self._planning_item_identity(item): item for item in previous_items}
        current_index = {self._planning_item_identity(item): item for item in full_items}
        added_items = [item for key, item in current_index.items() if key not in previous_index]
        removed_items = [item for key, item in previous_index.items() if key not in current_index]
        changed = False
        if has_previous_snapshot:
            changed = bool(added_items or removed_items or prior_fingerprint != current_fingerprint)
        elif previous_fingerprint is not None:
            changed = previous_fingerprint != current_fingerprint

        if scope_changed:
            warnings = warnings + ['The stored watch scope changed. The previous snapshot was ignored for diff computation.']

        data = {
            'section': section,
            'year': planning.get('year') or year,
            'month': planning.get('month') or month,
            'watch_id': watch_id,
            'has_previous_snapshot': has_previous_snapshot,
            'scope_changed': scope_changed,
            'changed': changed,
            'previous_fingerprint': prior_fingerprint,
            'current_fingerprint': current_fingerprint,
            'total_items': len(full_items),
            'added_count': len(added_items),
            'removed_count': len(removed_items),
            'added_items': added_items[:preview_limit],
            'removed_items': removed_items[:preview_limit],
            'current_items_preview': full_items[:preview_limit],
            'filters': scope,
        }
        log_event(
            logger,
            logging.INFO,
            'planning_watch',
            json_mode=self._json_logs,
            changed=changed,
            watch_id=watch_id,
            total_items=len(full_items),
            added_count=len(added_items),
            removed_count=len(removed_items),
        )
        return self._envelope(
            {'data': data, 'source_url': payload.get('source_url')},
            entry,
            cached=cached,
            partial=partial,
            warnings=warnings,
            cache_state=cache_state,
            resource_kind='planning',
            found=True,
        )

    def cache_stats(self) -> Envelope:
        data = self.cache.stats()
        return Envelope(
            ok=True,
            found=True,
            source='manga_news',
            source_url=None,
            cached=False,
            cache_state=None,
            fetched_at=now_utc().isoformat(),
            cache_expires_at=None,
            partial=False,
            parse_status='complete',
            missing_fields=[],
            fingerprint=make_fingerprint(data),
            warnings=[],
            data=data,
        )

    def invalidate_cache(
        self,
        *,
        cache_key: str | None,
        namespace: str | None,
        resource_url: str | None,
        expired_only: bool,
        all_entries: bool,
    ) -> Envelope:
        deleted_entries = self.cache.invalidate(
            cache_key=cache_key,
            namespace=namespace,
            resource_url=resource_url,
            expired_only=expired_only,
            all_entries=all_entries,
        )
        log_event(
            logger,
            logging.WARNING,
            'cache_invalidate',
            json_mode=self._json_logs,
            deleted_entries=deleted_entries,
            cache_key=cache_key,
            namespace=namespace,
            resource_url=resource_url,
            expired_only=expired_only,
            all_entries=all_entries,
        )
        data = {
            'deleted_entries': deleted_entries,
            'filters': {
                'cache_key': cache_key,
                'namespace': namespace,
                'resource_url': resource_url,
                'expired_only': expired_only,
                'all_entries': all_entries,
            },
        }
        return Envelope(
            ok=True,
            found=True,
            source='manga_news',
            source_url=None,
            cached=False,
            cache_state=None,
            fetched_at=now_utc().isoformat(),
            cache_expires_at=None,
            partial=False,
            parse_status='complete',
            missing_fields=[],
            fingerprint=make_fingerprint(data),
            warnings=[],
            data=data,
        )

    def _planning_item_identity(self, item: dict[str, Any]) -> str:
        return item.get('url') or '|'.join(
            [
                item.get('title') or '',
                item.get('release_date') or '',
                item.get('publisher') or '',
            ]
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

        payload, entry, cached, partial, warnings, cache_state = await self._cached_payload(
            namespace=cache_namespace,
            cache_key=cache_key,
            ttl_seconds=ttl,
            loader=loader,
        )
        return self._envelope(payload, entry, cached=cached, partial=partial, warnings=warnings, cache_state=cache_state, resource_kind='news')

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
