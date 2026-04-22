import pytest
from pathlib import Path
from types import SimpleNamespace

from app.cache import SQLiteCache
from app.manga_news.service import MangaNewsService, project_resource_payload, versioned_cache_key


SERIES_PAYLOAD = {
    'title': 'One Piece',
    'title_vo': 'ワンピース',
    'vf': {'volumes': 112, 'status': 'En cours'},
    'vo': {'volumes': 114, 'status': 'En cours'},
    'stats': {'likes': 531, 'reader_score': 16.5},
    'raw_sections': {'resume': ['Résumé principal de la série.']},
}



def test_project_resource_payload_fields_only():
    projected = project_resource_payload(SERIES_PAYLOAD, resource='series', fields=['vf.volumes'])
    assert projected == {'vf': {'volumes': 112}}



def test_project_resource_payload_blocks_and_fields_union():
    projected = project_resource_payload(
        SERIES_PAYLOAD,
        resource='series',
        blocks=['stats'],
        fields=['title'],
    )
    assert projected['title'] == 'One Piece'
    assert projected['stats']['likes'] == 531
    assert 'raw_sections' not in projected



def test_project_resource_payload_include_raw_sections():
    projected = project_resource_payload(SERIES_PAYLOAD, resource='series', include_raw_sections=True)
    assert projected['raw_sections']['resume'][0] == 'Résumé principal de la série.'


class _FakeFetcher:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def get_text(self, url, params=None):
        self.calls.append(url)
        response = self.responses[url]
        return SimpleNamespace(text=response, url=url)


