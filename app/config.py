from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = Field(default='Manga News Private API', alias='APP_NAME')
    app_env: str = Field(default='development', alias='APP_ENV')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')
    log_format: str = Field(default='text', alias='LOG_FORMAT')
    manga_news_base_url: str = Field(default='https://www.manga-news.com', alias='MANGA_NEWS_BASE_URL')
    user_agent: str = Field(default='MangaNewsPrivateAPI/0.1 (+private-selfhosted)', alias='USER_AGENT')
    api_token: str | None = Field(default=None, alias='API_TOKEN')
    admin_token: str | None = Field(default=None, alias='ADMIN_TOKEN')
    db_path: Path = Field(default=Path('/data/cache.sqlite3'), alias='DB_PATH')
    request_timeout_seconds: float = Field(default=20.0, alias='REQUEST_TIMEOUT_SECONDS')
    request_max_retries: int = Field(default=2, alias='REQUEST_MAX_RETRIES')
    request_backoff_seconds: float = Field(default=0.5, alias='REQUEST_BACKOFF_SECONDS')
    sqlite_busy_timeout_ms: int = Field(default=5000, validation_alias=AliasChoices('SQLITE_BUSY_TIMEOUT_MS'))
    cache_memory_entries: int = Field(default=512, validation_alias=AliasChoices('CACHE_MEMORY_ENTRIES'))
    cache_stale_grace_seconds: int = Field(default=7 * 24 * 3600, alias='CACHE_STALE_GRACE_SECONDS')
    cache_ttl_search_seconds: int = Field(default=24 * 3600, alias='CACHE_TTL_SEARCH_SECONDS')
    cache_ttl_series_seconds: int = Field(default=24 * 3600, alias='CACHE_TTL_SERIES_SECONDS')
    cache_ttl_volume_seconds: int = Field(default=7 * 24 * 3600, alias='CACHE_TTL_VOLUME_SECONDS')
    cache_ttl_news_global_seconds: int = Field(default=6 * 3600, alias='CACHE_TTL_NEWS_GLOBAL_SECONDS')
    cache_ttl_news_series_seconds: int = Field(default=12 * 3600, alias='CACHE_TTL_NEWS_SERIES_SECONDS')
    cache_ttl_planning_seconds: int = Field(default=12 * 3600, alias='CACHE_TTL_PLANNING_SECONDS')
    search_score_threshold: int = Field(default=60, alias='SEARCH_SCORE_THRESHOLD')
    default_limit: int = Field(default=10, alias='DEFAULT_LIMIT')
    max_limit: int = Field(default=50, alias='MAX_LIMIT')
    search_source_concurrency: int = Field(
        default=4,
        validation_alias=AliasChoices('SEARCH_SOURCE_CONCURRENCY', 'SEARCH_FETCH_CONCURRENCY'),
    )
    search_enrichment_concurrency: int = Field(
        default=4,
        validation_alias=AliasChoices('SEARCH_ENRICHMENT_CONCURRENCY', 'SEARCH_ENRICH_CONCURRENCY'),
    )
    search_default_enrich: bool = Field(default=True, validation_alias=AliasChoices('SEARCH_DEFAULT_ENRICH'))
    search_default_include_editions: bool = Field(
        default=True,
        validation_alias=AliasChoices('SEARCH_DEFAULT_INCLUDE_EDITIONS'),
    )
    search_default_prefer_main_series: bool = Field(
        default=False,
        validation_alias=AliasChoices('SEARCH_DEFAULT_PREFER_MAIN_SERIES'),
    )
    search_default_include_related: bool = Field(
        default=True,
        validation_alias=AliasChoices('SEARCH_DEFAULT_INCLUDE_RELATED'),
    )
    search_default_include_books: bool = Field(
        default=True,
        validation_alias=AliasChoices('SEARCH_DEFAULT_INCLUDE_BOOKS'),
    )
    volume_default_include_parent_editions: bool = Field(
        default=False,
        validation_alias=AliasChoices('VOLUME_DEFAULT_INCLUDE_PARENT_EDITIONS'),
    )
    enable_docs: bool = Field(default=True, alias='ENABLE_DOCS')
    debug_capture_html_on_error: bool = Field(default=False, alias='DEBUG_CAPTURE_HTML_ON_ERROR')
    debug_html_dump_dir: Path = Field(default=Path('/tmp/manga-news-debug-html'), alias='DEBUG_HTML_DUMP_DIR')
    negative_cache_enabled: bool = Field(default=True, alias='NEGATIVE_CACHE_ENABLED')
    negative_cache_ttl_seconds: int = Field(default=120, alias='NEGATIVE_CACHE_TTL_SECONDS')
    rate_limit_enabled: bool = Field(default=False, alias='RATE_LIMIT_ENABLED')
    rate_limit_requests: int = Field(default=60, alias='RATE_LIMIT_REQUESTS')
    rate_limit_window_seconds: int = Field(default=60, alias='RATE_LIMIT_WINDOW_SECONDS')
    rate_limit_scope: str = Field(default='ip_or_token', alias='RATE_LIMIT_SCOPE')
    rate_limit_include_admin: bool = Field(default=False, alias='RATE_LIMIT_INCLUDE_ADMIN')
    rate_limit_exempt_paths: str = Field(
        default='/openapi.json,/docs,/redoc,/health',
        alias='RATE_LIMIT_EXEMPT_PATHS',
    )

    @property
    def docs_url(self) -> str | None:
        return '/docs' if self.enable_docs else None

    @property
    def redoc_url(self) -> str | None:
        return '/redoc' if self.enable_docs else None

    @property
    def rate_limit_exempt_path_list(self) -> list[str]:
        return [part.strip() for part in self.rate_limit_exempt_paths.split(',') if part.strip()]


def _resolve_writable_db_path(db_path: Path) -> Path:
    candidate = db_path.expanduser()
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate
    except OSError:
        fallback = Path.cwd() / '.data' / candidate.name
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.db_path = _resolve_writable_db_path(settings.db_path)
    return settings
