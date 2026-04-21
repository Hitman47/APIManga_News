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



TAGS_METADATA = [
    {'name': 'Health', 'description': 'Minimal availability checks.'},
    {'name': 'Search', 'description': 'Search and best-candidate resolution against Manga-News search pages.'},
    {'name': 'Series', 'description': 'Detailed series payloads, related links, and edition listings.'},
    {'name': 'Volume', 'description': 'Detailed volume payloads.'},
    {'name': 'News', 'description': 'Global, series-level, and volume-level news lists.'},
    {'name': 'Planning', 'description': 'Upcoming release planning pages.'},
]

APP_DESCRIPTION = """
API non officielle, auto-hébergeable, qui convertit des pages publiques Manga-News en JSON.

Contrat actuel :
- pas de préfixe `/v1` ;
- pas de routes admin publiques ;
- pas de pagination générique sur les endpoints de liste ;
- authentification optionnelle via `Authorization: Bearer <API_TOKEN>` si `API_TOKEN` est défini.

Flux conseillé :
1. utiliser `/search` ou `/search/resolve` pour obtenir un slug ou un couple `series_slug` / `volume_slug` ;
2. consommer ensuite `/series/{slug}` ou `/volume/{series_slug}/{volume_slug}` ;
3. réutiliser `ETag` et `If-None-Match` pour éviter des téléchargements inutiles.
"""

SEARCH_RESPONSE_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/recherche/?cat=manga-volume-vf&q=Dogs: Bullets & Carnage',
    'cached': False,
    'fetched_at': '2026-04-21T10:10:10+00:00',
    'cache_expires_at': '2026-04-22T10:10:10+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-search-dogs',
    'data': [
        {
            'title': 'Dogs: Bullets & Carnage Vol.1',
            'url': 'https://www.manga-news.com/index.php/manga/Dogs:-Bullets-Carnage/vol-1',
            'kind': 'volume',
            'score': 100,
            'slug': None,
            'series_slug': 'Dogs:-Bullets-Carnage',
            'volume_slug': 'vol-1',
            'number': '1',
            'number_int': 1,
            'edition_label': None,
            'is_special': False,
            'is_one_shot': False,
            'title_vo': 'Dogs: Bullets & Carnage',
            'translated_title': 'Dogs: Bullets & Carnage',
            'vf': {'volumes': 9, 'status': 'En cours'},
            'vo': {'volumes': 10, 'status': 'En pause'},
        }
    ],
}

RESOLVE_RESPONSE_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/recherche/?cat=manga-serie-vf&q=one piece',
    'cached': False,
    'fetched_at': '2026-04-21T10:10:10+00:00',
    'cache_expires_at': '2026-04-22T10:10:10+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-resolve-one-piece',
    'data': {
        'query': 'one piece',
        'kind_requested': 'series',
        'confidence': 'high',
        'best': {
            'title': 'One Piece',
            'url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            'kind': 'series',
            'score': 98,
            'slug': 'One-piece-Edition-originale',
            'series_slug': None,
            'volume_slug': None,
            'number': None,
            'number_int': None,
            'edition_label': None,
            'is_special': None,
            'is_one_shot': None,
            'title_vo': 'ワンピース',
            'translated_title': 'One Piece',
            'vf': {'volumes': 112, 'status': 'En cours'},
            'vo': {'volumes': 114, 'status': 'En cours'},
        },
        'candidates': [],
    },
}

SERIES_RESPONSE_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
    'cached': False,
    'fetched_at': '2026-04-21T10:10:10+00:00',
    'cache_expires_at': '2026-04-22T10:10:10+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-series',
    'data': {
        'title': 'One Piece',
        'title_vo': 'ワンピース',
        'translated_title': 'One Piece',
        'publisher_fr': 'Glénat',
        'publisher_vo': 'Shûeisha',
        'genres': ['Aventure', 'Fantastique'],
        'vf': {'volumes': 112, 'status': 'En cours'},
        'vo': {'volumes': 114, 'status': 'En cours'},
        'last_release_date': '2026-04-08',
        'next_release_date': '2026-05-06',
        'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
    },
}