@pytest.mark.asyncio
async def test_search_enriches_alternate_titles_from_detail_pages(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    search_url = f'{base_url}/index.php/recherche/?cat=manga-serie-vf&q=one piece'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-serie-vo&q=one piece'
    series_url = f'{base_url}/index.php/serie/One-piece-Edition-originale'

    search_html = f'''<html><body><a href="{series_url}">One Piece</a></body></html>'''
    series_html = Path('tests/fixtures/series_one_piece.html').read_text(encoding='utf-8')

    fetcher = _FakeFetcher({
        search_url: search_html,
        search_url_vo: '<html><body></body></html>',
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
    )
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=SQLiteCache(tmp_path / 'cache.sqlite3'))

    response = await service.search(query='one piece', kind='series', mode='all', limit=5, enrich=True)

    assert response.data[0]['title'] == 'One Piece'
    assert response.data[0]['title_vo'] == 'ワンピース'
    assert response.data[0]['translated_title'] == 'One Piece'
    assert response.data[0]['source_type'] == 'Shonen'
    assert response.data[0]['media_kind'] == 'manga'
    assert fetcher.calls.count(series_url) == 1


@pytest.mark.asyncio
async def test_search_enriches_volume_results_with_series_counts(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    search_url = f'{base_url}/index.php/recherche/?cat=manga-volume-vf&q=dogs bullets carnage'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-volume-vo&q=dogs bullets carnage'
    volume_url = f'{base_url}/index.php/manga/Dogs:-Bullets-Carnage/vol-1'
    series_url = f'{base_url}/index.php/serie/Dogs:-Bullets-Carnage'

    search_html = f'''<html><body><a href="{volume_url}">Dogs: Bullets &amp; Carnage Vol.1</a></body></html>'''
    volume_html = '''<html><body><h1>Dogs: Bullets &amp; Carnage Vol.1</h1><ul><li>Titre VO: Dogs: Bullets &amp; Carnage</li><li>Titre traduit: Dogs - Bullets &amp; Carnage</li></ul></body></html>'''
    series_html = '''<html><body><h1>Dogs: Bullets &amp; Carnage</h1><div id="numberblock"><div><div><span class="version">VF:</span><span>9</span><span class="small">(En cours)</span></div></div><div><a href="https://www.manga-news.com/index.php/serie-vo/Dogs-Bullets-Carnage-vo"><span class="version">VO</span>: 10 <span class="small">(En pause)</span></a></div></div></body></html>'''

    fetcher = _FakeFetcher({
        search_url: search_html,
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

    response = await service.search(query='dogs bullets carnage', kind='volume', mode='all', limit=5, enrich=True)

    first = response.data[0]
    assert first['number'] == '1'
    assert first['title_vo'] == 'Dogs: Bullets & Carnage'
    assert first['translated_title'] == 'Dogs - Bullets & Carnage'
    assert first['vf']['volumes'] == 9
    assert first['vo']['volumes'] == 10
    assert first['media_kind'] == 'manga'


@pytest.mark.asyncio
async def test_search_prioritizes_main_manga_over_books_and_marks_spinoffs(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    query = 'naruto'
    search_url = f'{base_url}/index.php/recherche/?cat=manga-serie-vf&q={query}'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-serie-vo&q={query}'
    naruto_url = f'{base_url}/index.php/serie/Naruto'
    roman_url = f'{base_url}/index.php/serie/Naruto-Roman'
    essay_url = f'{base_url}/index.php/serie/Philosophie-de-Naruto-la'
    boruto_url = f'{base_url}/index.php/serie/Boruto-Naruto-Next-Generations'

    search_html = f'''
    <html><body>
      <a href="{essay_url}">Philosophie de Naruto (la) (2021)</a>
      <a href="{roman_url}">Naruto - Roman (2008) Masashi KISHIMOTO</a>
      <a href="{naruto_url}">Naruto (1999) Masashi KISHIMOTO</a>
      <a href="{boruto_url}">Boruto - Naruto Next Generations (2016)</a>
    </body></html>
    '''
    naruto_html = '''
    <html><body><h1>Naruto</h1><ul><li>Type: Shonen</li></ul>
    <div id="numberblock"><div><div><span class="version">VF:</span><span>72</span><span class="small">(Terminé)</span></div></div></div>
    </body></html>
    '''
    roman_html = '''
    <html><body><h1>Naruto - Roman</h1><ul><li>Type: Roman</li></ul></body></html>
    '''
    essay_html = '''
    <html><body><h1>Philosophie de Naruto (la)</h1><ul><li>Type: Essai</li></ul></body></html>
    '''
    boruto_html = '''
    <html><body><h1>Boruto - Naruto Next Generations</h1><ul><li>Type: Shonen</li></ul>
    <div>Manga en relation</div><a href="/index.php/serie/Naruto">Naruto</a>
    </body></html>
    '''

    fetcher = _FakeFetcher({
        search_url: search_html,
        search_url_vo: '<html><body></body></html>',
        naruto_url: naruto_html,
        roman_url: roman_html,
        essay_url: essay_html,
        boruto_url: boruto_html,
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

    response = await service.search(query=query, kind='series', mode='all', limit=10, enrich=True, include_editions=False)

    assert [item['slug'] for item in response.data[:4]] == [
        'Naruto',
        'Boruto-Naruto-Next-Generations',
        'Naruto-Roman',
        'Philosophie-de-Naruto-la',
    ]
    assert response.data[0]['media_kind'] == 'manga'
    assert response.data[1]['media_kind'] == 'manga_spinoff'
    assert response.data[2]['media_kind'] == 'novel'
    assert response.data[3]['media_kind'] == 'essay'


@pytest.mark.asyncio
async def test_search_exposes_relation_kind_and_root_series_slug_with_main_series_preference(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    query = 'naruto'
    search_url = f'{base_url}/index.php/recherche/?cat=manga-serie-vf&q={query}'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-serie-vo&q={query}'
    naruto_url = f'{base_url}/index.php/serie/Naruto'
    boruto_url = f'{base_url}/index.php/serie/Boruto-Naruto-Next-Generations'
    roman_url = f'{base_url}/index.php/serie/Naruto-Roman'

    search_html = f'''
    <html><body>
      <a href="{roman_url}">Naruto - Roman (2008) Masashi KISHIMOTO</a>
      <a href="{boruto_url}">Boruto - Naruto Next Generations (2016)</a>
      <a href="{naruto_url}">Naruto (1999) Masashi KISHIMOTO</a>
    </body></html>
    '''
    naruto_html = '<html><body><h1>Naruto</h1><ul><li>Type: Shonen</li></ul></body></html>'
    boruto_html = '''
    <html><body><h1>Boruto - Naruto Next Generations</h1><ul><li>Type: Shonen</li></ul>
    <div>Manga en relation</div><a href="/index.php/serie/Naruto">Naruto</a>
    </body></html>
    '''
    roman_html = '<html><body><h1>Naruto - Roman</h1><ul><li>Type: Roman</li></ul></body></html>'

    fetcher = _FakeFetcher({
        search_url: search_html,
        search_url_vo: '<html><body></body></html>',
        naruto_url: naruto_html,
        boruto_url: boruto_html,
        roman_url: roman_html,
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

    response = await service.search(
        query=query,
        kind='series',
        mode='all',
        limit=10,
        prefer_main_series=True,
        include_related=True,
        include_books=True,
    )

    assert response.data[0]['slug'] == 'Naruto'
    assert response.data[0]['relation_kind'] == 'main'
    assert response.data[0]['root_series_slug'] == 'Naruto'
    assert response.data[1]['slug'] == 'Boruto-Naruto-Next-Generations'
    assert response.data[1]['relation_kind'] == 'spinoff'
    assert response.data[1]['root_series_slug'] == 'Naruto'
    assert response.data[2]['slug'] == 'Naruto-Roman'
    assert response.data[2]['relation_kind'] == 'related_book'
    assert response.data[2]['root_series_slug'] == 'Naruto'


@pytest.mark.asyncio
async def test_search_filters_exclude_books_and_related_results(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    query = 'naruto'
    search_url = f'{base_url}/index.php/recherche/?cat=manga-serie-vf&q={query}'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-serie-vo&q={query}'
    naruto_url = f'{base_url}/index.php/serie/Naruto'
    boruto_url = f'{base_url}/index.php/serie/Boruto-Naruto-Next-Generations'
    roman_url = f'{base_url}/index.php/serie/Naruto-Roman'

    search_html = f'''
    <html><body>
      <a href="{roman_url}">Naruto - Roman (2008) Masashi KISHIMOTO</a>
      <a href="{boruto_url}">Boruto - Naruto Next Generations (2016)</a>
      <a href="{naruto_url}">Naruto (1999) Masashi KISHIMOTO</a>
    </body></html>
    '''
    naruto_html = '<html><body><h1>Naruto</h1><ul><li>Type: Shonen</li></ul></body></html>'
    boruto_html = '''
    <html><body><h1>Boruto - Naruto Next Generations</h1><ul><li>Type: Shonen</li></ul>
    <div>Manga en relation</div><a href="/index.php/serie/Naruto">Naruto</a>
    </body></html>
    '''
    roman_html = '<html><body><h1>Naruto - Roman</h1><ul><li>Type: Roman</li></ul></body></html>'

    fetcher = _FakeFetcher({
        search_url: search_html,
        search_url_vo: '<html><body></body></html>',
        naruto_url: naruto_html,
        boruto_url: boruto_html,
        roman_url: roman_html,
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

    response = await service.search(
        query=query,
        kind='series',
        mode='all',
        limit=10,
        prefer_main_series=True,
        include_related=False,
        include_books=False,
        media_kinds='manga',
    )

    assert [item['slug'] for item in response.data] == ['Naruto']


@pytest.mark.asyncio
async def test_get_volume_enriches_with_parent_series_counts(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    volume_url = f'{base_url}/index.php/manga/One-Piece/vol-110'
    series_url = f'{base_url}/index.php/serie/One-Piece'

    fetcher = _FakeFetcher({
        volume_url: Path('tests/fixtures/volume_one_piece_110.html').read_text(encoding='utf-8'),
        series_url: '<html><body><h1>One Piece</h1><div id="numberblock"><div><div><span class="version">VF:</span><span>112</span><span class="small">(En cours)</span></div></div><div><a href="https://www.manga-news.com/index.php/serie-vo/One-Piece-vo"><span class="version">VO</span>: 114 <span class="small">(En cours)</span></a></div></div></body></html>',
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
async def test_get_volume_does_not_fetch_parent_series_by_default(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    volume_url = f'{base_url}/index.php/manga/One-Piece/vol-110'
    series_url = f'{base_url}/index.php/serie/One-Piece'

    fetcher = _FakeFetcher({
        volume_url: Path('tests/fixtures/volume_one_piece_110.html').read_text(encoding='utf-8'),
        series_url: '<html><body><h1>One Piece</h1></body></html>',
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

    response = await service.get_volume(series_slug='One-Piece', volume_slug='vol-110')

    assert 'vf' not in response.data or response.data['vf'] is None
    assert fetcher.calls == [volume_url]


@pytest.mark.asyncio
async def test_get_series_ignores_incompatible_cached_payload_and_refetches(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    series_url = f'{base_url}/index.php/serie/One-piece-Edition-originale'
    cache = SQLiteCache(tmp_path / 'cache.sqlite3')
    cache.set(
        cache_key=versioned_cache_key('series', series_url),
        payload={
            '_schema_version': 'outdated-cache-version',
            'data': {
                'title': 'One Piece',
                'vf': None,
                'vo': None,
                'source_url': series_url,
            },
            'source_url': series_url,
        },
        ttl_seconds=3600,
        stale_grace_seconds=3600,
        namespace='series',
        resource_url=series_url,
    )

    fetcher = _FakeFetcher({
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
    service = MangaNewsService(settings=settings, fetcher=fetcher, cache=cache)

    response = await service.get_series(slug='One-piece-Edition-originale')

    assert response.data['vf']['volumes'] == 112
    assert response.data['vo']['volumes'] == 114
    assert fetcher.calls == [series_url]
