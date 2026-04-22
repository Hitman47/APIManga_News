import asyncio
from pathlib import Path

import pytest

from app.cache import SQLiteCache
from app.exceptions import ParseError
from app.manga_news.service import MangaNewsService


class DummySettings:
    def __init__(self, tmp_path: Path, *, debug_capture_html_on_error: bool = False):
        self.manga_news_base_url = 'https://www.manga-news.com'
        self.log_format = 'text'
        self.cache_stale_grace_seconds = 60
        self.cache_ttl_search_seconds = 60
        self.cache_ttl_series_seconds = 60
        self.cache_ttl_volume_seconds = 60
        self.cache_ttl_news_global_seconds = 60
        self.cache_ttl_news_series_seconds = 60
        self.cache_ttl_planning_seconds = 60
        self.search_score_threshold = 60
        self.max_limit = 50
        self.search_default_enrich = False
        self.search_default_include_editions = True
        self.volume_default_include_parent_editions = False
        self.negative_cache_enabled = True
        self.negative_cache_ttl_seconds = 300
        self.debug_capture_html_on_error = debug_capture_html_on_error
        self.debug_html_dump_dir = tmp_path / 'debug-html'


class DummyFetchResult:
    def __init__(self, text: str, url: str):
        self.text = text
        self.url = url


class CountingFetcher:
    def __init__(self, html: str):
        self.html = html
        self.calls = 0

    async def get_text(self, url: str, params: dict | None = None):
        self.calls += 1
        return DummyFetchResult(self.html, url)


@pytest.mark.asyncio
async def test_negative_cache_prevents_second_fetch_after_parse_error(tmp_path: Path):
    fetcher = CountingFetcher('<html><body><div>Résumé</div><p>pas de titre</p></body></html>')
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=fetcher,
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    with pytest.raises(ParseError):
        await service.get_series(slug='One-piece-Edition-originale')
    with pytest.raises(ParseError):
        await service.get_series(slug='One-piece-Edition-originale')

    assert fetcher.calls == 1
    stats = service.cache.stats()
    assert stats['negative_cache']['totals']['entries'] == 1


