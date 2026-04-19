from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = Field(default='Manga News Private API', alias='APP_NAME')
    app_env: str = Field(default='development', alias='APP_ENV')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')
    manga_news_base_url: str = Field(default='https://www.manga-news.com', alias='MANGA_NEWS_BASE_URL')
    user_agent: str = Field(default='MangaNewsPrivateAPI/0.1 (+private-selfhosted)', alias='USER_AGENT')
    api_token: str | None = Field(default=None, alias='API_TOKEN')
    db_path: Path = Field(default=Path('/data/cache.sqlite3'), alias='DB_PATH')
    request_timeout_seconds: float = Field(default=20.0, alias='REQUEST_TIMEOUT_SECONDS')
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
    enable_docs: bool = Field(default=True, alias='ENABLE_DOCS')

    @property
    def docs_url(self) -> str | None:
        return '/docs' if self.enable_docs else None

    @property
    def redoc_url(self) -> str | None:
        return '/redoc' if self.enable_docs else None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
