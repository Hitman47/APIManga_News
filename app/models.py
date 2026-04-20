from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool = True


class EnvelopeBase(BaseModel):
    ok: bool = True
    found: bool = True
    source: Literal['manga_news'] = 'manga_news'
    source_url: str | None = None
    cached: bool = False
    fetched_at: str | None = None
    cache_expires_at: str | None = None
    partial: bool = False
    warnings: list[str] = Field(default_factory=list)
    schema_version: str = '1.0'
    fingerprint: str | None = None


class SearchResult(BaseModel):
    title: str
    url: str
    kind: Literal['series', 'volume']
    score: int
    slug: str | None = None
    series_slug: str | None = None
    volume_slug: str | None = None


class SearchResponse(EnvelopeBase):
    data: list[SearchResult] = Field(
        default_factory=list,
        examples=[[{
            'title': 'One Piece',
            'url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            'kind': 'series',
            'score': 97,
            'slug': 'One-piece-Edition-originale',
            'series_slug': 'One-piece-Edition-originale',
            'volume_slug': None,
        }]],
    )


class ResolveResult(BaseModel):
    query: str
    kind: Literal['series', 'volume', 'all']
    confidence: Literal['high', 'medium', 'low', 'none']
    result: SearchResult | None = None
    candidates: list[SearchResult] = Field(default_factory=list)


class ResolveResponse(EnvelopeBase):
    data: ResolveResult


class NewsItem(BaseModel):
    title: str
    url: str | None = None
    published_at: str | None = None
    excerpt: str | None = None
    comments: int | None = None
    category: str | None = None


class NewsResponse(EnvelopeBase):
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


class SeriesData(BaseModel):
    title: str
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
    advisory_age: str | None = None
    cover_image: str | None = None
    vf: EditionStatus | None = None
    vo: EditionStatus | None = None
    last_release_date: str | None = None
    next_release_date: str | None = None
    stats: SeriesStats | None = None
    themes: list[str] = Field(default_factory=list)
    strengths: str | None = None
    source_url: str


class SeriesResponse(EnvelopeBase):
    data: SeriesData


class VolumeData(BaseModel):
    title: str
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
    advisory_age: str | None = None
    publication_date: str | None = None
    isbn_ean: str | None = None
    price_code: str | None = None
    cover_image: str | None = None
    editorial_score: float | None = None
    reader_score: float | None = None
    source_url: str


class VolumeResponse(EnvelopeBase):
    data: VolumeData


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


class PlanningData(BaseModel):
    section: Literal['manga-vf', 'manga-vo']
    year: int | None = None
    month: int | None = None
    page: int = 1
    filters: dict[str, str | None] = Field(default_factory=dict)
    sort: Literal['date_asc', 'date_desc', 'title_asc', 'title_desc'] = 'date_asc'
    total_items: int = 0
    items: list[PlanningItem] = Field(default_factory=list)


class PlanningPage(BaseModel):
    section: Literal['manga-vf', 'manga-vo']
    year: int | None = None
    month: int | None = None
    items: list[PlanningItem] = Field(default_factory=list)


class PlanningResponse(EnvelopeBase):
    data: PlanningData
