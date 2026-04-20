from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = '1.1'


class BaseEnvelope(BaseModel):
    schema_version: str = Field(default=SCHEMA_VERSION, examples=[SCHEMA_VERSION])
    ok: bool = True
    found: bool = True
    source: Literal['manga_news'] = 'manga_news'
    source_url: str | None = None
    cached: bool = False
    fetched_at: str | None = None
    cache_expires_at: str | None = None
    partial: bool = False
    warnings: list[str] = Field(default_factory=list)
    fingerprint: str | None = Field(default=None, description='Stable hash of the response envelope, used for ETag/304 handling.')


class SearchResult(BaseModel):
    title: str = Field(examples=['One Piece'])
    url: str = Field(examples=['https://www.manga-news.com/index.php/serie/One-piece-Edition-originale'])
    kind: Literal['series', 'volume'] = Field(examples=['series'])
    score: int = Field(examples=[98])
    slug: str | None = Field(default=None, examples=['One-piece-Edition-originale'])
    series_slug: str | None = Field(default=None, examples=['One-piece-Edition-originale'])
    volume_slug: str | None = Field(default=None, examples=['vol-110'])


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
                'fetched_at': '2026-04-20T10:00:00+00:00',
                'cache_expires_at': '2026-04-21T10:00:00+00:00',
                'partial': False,
                'warnings': [],
                'fingerprint': '9be9ad8df0f1d4f8b0e7f1a16fd20b26023b8578d6fd9d91f4cc7a61d8618cb0',
                'data': [
                    {
                        'title': 'One Piece',
                        'url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                        'kind': 'series',
                        'score': 98,
                        'slug': 'One-piece-Edition-originale',
                        'series_slug': 'One-piece-Edition-originale',
                        'volume_slug': None,
                    }
                ],
            }
        }
    )


class ResolveData(BaseModel):
    query: str = Field(examples=['one piece'])
    result: SearchResult | None = None
    confidence: Literal['high', 'medium', 'low', 'none'] = Field(examples=['high'])
    alternatives_count: int = Field(default=0, examples=[3])


class ResolveResponse(BaseEnvelope):
    data: ResolveData

    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'schema_version': SCHEMA_VERSION,
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/recherche/?cat=manga-serie-vf&q=one%20piece',
                'cached': False,
                'fetched_at': '2026-04-20T10:00:00+00:00',
                'cache_expires_at': '2026-04-21T10:00:00+00:00',
                'partial': False,
                'warnings': [],
                'fingerprint': '4f50dd8fa07c5f2fbb90c480baf74d8f06dd85cf57f8503cc64f15ef38d18b60',
                'data': {
                    'query': 'one piece',
                    'confidence': 'high',
                    'alternatives_count': 4,
                    'result': {
                        'title': 'One Piece',
                        'url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                        'kind': 'series',
                        'score': 98,
                        'slug': 'One-piece-Edition-originale',
                        'series_slug': 'One-piece-Edition-originale',
                        'volume_slug': None,
                    },
                },
            }
        }
    )


class NewsItem(BaseModel):
    title: str = Field(examples=['La saison 2 de la série live One Piece disponible sur Netflix !'])
    url: str | None = Field(default=None, examples=['https://www.manga-news.com/index.php/actus/2026/03/10/La-saison-2-de-la-serie-live-One-Piece-disponible-sur-Netflix'])
    published_at: str | None = Field(default=None, examples=['2026-03-10'])
    excerpt: str | None = Field(default=None, examples=["C'est aujourd'hui ! Les fans peuvent désormais se rassasier..."])
    comments: int | None = Field(default=None, examples=[0])
    category: str | None = Field(default=None, examples=['Manga'])


class NewsResponse(BaseEnvelope):
    data: list[NewsItem] = Field(default_factory=list)


class SeriesStats(BaseModel):
    likes: int | None = Field(default=None, examples=[531])
    in_collection: int | None = Field(default=None, examples=[7053])
    in_wishlist: int | None = Field(default=None, examples=[984])
    marketplace: int | None = Field(default=None, examples=[2])
    editorial_score: float | None = Field(default=None, examples=[16.23])
    reader_score: float | None = Field(default=None, examples=[16.5])


