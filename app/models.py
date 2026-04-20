from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = '1.0'


class BaseEnvelope(BaseModel):
    schema_version: str = SCHEMA_VERSION
    ok: bool = True
    found: bool = True
    source: Literal['manga_news'] = 'manga_news'
    source_url: str | None = None
    cached: bool = False
    fetched_at: str | None = None
    cache_expires_at: str | None = None
    partial: bool = False
    warnings: list[str] = Field(default_factory=list)
    fingerprint: str | None = None


class Envelope(BaseEnvelope):
    data: Any = None


class HealthResponse(BaseModel):
    ok: bool = True
    model_config = ConfigDict(
        json_schema_extra={
            'example': {'ok': True},
        }
    )


class SearchResult(BaseModel):
    title: str
    url: str
    kind: Literal['series', 'volume']
    score: int
    slug: str | None = None
    series_slug: str | None = None
    volume_slug: str | None = None


class SearchResponse(BaseEnvelope):
    data: list[SearchResult] = Field(default_factory=list)
    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'schema_version': SCHEMA_VERSION,
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/recherche/?cat=manga-serie-vf&q=one%20piece',
                'cached': False,
                'fetched_at': '2026-04-20T12:00:00+00:00',
                'cache_expires_at': '2026-04-21T12:00:00+00:00',
                'partial': False,
                'warnings': [],
                'fingerprint': '9f3a3a',
                'data': [
                    {
                        'title': 'One Piece',
                        'url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                        'kind': 'series',
                        'score': 100,
                        'slug': 'One-piece-Edition-originale',
                        'series_slug': None,
                        'volume_slug': None,
                    }
                ],
            }
        }
    )


class SearchResolveData(BaseModel):
    query: str
    kind: Literal['series', 'volume', 'all']
    confidence: Literal['high', 'medium', 'low', 'none']
    result: SearchResult | None = None
    candidates: list[SearchResult] = Field(default_factory=list)


class SearchResolveResponse(BaseEnvelope):
    data: SearchResolveData
    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'schema_version': SCHEMA_VERSION,
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/recherche/?cat=manga-serie-vf&q=one%20piece',
                'cached': True,
                'fetched_at': '2026-04-20T12:00:00+00:00',
                'cache_expires_at': '2026-04-21T12:00:00+00:00',
                'partial': False,
                'warnings': [],
                'fingerprint': '4f2c31',
                'data': {
                    'query': 'one piece',
                    'kind': 'series',
                    'confidence': 'high',
                    'result': {
                        'title': 'One Piece',
                        'url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                        'kind': 'series',
                        'score': 100,
                        'slug': 'One-piece-Edition-originale',
                        'series_slug': None,
                        'volume_slug': None,
                    },
                    'candidates': [],
                },
            }
        }
    )


class NewsItem(BaseModel):
    title: str
    url: str | None = None
    published_at: str | None = None
    excerpt: str | None = None
    comments: int | None = None
    category: str | None = None


class NewsResponse(BaseEnvelope):
    data: list[NewsItem] = Field(default_factory=list)


class SeriesStats(BaseModel):
    likes: int | None = None
    in_collection: int | None = None
    in_wishlist: int | None = None
    marketplace: int | None = None
    editorial_score: float | None = None
    reader_score: float | None = None


class EditionStatus(BaseModel):
    volumes: int | None = None
    status: str | None = None


class IllustrationDetails(BaseModel):
    raw: str | None = None
    pages: int | None = None
    has_color_pages: bool | None = None


class LinkItem(BaseModel):
    title: str
    url: str
    kind: str | None = None


class RelatedLinks(BaseModel):
    series: list[LinkItem] = Field(default_factory=list)
    volumes: list[LinkItem] = Field(default_factory=list)
    anime: list[LinkItem] = Field(default_factory=list)
    drama: list[LinkItem] = Field(default_factory=list)
    dossiers: list[LinkItem] = Field(default_factory=list)
    univers: list[LinkItem] = Field(default_factory=list)
    external: list[LinkItem] = Field(default_factory=list)
    misc: list[LinkItem] = Field(default_factory=list)


