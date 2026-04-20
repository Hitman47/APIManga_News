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

APP_DESCRIPTION = """
API non officielle, auto-hébergée, qui transforme le HTML public de Manga News en JSON exploitable.

Elle sert surtout à :
- résoudre un titre ou un tome via la recherche ;
- récupérer une fiche série ou volume ;
- lister les éditions liées à une série ;
- lire les news globales, série ou volume ;
- interroger le planning de sorties ;
- réutiliser les réponses via `ETag` / `If-None-Match`.

Points importants :
- ce projet n'utilise **pas** de `/v1` aujourd'hui ;
- les routes décrites dans l'OpenAPI sont le contrat réel ;
- la source de vérité publique est `GET /openapi.json` ;
- si `API_TOKEN` est défini, il faut envoyer `Authorization: Bearer <token>`.
""".strip()

OPENAPI_TAGS = [
    {
        'name': 'health',
        'description': 'Vérification simple de disponibilité de l’API.',
    },
    {
        'name': 'search',
        'description': 'Recherche de séries et de volumes à partir d’un titre libre.',
    },
    {
        'name': 'series',
        'description': 'Fiches série, liens liés et listes d’éditions.',
    },
    {
        'name': 'volume',
        'description': 'Fiches volume et news liées à un tome précis.',
    },
    {
        'name': 'news',
        'description': 'News globales ou filtrées sur une série / un volume.',
    },
    {
        'name': 'planning',
        'description': 'Planning des sorties Manga News avec filtres et tri.',
    },
]

ERROR_401 = {
    'description': 'Authentification absente ou invalide.',
    'content': {
        'application/json': {
            'examples': {
                'unauthorized': {
                    'summary': 'Token Bearer invalide',
                    'value': {'detail': 'Missing or invalid bearer token.'},
                }
            }
        }
    },
}

ERROR_404 = {
    'description': 'Ressource absente côté Manga News.',
    'content': {
        'application/json': {
            'examples': {
                'not_found': {
                    'summary': 'Slug inconnu ou page supprimée',
                    'value': {'detail': 'Resource not found on Manga News.'},
                }
            }
        }
    },
}

ERROR_502 = {
    'description': 'Erreur de fetch ou de parsing côté upstream.',
    'content': {
        'application/json': {
            'examples': {
                'upstream_error': {
                    'summary': 'Manga News indisponible ou structure HTML inattendue',
                    'value': {'detail': 'Unable to reach Manga News: timeout'},
                }
            }
        }
    },
}

ERROR_304 = {
    'description': 'Aucune modification depuis le fingerprint / ETag fourni.',
}

COMMON_READ_RESPONSES = {
    304: ERROR_304,
    401: ERROR_401,
    404: ERROR_404,
    502: ERROR_502,
}

SEARCH_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/recherche/?cat=manga-serie-vf&q=one%20piece',
    'cached': False,
    'fetched_at': '2026-04-20T12:00:00+00:00',
    'cache_expires_at': '2026-04-21T12:00:00+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-search',
    'data': [
        {
            'title': 'One Piece',
            'url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            'kind': 'series',
            'score': 98,
            'slug': 'One-piece-Edition-originale',
            'series_slug': None,
            'volume_slug': None,
        }
    ],
}

RESOLVE_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/recherche/?cat=manga-serie-vf&q=one%20piece',
    'cached': False,
    'fetched_at': '2026-04-20T12:00:00+00:00',
    'cache_expires_at': '2026-04-21T12:00:00+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-resolve',
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
    'cached': True,
    'fetched_at': '2026-04-20T12:00:00+00:00',
    'cache_expires_at': '2026-04-21T12:00:00+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-series',
    'data': {
        'title': 'One Piece',
        'summary': 'Résumé normalisé de la série.',
        'authors_story': ['Eiichirô ODA'],
        'authors_art': ['Eiichirô ODA'],
        'publisher_fr': 'Glénat',
        'genres': ['Aventure', 'Action'],
        'vf': {'volumes': 112, 'status': 'en cours'},
        'vo': {'volumes': 111, 'status': 'en cours'},
        'stats': {
            'likes': 531,
            'editorial_score': 9.0,
            'reader_score': 8.7,
        },
        'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
    },
}

VOLUME_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
    'cached': True,
    'fetched_at': '2026-04-20T12:00:00+00:00',
    'cache_expires_at': '2026-04-27T12:00:00+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-volume',
    'data': {
        'title': 'One Piece Vol.110',
        'series_title': 'One Piece',
        'publication_date': '2026-04-27',
        'isbn_ean': '9782344XXXXXX',
        'publisher_fr': 'Glénat',
        'editorial_score': 9.0,
        'reader_score': 8.8,
        'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
    },
}