class EditionStatus(BaseModel):
    volumes: int | None = Field(default=None, examples=[112])
    status: str | None = Field(default=None, examples=['En cours'])


class SeriesData(BaseModel):
    title: str = Field(examples=['One Piece'])
    title_vo: str | None = Field(default=None, examples=['ワンピース'])
    translated_title: str | None = Field(default=None, examples=['One Piece'])
    summary: str | None = Field(default=None, examples=['Résumé principal de la série.'])
    authors_story: list[str] = Field(default_factory=list, examples=[['Eiichirô ODA']])
    authors_art: list[str] = Field(default_factory=list, examples=[['Eiichirô ODA']])
    translators: list[str] = Field(default_factory=list, examples=[['Djamel RABAHI', 'Julien FAVEREAU']])
    publisher_fr: str | None = Field(default=None, examples=['Glénat'])
    publisher_vo: str | None = Field(default=None, examples=['Shûeisha'])
    collection: str | None = Field(default=None, examples=['Shonen'])
    type: str | None = Field(default=None, examples=['Shonen'])
    genres: list[str] = Field(default_factory=list, examples=[['Aventure', 'Fantastique']])
    prepublication: str | None = Field(default=None, examples=['Shônen Jump'])
    origin: str | None = Field(default=None, examples=['Japon - 1997'])
    illustration: str | None = Field(default=None, examples=['n&b + couleurs'])
    advisory_age: str | None = Field(default=None, examples=['8+'])
    cover_image: str | None = Field(default=None, examples=['https://www.manga-news.com/public/images/series/one-piece.jpg'])
    vf: EditionStatus | None = None
    vo: EditionStatus | None = None
    last_release_date: str | None = Field(default=None, examples=['2026-04-08'])
    next_release_date: str | None = Field(default=None, examples=['2026-05-06'])
    stats: SeriesStats | None = None
    themes: list[str] = Field(default_factory=list, examples=[['Série manga incontournable', 'aventure fantastique pirates']])
    strengths: str | None = Field(default=None, examples=['Un énorme succès populaire.'])
    source_url: str = Field(examples=['https://www.manga-news.com/index.php/serie/One-piece-Edition-originale'])


class SeriesResponse(BaseEnvelope):
    data: SeriesData

    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'schema_version': SCHEMA_VERSION,
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                'cached': False,
                'fetched_at': '2026-04-20T10:00:00+00:00',
                'cache_expires_at': '2026-04-21T10:00:00+00:00',
                'partial': False,
                'warnings': [],
                'fingerprint': 'a7bc612fd6d3f9be9a2194b22e3feef0f90de8dbcd0dd4b12d1662b52c18f1c4',
                'data': {
                    'title': 'One Piece',
                    'title_vo': 'ワンピース',
                    'translated_title': 'One Piece',
                    'summary': 'Résumé principal de la série.',
                    'authors_story': ['Eiichirô ODA'],
                    'authors_art': ['Eiichirô ODA'],
                    'translators': ['Djamel RABAHI', 'Julien FAVEREAU'],
                    'publisher_fr': 'Glénat',
                    'publisher_vo': 'Shûeisha',
                    'collection': 'Shonen',
                    'type': 'Shonen',
                    'genres': ['Aventure', 'Fantastique'],
                    'prepublication': 'Shônen Jump',
                    'origin': 'Japon - 1997',
                    'illustration': 'n&b + couleurs',
                    'advisory_age': '8+',
                    'cover_image': 'https://www.manga-news.com/public/images/series/one-piece.jpg',
                    'vf': {'volumes': 112, 'status': 'En cours'},
                    'vo': {'volumes': 114, 'status': 'En cours'},
                    'last_release_date': '2026-04-08',
                    'next_release_date': '2026-05-06',
                    'stats': {
                        'likes': 531,
                        'in_collection': 7053,
                        'in_wishlist': 984,
                        'marketplace': 2,
                        'editorial_score': 16.23,
                        'reader_score': 16.5,
                    },
                    'themes': ['Série manga incontournable', 'aventure fantastique pirates'],
                    'strengths': 'Un énorme succès populaire.',
                    'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                },
            }
        }
    )


