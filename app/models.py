from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PaginationMeta(BaseModel):
    page: int = 1
    limit: int
    returned: int
    total: int
    has_more: bool = False


class BaseEnvelope(BaseModel):
    schema_version: str = '1.0'
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
    pagination: PaginationMeta | None = None


class Envelope(BaseEnvelope):
    data: Any = None


class ApiErrorResponse(BaseModel):
    ok: bool = False
    code: str
    detail: str


class CacheNamespaceStats(BaseModel):
    entries: int
    fresh: int
    stale_usable: int = 0
    expired: int


class NegativeCacheStats(BaseModel):
    entries: int
    fresh: int
    expired: int


class NegativeCacheDetails(BaseModel):
    totals: NegativeCacheStats
    by_namespace: dict[str, NegativeCacheStats] = Field(default_factory=dict)


class WatchSnapshotStats(BaseModel):
    entries: int
    oldest_updated_at: str | None = None
    newest_updated_at: str | None = None


class CacheStatsData(BaseModel):
    db_path: str
    totals: CacheNamespaceStats
    by_namespace: dict[str, CacheNamespaceStats] = Field(default_factory=dict)
    negative_cache: NegativeCacheDetails
    watch_snapshots: WatchSnapshotStats
    oldest_fetched_at: str | None = None
    newest_fetched_at: str | None = None


class CacheStatsResponse(BaseModel):
    ok: bool = True
    data: CacheStatsData


class MetricsData(BaseModel):
    started_at: str
    counters: dict[str, int] = Field(default_factory=dict)
    ratios: dict[str, float] = Field(default_factory=dict)


class MetricsResponse(BaseModel):
    ok: bool = True
    data: MetricsData


class CacheInvalidateRequest(BaseModel):
    cache_key: str | None = None
    namespace: str | None = None
    resource_url: str | None = None
    expired_only: bool = False
    all_entries: bool = False


class CacheInvalidateResponse(BaseModel):
    ok: bool = True
    deleted: int
    filters: dict[str, Any] = Field(default_factory=dict)
    stats: CacheStatsData


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
    number: str | None = None
    number_int: int | None = None
    edition_label: str | None = None
    is_special: bool | None = None
    is_one_shot: bool | None = None


class SearchResponse(BaseEnvelope):
    data: list[SearchResult] = Field(default_factory=list)


class ResolveResult(BaseModel):
    title: str
    url: str
    kind: Literal['series', 'volume']
    score: int
    slug: str | None = None
    series_slug: str | None = None
    volume_slug: str | None = None
    number: str | None = None
    number_int: int | None = None
    edition_label: str | None = None
    is_special: bool | None = None
    is_one_shot: bool | None = None


class ResolveData(BaseModel):
    query: str
    kind_requested: Literal['series', 'volume', 'all']
    confidence: Literal['high', 'medium', 'low', 'none']
    best: ResolveResult | None = None
    candidates: list[ResolveResult] = Field(default_factory=list)


class ResolveResponse(BaseEnvelope):
    data: ResolveData | None = None


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
    number: str | None = None
    number_int: int | None = None
    edition_label: str | None = None
    is_special: bool | None = None
    is_one_shot: bool | None = None
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
    number: str | None = None
    number_int: int | None = None
    edition_label: str | None = None
    is_special: bool | None = None
    is_one_shot: bool | None = None


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


class SeriesEditionItem(BaseModel):
    title: str
    url: str
    series_slug: str | None = None
    volume_slug: str | None = None
    number: str | None = None
    number_int: int | None = None
    edition_label: str | None = None
    is_special: bool | None = None
    is_one_shot: bool | None = None
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


class VolumeLookupData(BaseModel):
    query: str
    requested_series: str
    requested_number: str
    resolved: ResolveResult | None = None
    volume: VolumeData | dict[str, Any] | None = None
    candidates: list[ResolveResult] = Field(default_factory=list)


class VolumeLookupResponse(BaseEnvelope):
    data: VolumeLookupData | None = None
