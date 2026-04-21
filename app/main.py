from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
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
from app.metrics import MetricsStore
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

ROOT_DIR = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT_DIR / 'docs' / 'examples'


def _load_example(name: str, fallback: dict | list | None = None):
    path = EXAMPLES_DIR / name
    if path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            pass
    return fallback


def configure_logging(settings: Settings) -> None:
    json_logs = settings.log_format.lower() == 'json'
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format='%(message)s' if json_logs else '%(asctime)s %(levelname)s %(name)s: %(message)s',
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    cache = SQLiteCache(settings.db_path)
    metrics = MetricsStore()
    fetcher = AsyncFetcher(
        settings.user_agent,
        settings.request_timeout_seconds,
        max_retries=settings.request_max_retries,
        backoff_seconds=settings.request_backoff_seconds,
        log_json=settings.log_format.lower() == 'json',
        metrics=metrics,
    )
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=cache)
    app.state.settings = settings
    app.state.service = service
    app.state.metrics = metrics
    try:
        yield
    finally:
        await fetcher.close()


TAGS_METADATA = [
    {
        'name': 'Health',
        'description': 'Vérification simple que le service FastAPI répond. Cette route ne teste pas la disponibilité de Manga News.',
    },
    {
        'name': 'Search',
        'description': 'Recherche floue de séries ou de volumes à partir du moteur de recherche Manga News, avec score de similarité et titres alternatifs quand ils sont disponibles.',
    },
    {
        'name': 'Series',
        'description': 'Fiches détaillées de séries, liens liés et liste des éditions VF/VO.',
    },
    {
        'name': 'Volume',
        'description': 'Fiches détaillées de volumes. Les réponses exposent aussi la normalisation volume (`number`, `number_int`, `edition_label`, `is_special`, `is_one_shot`).',
    },
    {
        'name': 'News',
        'description': 'News globales et news rattachées à une série ou un volume.',
    },
    {
        'name': 'Planning',
        'description': 'Planning Manga News VF ou VO, avec filtres locaux sur éditeur, texte, plage de dates et tri.',
    },
]


COMMON_ERROR_RESPONSES = {
    401: {
        'description': 'Authentification requise ou Bearer token invalide.',
        'content': {
            'application/json': {
                'example': {
                    'code': 'AUTH_REQUIRED',
                    'detail': 'Missing or invalid bearer token.',
                }
            }
        },
    },
    404: {
        'description': 'Ressource absente côté Manga News.',
        'content': {
            'application/json': {'example': _load_example('error_resource_not_found.json', {'code': 'RESOURCE_NOT_FOUND', 'detail': 'Resource not found on Manga News.'})}
        },
    },
    502: {
        'description': 'Échec de récupération ou de parsing de la page source Manga News.',
        'content': {
            'application/json': {'example': _load_example('error_upstream_parse.json', {'code': 'UPSTREAM_PARSE_ERROR', 'detail': 'Unable to parse the requested Manga News page.'})}
        },
    },
}


app = FastAPI(
    title='Manga News Private API',
    version='0.2.0',
    summary='API non officielle, auto-hébergeable, qui transforme des pages Manga News en JSON consommable.',
    description=(
        'Cette API expose des données publiques de Manga News en JSON stable.\n\n'
        'Contrat public actuel : **sans préfixe de version**. Utilise les routes exactement telles qu’elles apparaissent dans `/openapi.json`.\n\n'
        'Fonctions principales : recherche, résolution du meilleur match, fiches série, fiches volume, liens liés, éditions, news et planning.\n\n'
        'Points importants :\n'
        '- authentification optionnelle via `API_TOKEN` ;\n'
        '- cache SQLite persistant ;\n'
        '- `ETag` et `X-Data-Fingerprint` sur les réponses enveloppées ;\n'
        '- negative cache court pour éviter de retaper immédiatement une ressource cassée ou absente ;\n'
        '- titres alternatifs (`title_vo`, `translated_title`) visibles sur les fiches détaillées et les résultats de recherche enrichis ;\n'
        '- projections légères via `blocks`, `fields` et `include_raw_sections` sur les routes détail.\n\n'
        'Ce que l’API **n’expose pas** aujourd’hui comme contrat public : routes admin, versionnement `/v1`, pagination normalisée commune, rate limit public branché aux routes.'
    ),
    docs_url=get_settings().docs_url,
    redoc_url=get_settings().redoc_url,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
)


