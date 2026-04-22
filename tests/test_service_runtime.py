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
    async def get_text(self, url: str, params: dict | None = None):
        await asyncio.sleep(0.05)
        return await super().get_text(url, params=params)


@pytest.mark.asyncio
async def test_single_flight_prevents_duplicate_concurrent_fetches(tmp_path: Path):
    fetcher = SlowCountingFetcher(Path('tests/fixtures/series_one_piece.html').read_text(encoding='utf-8'))
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=fetcher,
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    await asyncio.gather(
        service.get_series(slug='One-piece-Edition-originale'),
        service.get_series(slug='One-piece-Edition-originale'),
        service.get_series(slug='One-piece-Edition-originale'),
    )

    assert fetcher.calls == 1


class MappingFetcher:
    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.calls: list[str] = []

    async def get_text(self, url: str, params: dict | None = None):
        self.calls.append(url)
        return DummyFetchResult(self.responses[url], url)


@pytest.mark.asyncio
async def test_search_reuses_cached_source_pages_across_modes_and_enrichment(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    search_url_vf = f'{base_url}/index.php/recherche/?cat=manga-serie-vf&q=one piece'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-serie-vo&q=one piece'
    series_url = f'{base_url}/index.php/serie/One-piece-Edition-originale'
    fetcher = MappingFetcher({
        search_url_vf: f'<html><body><a href="{series_url}">One Piece</a></body></html>',
        search_url_vo: '<html><body></body></html>',
        series_url: Path('tests/fixtures/series_one_piece.html').read_text(encoding='utf-8'),
    })
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=fetcher,
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    first = await service.search(query='one piece', kind='series', mode='all', limit=5, enrich=False)
    second = await service.search(query='one piece', kind='series', mode='best', limit=1, enrich=True)

    assert first.data[0]['title'] == 'One Piece'
    assert first.data[0]['vf']['volumes'] == 112
    assert second.data[0]['title_vo'] == 'ワンピース'
    assert fetcher.calls.count(search_url_vf) == 1
    assert fetcher.calls.count(search_url_vo) == 1
    assert fetcher.calls.count(series_url) == 1


@pytest.mark.asyncio
async def test_series_editions_reuses_cached_series_and_edition_blocks(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    series_slug = 'One-piece-Edition-originale'
    series_url = f'{base_url}/index.php/serie/{series_slug}'
    vf_url = f'{base_url}/index.php/serie/editions/{series_slug}'
    vo_url = f'{base_url}/index.php/serie/editionsVo/{series_slug}'
    editions_html = Path('tests/fixtures/html/editions.html').read_text(encoding='utf-8')
    fetcher = MappingFetcher({
        series_url: Path('tests/fixtures/series_one_piece.html').read_text(encoding='utf-8'),
        vf_url: editions_html,
        vo_url: editions_html,
    })
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=fetcher,
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    first = await service.get_series_editions(slug=series_slug, edition='vf')
    second = await service.get_series_editions(slug=series_slug, edition='all')

    assert first.data['vf']['total'] == 2
    assert second.data['vf']['total'] == 2
    assert second.data['vo']['total'] == 2
    assert fetcher.calls.count(series_url) == 1
    assert fetcher.calls.count(vf_url) == 1
    assert fetcher.calls.count(vo_url) == 1


@pytest.mark.asyncio
async def test_search_keeps_vf_vo_counters_without_full_enrichment(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    search_url_vf = f'{base_url}/index.php/recherche/?cat=manga-serie-vf&q=a couple of cuckoos'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-serie-vo&q=a couple of cuckoos'
    series_url = f'{base_url}/index.php/serie/A-Couple-of-Cuckoos'

    fetcher = MappingFetcher({
        search_url_vf: f'<html><body><a href="{series_url}">A Couple of Cuckoos</a></body></html>',
        search_url_vo: '<html><body></body></html>',
        series_url: """<html><body><h1>A Couple of Cuckoos</h1><div>VF : 19 (En cours)</div><div>VO : 22 (En cours)</div></body></html>""",
    })
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=fetcher,
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    response = await service.search(query='a couple of cuckoos', kind='series', mode='best', limit=1, enrich=False)

    item = response.data[0]
    assert item['title'] == 'A Couple of Cuckoos'
    assert item['title_vo'] is None
    assert item['translated_title'] is None
    assert item['vf']['volumes'] == 19
    assert item['vo']['volumes'] == 22
    assert fetcher.calls.count(series_url) == 1
