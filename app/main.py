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
from app.models import HealthResponse, NewsResponse, PlanningResponse, SearchResponse, SeriesResponse, VolumeResponse


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
        'API privée auto-hébergée pour rechercher des séries et volumes sur Manga News, '
        'lire les fiches détaillées, les news associées et le planning des sorties.'
    ),
    docs_url=get_settings().docs_url,
    redoc_url=get_settings().redoc_url,
    lifespan=lifespan,
    openapi_tags=[
        {'name': 'system', 'description': 'Santé et introspection de service.'},
        {'name': 'search', 'description': 'Recherche de séries et de volumes.'},
        {'name': 'series', 'description': 'Fiches détaillées de séries.'},
        {'name': 'volumes', 'description': 'Fiches détaillées de volumes.'},
        {'name': 'news', 'description': 'News globales ou liées à une série / un volume.'},
        {'name': 'planning', 'description': 'Planning des sorties manga VF et VO.'},
    ],
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


@app.get('/health', dependencies=[Depends(auth_dependency)], tags=['system'], response_model=HealthResponse, summary='Vérifie que l’API répond')
async def health() -> HealthResponse:
    return HealthResponse(ok=True)


@app.get('/search', dependencies=[Depends(auth_dependency)], tags=['search'], response_model=SearchResponse, summary='Recherche des séries ou volumes')
async def search(
    q: str = Query(..., min_length=1, description='Texte recherché.'),
    kind: Literal['series', 'volume', 'all'] = Query(default='all', description='Limite la recherche aux séries, aux volumes ou aux deux.'),
    mode: Literal['best', 'all'] = Query(default='best', description='Renvoie seulement le meilleur match ou tous les résultats pertinents.'),
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximal de résultats renvoyés.'),
    service: MangaNewsService = Depends(get_service),
):
    return await service.search(query=q, kind=kind, mode=mode, limit=limit)


@app.get('/series/{slug}', dependencies=[Depends(auth_dependency)], tags=['series'], response_model=SeriesResponse, summary='Récupère une fiche série par slug')
async def get_series(slug: str, service: MangaNewsService = Depends(get_service)):
    return await service.get_series(slug=slug)


@app.get('/series/by-url', dependencies=[Depends(auth_dependency)], tags=['series'], response_model=SeriesResponse, summary='Récupère une fiche série à partir de son URL Manga News')
async def get_series_by_url(url: str = Query(..., description='URL absolue d’une fiche série Manga News.'), service: MangaNewsService = Depends(get_service)):
    return await service.get_series(url=url)


@app.get('/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], tags=['volumes'], response_model=VolumeResponse, summary='Récupère une fiche volume par slug de série et slug de volume')
async def get_volume(series_slug: str, volume_slug: str, service: MangaNewsService = Depends(get_service)):
    return await service.get_volume(series_slug=series_slug, volume_slug=volume_slug)


@app.get('/volume/by-url', dependencies=[Depends(auth_dependency)], tags=['volumes'], response_model=VolumeResponse, summary='Récupère une fiche volume à partir de son URL Manga News')
async def get_volume_by_url(url: str = Query(..., description='URL absolue d’une fiche volume Manga News.'), service: MangaNewsService = Depends(get_service)):
    return await service.get_volume(url=url)


@app.get('/news/global', dependencies=[Depends(auth_dependency)], tags=['news'], response_model=NewsResponse, summary='Récupère les news globales du site')
async def get_global_news(
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximal de news renvoyées.'),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_global_news(limit=limit)


@app.get('/news/series/{slug}', dependencies=[Depends(auth_dependency)], tags=['news'], response_model=NewsResponse, summary='Récupère les news liées à une série')
async def get_series_news(
    slug: str,
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximal de news renvoyées.'),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_series_news(slug=slug, limit=limit)


@app.get('/news/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], tags=['news'], response_model=NewsResponse, summary='Récupère les news liées à un volume')
async def get_volume_news(
    series_slug: str,
    volume_slug: str,
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximal de news renvoyées.'),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_volume_news(series_slug=series_slug, volume_slug=volume_slug, limit=limit)


@app.get('/news/volume/by-url', dependencies=[Depends(auth_dependency)], tags=['news'], response_model=NewsResponse, summary='Récupère les news d’un volume à partir de son URL')
async def get_volume_news_by_url(
    url: str = Query(..., description='URL absolue d’une fiche volume Manga News.'),
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximal de news renvoyées.'),
    service: MangaNewsService = Depends(get_service),
):
    return await service.get_volume_news(url=url, limit=limit)


@app.get('/planning', dependencies=[Depends(auth_dependency)], tags=['planning'], response_model=PlanningResponse, summary='Récupère le planning des sorties')
async def get_planning(
    section: Literal['manga-vf', 'manga-vo'] = Query(default='manga-vf', description='Planning VF ou VO.'),
    year: int | None = Query(default=None, ge=1900, le=2100, description='Année ciblée côté planning Manga News.'),
    month: int | None = Query(default=None, ge=1, le=12, description='Mois ciblé côté planning Manga News.'),
    page: int = Query(default=1, ge=1, le=100, description='Page du planning côté site.'),
    publisher: str | None = Query(default=None, description='Filtre local sur l’éditeur.'),
    q: str | None = Query(default=None, min_length=1, description='Filtre local par texte sur le titre, les auteurs et l’éditeur.'),
    date_from: str | None = Query(default=None, description='Filtre local inclusif au format YYYY-MM-DD.'),
    date_to: str | None = Query(default=None, description='Filtre local inclusif au format YYYY-MM-DD.'),
    sort: Literal['date_asc', 'date_desc', 'title_asc', 'title_desc'] = Query(default='date_asc', description='Tri local des résultats.'),
    limit: int = Query(default=25, ge=1, le=100, description='Nombre maximal d’éléments renvoyés après filtrage.'),
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
