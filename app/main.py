from __future__ import annotations

import hashlib
import json
import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import require_api_token
from app.cache import SQLiteCache
from app.config import Settings, get_settings
from app.exceptions import ParseError, ResourceNotFound, UpstreamError
from app.http import AsyncFetcher
from app.manga_news.service import MangaNewsService
from app.models import NewsResponse, PlanningResponse, ResolveResponse, SearchResponse, SeriesResponse, VolumeResponse


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    cache = SQLiteCache(settings.db_path)
    fetcher = AsyncFetcher(settings.user_agent, settings.request_timeout_seconds)
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


def get_service() -> MangaNewsService:
    return app.state.service


def get_settings_dep() -> Settings:
    return app.state.settings


async def auth_dependency(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings_dep),
):
    return await require_api_token(settings, authorization)


@app.exception_handler(ResourceNotFound)
async def not_found_handler(_, exc: ResourceNotFound):
    return JSONResponse(status_code=404, content={'detail': str(exc)})


@app.exception_handler(ParseError)
async def parse_error_handler(_, exc: ParseError):
    return JSONResponse(status_code=502, content={'detail': str(exc)})


@app.exception_handler(UpstreamError)
async def upstream_error_handler(_, exc: UpstreamError):
    return JSONResponse(status_code=502, content={'detail': str(exc)})


def _normalize_etag(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().strip('"')


def _payload_fingerprint(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def finalize_payload_response(payload_model: BaseModel | dict, if_none_match: str | None) -> Response:
    payload = payload_model.model_dump(mode='json') if isinstance(payload_model, BaseModel) else dict(payload_model)
    fingerprint = payload.get('fingerprint')
    if not fingerprint:
        payload_without_fingerprint = {k: v for k, v in payload.items() if k != 'fingerprint'}
        fingerprint = _payload_fingerprint(payload_without_fingerprint)
        payload['fingerprint'] = fingerprint
    headers = {
        'ETag': f'"{fingerprint}"',
        'X-Data-Fingerprint': fingerprint,
    }
    if _normalize_etag(if_none_match) == fingerprint:
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=payload, headers=headers)


@app.get('/health', dependencies=[Depends(auth_dependency)])
async def health():
    return {'ok': True}


@app.get('/search', dependencies=[Depends(auth_dependency)], response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    kind: Literal['series', 'volume', 'all'] = Query(default='all'),
    mode: Literal['best', 'all'] = Query(default='best'),
    limit: int = Query(default=10, ge=1, le=50),
    if_none_match: str | None = Header(default=None, alias='If-None-Match'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.search(query=q, kind=kind, mode=mode, limit=limit)
    return finalize_payload_response(payload, if_none_match)


@app.get('/search/resolve', dependencies=[Depends(auth_dependency)], response_model=ResolveResponse)
async def search_resolve(
    q: str = Query(..., min_length=1),
    kind: Literal['series', 'volume', 'all'] = Query(default='all'),
    if_none_match: str | None = Header(default=None, alias='If-None-Match'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.resolve_search(query=q, kind=kind)
    return finalize_payload_response(payload, if_none_match)


@app.get('/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse)
async def get_series(
    slug: str,
    if_none_match: str | None = Header(default=None, alias='If-None-Match'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series(slug=slug)
    return finalize_payload_response(payload, if_none_match)


@app.get('/series/by-url', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse)
async def get_series_by_url(
    url: str = Query(...),
    if_none_match: str | None = Header(default=None, alias='If-None-Match'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series(url=url)
    return finalize_payload_response(payload, if_none_match)


@app.get('/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse)
async def get_volume(
    series_slug: str,
    volume_slug: str,
    if_none_match: str | None = Header(default=None, alias='If-None-Match'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume(series_slug=series_slug, volume_slug=volume_slug)
    return finalize_payload_response(payload, if_none_match)


@app.get('/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse)
async def get_volume_by_url(
    url: str = Query(...),
    if_none_match: str | None = Header(default=None, alias='If-None-Match'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume(url=url)
    return finalize_payload_response(payload, if_none_match)


@app.get('/news/global', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
async def get_global_news(
    limit: int = Query(default=10, ge=1, le=50),
    if_none_match: str | None = Header(default=None, alias='If-None-Match'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_global_news(limit=limit)
    return finalize_payload_response(payload, if_none_match)


@app.get('/news/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
async def get_series_news(
    slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    if_none_match: str | None = Header(default=None, alias='If-None-Match'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_news(slug=slug, limit=limit)
    return finalize_payload_response(payload, if_none_match)


@app.get('/news/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
async def get_volume_news(
    series_slug: str,
    volume_slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    if_none_match: str | None = Header(default=None, alias='If-None-Match'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(series_slug=series_slug, volume_slug=volume_slug, limit=limit)
    return finalize_payload_response(payload, if_none_match)


@app.get('/news/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
async def get_volume_news_by_url(
    url: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    if_none_match: str | None = Header(default=None, alias='If-None-Match'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(url=url, limit=limit)
    return finalize_payload_response(payload, if_none_match)


@app.get('/planning', dependencies=[Depends(auth_dependency)], response_model=PlanningResponse)
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
    if_none_match: str | None = Header(default=None, alias='If-None-Match'),
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
    return finalize_payload_response(payload, if_none_match)
