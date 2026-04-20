from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.openapi.utils import get_openapi
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from app.auth import require_admin_token, require_api_token
from app.cache import SQLiteCache
from app.config import Settings, get_settings
from app.exceptions import BadRequestError, ParseError, ResourceNotFound, UpstreamError
from app.http import AsyncFetcher
from app.logging_utils import log_event, reset_request_id, set_request_id
from app.manga_news.service import MangaNewsService
from app.metrics import MetricsStore
from app.rate_limit import InMemoryRateLimiter
from app.models import (
    ApiErrorResponse,
    CacheInvalidateRequest,
    CacheInvalidateResponse,
    CacheStatsResponse,
    HealthResponse,
    MetricsResponse,
    NewsResponse,
    PlanningResponse,
    ResolveResponse,
    SearchResponse,
    SeriesEditionsResponse,
    SeriesRelatedResponse,
    SeriesResponse,
    VolumeLookupResponse,
    VolumeResponse,
)

logger = logging.getLogger(__name__)


OPENAPI_ERROR_RESPONSES = {
    400: {
        'description': 'Invalid request parameters.',
        'model': ApiErrorResponse,
        'content': {'application/json': {'example': {'ok': False, 'code': 'INVALID_REQUEST', 'detail': 'Unknown volume field path: bogus'}}},
    },
    401: {
        'description': 'Authentication failure.',
        'model': ApiErrorResponse,
        'content': {'application/json': {'example': {'ok': False, 'code': 'AUTH_REQUIRED', 'detail': 'Missing or invalid bearer token.'}}},
    },
    404: {
        'description': 'No matching resource was found.',
        'model': ApiErrorResponse,
        'content': {'application/json': {'example': {'ok': False, 'code': 'RESOURCE_NOT_FOUND', 'detail': "No volume matched series='One Piece' and number='999'."}}},
    },
    429: {
        'description': 'Rate limit exceeded.',
        'model': ApiErrorResponse,
        'content': {'application/json': {'example': {'ok': False, 'code': 'RATE_LIMITED', 'detail': 'Too many requests for the current window.'}}},
    },
    502: {
        'description': 'Upstream Manga News fetch/parsing failure.',
        'model': ApiErrorResponse,
        'content': {'application/json': {'example': {'ok': False, 'code': 'UPSTREAM_PARSE_ERROR', 'detail': 'Unable to parse the Manga News page.'}}},
    },
}

SEARCH_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/recherche/',
    'cached': False,
    'fetched_at': '2026-04-20T12:00:00+00:00',
    'cache_expires_at': '2026-04-20T18:00:00+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-search-one-piece-91',
    'pagination': {'page': 1, 'limit': 10, 'returned': 1, 'total': 4, 'has_more': True},
    'data': [
        {
            'title': 'One Piece Vol.91',
            'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
            'kind': 'volume',
            'score': 98,
            'slug': None,
            'series_slug': 'One-Piece',
            'volume_slug': 'vol-91',
            'number': '91',
        }
    ],
}

RESOLVE_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/recherche/',
    'cached': False,
    'fetched_at': '2026-04-20T12:00:00+00:00',
    'cache_expires_at': '2026-04-20T18:00:00+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-resolve-one-piece-91',
    'pagination': {'page': 1, 'limit': 10, 'returned': 4, 'total': 4, 'has_more': False},
    'data': {
        'query': 'one piece tome 91',
        'kind_requested': 'volume',
        'confidence': 'high',
        'best': {
            'title': 'One Piece Vol.91',
            'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
            'kind': 'volume',
            'score': 98,
            'slug': None,
            'series_slug': 'One-Piece',
            'volume_slug': 'vol-91',
            'number': '91',
        },
        'candidates': [],
    },
}