NEWS_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/feed/news',
    'cached': False,
    'fetched_at': '2026-04-20T12:00:00+00:00',
    'cache_expires_at': '2026-04-20T18:00:00+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-news',
    'data': [
        {
            'title': 'One Piece revient avec une annonce importante',
            'url': 'https://www.manga-news.com/index.php/actus/2026/04/20/One-Piece',
            'published_at': '2026-04-20',
            'excerpt': 'Résumé court de la news.',
            'comments': 12,
            'category': 'Manga',
        }
    ],
}

PLANNING_EXAMPLE = {
    'schema_version': '1.0',
    'ok': True,
    'found': True,
    'source': 'manga_news',
    'source_url': 'https://www.manga-news.com/index.php/planning/',
    'cached': False,
    'fetched_at': '2026-04-20T12:00:00+00:00',
    'cache_expires_at': '2026-04-20T18:00:00+00:00',
    'partial': False,
    'warnings': [],
    'fingerprint': 'fp-planning',
    'data': {
        'section': 'manga-vf',
        'year': 2026,
        'month': 4,
        'page': 1,
        'filters': {
            'publisher': 'Glénat',
            'query': 'one piece',
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        },
        'sort': 'date_asc',
        'total_items': 1,
        'items': [
            {
                'title': 'One Piece Vol.110',
                'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
                'release_date': '2026-04-27',
                'authors': ['Eiichirô ODA'],
                'publisher': 'Glénat',
                'summary': 'Résumé court.',
                'featured': False,
                'series_slug': 'One-Piece',
                'volume_slug': 'vol-110',
            }
        ],
    },
}



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
    description=APP_DESCRIPTION,
    docs_url=get_settings().docs_url,
    redoc_url=get_settings().redoc_url,
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
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


@app.get(
    '/health',
    dependencies=[Depends(auth_dependency)],
    response_model=HealthResponse,
    tags=['health'],
    summary='Tester la disponibilité de l’API',
    description='Endpoint minimal pour vérifier que l’API répond et que l’authentification éventuelle fonctionne.',
    responses={401: ERROR_401},
)
async def health():
    return {'ok': True}