VOLUME_RESPONSE_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
    'cached': False,
    'fetched_at': '2026-04-21T10:10:10+00:00',
    'cache_expires_at': '2026-04-28T10:10:10+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-volume',
    'data': {
        'title': 'One Piece - Tome 91',
        'series_title': 'One Piece',
        'number': '91',
        'number_int': 91,
        'title_vo': 'ワンピース',
        'translated_title': 'One Piece',
        'publication_date': '2019-07-03',
        'isbn_ean': '9782344037102',
        'publisher_fr': 'Glénat',
        'vf': {'volumes': 112, 'status': 'En cours'},
        'vo': {'volumes': 114, 'status': 'En cours'},
        'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
    },
}

NEWS_RESPONSE_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/feed/news',
    'cached': False,
    'fetched_at': '2026-04-21T10:10:10+00:00',
    'cache_expires_at': '2026-04-21T16:10:10+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-news',
    'data': [
        {
            'title': 'La saison 2 de la série live One Piece disponible sur Netflix !',
            'url': 'https://www.manga-news.com/index.php/actus/2026/03/10/La-saison-2-de-la-serie-live-One-Piece-disponible-sur-Netflix',
            'published_at': '2026-03-10',
            'excerpt': "C'est aujourd'hui !",
            'comments': 0,
            'category': 'Manga',
        }
    ],
}

PLANNING_RESPONSE_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/planning/',
    'cached': False,
    'fetched_at': '2026-04-21T10:10:10+00:00',
    'cache_expires_at': '2026-04-21T22:10:10+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-plan',
    'data': {
        'section': 'manga-vf',
        'year': 2026,
        'month': 4,
        'page': 1,
        'filters': {'publisher': 'Glénat', 'query': None, 'date_from': None, 'date_to': None},
        'sort': 'date_asc',
        'total_items': 1,
        'items': [
            {
                'title': 'One Piece Vol.110',
                'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
                'release_date': '2026-04-27',
                'authors': ['Eiichirô ODA'],
                'publisher': 'Glénat',
                'summary': 'Le retour des Mugiwara dans un nouveau volume.',
                'featured': True,
                'series_slug': 'One-Piece',
                'volume_slug': 'vol-110',
                'number': '110',
                'number_int': 110,
                'edition_label': None,
                'is_special': False,
                'is_one_shot': False,
            }
        ],
    },
}

