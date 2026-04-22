from pathlib import Path
from types import SimpleNamespace

import pytest

from app.cache import SQLiteCache
from app.manga_news.service import MangaNewsService


class _FakeFetcher:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def get_text(self, url, params=None):
        self.calls.append(url)
        return SimpleNamespace(text=self.responses[url], url=url)


@pytest.mark.asyncio
async def test_search_series_enrichment_adds_titles_and_vf_vo(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    search_url = f'{base_url}/index.php/recherche/?cat=manga-serie-vf&q=one piece'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-serie-vo&q=one piece'
    series_url = f'{base_url}/index.php/serie/One-piece-Edition-originale'

    fetcher = _FakeFetcher({
        search_url: f'<html><body><a href="{series_url}">One Piece</a></body></html>',
        search_url_vo: '<html><body></body></html>',
        series_url: Path('tests/fixtures/series_one_piece.html').read_text(encoding='utf-8'),
    })
    settings = SimpleNamespace(
        manga_news_base_url=base_url,
        cache_stale_grace_seconds=3600,
        cache_ttl_search_seconds=3600,
        cache_ttl_series_seconds=3600,
        cache_ttl_volume_seconds=3600,
        cache_ttl_news_global_seconds=3600,
        cache_ttl_news_series_seconds=3600,
        cache_ttl_planning_seconds=3600,
        search_score_threshold=1,
        max_limit=50,
        negative_cache_enabled=True,
        negative_cache_ttl_seconds=120,
    )
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=SQLiteCache(tmp_path / 'cache.sqlite3'))

    response = await service.search(query='one piece', kind='series', mode='all', limit=5)

    item = response.data[0]
    assert item['title_vo'] == 'ワンピース'
    assert item['translated_title'] == 'One Piece'
    assert item['vf']['volumes'] == 112
    assert item['vo']['volumes'] == 114


@pytest.mark.asyncio
async def test_search_volume_enrichment_adds_titles_and_parent_vf_vo(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    query = 'dogs bullets carnage'
    search_url = f'{base_url}/index.php/recherche/?cat=manga-volume-vf&q={query}'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-volume-vo&q={query}'
    series_url = f'{base_url}/index.php/serie/Dogs:-Bullets-Carnage'
    volume_url = f'{base_url}/index.php/manga/Dogs:-Bullets-Carnage/vol-1'

    volume_html = '''
    <html>
      <body>
        <h1>Dogs: Bullets & Carnage Vol.1</h1>
        <ul>
          <li>Titre VO : Dogs: Bullets & Carnage</li>
          <li>Titre traduit : Dogs: Bullets & Carnage</li>
          <li>Collection : Seinen</li>
          <li>Type : Seinen</li>
          <li>Date de publication : 09 Octobre 2008</li>
        </ul>
        <div>Résumé</div><p>Résumé</p>
      </body>
    </html>
    '''
    series_html = '''
    <html>
      <body>
        <h1>Dogs: Bullets & Carnage</h1>
        <ul>
          <li>Titre VO : Dogs: Bullets & Carnage</li>
          <li>Titre traduit : Dogs: Bullets & Carnage</li>
        </ul>
        <div>VF:9 (En cours)</div>
        <div>VO : 10 (En pause)</div>
      </body>
    </html>
    '''

    fetcher = _FakeFetcher({
        search_url: f'<html><body><a href="{volume_url}">Dogs: Bullets & Carnage Vol.1</a></body></html>',
        search_url_vo: '<html><body></body></html>',
        volume_url: volume_html,
        series_url: series_html,
    })
    settings = SimpleNamespace(
        manga_news_base_url=base_url,
        cache_stale_grace_seconds=3600,
        cache_ttl_search_seconds=3600,
        cache_ttl_series_seconds=3600,
        cache_ttl_volume_seconds=3600,
        cache_ttl_news_global_seconds=3600,
        cache_ttl_news_series_seconds=3600,
        cache_ttl_planning_seconds=3600,
        search_score_threshold=1,
        max_limit=50,
        negative_cache_enabled=True,
        negative_cache_ttl_seconds=120,
    )
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=SQLiteCache(tmp_path / 'cache.sqlite3'))

    response = await service.search(query=query, kind='volume', mode='all', limit=5)

    item = response.data[0]
    assert item['title_vo'] == 'Dogs: Bullets & Carnage'
    assert item['translated_title'] == 'Dogs: Bullets & Carnage'
    assert item['number'] == '1'
    assert item['vf']['volumes'] == 9
    assert item['vo']['volumes'] == 10


@pytest.mark.asyncio
async def test_volume_payload_includes_parent_vf_vo(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    series_url = f'{base_url}/index.php/serie/One-Piece'
    volume_url = f'{base_url}/index.php/manga/One-Piece/vol-110'

    fetcher = _FakeFetcher({
        volume_url: Path('tests/fixtures/volume_one_piece_110.html').read_text(encoding='utf-8'),
        series_url: Path('tests/fixtures/series_one_piece.html').read_text(encoding='utf-8'),
    })
    settings = SimpleNamespace(
        manga_news_base_url=base_url,
        cache_stale_grace_seconds=3600,
        cache_ttl_search_seconds=3600,
        cache_ttl_series_seconds=3600,
        cache_ttl_volume_seconds=3600,
        cache_ttl_news_global_seconds=3600,
        cache_ttl_news_series_seconds=3600,
        cache_ttl_planning_seconds=3600,
        search_score_threshold=1,
        max_limit=50,
        negative_cache_enabled=True,
        negative_cache_ttl_seconds=120,
    )
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=SQLiteCache(tmp_path / 'cache.sqlite3'))

    response = await service.get_volume(series_slug='One-Piece', volume_slug='vol-110', include_parent_editions=True)

    assert response.data['vf']['volumes'] == 112
    assert response.data['vo']['volumes'] == 114



