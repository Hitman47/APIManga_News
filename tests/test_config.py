from app.config import Settings


def test_settings_accept_legacy_and_restored_env_knobs(monkeypatch):
    monkeypatch.setenv('SEARCH_FETCH_CONCURRENCY', '7')
    monkeypatch.setenv('SEARCH_ENRICH_CONCURRENCY', '8')
    monkeypatch.setenv('SQLITE_BUSY_TIMEOUT_MS', '9000')
    monkeypatch.setenv('CACHE_MEMORY_ENTRIES', '123')
    monkeypatch.setenv('SEARCH_DEFAULT_ENRICH', 'true')
    monkeypatch.setenv('SEARCH_DEFAULT_INCLUDE_EDITIONS', 'false')
    monkeypatch.setenv('VOLUME_DEFAULT_INCLUDE_PARENT_EDITIONS', 'true')

    settings = Settings(_env_file=None)

    assert settings.search_source_concurrency == 7
    assert settings.search_enrichment_concurrency == 8
    assert settings.sqlite_busy_timeout_ms == 9000
    assert settings.cache_memory_entries == 123
    assert settings.search_default_enrich is True
    assert settings.search_default_include_editions is False
    assert settings.volume_default_include_parent_editions is True