def get_service() -> MangaNewsService:
    return app.state.service


def get_settings_dep() -> Settings:
    return app.state.settings


HEALTH_EXAMPLE = _load_example('health.json', {'ok': True})
SEARCH_EXAMPLE = _load_example('search_response_one_piece.json', {})
RESOLVE_EXAMPLE = _load_example('resolve_response_one_piece.json', {})
SERIES_EXAMPLE = _load_example('series_one_piece.json', {})
VOLUME_EXAMPLE = _load_example('volume_one_piece_91.json', {})
NEWS_EXAMPLE = _load_example('news_global_one_piece_sample.json', {})
PLANNING_EXAMPLE = _load_example('planning_example.json', {})
SERIES_RELATED_EXAMPLE = _load_example('series_related_one_piece.json', {})
SERIES_EDITIONS_EXAMPLE = _load_example('series_editions_one_piece.json', {})


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
    authorization: str | None = Header(default=None, description='Bearer token attendu si `API_TOKEN` est configuré.'),
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
    summary='Vérifier que l’API répond.',
    description='Route de santé locale. Elle confirme que le service FastAPI tourne, mais elle ne vérifie pas le fetch ou le parsing de Manga News.',
    responses={200: {'description': 'API joignable.', 'content': {'application/json': {'example': HEALTH_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def health():
    return {'ok': True}


@app.get(
    '/search',
    dependencies=[Depends(auth_dependency)],
    response_model=SearchResponse,
    tags=['Search'],
    summary='Rechercher des séries ou des volumes.',
    description=(
        'Interroge le moteur de recherche Manga News puis reclasse les résultats par score de similarité. '
        'Les résultats retenus sont enrichis si possible avec `title_vo` et `translated_title` en relisant la fiche détaillée correspondante.'
    ),
    responses={200: {'description': 'Liste de résultats triés par score décroissant.', 'content': {'application/json': {'example': SEARCH_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def search(
    request: Request,
    q: str = Query(..., min_length=1, description='Texte recherché. Exemple : `one piece`, `Dogs - Bullets & Carnage`, `black night parade`.') ,
    kind: Literal['series', 'volume', 'all'] = Query(default='all', description='Type de recherche à lancer sur Manga News.'),
    mode: Literal['best', 'all'] = Query(default='best', description='`best` garde le meilleur résultat ; `all` renvoie tous les résultats conservés.'),
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximum de résultats après tri et déduplication.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.search(query=q, kind=kind, mode=mode, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/search/resolve',
    dependencies=[Depends(auth_dependency)],
    response_model=ResolveResponse,
    tags=['Search'],
    summary='Résoudre le meilleur candidat pour une requête.',
    description='S’appuie sur `/search`, choisit un meilleur candidat (`best`) et calcule un niveau de confiance (`high`, `medium`, `low`, `none`).',
    responses={200: {'description': 'Résultat résolu avec meilleur candidat et liste de candidats.', 'content': {'application/json': {'example': RESOLVE_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def search_resolve(
    request: Request,
    q: str = Query(..., min_length=1, description='Texte recherché à résoudre.'),
    kind: Literal['series', 'volume', 'all'] = Query(default='all', description='Type de ressource attendue.'),
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximum de candidats étudiés.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.resolve_search(query=q, kind=kind, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/{slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesResponse,
    tags=['Series'],
    summary='Lire la fiche détaillée d’une série via son slug Manga News.',
    description='Retourne la fiche série complète ou projetée. Utilise `blocks`, `fields` et `include_raw_sections` pour limiter ou enrichir le payload.',
    responses={200: {'description': 'Fiche série.', 'content': {'application/json': {'example': SERIES_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_series(
    request: Request,
    slug: str,
    blocks: str | None = Query(default=None, description='Blocs prédéfinis séparés par des virgules. Exemples : `identity,publishing,editions`, `stats`, `all`.'),
    fields: str | None = Query(default=None, description='Chemins précis séparés par des virgules. Exemples : `title,title_vo,vf.volumes,next_release_date`.'),
    include_raw_sections: bool = Query(default=False, description='Inclut `raw_sections` si `true`, même si le champ n’est pas demandé via `blocks` ou `fields`.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series(slug=slug, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/by-url',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesResponse,
    tags=['Series'],
    summary='Lire une fiche série à partir d’une URL Manga News complète.',
    description='Alternative à `/series/{slug}` quand le client possède déjà l’URL source exacte.',
    responses={200: {'description': 'Fiche série.', 'content': {'application/json': {'example': SERIES_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_series_by_url(
    request: Request,
    url: str = Query(..., description='URL complète Manga News de la série.'),
    blocks: str | None = Query(default=None, description='Même comportement que sur `/series/{slug}`.'),
    fields: str | None = Query(default=None, description='Même comportement que sur `/series/{slug}`.'),
    include_raw_sections: bool = Query(default=False, description='Même comportement que sur `/series/{slug}`.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series(url=url, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/{slug}/related',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesRelatedResponse,
    tags=['Series'],
    summary='Récupérer uniquement les liens liés à une série.',
    description='Extrait le bloc `related` d’une fiche série et le renvoie dans une enveloppe plus légère.',
    responses={200: {'description': 'Liens liés à la série.', 'content': {'application/json': {'example': SERIES_RELATED_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_series_related(request: Request, slug: str, service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(slug=slug)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/by-url/related',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesRelatedResponse,
    tags=['Series'],
    summary='Récupérer les liens liés à une série via son URL.',
    description='Même contrat que `/series/{slug}/related`, mais en entrée URL complète.',
    responses={200: {'description': 'Liens liés à la série.', 'content': {'application/json': {'example': SERIES_RELATED_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_series_related_by_url(request: Request, url: str = Query(..., description='URL complète Manga News de la série.'), service: MangaNewsService = Depends(get_service)):
    payload = await service.get_series_related(url=url)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/{slug}/editions',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesEditionsResponse,
    tags=['Series'],
    summary='Lister les éditions VF et/ou VO d’une série.',
    description='Charge la fiche série puis les pages d’éditions VF et/ou VO correspondantes.',
    responses={200: {'description': 'Éditions de la série.', 'content': {'application/json': {'example': SERIES_EDITIONS_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_series_editions(
    request: Request,
    slug: str,
    edition: Literal['all', 'vf', 'vo'] = Query(default='all', description='`all` charge VF et VO ; `vf` ou `vo` limitent le résultat.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(slug=slug, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/series/by-url/editions',
    dependencies=[Depends(auth_dependency)],
    response_model=SeriesEditionsResponse,
    tags=['Series'],
    summary='Lister les éditions d’une série à partir de son URL.',
    description='Même contrat que `/series/{slug}/editions`, mais avec l’URL Manga News en entrée.',
    responses={200: {'description': 'Éditions de la série.', 'content': {'application/json': {'example': SERIES_EDITIONS_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_series_editions_by_url(
    request: Request,
    url: str = Query(..., description='URL complète Manga News de la série.'),
    edition: Literal['all', 'vf', 'vo'] = Query(default='all', description='`all`, `vf` ou `vo`.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_editions(url=url, edition=edition)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/volume/{series_slug}/{volume_slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=VolumeResponse,
    tags=['Volume'],
    summary='Lire la fiche détaillée d’un volume via ses slugs Manga News.',
    description='Retourne la fiche volume complète ou projetée. Expose aussi les champs normalisés de volume pour faciliter le rapprochement côté client.',
    responses={200: {'description': 'Fiche volume.', 'content': {'application/json': {'example': VOLUME_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_volume(
    request: Request,
    series_slug: str,
    volume_slug: str,
    blocks: str | None = Query(default=None, description='Blocs prédéfinis séparés par des virgules. Exemples : `identity,release`, `scores`, `all`.'),
    fields: str | None = Query(default=None, description='Chemins précis séparés par des virgules. Exemples : `publication_date,isbn_ean,number,number_int`.'),
    include_raw_sections: bool = Query(default=False, description='Inclut `raw_sections` si `true`.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume(series_slug=series_slug, volume_slug=volume_slug, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/volume/by-url',
    dependencies=[Depends(auth_dependency)],
    response_model=VolumeResponse,
    tags=['Volume'],
    summary='Lire une fiche volume à partir d’une URL Manga News complète.',
    description='Alternative à `/volume/{series_slug}/{volume_slug}` quand l’URL source est déjà connue.',
    responses={200: {'description': 'Fiche volume.', 'content': {'application/json': {'example': VOLUME_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_volume_by_url(
    request: Request,
    url: str = Query(..., description='URL complète Manga News du volume.'),
    blocks: str | None = Query(default=None, description='Même comportement que sur `/volume/{series_slug}/{volume_slug}`.'),
    fields: str | None = Query(default=None, description='Même comportement que sur `/volume/{series_slug}/{volume_slug}`.'),
    include_raw_sections: bool = Query(default=False, description='Même comportement que sur `/volume/{series_slug}/{volume_slug}`.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume(url=url, blocks=blocks, fields=fields, include_raw_sections=include_raw_sections)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/news/global',
    dependencies=[Depends(auth_dependency)],
    response_model=NewsResponse,
    tags=['News'],
    summary='Lire les dernières news globales du flux RSS Manga News.',
    description='Lit le flux RSS global de news et renvoie jusqu’à `limit` éléments.',
    responses={200: {'description': 'News globales.', 'content': {'application/json': {'example': NEWS_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_global_news(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximum d’items à retourner.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_global_news(limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/news/series/{slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=NewsResponse,
    tags=['News'],
    summary='Lire les news liées à une série.',
    description='Charge la page de news rattachée à une série Manga News et en extrait les items.',
    responses={200: {'description': 'News de série.', 'content': {'application/json': {'example': NEWS_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_series_news(
    request: Request,
    slug: str,
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximum d’items à retourner.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_series_news(slug=slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/news/volume/{series_slug}/{volume_slug}',
    dependencies=[Depends(auth_dependency)],
    response_model=NewsResponse,
    tags=['News'],
    summary='Lire les news liées à un volume.',
    description='Construit l’URL de news du volume à partir des slugs, puis extrait les items de news.',
    responses={200: {'description': 'News de volume.', 'content': {'application/json': {'example': NEWS_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_volume_news(
    request: Request,
    series_slug: str,
    volume_slug: str,
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximum d’items à retourner.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(series_slug=series_slug, volume_slug=volume_slug, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/news/volume/by-url',
    dependencies=[Depends(auth_dependency)],
    response_model=NewsResponse,
    tags=['News'],
    summary='Lire les news d’un volume à partir de son URL.',
    description='Alternative à `/news/volume/{series_slug}/{volume_slug}` avec une URL Manga News directe.',
    responses={200: {'description': 'News de volume.', 'content': {'application/json': {'example': NEWS_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_volume_news_by_url(
    request: Request,
    url: str = Query(..., description='URL complète Manga News du volume.'),
    limit: int = Query(default=10, ge=1, le=50, description='Nombre maximum d’items à retourner.'),
    service: MangaNewsService = Depends(get_service),
):
    payload = await service.get_volume_news(url=url, limit=limit)
    return _build_envelope_response(payload.model_dump(), request)


@app.get(
    '/planning',
    dependencies=[Depends(auth_dependency)],
    response_model=PlanningResponse,
    tags=['Planning'],
    summary='Lire le planning VF ou VO avec filtres locaux.',
    description=(
        'Charge une page de planning Manga News puis applique des filtres locaux sur les items extraits : éditeur, texte, dates, tri et limite. '
        '`total_items` correspond au nombre d’items après filtrage local sur la page chargée, pas à un total global du site.'
    ),
    responses={200: {'description': 'Planning filtré.', 'content': {'application/json': {'example': PLANNING_EXAMPLE}}}, **COMMON_ERROR_RESPONSES},
)
async def get_planning(
    request: Request,
    section: Literal['manga-vf', 'manga-vo'] = Query(default='manga-vf', description='Section de planning à lire.'),
    year: int | None = Query(default=None, ge=1900, le=2100, description='Année de planning demandée côté URL Manga News.'),
    month: int | None = Query(default=None, ge=1, le=12, description='Mois de planning demandé côté URL Manga News.'),
    page: int = Query(default=1, ge=1, le=100, description='Page du planning à charger avant filtres locaux.'),
    publisher: str | None = Query(default=None, description='Filtre local sur le nom d’éditeur.'),
    q: str | None = Query(default=None, min_length=1, description='Filtre local fuzzy sur titre + auteurs + éditeur.'),
    date_from: str | None = Query(default=None, description='Date minimale incluse, au format ISO `YYYY-MM-DD`.'),
    date_to: str | None = Query(default=None, description='Date maximale incluse, au format ISO `YYYY-MM-DD`.'),
    sort: Literal['date_asc', 'date_desc', 'title_asc', 'title_desc'] = Query(default='date_asc', description='Tri local appliqué après filtrage.'),
    limit: int = Query(default=25, ge=1, le=100, description='Nombre maximum d’items retournés après filtres et tri.'),
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
