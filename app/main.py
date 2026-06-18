from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Path as ApiPath, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from app.auth import require_api_token
from app.cache import SQLiteCache
from app.config import Settings, get_settings
from app.exceptions import ParseError, ResourceNotFound, UpstreamError
from app.http import AsyncFetcher
from app.logging_utils import get_request_id, reset_request_id, set_request_id
from app.manga_news.service import MangaNewsService
from app.metrics import MetricsStore
from app.models import (
    HealthResponse,
    NewsResponse,
    PlanningResponse,
    ResolveResponse,
    RuntimeObservabilityResponse,
    SearchResponse,
    SeriesEditionsResponse,
    SeriesRelatedResponse,
    SeriesResponse,
    ReleaseStateResponse,
    VolumeResponse,
)


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = getattr(app.state, 'settings', get_settings())
    configure_logging(settings)
    metrics = MetricsStore()
    cache = SQLiteCache(
        settings.db_path,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        memory_entries=settings.cache_memory_entries,
        metrics=metrics,
    )
    fetcher = AsyncFetcher(
        settings.user_agent,
        settings.request_timeout_seconds,
        max_retries=settings.request_max_retries,
        backoff_seconds=settings.request_backoff_seconds,
        max_concurrency=settings.request_max_concurrency,
        log_json=settings.log_format == 'json',
        metrics=metrics,
    )
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=cache, metrics=metrics)
    app.state.settings = settings
    app.state.metrics = metrics
    app.state.service = service
    try:
        yield
    finally:
        await fetcher.close()


TAGS_METADATA = [
    {'name': 'Health', 'description': 'Minimal availability checks and runtime observability helpers.'},
    {'name': 'Observability', 'description': 'Request correlation headers, rolling metrics, and cache/runtime inspection.'},
    {'name': 'Search', 'description': 'Search Manga-News public pages and resolve the best candidate.'},
    {'name': 'Series', 'description': 'Detailed series payloads, related links, and edition listings.'},
    {'name': 'Volume', 'description': 'Detailed volume payloads.'},
    {'name': 'News', 'description': 'Global, series-level, and volume-level news feeds.'},
    {'name': 'Planning', 'description': 'Upcoming release planning pages.'},
]

APP_DESCRIPTION = """
API non officielle, auto-hébergeable, qui transforme des pages publiques Manga-News en JSON.

Points importants :
- pas de préfixe `/v1` ;
- pas de routes admin publiques ;
- authentification optionnelle via `Authorization: Bearer <API_TOKEN>` si `API_TOKEN` est défini ;
- `ETag` / `If-None-Match` disponibles sur les réponses enveloppées ;
- `X-Request-Id` renvoyé sur toutes les réponses pour corréler les logs ;
- les réponses de recherche et de résolution peuvent être enrichies avec `title_vo`, `translated_title`, et, quand l'information existe, les compteurs `vf` / `vo` issus de la fiche série parente ;
- les réponses volume restent légères par défaut et n'hydratent `vf` / `vo` que si `include_parent_editions=true` ou si la configuration serveur l'active explicitement ;
- une route technique `/health/runtime` expose les métriques agrégées, les derniers événements de perf et l'état du cache local.

Flux conseillé :
1. utiliser `/search` ou `/search/resolve` pour obtenir un slug ou un couple `series_slug` / `volume_slug` ;
2. consommer ensuite `/series/{slug}` ou `/volume/{series_slug}/{volume_slug}` ;
3. réutiliser `ETag` et `If-None-Match` pour limiter les téléchargements inutiles.
""".strip()

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
            'series_slug': 'One-piece-Edition-originale',
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
                'title': 'One Piece Vol.112',
                'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-112',
                'release_date': '2026-05-06',
                'authors': ['Eiichirô ODA'],
                'publisher': 'Glénat',
                'summary': 'Nouveau volume de la série.',
                'featured': True,
                'series_slug': 'One-Piece',
                'volume_slug': 'vol-112',
                'number': '112',
                'number_int': 112,
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


