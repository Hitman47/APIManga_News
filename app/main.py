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
    HealthResponse,
    NewsResponse,
    PlanningResponse,
    SearchResponse,
    SeriesEditionsResponse,
    SeriesRelatedResponse,
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
async def get_series(
    slug: str,
    blocks: str | None = Query(default=None, description='Comma-separated block names. Example: editions,stats'),
    fields: str | None = Query(default=None, description='Comma-separated dot paths. Example: title,vf.volumes'),
    include_raw_sections: bool = Query(default=False),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_series(slug=slug, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)


@app.get('/series/by-url', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse)
async def get_series_by_url(
    url: str = Query(...),
    blocks: str | None = Query(default=None),
    fields: str | None = Query(default=None),
    include_raw_sections: bool = Query(default=False),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_series(url=url, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)


@app.get('/series/{slug}/related', dependencies=[Depends(auth_dependency)], response_model=SeriesRelatedResponse)
async def get_series_related(slug: str, service: MangaNewsService = Depends(get_service)):
    return await service.get_series_related(slug=slug)


@app.get('/series/by-url/related', dependencies=[Depends(auth_dependency)], response_model=SeriesRelatedResponse)
async def get_series_related_by_url(url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    return await service.get_series_related(url=url)


@app.get('/series/{slug}/editions', dependencies=[Depends(auth_dependency)], response_model=SeriesEditionsResponse)
async def get_series_editions(
    slug: str,
    edition: Literal['all', 'vf', 'vo'] = Query(default='all'),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_series_editions(slug=slug, edition=edition)


@app.get('/series/by-url/editions', dependencies=[Depends(auth_dependency)], response_model=SeriesEditionsResponse)
async def get_series_editions_by_url(
    url: str = Query(...),
    edition: Literal['all', 'vf', 'vo'] = Query(default='all'),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_series_editions(url=url, edition=edition)


@app.get('/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse)
async def get_volume(
    series_slug: str,
    volume_slug: str,
    blocks: str | None = Query(default=None, description='Comma-separated block names. Example: release,scores'),
    fields: str | None = Query(default=None, description='Comma-separated dot paths. Example: publication_date,isbn_ean'),
    include_raw_sections: bool = Query(default=False),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_volume(series_slug=series_slug, volume_slug=volume_slug, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)


@app.get('/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse)
async def get_volume_by_url(
    url: str = Query(...),
    blocks: str | None = Query(default=None),
    fields: str | None = Query(default=None),
    include_raw_sections: bool = Query(default=False),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_volume(url=url, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)


@app.get('/news/global', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
async def get_global_news(
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_global_news(limit=limit)


@app.get('/news/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
async def get_series_news(
    slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_series_news(slug=slug, limit=limit)


@app.get('/news/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
async def get_volume_news(
    series_slug: str,
    volume_slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_volume_news(series_slug=series_slug, volume_slug=volume_slug, limit=limit)


@app.get('/news/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=NewsResponse)
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