SERIES_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
    'cached': False,
    'fetched_at': '2026-04-20T12:00:00+00:00',
    'cache_expires_at': '2026-04-21T12:00:00+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-series-one-piece',
    'data': {
        'title': 'One Piece',
        'publisher_fr': 'Glénat',
        'vf': {'volumes': 111, 'status': 'En cours'},
        'vo': {'volumes': 113, 'status': 'En cours'},
        'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
    },
}

VOLUME_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
    'cached': False,
    'fetched_at': '2026-04-20T12:00:00+00:00',
    'cache_expires_at': '2026-04-21T12:00:00+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-volume-one-piece-91',
    'data': {
        'title': 'One Piece Vol.91',
        'series_title': 'One Piece',
        'number': '91',
        'number_int': 91,
        'edition_label': 'edition_originale',
        'is_special': False,
        'is_one_shot': None,
        'publisher_fr': 'Glénat',
        'publication_date': '2019-07-03',
        'isbn_ean': '9782344037102',
        'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
    },
}

LOOKUP_VOLUME_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
    'cached': False,
    'fetched_at': '2026-04-20T12:00:00+00:00',
    'cache_expires_at': '2026-04-21T12:00:00+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-lookup-one-piece-91',
    'data': {
        'query': 'One Piece tome 91',
        'requested_series': 'One Piece',
        'requested_number': '91',
        'pagination': {'page': 1, 'limit': 10, 'returned': 1, 'total': 4, 'has_more': True},
        'resolved': {
            'title': 'One Piece Vol.91',
            'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
            'kind': 'volume',
            'score': 98,
            'slug': None,
            'series_slug': 'One-Piece',
            'volume_slug': 'vol-91',
            'number': '91',
        },
        'volume': VOLUME_EXAMPLE['data'],
        'candidates': [],
    },
}


def _error_response(status_code: int, code: str, detail: str, *, headers: dict[str, str] | None = None) -> JSONResponse:
    payload = {'ok': False, 'code': code, 'detail': detail}
    return JSONResponse(status_code=status_code, content=payload, headers=headers or {})


def _is_schema_or_docs_path(path: str, settings: Settings) -> bool:
    if path == '/openapi.json' or path == '/docs/oauth2-redirect':
        return True
    if settings.docs_url and path.startswith(settings.docs_url):
        return True
    if settings.redoc_url and path.startswith(settings.redoc_url):
        return True
    return False


def _is_legacy_path(path: str, settings: Settings) -> bool:
    if path.startswith('/v1') or _is_schema_or_docs_path(path, settings):
        return False
    return path.startswith('/')


def _rate_limit_key(request: Request, settings: Settings) -> str:
    auth = request.headers.get('authorization', '').strip()
    client_ip = request.client.host if request.client else 'unknown'
    scope = settings.rate_limit_scope.lower()
    if scope == 'token' and auth:
        return f'token:{auth}'
    if scope == 'ip':
        return f'ip:{client_ip}'
    if auth:
        return f'token:{auth}'
    return f'ip:{client_ip}'


def _should_rate_limit(request: Request, settings: Settings) -> bool:
    path = request.url.path
    if path in set(settings.rate_limit_exempt_path_list):
        return False
    if _is_schema_or_docs_path(path, settings):
        return False
    if path.startswith('/v1/admin/') and not settings.rate_limit_include_admin:
        return False
    return True


def _apply_rate_limit_headers(response: Response, decision) -> None:
    response.headers['X-RateLimit-Limit'] = str(decision.limit)
    response.headers['X-RateLimit-Remaining'] = str(decision.remaining)
    response.headers['X-RateLimit-Reset'] = str(decision.reset_after_seconds)



def configure_logging(settings: Settings) -> None:
    json_logs = settings.log_format.lower() == 'json'
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format='%(message)s' if json_logs else '%(asctime)s %(levelname)s %(name)s: %(message)s',
        force=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    cache = SQLiteCache(settings.db_path)
    metrics = MetricsStore()
    fetcher = AsyncFetcher(
        settings.user_agent,
        settings.request_timeout_seconds,
        max_retries=settings.request_max_retries,
        backoff_seconds=settings.request_backoff_seconds,
        log_json=settings.log_format.lower() == 'json',
        metrics=metrics,
    )
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=cache, metrics=metrics)
    app.state.settings = settings
    app.state.service = service
    app.state.metrics = metrics
    app.state.rate_limiter = InMemoryRateLimiter(limit=settings.rate_limit_requests, window_seconds=settings.rate_limit_window_seconds)
    try:
        yield
    finally:
        await fetcher.close()