@app.get(
    '/search',
    dependencies=[Depends(auth_dependency)],
    response_model=SearchResponse,
    tags=['search'],
    summary='Rechercher des séries ou des volumes',
    description=(
        'Recherche libre dans Manga News. Utilise plusieurs pages de recherche publiques, déduplique les résultats, '
        'puis les trie par score décroissant. Utiliser `/search/resolve` si tu veux directement un meilleur résultat.'
    ),
    responses={
        200: {'description': 'Liste de résultats classés.', 'content': {'application/json': {'example': SEARCH_EXAMPLE}}},
        401: ERROR_401,
        502: ERROR_502,
    },
)
async def search(
    request: Request,
    q: str = Query(..., min_length=1, description='Texte libre à rechercher. Exemple : `one piece`, `one piece tome 91`.') ,
    kind: Literal['series', 'volume', 'all'] = Query(default='all', description='Limiter la recherche aux séries, aux volumes ou aux deux.'),
    mode: Literal['best', 'all'] = Query(default='best', description='`best` renvoie uniquement le premier résultat ; `all` renvoie une liste.'),
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximal de résultats renvoyés.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.search(query=q, kind=kind, mode=mode, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/search/resolve',
    dependencies=[Depends(auth_dependency)],
    response_model=ResolveResponse,
    tags=['search'],
    summary='Résoudre automatiquement le meilleur résultat',
    description=(
        'Variante orientée automatisation de `/search`. Le résultat renvoie `best`, la liste des `candidates`, '
        'et un niveau de confiance (`high`, `medium`, `low`, `none`).'
    ),
    responses={
        200: {'description': 'Meilleur match et candidats.', 'content': {'application/json': {'example': RESOLVE_EXAMPLE}}},
        401: ERROR_401,
        502: ERROR_502,
    },
)
async def search_resolve(
    request: Request,
    q: str = Query(..., min_length=1, description='Texte libre à résoudre. Exemple : `one piece`, `one piece tome 91`.') ,
    kind: Literal['series', 'volume', 'all'] = Query(default='all', description='Type de ressource attendue.'),
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximal de candidats analysés et renvoyés.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.resolve_search(query=q, kind=kind, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/{slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesResponse,
    tags=['series'],
    summary='Récupérer une fiche série par slug',
    description=(
        'Charge la fiche série Manga News à partir du slug. Les paramètres `blocks` et `fields` permettent de projeter '
        'uniquement une partie des données, ce qui est pratique pour des intégrations automatisées.'
    ),
    responses={
        200: {'description': 'Fiche série normalisée.', 'content': {'application/json': {'example': SERIES_EXAMPLE}}},
        **COMMON_READ_RESPONSES,
    },
)
async def get_series(
    request: Request,
    slug: str,
    blocks: str | None = Query(default=None, description='Blocs métier séparés par des virgules. Exemple : `identity,editions,stats`.') ,
    fields: str | None = Query(default=None, description='Chemins de champs séparés par des virgules. Exemple : `title,vf.volumes`.') ,
    include_raw_sections: bool = Query(default=False, description='Inclure les sections brutes extraites du HTML pour le debug ou l’analyse.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series(slug=slug, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/by-url',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesResponse,
    tags=['series'],
    summary='Récupérer une fiche série à partir de son URL complète',
    description='Utile quand le client connaît déjà l’URL Manga News et ne veut pas recalculer le slug.',
    responses={
        200: {'description': 'Fiche série normalisée.', 'content': {'application/json': {'example': SERIES_EXAMPLE}}},
        **COMMON_READ_RESPONSES,
    },
)
async def get_series_by_url(
    request: Request,
    url: str = Query(..., description='URL complète d’une fiche série Manga News.'),
    blocks: str | None = Query(default=None, description='Blocs métier séparés par des virgules.'),
    fields: str | None = Query(default=None, description='Chemins de champs séparés par des virgules.'),
    include_raw_sections: bool = Query(default=False, description='Inclure les sections brutes extraites du HTML.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series(url=url, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/{slug}/related',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesRelatedResponse,
    tags=['series'],
    summary='Lister les contenus liés à une série',
    description='Retourne les liens liés détectés sur la fiche série : séries, volumes, anime, drama, dossiers, univers, etc.',
    responses={**COMMON_READ_RESPONSES},
)
async def get_series_related(request: Request, slug: str, service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(slug=slug)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/by-url/related',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesRelatedResponse,
    tags=['series'],
    summary='Lister les contenus liés à une série à partir de son URL',
    description='Même comportement que `/series/{slug}/related`, mais à partir d’une URL Manga News complète.',
    responses={**COMMON_READ_RESPONSES},
)
async def get_series_related_by_url(request: Request, url: str = Query(..., description='URL complète d’une fiche série Manga News.'), service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(url=url)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/{slug}/editions',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesEditionsResponse,
    tags=['series'],
    summary='Récupérer les éditions VF / VO d’une série',
    description='Charge la page des éditions VF, VO ou les deux selon `edition`.',
    responses={**COMMON_READ_RESPONSES},
)
async def get_series_editions(
    request: Request,
    slug: str,
    edition: Literal['all', 'vf', 'vo'] = Query(default='all', description='`all` pour VF+VO, `vf` uniquement, ou `vo` uniquement.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(slug=slug, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/by-url/editions',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesEditionsResponse,
    tags=['series'],
    summary='Récupérer les éditions d’une série à partir de son URL',
    description='Même comportement que `/series/{slug}/editions`, mais à partir d’une URL complète.',
    responses={**COMMON_READ_RESPONSES},
)
async def get_series_editions_by_url(
    request: Request,
    url: str = Query(..., description='URL complète d’une fiche série Manga News.'),
    edition: Literal['all', 'vf', 'vo'] = Query(default='all', description='`all` pour VF+VO, `vf` uniquement, ou `vo` uniquement.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(url=url, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/volume/{series_slug}/{volume_slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=VolumeResponse,
    tags=['volume'],
    summary='Récupérer une fiche volume par slug série + slug volume',
    description='Retourne la fiche volume normalisée. Les paramètres `blocks` et `fields` fonctionnent comme sur les fiches série.',
    responses={
        200: {'description': 'Fiche volume normalisée.', 'content': {'application/json': {'example': VOLUME_EXAMPLE}}},
        **COMMON_READ_RESPONSES,
    },
)
async def get_volume(
    request: Request,
    series_slug: str,
    volume_slug: str,
    blocks: str | None = Query(default=None, description='Blocs métier séparés par des virgules. Exemple : `identity,release,scores`.') ,
    fields: str | None = Query(default=None, description='Chemins de champs séparés par des virgules. Exemple : `publication_date,isbn_ean`.') ,
    include_raw_sections: bool = Query(default=False, description='Inclure les sections brutes extraites du HTML.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume(series_slug=series_slug, volume_slug=volume_slug, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/volume/by-url',
    dependencies=[Depends(auth_dependency)],
    response_model=VolumeResponse,
    tags=['volume'],
    summary='Récupérer une fiche volume à partir de son URL complète',
    description='Utile quand le client a déjà l’URL d’un tome Manga News.',
    responses={
        200: {'description': 'Fiche volume normalisée.', 'content': {'application/json': {'example': VOLUME_EXAMPLE}}},
        **COMMON_READ_RESPONSES,
    },
)
async def get_volume_by_url(
    request: Request,
    url: str = Query(..., description='URL complète d’un volume Manga News.'),
    blocks: str | None = Query(default=None, description='Blocs métier séparés par des virgules.'),
    fields: str | None = Query(default=None, description='Chemins de champs séparés par des virgules.'),
    include_raw_sections: bool = Query(default=False, description='Inclure les sections brutes extraites du HTML.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume(url=url, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/news/global',
    dependencies=[Depends(auth_dependency)],
    response_model=NewsResponse,
    tags=['news'],
    summary='Lire les news globales Manga News',
    description='Parse le flux RSS public des news Manga News.',
    responses={
        200: {'description': 'Liste de news globales.', 'content': {'application/json': {'example': NEWS_EXAMPLE}}},
        401: ERROR_401,
        502: ERROR_502,
    },
)
async def get_global_news(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximal d’éléments renvoyés.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_global_news(limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/news/series/{slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=NewsResponse,
    tags=['news'],
    summary='Lire les news liées à une série',
    description='Parse la page news d’une série à partir du slug de la série.',
    responses={**COMMON_READ_RESPONSES},
)
async def get_series_news(
    request: Request,
    slug: str,
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximal d’éléments renvoyés.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_news(slug=slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/news/volume/{series_slug}/{volume_slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=NewsResponse,
    tags=['news'],
    summary='Lire les news liées à un volume',
    description='Parse la page news liée à un tome précis.',
    responses={**COMMON_READ_RESPONSES},
)
async def get_volume_news(
    request: Request,
    series_slug: str,
    volume_slug: str,
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximal d’éléments renvoyés.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(series_slug=series_slug, volume_slug=volume_slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/news/volume/by-url',
    dependencies=[Depends(auth_dependency)],
    response_model=NewsResponse,
    tags=['news'],
    summary='Lire les news liées à un volume à partir de son URL',
    description='Même comportement que `/news/volume/{series_slug}/{volume_slug}`, mais à partir de l’URL du volume.',
    responses={**COMMON_READ_RESPONSES},
)
async def get_volume_news_by_url(
    request: Request,
    url: str = Query(..., description='URL complète d’un volume Manga News.'),
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximal d’éléments renvoyés.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(url=url, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/planning',
    dependencies=[Depends(auth_dependency)],
    response_model=PlanningResponse,
    tags=['planning'],
    summary='Interroger le planning des sorties',
    description=(
        'Filtre le planning Manga News par section, mois, éditeur, date, texte libre et ordre de tri. '
        'Le résultat renvoie les filtres effectivement appliqués et la liste normalisée des éléments.'
    ),
    responses={
        200: {'description': 'Page de planning filtrée.', 'content': {'application/json': {'example': PLANNING_EXAMPLE}}},
        401: ERROR_401,
        502: ERROR_502,
    },
)
async def get_planning(
    request: Request,
    section: Literal['manga-vf', 'manga-vo'] = Query(default='manga-vf', description='Section du planning à interroger.'),
    year: int | None = Query(default=None, ge=1900, le=2100, description='Année du planning. Si absente, Manga News choisit la vue par défaut.'),
    month: int | None = Query(default=None, ge=1, le=12, description='Mois du planning (1-12).'),
    page: int = Query(default=1, ge=1, le=100, description='Numéro de page du planning.'),
    publisher: str | None = Query(default=None, description='Filtrer sur un éditeur précis.'),
    q: str | None = Query(default=None, min_length=1, description='Texte libre à filtrer dans le planning.'),
    date_from: str | None = Query(default=None, description='Date minimale au format `YYYY-MM-DD`.'),
    date_to: str | None = Query(default=None, description='Date maximale au format `YYYY-MM-DD`.'),
    sort: Literal['date_asc', 'date_desc', 'title_asc', 'title_desc'] = Query(default='date_asc', description='Ordre de tri appliqué côté API.'),
    limit: int = Query(default=25, ge=1, le=100, description='Nombre maximal d’éléments renvoyés après filtrage.'),
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