class SeriesData(BaseModel):
    title: str | None = None
    title_vo: str | None = None
    translated_title: str | None = None
    summary: str | None = None
    authors_story: list[str] = Field(default_factory=list)
    authors_art: list[str] = Field(default_factory=list)
    translators: list[str] = Field(default_factory=list)
    publisher_fr: str | None = None
    publisher_vo: str | None = None
    collection: str | None = None
    type: str | None = None
    genres: list[str] = Field(default_factory=list)
    prepublication: str | None = None
    origin: str | None = None
    illustration: str | None = None
    illustration_details: IllustrationDetails | None = None
    advisory_age: str | None = None
    cover_image: str | None = None
    vf: EditionStatus | None = None
    vo: EditionStatus | None = None
    last_release_date: str | None = None
    next_release_date: str | None = None
    stats: SeriesStats | None = None
    themes: list[str] = Field(default_factory=list)
    strengths: str | None = None
    related: RelatedLinks | None = None
    raw_sections: dict[str, list[str]] | None = None
    source_url: str | None = None


class VolumeData(BaseModel):
    title: str | None = None
    series_title: str | None = None
    title_vo: str | None = None
    translated_title: str | None = None
    summary: str | None = None
    authors_story: list[str] = Field(default_factory=list)
    authors_art: list[str] = Field(default_factory=list)
    translators: list[str] = Field(default_factory=list)
    publisher_fr: str | None = None
    publisher_vo: str | None = None
    collection: str | None = None
    type: str | None = None
    genres: list[str] = Field(default_factory=list)
    prepublication: str | None = None
    origin: str | None = None
    illustration: str | None = None
    illustration_details: IllustrationDetails | None = None
    advisory_age: str | None = None
    publication_date: str | None = None
    isbn_ean: str | None = None
    price_code: str | None = None
    cover_image: str | None = None
    editorial_score: float | None = None
    reader_score: float | None = None
    related: RelatedLinks | None = None
    raw_sections: dict[str, list[str]] | None = None
    source_url: str | None = None


class SeriesResponse(BaseEnvelope):
    data: SeriesData | dict[str, Any] | None = None
    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'schema_version': SCHEMA_VERSION,
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                'cached': False,
                'fetched_at': '2026-04-20T12:00:00+00:00',
                'cache_expires_at': '2026-04-21T12:00:00+00:00',
                'partial': False,
                'warnings': [],
                'fingerprint': '7a1f88',
                'data': {
                    'title': 'One Piece',
                    'title_vo': 'ワンピース',
                    'publisher_fr': 'Glénat',
                    'vf': {'volumes': 112, 'status': 'En cours'},
                    'next_release_date': '2026-05-06',
                },
            }
        }
    )


class VolumeResponse(BaseEnvelope):
    data: VolumeData | dict[str, Any] | None = None


class PlanningItem(BaseModel):
    title: str
    url: str | None = None
    release_date: str | None = None
    authors: list[str] = Field(default_factory=list)
    publisher: str | None = None
    summary: str | None = None
    featured: bool = False
    series_slug: str | None = None
    volume_slug: str | None = None


class PlanningPage(BaseModel):
    section: str
    year: int | None = None
    month: int | None = None
    page: int | None = None
    filters: dict[str, Any] | None = None
    sort: str | None = None
    total_items: int | None = None
    items: list[PlanningItem] = Field(default_factory=list)


class PlanningResponse(BaseEnvelope):
    data: PlanningPage | dict[str, Any] | None = None
    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'schema_version': SCHEMA_VERSION,
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/planning/?p_year=2026&p_month=4',
                'cached': False,
                'fetched_at': '2026-04-20T12:00:00+00:00',
                'cache_expires_at': '2026-04-20T18:00:00+00:00',
                'partial': False,
                'warnings': [],
                'fingerprint': '7f90d1',
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
                            'summary': 'Résumé',
                            'featured': False,
                            'series_slug': 'One-Piece',
                            'volume_slug': 'vol-110',
                        }
                    ],
                },
            }
        }
    )


class SeriesEditionItem(BaseModel):
    title: str
    url: str
    series_slug: str | None = None
    volume_slug: str | None = None
    number: str | None = None
    publication_date: str | None = None
    cover_image: str | None = None


class SeriesEditionsBlock(BaseModel):
    edition: Literal['vf', 'vo']
    source_url: str | None = None
    total: int = 0
    items: list[SeriesEditionItem] = Field(default_factory=list)


class SeriesEditionsData(BaseModel):
    title: str | None = None
    series_slug: str | None = None
    vf: SeriesEditionsBlock | None = None
    vo: SeriesEditionsBlock | None = None
    source_url: str | None = None


class SeriesEditionsResponse(BaseEnvelope):
    data: SeriesEditionsData | None = None


class SeriesRelatedData(BaseModel):
    title: str | None = None
    related: RelatedLinks = Field(default_factory=RelatedLinks)
    source_url: str | None = None


class SeriesRelatedResponse(BaseEnvelope):
    data: SeriesRelatedData | None = None
