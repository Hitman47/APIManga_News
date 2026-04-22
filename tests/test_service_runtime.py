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
