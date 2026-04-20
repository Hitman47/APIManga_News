from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, Query
from fastapi.responses import JSONResponse

from app.auth import require_api_token
from app.cache import SQLiteCache
from app.config import Settings, get_settings
from app.exceptions import ParseError, ResourceNotFound, UpstreamError
from app.http import AsyncFetcher
from app.manga_news.service import MangaNewsService
from app.models import (
    ComparisonResponse,
    Envelope,
    HealthResponse,
    MachineSeriesSummaryResponse,
    MachineVolumeSummaryResponse,
    NewsListResponse,
    PlanningResponse,
    SearchResponse,
    SeriesNewsSummaryResponse,
    SeriesReleaseSummaryResponse,
    SeriesResponse,
    VolumeResponse,
)


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


@app.get('/health', dependencies=[Depends(auth_dependency)], response_model=HealthResponse)
async def health():
    return {'ok': True}


@app.get('/search', dependencies=[Depends(auth_dependency)], response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    kind: Literal['series', 'volume', 'all'] = Query(default='all'),
    mode: Literal['best', 'all'] = Query(default='best'),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.search(query=q, kind=kind, mode=mode, limit=limit)


@app.get('/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse)
async def get_series(slug: str, service: MangaNewsService = Depends(get_service)):
    return await service.get_series(slug=slug)


@app.get('/series/by-url', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse)
async def get_series_by_url(url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    return await service.get_series(url=url)


@app.get('/series/{slug}/select', dependencies=[Depends(auth_dependency)], response_model=Envelope)
async def select_series_fields(
    slug: str,
    fields: str = Query(..., description='Comma-separated list of dotted fields, e.g. title,vf.volumes'),
    service: MangaNewsService = Depends(get_service),
):
    return await service.select_series_fields(slug=slug, fields=fields)


@app.get('/series/by-url/select', dependencies=[Depends(auth_dependency)], response_model=Envelope)
async def select_series_fields_by_url(
    url: str = Query(...),
    fields: str = Query(..., description='Comma-separated list of dotted fields, e.g. title,vf.volumes'),
    service: MangaNewsService = Depends(get_service),
):
    return await service.select_series_fields(url=url, fields=fields)


@app.get('/series/{slug}/summary', dependencies=[Depends(auth_dependency)], response_model=MachineSeriesSummaryResponse)
async def get_series_summary(slug: str, service: MangaNewsService = Depends(get_service)):
    return await service.get_series_summary(slug=slug)


@app.get('/series/by-url/summary', dependencies=[Depends(auth_dependency)], response_model=MachineSeriesSummaryResponse)
async def get_series_summary_by_url(url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    return await service.get_series_summary(url=url)


@app.get('/series/{slug}/release-summary', dependencies=[Depends(auth_dependency)], response_model=SeriesReleaseSummaryResponse)
async def get_series_release_summary(slug: str, service: MangaNewsService = Depends(get_service)):
    return await service.get_series_release_summary(slug=slug)


@app.get('/series/by-url/release-summary', dependencies=[Depends(auth_dependency)], response_model=SeriesReleaseSummaryResponse)
async def get_series_release_summary_by_url(url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    return await service.get_series_release_summary(url=url)


@app.get('/series/{slug}/news-summary', dependencies=[Depends(auth_dependency)], response_model=SeriesNewsSummaryResponse)
async def get_series_news_summary(
    slug: str,
    limit: int = Query(default=20, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_series_news_summary(slug=slug, limit=limit)


@app.get('/series/by-url/news-summary', dependencies=[Depends(auth_dependency)], response_model=SeriesNewsSummaryResponse)
async def get_series_news_summary_by_url(
    url: str = Query(...),
    limit: int = Query(default=20, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_series_news_summary(url=url, limit=limit)


@app.get('/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse)
async def get_volume(series_slug: str, volume_slug: str, service: MangaNewsService = Depends(get_service)):
    return await service.get_volume(series_slug=series_slug, volume_slug=volume_slug)


@app.get('/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse)
async def get_volume_by_url(url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    return await service.get_volume(url=url)


@app.get('/volume/{series_slug}/{volume_slug}/select', dependencies=[Depends(auth_dependency)], response_model=Envelope)
async def select_volume_fields(
    series_slug: str,
    volume_slug: str,
    fields: str = Query(..., description='Comma-separated list of dotted fields, e.g. title,publication_date,isbn_ean'),
    service: MangaNewsService = Depends(get_service),
):
    return await service.select_volume_fields(series_slug=series_slug, volume_slug=volume_slug, fields=fields)


@app.get('/volume/by-url/select', dependencies=[Depends(auth_dependency)], response_model=Envelope)
async def select_volume_fields_by_url(
    url: str = Query(...),
    fields: str = Query(..., description='Comma-separated list of dotted fields, e.g. title,publication_date,isbn_ean'),
    service: MangaNewsService = Depends(get_service),
):
    return await service.select_volume_fields(url=url, fields=fields)


@app.get('/volume/{series_slug}/{volume_slug}/summary', dependencies=[Depends(auth_dependency)], response_model=MachineVolumeSummaryResponse)
async def get_volume_summary(series_slug: str, volume_slug: str, service: MangaNewsService = Depends(get_service)):
    return await service.get_volume_summary(series_slug=series_slug, volume_slug=volume_slug)


@app.get('/volume/by-url/summary', dependencies=[Depends(auth_dependency)], response_model=MachineVolumeSummaryResponse)
async def get_volume_summary_by_url(url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    return await service.get_volume_summary(url=url)


@app.get('/compare/series', dependencies=[Depends(auth_dependency)], response_model=ComparisonResponse)
async def compare_series(
    left_slug: str | None = Query(default=None),
    right_slug: str | None = Query(default=None),
    left_url: str | None = Query(default=None),
    right_url: str | None = Query(default=None),
    service: MangaNewsService = Depends(get_service),
):
    return await service.compare_series(left_slug=left_slug, right_slug=right_slug, left_url=left_url, right_url=right_url)


@app.get('/compare/volume', dependencies=[Depends(auth_dependency)], response_model=ComparisonResponse)
async def compare_volume(
    left_series_slug: str | None = Query(default=None),
    left_volume_slug: str | None = Query(default=None),
    right_series_slug: str | None = Query(default=None),
    right_volume_slug: str | None = Query(default=None),
    left_url: str | None = Query(default=None),
    right_url: str | None = Query(default=None),
    service: MangaNewsService = Depends(get_service),
):
    return await service.compare_volume(
        left_series_slug=left_series_slug,
        left_volume_slug=left_volume_slug,
        right_series_slug=right_series_slug,
        right_volume_slug=right_volume_slug,
        left_url=left_url,
        right_url=right_url,
    )


@app.get('/news/global', dependencies=[Depends(auth_dependency)], response_model=NewsListResponse)
async def get_global_news(
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_global_news(limit=limit)


@app.get('/news/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=NewsListResponse)
async def get_series_news(
    slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_series_news(slug=slug, limit=limit)


@app.get('/news/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=NewsListResponse)
async def get_volume_news(
    series_slug: str,
    volume_slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_volume_news(series_slug=series_slug, volume_slug=volume_slug, limit=limit)


@app.get('/news/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=NewsListResponse)
async def get_volume_news_by_url(
    url: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_volume_news(url=url, limit=limit)


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