app = FastAPI(
    title='Manga News Private API',
    version='0.4.0',
    docs_url=get_settings().docs_url,
    redoc_url=get_settings().redoc_url,
    lifespan=lifespan,
)


@app.middleware('http')
async def request_context_middleware(request: Request, call_next):
    settings = get_settings()
    json_logs = settings.log_format.lower() == 'json'
    request_id = request.headers.get('x-request-id') or uuid4().hex
    token = set_request_id(request_id)
    started = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        'request_started',
        json_mode=json_logs,
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        query=str(request.url.query) or None,
    )

    decision = None
    if not settings.enable_legacy_routes and _is_legacy_path(request.url.path, settings):
        response = _error_response(404, 'ENDPOINT_NOT_FOUND', 'Legacy unversioned routes are disabled. Use /v1/... instead.')
        response.headers['X-Request-ID'] = request_id
        request.app.state.metrics.record_response(response.status_code)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(logger, logging.INFO, 'request_completed', json_mode=json_logs, request_id=request_id, method=request.method, path=request.url.path, status_code=response.status_code, duration_ms=duration_ms)
        reset_request_id(token)
        return response

    if settings.rate_limit_enabled and _should_rate_limit(request, settings):
        decision = request.app.state.rate_limiter.check(_rate_limit_key(request, settings))
        if not decision.allowed:
            response = _error_response(429, 'RATE_LIMITED', 'Too many requests for the current window.', headers={'Retry-After': str(decision.retry_after_seconds)})
            response.headers['X-Request-ID'] = request_id
            _apply_rate_limit_headers(response, decision)
            request.app.state.metrics.increment('rate_limited_requests')
            request.app.state.metrics.record_response(response.status_code)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log_event(logger, logging.WARNING, 'request_rate_limited', json_mode=json_logs, request_id=request_id, method=request.method, path=request.url.path, status_code=response.status_code, duration_ms=duration_ms)
            reset_request_id(token)
            return response

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(
            logger,
            logging.ERROR,
            'request_failed',
            json_mode=json_logs,
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
        )
        reset_request_id(token)
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers['X-Request-ID'] = request_id
    if decision is not None:
        _apply_rate_limit_headers(response, decision)
    request.app.state.metrics.record_response(response.status_code)
    log_event(
        logger,
        logging.INFO,
        'request_completed',
        json_mode=json_logs,
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        cache_status=response.headers.get('X-Cache-Status'),
    )
    reset_request_id(token)
    return response


def get_service() -> MangaNewsService:
    return app.state.service


def get_settings_dep() -> Settings:
    return app.state.settings


def get_metrics():
    return app.state.metrics


def _etag_matches(if_none_match: str | None, etag: str | None) -> bool:
    if not if_none_match or not etag:
        return False
    candidates = [item.strip() for item in if_none_match.split(',') if item.strip()]
    for candidate in candidates:
        if candidate == '*':
            return True
        if candidate == etag:
            return True
        if candidate.startswith('W/') and candidate[2:].strip() == etag:
            return True
    return False


def _cache_status_header(payload: dict) -> str:
    if payload.get('partial') and payload.get('cached'):
        return 'STALE'
    if payload.get('cached'):
        return 'HIT'
    return 'MISS'