@pytest.mark.asyncio
async def test_parse_error_can_dump_debug_html(tmp_path: Path):
    fetcher = CountingFetcher('<html><body><div>Date de publication: 27 Septembre 2025</div></body></html>')
    settings = DummySettings(tmp_path, debug_capture_html_on_error=True)
    service = MangaNewsService(
        settings=settings,
        fetcher=fetcher,
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    with pytest.raises(ParseError) as exc_info:
        await service.get_volume(series_slug='One-Piece', volume_slug='vol-999')

    assert 'Debug HTML saved to' in str(exc_info.value)
    dump_files = list((tmp_path / 'debug-html').glob('*.html'))
    meta_files = list((tmp_path / 'debug-html').glob('*.json'))
    assert dump_files
    assert meta_files



class SlowCountingFetcher(CountingFetcher):
    def __init__(self, html: str, delay_seconds: float = 0.05):
        super().__init__(html)
        self.delay_seconds = delay_seconds

    async def get_text(self, url: str, params: dict | None = None):
        self.calls += 1
        await asyncio.sleep(self.delay_seconds)
        return DummyFetchResult(self.html, url)


@pytest.mark.asyncio
async def test_singleflight_prevents_duplicate_concurrent_series_fetches(tmp_path: Path):
    html = Path('tests/fixtures/series_one_piece.html').read_text(encoding='utf-8')
    fetcher = SlowCountingFetcher(html)
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=fetcher,
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    await asyncio.gather(
        service.get_series(slug='One-piece-Edition-originale'),
        service.get_series(slug='One-piece-Edition-originale'),
    )

    assert fetcher.calls == 1



@pytest.mark.asyncio
async def test_series_editions_reuses_series_cache_and_block_cache(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    series_url = f'{base_url}/index.php/serie/One-piece-Edition-originale'
    vf_url = f'{base_url}/index.php/serie/editions/One-piece-Edition-originale'
    vo_url = f'{base_url}/index.php/serie/editionsVo/One-piece-Edition-originale'

    class MappingFetcher:
        def __init__(self, responses):
            self.responses = responses
            self.calls = []

        async def get_text(self, url: str, params: dict | None = None):
            self.calls.append(url)
            return DummyFetchResult(self.responses[url], url)

    fetcher = MappingFetcher({
        series_url: Path('tests/fixtures/series_one_piece.html').read_text(encoding='utf-8'),
        vf_url: Path('tests/fixtures/html/editions.html').read_text(encoding='utf-8'),
        vo_url: Path('tests/fixtures/html/editions.html').read_text(encoding='utf-8'),
    })
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=fetcher,
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    await service.get_series(slug='One-piece-Edition-originale')
    await service.get_series_editions(slug='One-piece-Edition-originale', edition='all')
    await service.get_series_editions(slug='One-piece-Edition-originale', edition='vf')

    assert fetcher.calls.count(series_url) == 1
    assert fetcher.calls.count(vf_url) == 1
    assert fetcher.calls.count(vo_url) == 1


@pytest.mark.asyncio
async def test_search_uses_settings_defaults_for_optional_flags(tmp_path: Path):
    class SearchDefaultsSettings(DummySettings):
        def __init__(self, tmp_path: Path):
            super().__init__(tmp_path)
            self.search_default_enrich = True
            self.search_default_include_editions = False

    service = MangaNewsService(
        settings=SearchDefaultsSettings(tmp_path),
        fetcher=CountingFetcher('<html></html>'),
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )
    called = {}

    async def fake_get_search_source_results(*, url: str, query: str):
        from app.models import SearchResult
        return [SearchResult(title='One Piece', url=url, kind='series', score=95, slug='One-piece-Edition-originale')]

    async def fake_enrich(results, *, enrich: bool, include_editions: bool):
        called['enrich'] = enrich
        called['include_editions'] = include_editions
        return results

    service._get_search_source_results = fake_get_search_source_results
    service._enrich_search_results = fake_enrich

    await service.search(query='one piece', kind='series', mode='all', limit=10)

    assert called == {'enrich': True, 'include_editions': False}


@pytest.mark.asyncio
async def test_volume_uses_settings_default_include_parent_editions(tmp_path: Path):
    class VolumeDefaultsSettings(DummySettings):
        def __init__(self, tmp_path: Path):
            super().__init__(tmp_path)
            self.volume_default_include_parent_editions = True

    service = MangaNewsService(
        settings=VolumeDefaultsSettings(tmp_path),
        fetcher=CountingFetcher('<html></html>'),
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    class DummyEntry:
        from datetime import UTC, datetime
        fetched_at = datetime(2026, 4, 22, 10, 0, tzinfo=UTC)
        expires_at = datetime(2026, 4, 22, 11, 0, tzinfo=UTC)

    async def fake_get_volume_payload(**kwargs):
        return ({'data': {'title': 'One Piece 1'}, 'source_url': 'https://example/volume'}, DummyEntry(), False, False, [])

    calls = {'series': 0}

    async def fake_get_series_payload(**kwargs):
        calls['series'] += 1
        return ({'data': {'vf': {'volumes': 1}, 'vo': {'volumes': 2}}, 'source_url': 'https://example/series'}, DummyEntry(), False, False, [])

    service._get_volume_payload = fake_get_volume_payload
    service._get_series_payload = fake_get_series_payload
    service._extract_series_slug_from_volume_url = lambda url: 'One-Piece'

    payload = await service.get_volume(series_slug=None, volume_slug=None, url='https://example/volume')

    assert calls['series'] == 1
    assert payload.data['vf']['volumes'] == 1
    assert payload.data['vo']['volumes'] == 2
