import pytest
from pathlib import Path
from types import SimpleNamespace

from app.cache import SQLiteCache
from app.manga_news.service import MangaNewsService, project_resource_payload
from app.utils import make_cache_key


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

    response = await service.search(query='one piece', kind='series', mode='all', limit=5)

    assert response.data[0]['title'] == 'One Piece'
    assert response.data[0]['title_vo'] == 'ワンピース'
    assert response.data[0]['translated_title'] == 'One Piece'
    assert fetcher.calls.count(series_url) == 1



@pytest.mark.asyncio
async def test_series_fetch_ignores_legacy_cache_key_after_payload_schema_change(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    series_url = f'{base_url}/index.php/serie/One-piece-Edition-originale'
    cache = SQLiteCache(tmp_path / 'cache.sqlite3')
    cache.set(
        cache_key=make_cache_key('series', series_url),
        payload={'data': {'title': 'stale payload', 'vf': None, 'vo': None}, 'source_url': series_url},
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

    assert fetcher.calls == [series_url]
    assert response.data['title'] == 'One Piece'
    assert response.data['vf']['volumes'] == 112
    assert response.data['vo']['volumes'] == 114
