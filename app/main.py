from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse

from app.auth import require_api_token
from app.cache import SQLiteCache
from app.config import Settings, get_settings
from app.exceptions import ParseError, ResourceNotFound, UpstreamError
from app.http import AsyncFetcher
from app.logging_utils import log_event, reset_request_id, set_request_id
from app.manga_news.service import MangaNewsService
from app.models import Envelope, ErrorEnvelope, HealthResponse


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format='%(message)s' if settings.log_format.lower() == 'json' else '%(asctime)s %(levelname)s %(name)s: %(message)s',
        force=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    cache = SQLiteCache(settings.db_path)
    fetcher = AsyncFetcher(settings.user_agent, settings.request_timeout_seconds, log_json=settings.log_format.lower() == 'json')
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=cache)
    app.state.settings = settings
    app.state.service = service
    try:
        yield
    finally:
        await fetcher.close()


app = FastAPI(
    title='Manga News Private API',
    version='0.2.0',
    docs_url=get_settings().docs_url,
    redoc_url=get_settings().redoc_url,
    lifespan=lifespan,
)


@app.middleware('http')
async def request_context_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    token = set_request_id(request_id)
    started = time.perf_counter()
    settings = getattr(app.state, 'settings', get_settings())
    try:
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers['X-Request-ID'] = request_id
        log_event(
            logging.getLogger('app.access'),
            logging.INFO,
            'request_complete',
            json_mode=settings.log_format.lower() == 'json',
            method=request.method,
            path=request.url.path,
            query=str(request.url.query),
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(
            logging.getLogger('app.access'),
            logging.ERROR,
            'request_error',
            json_mode=settings.log_format.lower() == 'json',
            method=request.method,
            path=request.url.path,
            query=str(request.url.query),
            duration_ms=duration_ms,
        )
        raise
    finally:
        reset_request_id(token)


def get_service() -> MangaNewsService:
    return app.state.service


def get_settings_dep() -> Settings:
    return app.state.settings


async def auth_dependency(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings_dep),
):
    return await require_api_token(settings, authorization)


def _error_response(status_code: int, error_code: str, detail: str) -> JSONResponse:
    payload = ErrorEnvelope(error_code=error_code, detail=detail)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


@app.exception_handler(ResourceNotFound)
async def not_found_handler(_, exc: ResourceNotFound):
    return _error_response(404, 'not_found', str(exc))


@app.exception_handler(ParseError)
async def parse_error_handler(_, exc: ParseError):
    return _error_response(502, 'parse_error', str(exc))


@app.exception_handler(UpstreamError)
async def upstream_error_handler(_, exc: UpstreamError):
    return _error_response(502, 'upstream_error', str(exc))


@app.get('/health', response_model=HealthResponse, dependencies=[Depends(auth_dependency)])
async def health():
    return {'ok': True}


