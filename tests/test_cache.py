from pathlib import Path

from app.cache import SQLiteCache


def test_cache_stats_and_invalidate(tmp_path: Path):
    cache = SQLiteCache(tmp_path / 'cache.sqlite3')
    cache.set('key1', {'x': 1}, ttl_seconds=3600, stale_grace_seconds=3600, namespace='series', resource_url='https://example/series')
    cache.set('key2', {'x': 2}, ttl_seconds=3600, stale_grace_seconds=3600, namespace='planning', resource_url='https://example/planning')
    stats = cache.stats()
    assert stats['totals']['entries'] == 2
    assert stats['by_namespace']['series']['entries'] == 1
    assert stats['by_namespace']['planning']['entries'] == 1

    deleted = cache.invalidate(namespace='planning')
    assert deleted == 1
    stats_after = cache.stats()
    assert stats_after['totals']['entries'] == 1
    assert 'planning' not in stats_after['by_namespace'] or stats_after['by_namespace']['planning']['entries'] == 0
