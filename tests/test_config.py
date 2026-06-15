from app.config import Settings


def test_v2_defaults_keep_search_light_and_bound_upstream_concurrency(monkeypatch):
    monkeypatch.delenv('SEARCH_DEFAULT_ENRICH', raising=False)
    monkeypatch.delenv('SEARCH_DEFAULT_INCLUDE_EDITIONS', raising=False)
    monkeypatch.delenv('REQUEST_MAX_CONCURRENCY', raising=False)

    settings = Settings(_env_file=None)

    assert settings.search_default_enrich is False
    assert settings.search_default_include_editions is False
    assert settings.request_max_concurrency == 6


def test_settings_accept_legacy_and_restored_env_knobs(monkeypatch):
    monkeypatch.setenv('SEARCH_FETCH_CONCURRENCY', '7')
    monkeypatch.setenv('SEARCH_ENRICH_CONCURRENCY', '8')
    monkeypatch.setenv('SQLITE_BUSY_TIMEOUT_MS', '9000')
    monkeypatch.setenv('CACHE_MEMORY_ENTRIES', '123')
    monkeypatch.setenv('SEARCH_DEFAULT_ENRICH', 'true')
    monkeypatch.setenv('SEARCH_DEFAULT_INCLUDE_EDITIONS', 'false')
    monkeypatch.setenv('SEARCH_DEFAULT_PREFER_MAIN_SERIES', 'true')
    monkeypatch.setenv('SEARCH_DEFAULT_INCLUDE_RELATED', 'false')
    monkeypatch.setenv('SEARCH_DEFAULT_INCLUDE_BOOKS', 'false')
    monkeypatch.setenv('VOLUME_DEFAULT_INCLUDE_PARENT_EDITIONS', 'true')
    monkeypatch.setenv('REQUEST_MAX_CONCURRENCY', '9')

    settings = Settings(_env_file=None)

    assert settings.search_source_concurrency == 7
    assert settings.search_enrichment_concurrency == 8
    assert settings.sqlite_busy_timeout_ms == 9000
    assert settings.cache_memory_entries == 123
    assert settings.search_default_enrich is True
    assert settings.search_default_include_editions is False
    assert settings.search_default_prefer_main_series is True
    assert settings.search_default_include_related is False
    assert settings.search_default_include_books is False
    assert settings.volume_default_include_parent_editions is True
    assert settings.request_max_concurrency == 9