@app.middleware('http')
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get('X-Request-Id') or uuid4().hex
    token = set_request_id(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        metrics = getattr(app.state, 'metrics', None)
        if metrics is not None:
            metrics.record_request(
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
                request_id=request_id,
            )
        reset_request_id(token)
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers['X-Request-Id'] = request_id
    metrics = getattr(app.state, 'metrics', None)
    if metrics is not None:
        metrics.record_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )
    reset_request_id(token)
    return response


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


@app.get(
    '/health',
    dependencies=[Depends(auth_dependency)],
    response_model=HealthResponse,
    tags=['Health'],
    summary='Check API availability',
    description='Retourne simplement `{ "ok": true }` si l’application répond et que la vérification d’authentification éventuelle a réussi.',
)
async def health():
    return {'ok': True}


@app.get(
    '/health/runtime',
    dependencies=[Depends(auth_dependency)],
    response_model=RuntimeObservabilityResponse,
    tags=['Observability'],
    summary='Inspect runtime metrics and cache state',
    description=(
        'Route technique destinée au diagnostic local. Elle renvoie les compteurs agrégés, les timings roulants, '
        'les derniers événements de performance, l’état du cache SQLite/L1, ainsi que les comportements par défaut actifs '
        'pour `/search`, `/search/resolve` et `/volume`. Toutes les réponses incluent aussi `X-Request-Id`.'
    ),
)
async def health_runtime(
    include_recent: bool = Query(default=True, description='Inclure les dernières requêtes et événements de performance.'),
):
    metrics = getattr(app.state, 'metrics', None)
    service = getattr(app.state, 'service', None)
    settings = get_settings()
    snapshot = metrics.snapshot(include_recent=include_recent).model_dump() if metrics is not None else {}
    cache_stats = service.cache.stats() if service is not None else {}
    return {
        'ok': True,
        'request_id': get_request_id(),
        'metrics': snapshot,
        'cache': cache_stats,
        'defaults': {
            'search_default_enrich': settings.search_default_enrich,
            'search_default_include_editions': settings.search_default_include_editions,
            'search_default_prefer_main_series': settings.search_default_prefer_main_series,
            'search_default_include_related': settings.search_default_include_related,
            'search_default_include_books': settings.search_default_include_books,
            'volume_default_include_parent_editions': settings.volume_default_include_parent_editions,
            'search_source_concurrency': settings.search_source_concurrency,
            'search_enrichment_concurrency': settings.search_enrichment_concurrency,
            'request_max_retries': settings.request_max_retries,
            'request_backoff_seconds': settings.request_backoff_seconds,
            'request_max_concurrency': settings.request_max_concurrency,
            'sqlite_busy_timeout_ms': settings.sqlite_busy_timeout_ms,
            'cache_memory_entries': settings.cache_memory_entries,
        },
        'service': {
            'cache_schema_version': getattr(service, 'cache_schema_version', None),
            'inflight_singleflight': service.inflight_count() if service is not None else 0,
        },
    }