@pytest.mark.asyncio
async def test_search_source_cache_is_reused_across_modes_and_limits(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    query = 'one piece'
    search_url = f'{base_url}/index.php/recherche/?cat=manga-serie-vf&q={query}'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-serie-vo&q={query}'
    series_url = f'{base_url}/index.php/serie/One-piece-Edition-originale'

    fetcher = _FakeFetcher({
        search_url: f'<html><body><a href="{series_url}">One Piece</a></body></html>',
        search_url_vo: '<html><body></body></html>',
        series_url: Path('tests/fixtures/series_one_piece.html').read_text(encoding='utf-8'),
    })
    settings = SimpleNamespace(
        manga_news_base_url=base_url,
        cache_stale_grace_seconds=3600,
        cache_ttl_search_seconds=3600,
        cache_ttl_series_seconds=3600,
        cache_ttl_volume_seconds=3600,
        cache_ttl_news_global_seconds=3600,
        cache_ttl_news_series_seconds=3600,
        cache_ttl_planning_seconds=3600,
        search_score_threshold=1,
        max_limit=50,
        negative_cache_enabled=True,
        negative_cache_ttl_seconds=120,
    )
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=SQLiteCache(tmp_path / 'cache.sqlite3'))

    await service.search(query=query, kind='series', mode='best', limit=1)
    first_call_count = len(fetcher.calls)
    await service.search(query=query, kind='series', mode='all', limit=5)

    assert first_call_count == 3
    assert len(fetcher.calls) == 3
    assert fetcher.calls.count(search_url) == 1
    assert fetcher.calls.count(search_url_vo) == 1
    assert fetcher.calls.count(series_url) == 1


@pytest.mark.asyncio
async def test_search_volume_enrichment_reuses_parent_series_once_per_series(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    query = 'dogs bullets carnage'
    search_url = f'{base_url}/index.php/recherche/?cat=manga-volume-vf&q={query}'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-volume-vo&q={query}'
    series_url = f'{base_url}/index.php/serie/Dogs:-Bullets-Carnage'
    volume_url_1 = f'{base_url}/index.php/manga/Dogs:-Bullets-Carnage/vol-1'
    volume_url_2 = f'{base_url}/index.php/manga/Dogs:-Bullets-Carnage/vol-2'

    volume_html_1 = '''
    <html><body><h1>Dogs: Bullets &amp; Carnage Vol.1</h1><ul><li>Titre VO : Dogs: Bullets &amp; Carnage</li><li>Titre traduit : Dogs: Bullets &amp; Carnage</li></ul></body></html>
    '''
    volume_html_2 = '''
    <html><body><h1>Dogs: Bullets &amp; Carnage Vol.2</h1><ul><li>Titre VO : Dogs: Bullets &amp; Carnage</li><li>Titre traduit : Dogs: Bullets &amp; Carnage</li></ul></body></html>
    '''
    series_html = '''
    <html><body><h1>Dogs: Bullets &amp; Carnage</h1><div id="numberblock"><div><div><span class="version">VF:</span><span>9</span><span class="small">(En cours)</span></div></div><div><a href="https://www.manga-news.com/index.php/serie-vo/Dogs-Bullets-Carnage-vo"><span class="version">VO</span>: 10 <span class="small">(En pause)</span></a></div></div></body></html>
    '''

    fetcher = _FakeFetcher({
        search_url: f'<html><body><a href="{volume_url_1}">Dogs: Bullets &amp; Carnage Vol.1</a><a href="{volume_url_2}">Dogs: Bullets &amp; Carnage Vol.2</a></body></html>',
        search_url_vo: '<html><body></body></html>',
        volume_url_1: volume_html_1,
        volume_url_2: volume_html_2,
        series_url: series_html,
    })
    settings = SimpleNamespace(
        manga_news_base_url=base_url,
        cache_stale_grace_seconds=3600,
        cache_ttl_search_seconds=3600,
        cache_ttl_series_seconds=3600,
        cache_ttl_volume_seconds=3600,
        cache_ttl_news_global_seconds=3600,
        cache_ttl_news_series_seconds=3600,
        cache_ttl_planning_seconds=3600,
        search_score_threshold=1,
        max_limit=50,
        negative_cache_enabled=True,
        negative_cache_ttl_seconds=120,
    )
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=SQLiteCache(tmp_path / 'cache.sqlite3'))

    response = await service.search(query=query, kind='volume', mode='all', limit=5)

    assert len(response.data) == 2
    assert fetcher.calls.count(series_url) == 1
    assert fetcher.calls.count(volume_url_1) == 1
    assert fetcher.calls.count(volume_url_2) == 1