class VolumeData(BaseModel):
    title: str = Field(examples=['One Piece Vol.110'])
    series_title: str | None = Field(default=None, examples=['One Piece'])
    title_vo: str | None = Field(default=None, examples=['ワンピース'])
    translated_title: str | None = Field(default=None, examples=['One Piece'])
    summary: str | None = Field(default=None, examples=['Résumé du volume.'])
    authors_story: list[str] = Field(default_factory=list, examples=[['Eiichirô ODA']])
    authors_art: list[str] = Field(default_factory=list, examples=[['Eiichirô ODA']])
    translators: list[str] = Field(default_factory=list, examples=[['Djamel RABAHI', 'Julien FAVEREAU']])
    publisher_fr: str | None = Field(default=None, examples=['Glénat'])
    publisher_vo: str | None = Field(default=None, examples=['Shûeisha'])
    collection: str | None = Field(default=None, examples=['Shonen'])
    type: str | None = Field(default=None, examples=['Shonen'])
    genres: list[str] = Field(default_factory=list, examples=[['Aventure', 'Fantastique']])
    prepublication: str | None = Field(default=None, examples=['Shônen Jump'])
    origin: str | None = Field(default=None, examples=['Japon - 1997'])
    illustration: str | None = Field(default=None, examples=['208 pages n&b + couleurs'])
    advisory_age: str | None = Field(default=None, examples=['8+'])
    publication_date: str | None = Field(default=None, examples=['2025-09-27'])
    isbn_ean: str | None = Field(default=None, examples=['9782344064092'])
    price_code: str | None = Field(default=None, examples=['7.20'])
    cover_image: str | None = Field(default=None, examples=['https://www.manga-news.com/public/images/series/one-piece-110.jpg'])
    editorial_score: float | None = Field(default=None, examples=[16.0])
    reader_score: float | None = Field(default=None, examples=[15.5])
    source_url: str = Field(examples=['https://www.manga-news.com/index.php/manga/One-Piece/vol-110'])


class VolumeResponse(BaseEnvelope):
    data: VolumeData


class PlanningItem(BaseModel):
    title: str = Field(examples=['One Piece Vol.110'])
    url: str | None = Field(default=None, examples=['https://www.manga-news.com/index.php/manga/One-Piece/vol-110'])
    release_date: str | None = Field(default=None, examples=['2026-04-27'])
    authors: list[str] = Field(default_factory=list, examples=[['Eiichirô ODA']])
    publisher: str | None = Field(default=None, examples=['Glénat'])
    summary: str | None = Field(default=None, examples=['Le retour des Mugiwara dans un nouveau volume.'])
    featured: bool = Field(default=False, examples=[True])
    series_slug: str | None = Field(default=None, examples=['One-Piece'])
    volume_slug: str | None = Field(default=None, examples=['vol-110'])


class PlanningPage(BaseModel):
    section: str = Field(examples=['manga-vf'])
    year: int | None = Field(default=None, examples=[2026])
    month: int | None = Field(default=None, examples=[4])
    page: int | None = Field(default=None, examples=[1])
    items: list[PlanningItem] = Field(default_factory=list)


class PlanningFilters(BaseModel):
    publisher: str | None = Field(default=None, examples=['Glénat'])
    query: str | None = Field(default=None, examples=['one piece'])
    date_from: str | None = Field(default=None, examples=['2026-04-01'])
    date_to: str | None = Field(default=None, examples=['2026-04-30'])


class PlanningData(BaseModel):
    section: str = Field(examples=['manga-vf'])
    year: int | None = Field(default=None, examples=[2026])
    month: int | None = Field(default=None, examples=[4])
    page: int | None = Field(default=None, examples=[1])
    filters: PlanningFilters
    sort: Literal['date_asc', 'date_desc', 'title_asc', 'title_desc'] = Field(examples=['date_asc'])
    total_items: int = Field(examples=[1])
    items: list[PlanningItem] = Field(default_factory=list)


class PlanningResponse(BaseEnvelope):
    data: PlanningData