def _build_envelope_response(payload, request: Request):
    if_none_match = request.headers.get('if-none-match')
    fingerprint = payload.get('fingerprint')
    etag = f'"{fingerprint}"' if fingerprint else None
    headers = {
        'Vary': 'Authorization, If-None-Match',
        'X-Cache-Status': _cache_status_header(payload),
    }
    if fingerprint:
        headers['X-Data-Fingerprint'] = fingerprint
        headers['ETag'] = etag
    if _etag_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=jsonable_encoder(payload), headers=headers)


async def auth_dependency(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings_dep),
):
    return await require_api_token(settings, authorization)


async def admin_auth_dependency(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings_dep),
):
    return await require_admin_token(settings, authorization)


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException):
    code = 'AUTH_REQUIRED' if exc.status_code == 401 else 'HTTP_ERROR'
    detail = str(exc.detail)
    return _error_response(exc.status_code, code, detail, headers=getattr(exc, 'headers', None))


@app.exception_handler(ResourceNotFound)
async def not_found_handler(_, exc: ResourceNotFound):
    return _error_response(404, exc.code, str(exc))


@app.exception_handler(BadRequestError)
async def bad_request_handler(_, exc: BadRequestError):
    return _error_response(400, exc.code, str(exc))


@app.exception_handler(ParseError)
async def parse_error_handler(_, exc: ParseError):
    return _error_response(502, exc.code, str(exc))


@app.exception_handler(UpstreamError)
async def upstream_error_handler(_, exc: UpstreamError):
    return _error_response(502, exc.code, str(exc))


@app.get('/health', dependencies=[Depends(auth_dependency)], response_model=HealthResponse)
async def health():
    return {'ok': True}


