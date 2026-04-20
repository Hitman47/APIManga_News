from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Envelope(BaseModel):
    schema_version: str = '1.1'
    ok: bool = True
    found: bool = True
    source: Literal['manga_news'] = 'manga_news'
    source_url: str | None = None
    cached: bool = False
    cache_state: Literal['fresh_hit', 'refreshed', 'stale_fallback'] | None = None
    fetched_at: str | None = None
    cache_expires_at: str | None = None
    partial: bool = False
    parse_status: Literal['complete', 'partial'] = 'complete'
    missing_fields: list[str] = Field(default_factory=list)
    fingerprint: str | None = None
    warnings: list[str] = Field(default_factory=list)
    data: Any


class ErrorEnvelope(BaseModel):
    schema_version: str = '1.1'
    ok: bool = False
    error_code: Literal['not_found', 'parse_error', 'upstream_error']
    detail: str
    source: Literal['manga_news'] = 'manga_news'


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
    items: list[PlanningItem] = Field(default_factory=list)


class CacheNamespaceStats(BaseModel):
    entries: int = 0
    fresh: int = 0
    stale_usable: int = 0
    expired: int = 0


class CacheStatsData(BaseModel):
    db_path: str
    totals: CacheNamespaceStats
    by_namespace: dict[str, CacheNamespaceStats] = Field(default_factory=dict)
    watch_snapshots: dict[str, Any] = Field(default_factory=dict)
    oldest_fetched_at: str | None = None
    newest_fetched_at: str | None = None


class CacheInvalidateData(BaseModel):
    deleted_entries: int
    filters: dict[str, Any] = Field(default_factory=dict)


class PlanningWatchData(BaseModel):
    section: str
    year: int | None = None
    month: int | None = None
    watch_id: str | None = None
    has_previous_snapshot: bool = False
    scope_changed: bool = False
    changed: bool = False
    previous_fingerprint: str | None = None
    current_fingerprint: str
    total_items: int = 0
    added_count: int = 0
    removed_count: int = 0
    added_items: list[PlanningItem] = Field(default_factory=list)
    removed_items: list[PlanningItem] = Field(default_factory=list)
    current_items_preview: list[PlanningItem] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