@app.get('/search', response_model=Envelope, responses={404: {'model': ErrorEnvelope}, 502: {'model': ErrorEnvelope}}, dependencies=[Depends(auth_dependency)])
async def search(
    q: str = Query(..., min_length=1),
    kind: Literal['series', 'volume', 'all'] = Query(default='all'),
    mode: Literal['best', 'all'] = Query(default='best'),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.search(query=q, kind=kind, mode=mode, limit=limit)


@app.get('/series/{slug}', response_model=Envelope, responses={404: {'model': ErrorEnvelope}, 502: {'model': ErrorEnvelope}}, dependencies=[Depends(auth_dependency)])
async def get_series(slug: str, service: MangaNewsService = Depends(get_service)):
    return await service.get_series(slug=slug)


@app.get('/series/by-url', response_model=Envelope, responses={404: {'model': ErrorEnvelope}, 502: {'model': ErrorEnvelope}}, dependencies=[Depends(auth_dependency)])
async def get_series_by_url(url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    return await service.get_series(url=url)


@app.get('/volume/{series_slug}/{volume_slug}', response_model=Envelope, responses={404: {'model': ErrorEnvelope}, 502: {'model': ErrorEnvelope}}, dependencies=[Depends(auth_dependency)])
async def get_volume(series_slug: str, volume_slug: str, service: MangaNewsService = Depends(get_service)):
    return await service.get_volume(series_slug=series_slug, volume_slug=volume_slug)


@app.get('/volume/by-url', response_model=Envelope, responses={404: {'model': ErrorEnvelope}, 502: {'model': ErrorEnvelope}}, dependencies=[Depends(auth_dependency)])
async def get_volume_by_url(url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    return await service.get_volume(url=url)


@app.get('/news/global', response_model=Envelope, responses={404: {'model': ErrorEnvelope}, 502: {'model': ErrorEnvelope}}, dependencies=[Depends(auth_dependency)])
async def get_global_news(
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_global_news(limit=limit)


@app.get('/news/series/{slug}', response_model=Envelope, responses={404: {'model': ErrorEnvelope}, 502: {'model': ErrorEnvelope}}, dependencies=[Depends(auth_dependency)])
async def get_series_news(
    slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_series_news(slug=slug, limit=limit)


@app.get('/news/volume/{series_slug}/{volume_slug}', response_model=Envelope, responses={404: {'model': ErrorEnvelope}, 502: {'model': ErrorEnvelope}}, dependencies=[Depends(auth_dependency)])
async def get_volume_news(
    series_slug: str,
    volume_slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_volume_news(series_slug=series_slug, volume_slug=volume_slug, limit=limit)


@app.get('/news/volume/by-url', response_model=Envelope, responses={404: {'model': ErrorEnvelope}, 502: {'model': ErrorEnvelope}}, dependencies=[Depends(auth_dependency)])
async def get_volume_news_by_url(
    url: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_volume_news(url=url, limit=limit)


@app.get('/planning', response_model=Envelope, responses={404: {'model': ErrorEnvelope}, 502: {'model': ErrorEnvelope}}, dependencies=[Depends(auth_dependency)])
async def get_planning(
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
    return await service.get_planning(
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


@app.get('/planning/watch', response_model=Envelope, responses={404: {'model': ErrorEnvelope}, 502: {'model': ErrorEnvelope}}, dependencies=[Depends(auth_dependency)])
async def get_planning_watch(
    section: Literal['manga-vf', 'manga-vo'] = Query(default='manga-vf'),
    year: int | None = Query(default=None, ge=1900, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    page: int = Query(default=1, ge=1, le=100),
    publisher: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    sort: Literal['date_asc', 'date_desc', 'title_asc', 'title_desc'] = Query(default='date_asc'),
    limit: int = Query(default=100, ge=1, le=500),
    watch_id: str | None = Query(default=None),
    previous_fingerprint: str | None = Query(default=None),
    commit_snapshot: bool = Query(default=True),
    preview_limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_planning_watch(
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
        watch_id=watch_id,
        previous_fingerprint=previous_fingerprint,
        commit_snapshot=commit_snapshot,
        preview_limit=preview_limit,
    )


@app.get('/admin/cache/stats', response_model=Envelope, dependencies=[Depends(auth_dependency)])
def cache_stats(service: MangaNewsService = Depends(get_service)):
    return service.cache_stats()


@app.post('/admin/cache/invalidate', response_model=Envelope, dependencies=[Depends(auth_dependency)])
def invalidate_cache(
    cache_key: str | None = Query(default=None),
    namespace: str | None = Query(default=None),
    resource_url: str | None = Query(default=None),
    expired_only: bool = Query(default=False),
    all_entries: bool = Query(default=False),
    service: MangaNewsService = Depends(get_service),
):
    return service.invalidate_cache(
        cache_key=cache_key,
        namespace=namespace,
        resource_url=resource_url,
        expired_only=expired_only,
        all_entries=all_entries,
    )