@app.get(
    '/search',
    dependencies=[Depends(auth_dependency)],
    response_model=SearchResponse,
    responses={200: {'description': 'Search results.', 'content': {'application/json': {'example': SEARCH_EXAMPLE}}}, **OPENAPI_ERROR_RESPONSES},
)
async def search(
    request: Request,
    q: str = Query(
        ...,
        min_length=1,
        description='Free-text query. Example: one piece tome 91',
        openapi_examples={'one_piece_volume': {'summary': 'One Piece tome 91', 'value': 'one piece tome 91'}},
    ),
    kind: Literal['series', 'volume', 'all'] = Query(default='all', openapi_examples={'volume': {'value': 'volume'}, 'series': {'value': 'series'}}),
    mode: Literal['best', 'all'] = Query(default='best', openapi_examples={'best': {'value': 'best'}, 'all': {'value': 'all'}}),
    limit: int = Query(default=10, ge=1, le=50, openapi_examples={'default': {'value': 10}}),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.search(query=q, kind=kind, mode=mode, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/search/resolve',
    dependencies=[Depends(auth_dependency)],
    response_model=ResolveResponse,
    responses={200: {'description': 'Resolved best match.', 'content': {'application/json': {'example': RESOLVE_EXAMPLE}}}, **OPENAPI_ERROR_RESPONSES},
)
async def search_resolve(
    request: Request,
    q: str = Query(
        ...,
        min_length=1,
        description='Free-text query. Example: one piece tome 91',
        openapi_examples={'one_piece_volume': {'summary': 'One Piece tome 91', 'value': 'one piece tome 91'}},
    ),
    kind: Literal['series', 'volume', 'all'] = Query(default='all', openapi_examples={'volume': {'value': 'volume'}, 'series': {'value': 'series'}}),
    limit: int = Query(default=10, ge=1, le=50, openapi_examples={'default': {'value': 10}}),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.resolve_search(query=q, kind=kind, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/{slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesResponse,
    responses={200: {'description': 'Series metadata.', 'content': {'application/json': {'example': SERIES_EXAMPLE}}}, **OPENAPI_ERROR_RESPONSES},
)
async def get_series(
    request: Request,
    slug: str,
    blocks: str | None = Query(default=None, description='Comma-separated block names. Example: editions,stats'),
    fields: str | None = Query(default=None, description='Comma-separated dot paths. Example: title,vf.volumes'),
    include_raw_sections: bool = Query(default=False),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series(slug=slug, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/by-url', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse)
async def get_series_by_url(
    request: Request,
    url: str = Query(...),
    blocks: str | None = Query(default=None),
    fields: str | None = Query(default=None),
    include_raw_sections: bool = Query(default=False),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series(url=url, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/{slug}/related', dependencies=[Depends(auth_dependency)], response_model=SeriesRelatedResponse)
async def get_series_related(request: Request, slug: str, service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(slug=slug)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/by-url/related', dependencies=[Depends(auth_dependency)], response_model=SeriesRelatedResponse)
async def get_series_related_by_url(request: Request, url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(url=url)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/{slug}/editions', dependencies=[Depends(auth_dependency)], response_model=SeriesEditionsResponse)
async def get_series_editions(
    request: Request,
    slug: str,
    edition: Literal['all', 'vf', 'vo'] = Query(default='all'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(slug=slug, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/by-url/editions', dependencies=[Depends(auth_dependency)], response_model=SeriesEditionsResponse)
async def get_series_editions_by_url(
    request: Request,
    url: str = Query(...),
    edition: Literal['all', 'vf', 'vo'] = Query(default='all'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(url=url, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/volume/{series_slug}/{volume_slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=VolumeResponse,
    responses={200: {'description': 'Volume metadata.', 'content': {'application/json': {'example': VOLUME_EXAMPLE}}}, **OPENAPI_ERROR_RESPONSES},
)
async def get_volume(
    request: Request,
    series_slug: str,
    volume_slug: str,
    blocks: str | None = Query(default=None, description='Comma-separated block names. Example: release,scores'),
    fields: str | None = Query(default=None, description='Comma-separated dot paths. Example: publication_date,isbn_ean'),
    include_raw_sections: bool = Query(default=False),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume(series_slug=series_slug, volume_slug=volume_slug, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse)
async def get_volume_by_url(
    request: Request,
    url: str = Query(...),
    blocks: str | None = Query(default=None),
    fields: str | None = Query(default=None),
    include_raw_sections: bool = Query(default=False),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume(url=url, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/lookup/volume',
    dependencies=[Depends(auth_dependency)],
    response_model=VolumeLookupResponse,
    responses={200: {'description': 'Resolve a series + number then return the volume metadata.', 'content': {'application/json': {'example': LOOKUP_VOLUME_EXAMPLE}}}, **OPENAPI_ERROR_RESPONSES},
)
async def lookup_volume(
    request: Request,
    series: str = Query(
        ...,
        min_length=1,
        description='Series title to resolve. Example: One Piece',
        openapi_examples={'one_piece': {'summary': 'One Piece', 'value': 'One Piece'}},
    ),
    number: str = Query(
        ...,
        min_length=1,
        description='Requested volume number. Example: 91',
        openapi_examples={'volume_91': {'summary': 'Volume 91', 'value': '91'}},
    ),
    limit: int = Query(default=10, ge=1, le=50, openapi_examples={'default': {'value': 10}}),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.lookup_volume(series=series, number=number, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/global', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
async def get_global_news(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_global_news(limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
async def get_series_news(
    request: Request,
    slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_news(slug=slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
async def get_volume_news(
    request: Request,
    series_slug: str,
    volume_slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(series_slug=series_slug, volume_slug=volume_slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
async def get_volume_news_by_url(
    request: Request,
    url: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(url=url, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/planning', dependencies=[Depends(auth_dependency)], response_model=PlanningResponse)
async def get_planning(
    request: Request,
    section: Literal['manga-vf', 'manga-vo'] = Query(default='manga-vf'),
    year: int | None = Query(default=None, ge=1900, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    page: int = Query(default=1, ge=1, le=100),
    publisher: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    sort: Literal['date_asc', 'date_desc', 'title_asc', 'title_desc'] = Query(default='date_asc'),
    limit: int = Query(default=25, ge=1, le=100),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_planning(
        section=section,
        year=year,
        month=month,
        page=page,
        publisher=publisher,
        query=q,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        limit=limit,
    )
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/admin/cache/stats', dependencies=[Depends(admin_auth_dependency)], response_model=CacheStatsResponse)
async def get_cache_stats(service: MangaNewsService = Depends(get_service)):
    return {'ok': True, 'data': service.cache.stats()}


@app.get('/admin/metrics', dependencies=[Depends(admin_auth_dependency)], response_model=MetricsResponse)
async def get_admin_metrics(metrics: MetricsStore = Depends(get_metrics)):
    return {'ok': True, 'data': metrics.snapshot().model_dump()}


@app.post('/admin/cache/invalidate', dependencies=[Depends(admin_auth_dependency)], response_model=CacheInvalidateResponse)
async def invalidate_cache(
    payload: CacheInvalidateRequest | None = Body(default=None),
    service: MangaNewsService = Depends(get_service),
):
    payload = payload or CacheInvalidateRequest()
    deleted = service.cache.invalidate(
        cache_key=payload.cache_key,
        namespace=payload.namespace,
        resource_url=payload.resource_url,
        expired_only=payload.expired_only,
        all_entries=payload.all_entries,
    )
    return {
        'ok': True,
        'deleted': deleted,
        'filters': payload.model_dump(),
        'stats': service.cache.stats(),
    }


_VERSIONED_ALIASES = [
    ('/v1/health', health, ['GET'], HealthResponse),
    ('/v1/search', search, ['GET'], SearchResponse),
    ('/v1/search/resolve', search_resolve, ['GET'], ResolveResponse),
    ('/v1/series/{slug}', get_series, ['GET'], SeriesResponse),
    ('/v1/series/by-url', get_series_by_url, ['GET'], SeriesResponse),
    ('/v1/series/{slug}/related', get_series_related, ['GET'], SeriesRelatedResponse),
    ('/v1/series/by-url/related', get_series_related_by_url, ['GET'], SeriesRelatedResponse),
    ('/v1/series/{slug}/editions', get_series_editions, ['GET'], SeriesEditionsResponse),
    ('/v1/series/by-url/editions', get_series_editions_by_url, ['GET'], SeriesEditionsResponse),
    ('/v1/volume/{series_slug}/{volume_slug}', get_volume, ['GET'], VolumeResponse),
    ('/v1/volume/by-url', get_volume_by_url, ['GET'], VolumeResponse),
    ('/v1/lookup/volume', lookup_volume, ['GET'], VolumeLookupResponse),
    ('/v1/news/global', get_global_news, ['GET'], NewsResponse),
    ('/v1/news/series/{slug}', get_series_news, ['GET'], NewsResponse),
    ('/v1/news/volume/{series_slug}/{volume_slug}', get_volume_news, ['GET'], NewsResponse),
    ('/v1/news/volume/by-url', get_volume_news_by_url, ['GET'], NewsResponse),
    ('/v1/planning', get_planning, ['GET'], PlanningResponse),
    ('/v1/admin/cache/stats', get_cache_stats, ['GET'], CacheStatsResponse),
    ('/v1/admin/cache/invalidate', invalidate_cache, ['POST'], CacheInvalidateResponse),
    ('/v1/admin/metrics', get_admin_metrics, ['GET'], MetricsResponse),
]


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    if not get_settings().enable_legacy_routes:
        original_paths = dict(schema.get('paths', {}))
        versioned_paths = {}
        for path, value in original_paths.items():
            if not path.startswith('/v1'):
                continue
            legacy_path = path[3:] or '/'
            versioned_paths[path] = original_paths.get(legacy_path, value)
        schema['paths'] = versioned_paths
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


for path, endpoint, methods, response_model in _VERSIONED_ALIASES:
    dependency = admin_auth_dependency if path.startswith('/v1/admin/') else auth_dependency
    app.add_api_route(
        path,
        endpoint,
        methods=methods,
        response_model=response_model,
        dependencies=[Depends(dependency)],
    )
