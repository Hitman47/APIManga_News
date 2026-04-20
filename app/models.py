from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field


T = TypeVar('T')


class Envelope(BaseModel, Generic[T]):
    ok: bool = True
    found: bool = True
    source: Literal['manga_news'] = 'manga_news'
    source_url: str | None = None
    cached: bool = False
    fetched_at: str | None = None
    cache_expires_at: str | None = None
    partial: bool = False
    warnings: list[str] = Field(default_factory=list)
    data: T


class HealthResponse(BaseModel):
    ok: bool = True


class SearchResult(BaseModel):
    title: str
    url: str
    kind: Literal['series', 'volume']
    score: int
    slug: str | None = None
    series_slug: str | None = None
    volume_slug: str | None = None


class NewsItem(BaseModel):
    title: str
    url: str | None = None
    published_at: str | None = None
    excerpt: str | None = None
    comments: int | None = None
    category: str | None = None


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
    page_count: int | None = None
    has_color_pages: bool | None = None
    advisory_age: str | None = None
    cover_image: str | None = None
    vf: EditionStatus | None = None
    vo: EditionStatus | None = None
    last_release_date: str | None = None
    next_release_date: str | None = None
    buy_digital_url: str | None = None
    stats: SeriesStats | None = None
    themes: list[str] = Field(default_factory=list)
    critique_excerpt: str | None = None
    strengths: str | None = None
    related_series: list[str] = Field(default_factory=list)
    recommended_series: list[str] = Field(default_factory=list)
    related_media: list[str] = Field(default_factory=list)
    dossiers: list[str] = Field(default_factory=list)
    universe: str | None = None
    games_url: str | None = None
    goodies_url: str | None = None
    external_links: list[str] = Field(default_factory=list)
    source_url: str


class VolumeData(BaseModel):
    title: str
    series_title: str | None = None
    volume_number: int | None = None
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
    page_count: int | None = None
    has_color_pages: bool | None = None
    advisory_age: str | None = None
    publication_date: str | None = None
    isbn_ean: str | None = None
    price_code: str | None = None
    cover_image: str | None = None
    stats: SeriesStats | None = None
    editorial_score: float | None = None
    reader_score: float | None = None
    themes: list[str] = Field(default_factory=list)
    critique_excerpt: str | None = None
    strengths: str | None = None
    related_series: list[str] = Field(default_factory=list)
    recommended_series: list[str] = Field(default_factory=list)
    related_media: list[str] = Field(default_factory=list)
    dossiers: list[str] = Field(default_factory=list)
    universe: str | None = None
    games_url: str | None = None
    goodies_url: str | None = None
    external_links: list[str] = Field(default_factory=list)
    buy_digital_url: str | None = None
    source_url: str


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


class PlanningFilters(BaseModel):
    publisher: str | None = None
    query: str | None = None
    date_from: str | None = None
    date_to: str | None = None


class PlanningData(BaseModel):
    section: str
    year: int | None = None
    month: int | None = None
    page: int | None = None
    filters: PlanningFilters = Field(default_factory=PlanningFilters)
    sort: str = 'date_asc'
    total_items: int = 0
    items: list[PlanningItem] = Field(default_factory=list)


class PlanningPage(BaseModel):
    section: str
    year: int | None = None
    month: int | None = None
    page: int | None = None
    items: list[PlanningItem] = Field(default_factory=list)


class SearchResponse(Envelope[list[SearchResult]]):
    pass


class SeriesResponse(Envelope[SeriesData]):
    pass


class VolumeResponse(Envelope[VolumeData]):
    pass


class NewsResponse(Envelope[list[NewsItem]]):
    pass


class PlanningResponse(Envelope[PlanningData]):
    pass