app = FastAPI(
    title='Manga News Private API',
    version='0.3.0',
    description=APP_DESCRIPTION,
    openapi_tags=TAGS_METADATA,
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
    return JSONResponse(status_code=404, content={'code': 'RESOURCE_NOT_FOUND', 'detail': str(exc)})


@app.exception_handler(ParseError)
async def parse_error_handler(_, exc: ParseError):
    return JSONResponse(status_code=502, content={'code': 'UPSTREAM_PARSE_ERROR', 'detail': str(exc)})


@app.exception_handler(UpstreamError)
async def upstream_error_handler(_, exc: UpstreamError):
    return JSONResponse(status_code=502, content={'code': 'UPSTREAM_FETCH_ERROR', 'detail': str(exc)})


@app.get('/health', dependencies=[Depends(auth_dependency)], response_model=HealthResponse, tags=['Health'], summary='Health check', description='Returns a minimal availability payload. This is the quickest way to verify that the service is alive and, if configured, that the Bearer token is accepted.')
async def health():
    return {'ok': True}


@app.get('/search', dependencies=[Depends(auth_dependency)], response_model=SearchResponse, tags=['Search'], summary='Search Manga-News titles', description='Runs one or more Manga-News search pages, scores the returned candidates, and enriches the results with alternate titles. For series and volumes, the response may also include VF/VO counters from the parent series when available.', responses={200: {'description': 'List of matching series and/or volumes.', 'content': {'application/json': {'example': SEARCH_RESPONSE_EXAMPLE}}}})
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


@app.get('/search/resolve', dependencies=[Depends(auth_dependency)], response_model=ResolveResponse, tags=['Search'], summary='Resolve a query to the best candidate', description='Wraps `/search` and returns the best candidate plus a qualitative confidence flag. Use this when the caller wants one best slug instead of manually ranking candidates.', responses={200: {'description': 'Best match and candidate list.', 'content': {'application/json': {'example': RESOLVE_RESPONSE_EXAMPLE}}}})
async def search_resolve(
    request: Request,
    q: str = Query(..., min_length=1),
    kind: Literal['series', 'volume', 'all'] = Query(default='all'),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.resolve_search(query=q, kind=kind, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse, tags=['Series'], summary='Get a series by slug', description='Fetches a Manga-News series page and returns a normalized JSON payload. Use `blocks` and `fields` to project only the parts you need.', responses={200: {'description': 'Normalized series payload.', 'content': {'application/json': {'example': SERIES_RESPONSE_EXAMPLE}}}})
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


@app.get('/series/by-url', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse, tags=['Series'], summary='Get a series by direct Manga-News URL', description='Same contract as `/series/{slug}`, but starts from a full Manga-News series URL.')
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


@app.get('/series/{slug}/related', dependencies=[Depends(auth_dependency)], response_model=SeriesRelatedResponse, tags=['Series'], summary='Get related links for a series', description='Returns the `related` block only, grouped by link category.')
async def get_series_related(request: Request, slug: str, service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(slug=slug)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/by-url/related', dependencies=[Depends(auth_dependency)], response_model=SeriesRelatedResponse, tags=['Series'], summary='Get related links for a series by URL', description='Same contract as `/series/{slug}/related`, but starts from a direct URL.')
async def get_series_related_by_url(request: Request, url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(url=url)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/{slug}/editions', dependencies=[Depends(auth_dependency)], response_model=SeriesEditionsResponse, tags=['Series'], summary='List VF/VO editions for a series', description='Fetches the Manga-News editions pages and returns edition blocks for VF, VO, or both.')
async def get_series_editions(
    request: Request,
    slug: str,
    edition: Literal['all', 'vf', 'vo'] = Query(default='all'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(slug=slug, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/by-url/editions', dependencies=[Depends(auth_dependency)], response_model=SeriesEditionsResponse, tags=['Series'], summary='List VF/VO editions by direct URL', description='Same contract as `/series/{slug}/editions`, but starts from a direct URL.')
async def get_series_editions_by_url(
    request: Request,
    url: str = Query(...),
    edition: Literal['all', 'vf', 'vo'] = Query(default='all'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(url=url, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse, tags=['Volume'], summary='Get a volume by slugs', description='Fetches a Manga-News volume page and returns a normalized JSON payload. The response also tries to attach parent-series VF/VO counters.', responses={200: {'description': 'Normalized volume payload.', 'content': {'application/json': {'example': VOLUME_RESPONSE_EXAMPLE}}}})
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


@app.get('/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse, tags=['Volume'], summary='Get a volume by direct Manga-News URL', description='Same contract as `/volume/{series_slug}/{volume_slug}`, but starts from a direct URL.')
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


@app.get('/news/global', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get global Manga-News items', description='Returns a normalized list of global news items from the public Manga-News feed.', responses={200: {'description': 'Normalized news list.', 'content': {'application/json': {'example': NEWS_RESPONSE_EXAMPLE}}}})
async def get_global_news(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_global_news(limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get news for a series', description='Returns the news page attached to a series slug.')
async def get_series_news(
    request: Request,
    slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_news(slug=slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get news for a volume', description='Returns the news page attached to a specific volume.')
async def get_volume_news(
    request: Request,
    series_slug: str,
    volume_slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(series_slug=series_slug, volume_slug=volume_slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get volume news by direct URL', description='Same contract as `/news/volume/{series_slug}/{volume_slug}`, but starts from a direct URL.')
async def get_volume_news_by_url(
    request: Request,
    url: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(url=url, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/planning', dependencies=[Depends(auth_dependency)], response_model=PlanningResponse, tags=['Planning'], summary='Get a planning page', description='Fetches a Manga-News planning page, applies optional publisher/query/date filters, and returns normalized planning items.', responses={200: {'description': 'Normalized planning page.', 'content': {'application/json': {'example': PLANNING_RESPONSE_EXAMPLE}}}})
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
