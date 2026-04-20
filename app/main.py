from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from app.auth import require_api_token
from app.cache import SQLiteCache
from app.config import Settings, get_settings
from app.exceptions import BadRequestError, ParseError, ResourceNotFound, UpstreamError
from app.http import AsyncFetcher
from app.logging_utils import log_event, reset_request_id, set_request_id
from app.manga_news.service import MangaNewsService
from app.models import (
    CacheInvalidateRequest,
    CacheInvalidateResponse,
    CacheStatsResponse,
    HealthResponse,
    NewsResponse,
    PlanningResponse,
    ResolveResponse,
    SearchResponse,
    SeriesEditionsResponse,
    SeriesRelatedResponse,
    SeriesResponse,
    VolumeResponse,
)

logger = logging.getLogger(__name__)


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
    fetcher = AsyncFetcher(
        settings.user_agent,
        settings.request_timeout_seconds,
        max_retries=settings.request_max_retries,
        backoff_seconds=settings.request_backoff_seconds,
        log_json=settings.log_format.lower() == 'json',
    )
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=cache)
    app.state.settings = settings
    app.state.service = service
    try:
        yield
    finally:
        await fetcher.close()


app = FastAPI(
    title='Manga News Private API',
    version='0.3.0',
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


@app.exception_handler(ResourceNotFound)
async def not_found_handler(_, exc: ResourceNotFound):
    return JSONResponse(status_code=404, content={'detail': str(exc)})


@app.exception_handler(BadRequestError)
async def bad_request_handler(_, exc: BadRequestError):
    return JSONResponse(status_code=400, content={'detail': str(exc)})


@app.exception_handler(ParseError)
async def parse_error_handler(_, exc: ParseError):
    return JSONResponse(status_code=502, content={'detail': str(exc)})


@app.exception_handler(UpstreamError)
async def upstream_error_handler(_, exc: UpstreamError):
    return JSONResponse(status_code=502, content={'detail': str(exc)})


@app.get('/health', dependencies=[Depends(auth_dependency)], response_model=HealthResponse)
async def health():
    return {'ok': True}


@app.get('/search', dependencies=[Depends(auth_dependency)], response_model=SearchResponse)
async def search(
    request: Request,
    q: str = Query(..., min_length=1),
    kind: Literal['series', 'volume', 'all'] = Query(default='all'),
    mode: Literal['best', 'all'] = Query(default='best'),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.search(query=q, kind=kind, mode=mode, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/search/resolve', dependencies=[Depends(auth_dependency)], response_model=ResolveResponse)
async def search_resolve(
    request: Request,
    q: str = Query(..., min_length=1),
    kind: Literal['series', 'volume', 'all'] = Query(default='all'),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.resolve_search(query=q, kind=kind, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse)
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


@app.get('/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse)
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


@app.get('/admin/cache/stats', dependencies=[Depends(auth_dependency)], response_model=CacheStatsResponse)
async def get_cache_stats(service: MangaNewsService = Depends(get_service)):
    return {'ok': True, 'data': service.cache.stats()}


@app.post('/admin/cache/invalidate', dependencies=[Depends(auth_dependency)], response_model=CacheInvalidateResponse)
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
    ('/v1/news/global', get_global_news, ['GET'], NewsResponse),
    ('/v1/news/series/{slug}', get_series_news, ['GET'], NewsResponse),
    ('/v1/news/volume/{series_slug}/{volume_slug}', get_volume_news, ['GET'], NewsResponse),
    ('/v1/news/volume/by-url', get_volume_news_by_url, ['GET'], NewsResponse),
    ('/v1/planning', get_planning, ['GET'], PlanningResponse),
    ('/v1/admin/cache/stats', get_cache_stats, ['GET'], CacheStatsResponse),
    ('/v1/admin/cache/invalidate', invalidate_cache, ['POST'], CacheInvalidateResponse),
]

for path, endpoint, methods, response_model in _VERSIONED_ALIASES:
    app.add_api_route(
        path,
        endpoint,
        methods=methods,
        response_model=response_model,
        dependencies=[Depends(auth_dependency)],
    )