@app.get(
    '/search',
    dependencies=[Depends(auth_dependency)],
    response_model=SearchResponse,
    tags=['Search'],
    summary='Search Manga-News public pages',
    description=(
        'Recherche des séries et/ou volumes à partir d’une requête libre. '
        'Les résultats sont scorés après normalisation du texte. Quand `enrich`, `include_editions`, '
        '`prefer_main_series`, `include_related` ou `include_books` sont absents, '
        'la route applique les defaults serveur documentés dans `.env.example`. '
        "L'enrichissement peut ajouter `title_vo`, `translated_title`, `source_type`, `media_kind`, `relation_kind`, `root_series_slug` et, quand la série parente est accessible, les compteurs `vf` / `vo`. "
        'Les filtres `media_kinds` et `exclude_media_kinds` permettent de restreindre explicitement le périmètre métier (manga, spin-off, roman, essai, guide, cookbook, etc.).'
    ),
    responses={200: {'description': 'Search results envelope.', 'content': {'application/json': {'example': SEARCH_RESPONSE_EXAMPLE}}}},
)
async def search(
    request: Request,
    q: str = Query(..., min_length=1, description='Requête libre, par exemple `one piece` ou `Dogs: Bullets & Carnage`.'),
    kind: Literal['series', 'volume', 'all'] = Query(default='all', description='Limiter la recherche aux séries, aux volumes, ou aux deux.'),
    mode: Literal['best', 'all'] = Query(default='all', description='`all` renvoie par défaut tous les candidats retenus ; `best` limite la réponse au meilleur candidat.'),
    limit: int = Query(default=50, ge=1, le=50, description='Nombre maximum de résultats renvoyés. La valeur par défaut couvre une recherche de franchise complète.'),
    enrich: bool | None = Query(default=None, description='`true` pour enrichir avec les titres alternatifs et métadonnées volume ; `null` applique `SEARCH_DEFAULT_ENRICH`.'),
    include_editions: bool | None = Query(default=None, description='`true` pour hydrater les compteurs `vf` / `vo` ; `null` applique `SEARCH_DEFAULT_INCLUDE_EDITIONS`.'),
    prefer_main_series: bool | None = Query(default=None, description='`true` pour renforcer la priorité donnée à la série mère quand la requête vise une franchise ; `null` applique `SEARCH_DEFAULT_PREFER_MAIN_SERIES`.'),
    include_related: bool | None = Query(default=None, description='`false` pour retirer les spin-offs et séries liées détectées ; `null` applique `SEARCH_DEFAULT_INCLUDE_RELATED`.'),
    include_books: bool | None = Query(default=None, description='`false` pour retirer les romans, essais, guides, artbooks, cookbooks et autres livres dérivés ; `null` applique `SEARCH_DEFAULT_INCLUDE_BOOKS`.'),
    media_kinds: str | None = Query(default=None, description='Liste CSV blanche des `media_kind` à conserver, par exemple `manga,manga_spinoff`.'),
    exclude_media_kinds: str | None = Query(default=None, description='Liste CSV noire des `media_kind` à exclure, par exemple `novel,essay,cookbook`.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.search(
        query=q,
        kind=kind,
        mode=mode,
        limit=limit,
        enrich=enrich,
        include_editions=include_editions,
        prefer_main_series=prefer_main_series,
        include_related=include_related,
        include_books=include_books,
        media_kinds=media_kinds,
        exclude_media_kinds=exclude_media_kinds,
    )
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/search/resolve',
    dependencies=[Depends(auth_dependency)],
    response_model=ResolveResponse,
    tags=['Search'],
    summary='Resolve the best search candidate',
    description='Construit sur `/search`, puis renvoie le meilleur candidat et un niveau de confiance `high`, `medium`, `low` ou `none`. Les flags `enrich`, `include_editions`, `prefer_main_series`, `include_related`, `include_books`, `media_kinds` et `exclude_media_kinds` suivent le même contrat que `/search`.',
    responses={200: {'description': 'Resolved best candidate.', 'content': {'application/json': {'example': RESOLVE_RESPONSE_EXAMPLE}}}},
)
async def search_resolve(
    request: Request,
    q: str = Query(..., min_length=1, description='Requête libre à résoudre.'),
    kind: Literal['series', 'volume', 'all'] = Query(default='all', description='Type d’objet à résoudre.'),
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximum de candidats inspectés.'),
    enrich: bool | None = Query(default=None, description='`true` pour enrichir avec les titres alternatifs et métadonnées volume ; `null` applique `SEARCH_DEFAULT_ENRICH`.'),
    include_editions: bool | None = Query(default=None, description='`true` pour hydrater les compteurs `vf` / `vo` ; `null` applique `SEARCH_DEFAULT_INCLUDE_EDITIONS`.'),
    prefer_main_series: bool | None = Query(default=None, description='`true` pour renforcer la priorité donnée à la série mère quand la requête vise une franchise ; `null` applique `SEARCH_DEFAULT_PREFER_MAIN_SERIES`.'),
    include_related: bool | None = Query(default=None, description='`false` pour retirer les spin-offs et séries liées détectées ; `null` applique `SEARCH_DEFAULT_INCLUDE_RELATED`.'),
    include_books: bool | None = Query(default=None, description='`false` pour retirer les romans, essais, guides, artbooks, cookbooks et autres livres dérivés ; `null` applique `SEARCH_DEFAULT_INCLUDE_BOOKS`.'),
    media_kinds: str | None = Query(default=None, description='Liste CSV blanche des `media_kind` à conserver, par exemple `manga,manga_spinoff`.'),
    exclude_media_kinds: str | None = Query(default=None, description='Liste CSV noire des `media_kind` à exclure, par exemple `novel,essay,cookbook`.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.resolve_search(
        query=q,
        kind=kind,
        limit=limit,
        enrich=enrich,
        include_editions=include_editions,
        prefer_main_series=prefer_main_series,
        include_related=include_related,
        include_books=include_books,
        media_kinds=media_kinds,
        exclude_media_kinds=exclude_media_kinds,
    )
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/{slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesResponse,
    tags=['Series'],
    summary='Get a detailed series payload',
    description='Lit une fiche série Manga-News, y compris les compteurs d’éditions `vf` / `vo` quand ils sont présents dans `#numberblock`.',
    responses={200: {'description': 'Series envelope.', 'content': {'application/json': {'example': SERIES_RESPONSE_EXAMPLE}}}},
)
async def get_series(
    request: Request,
    slug: str,
    blocks: str | None = Query(default=None, description='Liste de blocs séparés par des virgules, par exemple `editions,stats`.'),
    fields: str | None = Query(default=None, description='Liste de chemins de champs séparés par des virgules, par exemple `title,vf.volumes`.'),
    include_raw_sections: bool = Query(default=False, description='Inclure les sections brutes extraites de la page HTML.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series(slug=slug, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/by-url', dependencies=[Depends(auth_dependency)], response_model=SeriesResponse, tags=['Series'], summary='Get a series payload from a direct Manga-News URL', description='Même comportement que `/series/{slug}`, mais en partant d’une URL directe Manga-News.')
async def get_series_by_url(
    request: Request,
    url: str = Query(..., description='URL complète de la fiche série Manga-News.'),
    blocks: str | None = Query(default=None),
    fields: str | None = Query(default=None),
    include_raw_sections: bool = Query(default=False),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series(url=url, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/{slug}/related', dependencies=[Depends(auth_dependency)], response_model=SeriesRelatedResponse, tags=['Series'], summary='Get related links for a series', description='Renvoie les liens en relation extraits depuis la fiche série.')
async def get_series_related(request: Request, slug: str, service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(slug=slug)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/by-url/related', dependencies=[Depends(auth_dependency)], response_model=SeriesRelatedResponse, tags=['Series'], summary='Get related links from a direct series URL', description='Même comportement que `/series/{slug}/related`, mais en partant d’une URL directe Manga-News.')
async def get_series_related_by_url(request: Request, url: str = Query(...), service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(url=url)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/{slug}/release-state',
    dependencies=[Depends(auth_dependency)],
    response_model=ReleaseStateResponse,
    tags=['Series'],
    summary='Get latest and next VF manga volume releases',
    description=(
        'Calcule le dernier tome VF déjà sorti et le prochain tome VF annoncé pour une série Manga-News. '
        'Le calcul s’appuie sur la liste des éditions VF et ne charge les fiches volume que si `include_isbn=true`.'
    ),
)
async def get_series_release_state(
    request: Request,
    slug: str,
    include_isbn: bool = Query(default=False, description='Charger uniquement les fiches des tomes dernier/prochain pour ajouter `isbn_ean`.'),
    include_special: bool = Query(default=False, description='Inclure collectors, coffrets et éditions spéciales dans le calcul.'),
    today: str | None = Query(default=None, description='Date ISO optionnelle utilisée comme référence, par exemple `2026-06-18`.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_release_state_by_series(
        slug=slug,
        include_isbn=include_isbn,
        include_special=include_special,
        today=today,
    )
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/{slug}/editions', dependencies=[Depends(auth_dependency)], response_model=SeriesEditionsResponse, tags=['Series'], summary='List series editions', description='Récupère les pages Éditions VF et/ou VO d’une série.')
async def get_series_editions(
    request: Request,
    slug: str,
    edition: Literal['all', 'vf', 'vo'] = Query(default='all', description='`all`, `vf` ou `vo`.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(slug=slug, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/series/by-url/editions', dependencies=[Depends(auth_dependency)], response_model=SeriesEditionsResponse, tags=['Series'], summary='List series editions from a direct URL', description='Même comportement que `/series/{slug}/editions`, mais en partant d’une URL directe Manga-News.')
async def get_series_editions_by_url(
    request: Request,
    url: str = Query(...),
    edition: Literal['all', 'vf', 'vo'] = Query(default='all'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(url=url, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/volume/{series_slug}/number/{number}',
    dependencies=[Depends(auth_dependency)],
    response_model=VolumeResponse,
    tags=['Volume'],
    summary='Get a volume payload by series slug and volume number',
    description=(
        'Retrouve le volume VF correspondant à un numéro de tome depuis la page éditions de la série, '
        'puis renvoie la même fiche volume que `/volume/{series_slug}/{volume_slug}`.'
    ),
    responses={200: {'description': 'Volume envelope.', 'content': {'application/json': {'example': VOLUME_RESPONSE_EXAMPLE}}}},
)
async def get_volume_by_number(
    request: Request,
    series_slug: str,
    number: int = ApiPath(..., ge=1, description='Numéro entier du tome VF à retrouver.'),
    blocks: str | None = Query(default=None, description='Liste de blocs séparés par des virgules, par exemple `release,scores`.'),
    fields: str | None = Query(default=None, description='Liste de chemins de champs séparés par des virgules, par exemple `publication_date,isbn_ean`.'),
    include_raw_sections: bool = Query(default=False, description='Inclure les sections brutes extraites de la page HTML.'),
    include_parent_editions: bool | None = Query(default=None, description='`true` pour hydrater `vf` / `vo` depuis la série parente ; `null` applique `VOLUME_DEFAULT_INCLUDE_PARENT_EDITIONS`.'),
    include_special: bool = Query(default=False, description='Inclure les volumes spéciaux si un numéro identique existe.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_by_number(
        series_slug=series_slug,
        number=number,
        blocks=blocks,
        fields=fields,
        include_raw_sections=include_raw_sections,
        include_parent_editions=include_parent_editions,
        include_special=include_special,
    )
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/volume/{series_slug}/{volume_slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=VolumeResponse,
    tags=['Volume'],
    summary='Get a detailed volume payload',
    description='Lit une fiche volume Manga-News. Quand `include_parent_editions` est absent, la route applique `VOLUME_DEFAULT_INCLUDE_PARENT_EDITIONS`. Avec `false`, la réponse reste légère ; avec `true`, elle peut hydrater `vf` / `vo` depuis la série parente.',
    responses={200: {'description': 'Volume envelope.', 'content': {'application/json': {'example': VOLUME_RESPONSE_EXAMPLE}}}},
)
async def get_volume(
    request: Request,
    series_slug: str,
    volume_slug: str,
    blocks: str | None = Query(default=None, description='Liste de blocs séparés par des virgules, par exemple `release,scores`.'),
    fields: str | None = Query(default=None, description='Liste de chemins de champs séparés par des virgules, par exemple `publication_date,isbn_ean`.'),
    include_raw_sections: bool = Query(default=False, description='Inclure les sections brutes extraites de la page HTML.'),
    include_parent_editions: bool | None = Query(default=None, description='`true` pour hydrater `vf` / `vo` depuis la série parente ; `null` applique `VOLUME_DEFAULT_INCLUDE_PARENT_EDITIONS`.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume(
        series_slug=series_slug,
        volume_slug=volume_slug,
        blocks=blocks,
        fields=fields,
        include_raw_sections=include_raw_sections,
        include_parent_editions=include_parent_editions,
    )
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=VolumeResponse, tags=['Volume'], summary='Get a volume payload from a direct Manga-News URL', description='Même comportement que `/volume/{series_slug}/{volume_slug}`, mais en partant d’une URL directe Manga-News.')
async def get_volume_by_url(
    request: Request,
    url: str = Query(...),
    blocks: str | None = Query(default=None),
    fields: str | None = Query(default=None),
    include_raw_sections: bool = Query(default=False),
    include_parent_editions: bool | None = Query(default=None),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume(
        url=url,
        blocks=blocks,
        fields=fields,
        include_raw_sections=include_raw_sections,
        include_parent_editions=include_parent_editions,
    )
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/global', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get global Manga-News RSS items', description='Retourne le flux RSS global Manga-News converti en JSON.')
async def get_global_news(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_global_news(limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/series/{slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get news for a series', description='Récupère les actualités d’une série.')
async def get_series_news(
    request: Request,
    slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_news(slug=slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/volume/{series_slug}/{volume_slug}', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get news for a volume', description='Récupère les actualités d’un volume à partir de son couple `series_slug` / `volume_slug`.')
async def get_volume_news(
    request: Request,
    series_slug: str,
    volume_slug: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(series_slug=series_slug, volume_slug=volume_slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get('/news/volume/by-url', dependencies=[Depends(auth_dependency)], response_model=NewsResponse, tags=['News'], summary='Get volume news from a direct URL', description='Même comportement que `/news/volume/{series_slug}/{volume_slug}`, mais en partant d’une URL directe Manga-News.')
async def get_volume_news_by_url(
    request: Request,
    url: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(url=url, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/planning',
    dependencies=[Depends(auth_dependency)],
    response_model=PlanningResponse,
    tags=['Planning'],
    summary='Get Manga-News planning pages',
    description='Récupère les pages de planning VF ou VO, puis applique les filtres locaux par éditeur, requête, dates et tri.',
    responses={200: {'description': 'Planning envelope.', 'content': {'application/json': {'example': PLANNING_RESPONSE_EXAMPLE}}}},
)
async def get_planning(
    request: Request,
    section: Literal['manga-vf', 'manga-vo'] = Query(default='manga-vf', description='Section de planning à consulter.'),
    year: int | None = Query(default=None, ge=1900, le=2100, description='Année de planning, si connue.'),
    month: int | None = Query(default=None, ge=1, le=12, description='Mois de planning, si connu.'),
    page: int = Query(default=1, ge=1, le=100, description='Page de planning à lire.'),
    publisher: str | None = Query(default=None, description='Filtre local sur le nom d’éditeur.'),
    q: str | None = Query(default=None, min_length=1, description='Filtre local fuzzy sur le titre, les auteurs et l’éditeur.'),
    date_from: str | None = Query(default=None, description='Date ISO minimale, par exemple `2026-04-01`.'),
    date_to: str | None = Query(default=None, description='Date ISO maximale, par exemple `2026-04-30`.'),
    sort: Literal['date_asc', 'date_desc', 'title_asc', 'title_desc'] = Query(default='date_asc', description='Ordre de tri local.'),
    limit: int = Query(default=25, ge=1, le=100, description='Nombre maximum d’éléments renvoyés après filtrage.'),
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
