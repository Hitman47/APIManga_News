from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Envelope(BaseModel):
    ok: bool = True
    found: bool = True
    source: Literal['manga_news'] = 'manga_news'
    source_url: str | None = None
    cached: bool = False
    fetched_at: str | None = None
    cache_expires_at: str | None = None
    partial: bool = False
    warnings: list[str] = Field(default_factory=list)
    data: Any


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


class SearchResponse(Envelope):
    data: list[SearchResult] = Field(default_factory=list)


class NewsItem(BaseModel):
    title: str
    url: str | None = None
    published_at: str | None = None
    excerpt: str | None = None
    comments: int | None = None
    category: str | None = None


class NewsListResponse(Envelope):
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


class SeriesResponse(Envelope):
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


class VolumeResponse(Envelope):
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


class PlanningFilters(BaseModel):
    publisher: str | None = None
    query: str | None = None
    date_from: str | None = None
    date_to: str | None = None


class PlanningPage(BaseModel):
    section: str
    year: int | None = None
    month: int | None = None
    page: int | None = None
    items: list[PlanningItem] = Field(default_factory=list)


class FilteredPlanningData(BaseModel):
    section: str
    year: int | None = None
    month: int | None = None
    page: int | None = None
    filters: PlanningFilters = Field(default_factory=PlanningFilters)
    sort: str
    total_items: int = 0
    items: list[PlanningItem] = Field(default_factory=list)


class PlanningResponse(Envelope):
    data: FilteredPlanningData


class SeriesNewsSummaryData(BaseModel):
    schema_version: Literal['series-news-summary/v1'] = 'series-news-summary/v1'
    slug: str
    total_items: int
    latest: NewsItem | None = None
    categories: list[str] = Field(default_factory=list)
    source_url: str


class SeriesNewsSummaryResponse(Envelope):
    data: SeriesNewsSummaryData


class SeriesReleaseSummaryData(BaseModel):
    schema_version: Literal['series-release-summary/v1'] = 'series-release-summary/v1'
    slug: str
    title: str
    vf: EditionStatus | None = None
    vo: EditionStatus | None = None
    last_release_date: str | None = None
    next_release_date: str | None = None
    has_upcoming_release: bool = False
    publisher_fr: str | None = None
    source_url: str


class SeriesReleaseSummaryResponse(Envelope):
    data: SeriesReleaseSummaryData


class MachineSeriesSummaryData(BaseModel):
    schema_version: Literal['series-summary/v1'] = 'series-summary/v1'
    slug: str
    title: str
    title_vo: str | None = None
    publisher_fr: str | None = None
    vf: EditionStatus | None = None
    vo: EditionStatus | None = None
    last_release_date: str | None = None
    next_release_date: str | None = None
    source_url: str


class MachineSeriesSummaryResponse(Envelope):
    data: MachineSeriesSummaryData


class MachineVolumeSummaryData(BaseModel):
    schema_version: Literal['volume-summary/v1'] = 'volume-summary/v1'
    series_slug: str | None = None
    volume_slug: str | None = None
    title: str
    series_title: str | None = None
    publication_date: str | None = None
    isbn_ean: str | None = None
    publisher_fr: str | None = None
    editorial_score: float | None = None
    reader_score: float | None = None
    source_url: str


class MachineVolumeSummaryResponse(Envelope):
    data: MachineVolumeSummaryData


class ComparisonDiff(BaseModel):
    field: str
    left: Any = None
    right: Any = None


class ComparisonData(BaseModel):
    schema_version: Literal['compare/v1'] = 'compare/v1'
    kind: Literal['series', 'volume']
    left_source_url: str | None = None
    right_source_url: str | None = None
    compared_fields_count: int
    equal_fields: list[str] = Field(default_factory=list)
    differing_fields: list[ComparisonDiff] = Field(default_factory=list)
    similarity_score: int = 0


class ComparisonResponse(Envelope):
    data: ComparisonData
