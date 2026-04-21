from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

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
    ResolveResponse,
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
    description=(
        'Unofficial self-hostable API over public Manga News pages. '
        'It exposes normalized JSON for fuzzy search, series details, volume details, '
        'news feeds, series editions and release planning. Search results are enriched '
        'with alternate titles and, when known, VF/VO edition counters from the parent series.'
    ),
    docs_url=get_settings().docs_url,
    redoc_url=get_settings().redoc_url,
    lifespan=lifespan,
)


def get_service() -> MangaNewsService:
    return app.state.service


def get_settings_dep() -> Settings:
    return app.state.settings


def _build_envelope_response(payload, request: Request):
    if_none_match = request.headers.get('if-none-match')
    fingerprint = payload.get('fingerprint')
    etag = f'"{fingerprint}"' if fingerprint else None
    headers = {}
    if fingerprint:
        headers['X-Data-Fingerprint'] = fingerprint
        headers['ETag'] = etag
    if etag and if_none_match and if_none_match.strip() == etag:
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


@app.exception_handler(ParseError)
async def parse_error_handler(_, exc: ParseError):
    return JSONResponse(status_code=502, content={'detail': str(exc)})


@app.exception_handler(UpstreamError)
async def upstream_error_handler(_, exc: UpstreamError):
    return JSONResponse(status_code=502, content={'detail': str(exc)})


@app.get('/health', dependencies=[Depends(auth_dependency)], response_model=HealthResponse, tags=['Health'], summary='Health check', description='Returns a minimal OK payload so callers can verify the API is reachable and authorized.')
async def health():
    return {'ok': True}


@app.get('/search', dependencies=[Depends(auth_dependency)], response_model=SearchResponse, tags=['Search'], summary='Search series and volumes', description='Fuzzy search against Manga News series and volume search pages. Results are scored on 100, deduplicated, and enriched with alternate titles. For series results, VF/VO counters come from the series page; for volume results, VF/VO counters come from the parent series when it can be resolved.')
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


@app.get('/search/resolve', dependencies=[Depends(auth_dependency)], response_model=ResolveResponse, tags=['Search'], summary='Resolve one best search match', description='Runs a fuzzy search and returns the best candidate directly with a confidence level plus the candidate list.')
async def search_resolve(
    request: Request,
    q: str = Query(..., min_length=1),
    kind: Literal['series', 'volume', 'all'] = Query(default='all'),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.resolve_search(query=q, kind=kind, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse, tags=['Series'], summary='Get a series by slug', description='Returns the normalized series page with alternate titles, staff, VF/VO counters, stats, links and raw sections when requested.')
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


@app.get('/series/by-url', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse, tags=['Series'], summary='Get a series by direct Manga News URL', description='Same as /series/{slug} but uses a direct Manga News series URL.')
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


@app.get('/series/{slug}/related', dependencies=[Depends(auth_dependency)], response_model=SeriesRelatedResponse, tags=['Series'], summary='Get related links for a series', description='Returns related series, volumes, anime, dossiers, univers and external links extracted from the series page.')
async def get_series_related(request: Request, slug: str, service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(slug=slug)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/by-url/related', dependencies=[Depends(auth_dependency)], response_model=SeriesRelatedResponse, tags=['Series'], summary='Get related links for a series by URL', description='Same as /series/{slug}/related but uses a direct Manga News series URL.')
async def get_series_related_by_url(request: Request, url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(url=url)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/{slug}/editions', dependencies=[Depends(auth_dependency)], response_model=SeriesEditionsResponse, tags=['Series'], summary='List VF/VO editions for a series', description='Returns VF and/or VO edition blocks with edition items, volume numbers, publication dates and cover images.')
async def get_series_editions(
    request: Request,
    slug: str,
    edition: Literal['all', 'vf', 'vo'] = Query(default='all'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(slug=slug, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/by-url/editions', dependencies=[Depends(auth_dependency)], response_model=SeriesEditionsResponse, tags=['Series'], summary='List VF/VO editions for a series by URL', description='Same as /series/{slug}/editions but uses a direct Manga News series URL.')
async def get_series_editions_by_url(
    request: Request,
    url: str = Query(...),
    edition: Literal['all', 'vf', 'vo'] = Query(default='all'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(url=url, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse, tags=['Volume'], summary='Get a volume by slugs', description='Returns the normalized volume page. Alternate titles come from the volume page. VF/VO counters are enriched from the parent series when it can be resolved.')
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


@app.get('/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse, tags=['Volume'], summary='Get a volume by direct Manga News URL', description='Same as /volume/{series_slug}/{volume_slug} but uses a direct Manga News volume URL.')
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


@app.get('/news/global', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get global Manga News RSS news', description='Returns normalized global news items from the public Manga News RSS feed.')
async def get_global_news(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_global_news(limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get news for a series', description='Returns news items extracted from the series news page.')
async def get_series_news(
    request: Request,
    slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_news(slug=slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get news for a volume', description='Returns news items extracted from the volume news page.')
async def get_volume_news(
    request: Request,
    series_slug: str,
    volume_slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(series_slug=series_slug, volume_slug=volume_slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get news for a volume by URL', description='Same as /news/volume/{series_slug}/{volume_slug} but uses a direct Manga News volume URL.')
async def get_volume_news_by_url(
    request: Request,
    url: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(url=url, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/planning', dependencies=[Depends(auth_dependency)], response_model=PlanningResponse, tags=['Planning'], summary='Get the release planning', description='Returns the Manga News release planning for manga VF or manga VO, then applies local filters, sorting and truncation.' )
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
