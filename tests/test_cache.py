from pathlib import Path

from app.cache import SQLiteCache


def test_cache_stats_and_invalidate(tmp_path: Path):
    cache = SQLiteCache(tmp_path / 'cache.sqlite3')
    cache.set('key1', {'x': 1}, ttl_seconds=3600, stale_grace_seconds=3600, namespace='series', resource_url='https://example/series')
    cache.set('key2', {'x': 2}, ttl_seconds=3600, stale_grace_seconds=3600, namespace='planning', resource_url='https://example/planning')
    cache.set_negative('neg1', error_code='UPSTREAM_PARSE_ERROR', detail='broken html', ttl_seconds=120, namespace='series', resource_url='https://example/series')
    stats = cache.stats()
    assert stats['totals']['entries'] == 2
    assert stats['by_namespace']['series']['entries'] == 1
    assert stats['by_namespace']['planning']['entries'] == 1
    assert stats['negative_cache']['totals']['entries'] == 1
    assert stats['negative_cache']['by_namespace']['series']['entries'] == 1

    deleted = cache.invalidate(namespace='planning')
    assert deleted == 1
    stats_after = cache.stats()
    assert stats_after['totals']['entries'] == 1
    assert 'planning' not in stats_after['by_namespace'] or stats_after['by_namespace']['planning']['entries'] == 0


def test_negative_cache_round_trip(tmp_path: Path):
    cache = SQLiteCache(tmp_path / 'cache.sqlite3')
    cache.set_negative(
        'neg-series',
        error_code='UPSTREAM_FETCH_ERROR',
        detail='upstream down',
        ttl_seconds=60,
        namespace='series',
        resource_url='https://example/series',
        debug_dump_path='/tmp/debug.html',
    )
    entry = cache.get_negative('neg-series')
    assert entry is not None
    assert entry.error_code == 'UPSTREAM_FETCH_ERROR'
    assert entry.detail == 'upstream down'
    assert entry.debug_dump_path == '/tmp/debug.html'


def test_memory_cache_is_configurable_and_clears_on_invalidate(tmp_path: Path):
    cache = SQLiteCache(tmp_path / 'cache.sqlite3', busy_timeout_ms=9000, memory_entries=1)
    cache.set('key1', {'x': 1}, ttl_seconds=3600, stale_grace_seconds=3600, namespace='series', resource_url='https://example/series/1')
    assert cache.stats()['memory_cache']['configured_entries'] == 1
    assert cache.stats()['memory_cache']['entry_count'] == 1

    cache.set('key2', {'x': 2}, ttl_seconds=3600, stale_grace_seconds=3600, namespace='series', resource_url='https://example/series/2')
    cache_stats = cache.stats()
    assert cache_stats['memory_cache']['configured_entries'] == 1
    assert cache_stats['memory_cache']['entry_count'] == 1

    pragma_timeout = cache._conn.execute('PRAGMA busy_timeout').fetchone()[0]
    assert pragma_timeout == 9000

    deleted = cache.invalidate(all_entries=True)
    assert deleted >= 2
    assert cache.stats()['memory_cache']['entry_count'] == 0
