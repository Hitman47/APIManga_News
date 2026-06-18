import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.cache import SQLiteCache
from app.exceptions import ParseError
from app.manga_news.service import CACHE_SCHEMA_VERSION, MangaNewsService, versioned_cache_key
from app.models import Envelope


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
        self.search_default_prefer_main_series = False
        self.search_default_include_related = True
        self.search_default_include_books = True
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
async def test_fresh_negative_cache_keeps_serving_usable_stale_payload(tmp_path: Path):
    cache = SQLiteCache(tmp_path / 'cache.sqlite3')
    series_url = 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale'
    cache_key = versioned_cache_key('series', series_url)
    cache.set(
        cache_key,
        {
            '_schema_version': CACHE_SCHEMA_VERSION,
            'data': {'title': 'One Piece', 'source_url': series_url},
            'source_url': series_url,
        },
        ttl_seconds=-1,
        stale_grace_seconds=3600,
        namespace='series',
        resource_url=series_url,
    )
    cache.set_negative(
        cache_key,
        error_code='UPSTREAM_PARSE_ERROR',
        detail='recent parser failure',
        ttl_seconds=300,
        namespace='series',
        resource_url=series_url,
    )
    fetcher = CountingFetcher('<html></html>')
    service = MangaNewsService(settings=DummySettings(tmp_path), fetcher=fetcher, cache=cache)

    response = await service.get_series(slug='One-piece-Edition-originale')

    assert response.cached is True
    assert response.partial is True
    assert response.data['title'] == 'One Piece'
    assert 'negatively cached' in response.warnings[0]
    assert fetcher.calls == 0


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
async def test_release_state_by_series_uses_vf_editions_and_optional_isbn(tmp_path: Path):
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=CountingFetcher('<html></html>'),
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    class DummyEntry:
        fetched_at = datetime(2026, 6, 18, 10, 0, tzinfo=UTC)
        expires_at = datetime(2026, 6, 19, 10, 0, tzinfo=UTC)

    async def fake_get_series_payload(**kwargs):
        assert kwargs == {'slug': 'One-piece-Edition-originale'}
        return (
            {
                'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                'data': {
                    'title': 'One Piece',
                    'publisher_fr': 'Glénat',
                    'vf': {'volumes': 111, 'status': 'En cours'},
                },
            },
            DummyEntry(),
            True,
            False,
            [],
        )

    async def fake_get_series_editions(**kwargs):
        assert kwargs == {'slug': 'One-piece-Edition-originale', 'edition': 'vf'}
        return Envelope(
            schema_version='1.0',
            ok=True,
            found=True,
            source='manga_news',
            source_url='https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            cached=True,
            fetched_at='2026-06-18T10:00:00+00:00',
            cache_expires_at='2026-06-19T10:00:00+00:00',
            partial=False,
            warnings=[],
            fingerprint='fp-editions',
            data={
                'title': 'One Piece',
                'series_slug': 'One-piece-Edition-originale',
                'vf': {
                    'edition': 'vf',
                    'source_url': 'https://www.manga-news.com/index.php/serie/editions/One-piece-Edition-originale',
                    'total': 4,
                    'items': [
                        {
                            'title': 'One Piece Vol.109',
                            'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-109',
                            'series_slug': 'One-Piece',
                            'volume_slug': 'vol-109',
                            'number': '109',
                            'number_int': 109,
                            'publication_date': '2026-01-02',
                            'is_special': False,
                            'is_one_shot': False,
                        },
                        {
                            'title': 'One Piece Vol.110',
                            'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
                            'series_slug': 'One-Piece',
                            'volume_slug': 'vol-110',
                            'number': '110',
                            'number_int': 110,
                            'publication_date': '2026-04-02',
                            'is_special': False,
                            'is_one_shot': False,
                        },
                        {
                            'title': 'One Piece Vol.111',
                            'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-111',
                            'series_slug': 'One-Piece',
                            'volume_slug': 'vol-111',
                            'number': '111',
                            'number_int': 111,
                            'publication_date': '2026-07-02',
                            'is_special': False,
                            'is_one_shot': False,
                        },
                        {
                            'title': 'One Piece Special',
                            'url': 'https://www.manga-news.com/index.php/manga/One-Piece/special',
                            'series_slug': 'One-Piece',
                            'volume_slug': 'special',
                            'number': '999',
                            'number_int': 999,
                            'publication_date': '2026-06-01',
                            'is_special': True,
                            'is_one_shot': False,
                        },
                    ],
                },
                'vo': None,
                'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            },
        )

    volume_calls = []

    async def fake_get_volume(**kwargs):
        volume_calls.append(kwargs)
        return Envelope(
            schema_version='1.0',
            ok=True,
            found=True,
            source='manga_news',
            source_url=f"https://www.manga-news.com/index.php/manga/{kwargs['series_slug']}/{kwargs['volume_slug']}",
            cached=True,
            fetched_at='2026-06-18T10:00:00+00:00',
            cache_expires_at='2026-06-19T10:00:00+00:00',
            partial=False,
            warnings=[],
            fingerprint=f"fp-{kwargs['volume_slug']}",
            data={'isbn_ean': f"9780000000{kwargs['volume_slug'][-3:]}"},
        )

    service._get_series_payload = fake_get_series_payload
    service.get_series_editions = fake_get_series_editions
    service.get_volume = fake_get_volume

    response = await service.get_release_state_by_series(
        slug='One-piece-Edition-originale',
        include_isbn=True,
        today='2026-06-18',
    )

    assert response.cached is True
    assert response.partial is False
    assert response.data['status'] == 'FOUND_CONFIRMED'
    assert response.data['confidence'] == 'high'
    assert response.data['last_released']['number'] == '110'
    assert response.data['last_released']['isbn_ean'] == '9780000000110'
    assert response.data['next_release']['number'] == '111'
    assert response.data['next_release']['isbn_ean'] == '9780000000111'
    assert [call['volume_slug'] for call in volume_calls] == ['vol-110', 'vol-111']
    assert all(call['fields'] == 'isbn_ean' for call in volume_calls)
    assert all(call['include_parent_editions'] is False for call in volume_calls)


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

    async def fake_enrich(results, *, query: str, enrich: bool, include_editions: bool, load_search_metadata: bool = False):
        called['query'] = query
        called['enrich'] = enrich
        called['include_editions'] = include_editions
        called['load_search_metadata'] = load_search_metadata
        return results

    service._get_search_source_results = fake_get_search_source_results
    service._enrich_search_results = fake_enrich

    await service.search(query='one piece', kind='series', mode='all', limit=10)

    assert called == {'query': 'one piece', 'enrich': True, 'include_editions': False, 'load_search_metadata': True}


@pytest.mark.asyncio
async def test_search_best_enriches_only_one_candidate(tmp_path: Path):
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=CountingFetcher('<html></html>'),
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )
    enriched_counts = []

    async def fake_get_search_source_results(*, url: str, query: str):
        from app.models import SearchResult

        return [
            SearchResult(
                title=f'One Piece {index}',
                url=f'https://example.test/series/{index}',
                kind='series',
                score=100 - index,
                slug=f'One-Piece-{index}',
            )
            for index in range(12)
        ]

    async def fake_enrich(results, **kwargs):
        enriched_counts.append(len(results))
        return results

    service._get_search_source_results = fake_get_search_source_results
    service._enrich_search_results = fake_enrich

    response = await service.search(
        query='one piece',
        kind='series',
        mode='best',
        limit=1,
        enrich=True,
        include_editions=True,
    )

    assert enriched_counts == [1]
    assert len(response.data) == 1


@pytest.mark.asyncio
async def test_light_search_defaults_only_fetch_search_pages(tmp_path: Path):
    class LightSearchSettings(DummySettings):
        def __init__(self, path: Path):
            super().__init__(path)
            self.search_default_enrich = False
            self.search_default_include_editions = False

    base_url = 'https://www.manga-news.com'
    query = 'one piece'
    search_url = f'{base_url}/index.php/recherche/?cat=manga-serie-vf&q={query}'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-serie-vo&q={query}'
    series_url = f'{base_url}/index.php/serie/One-piece-Edition-originale'

    class MappingFetcher:
        def __init__(self):
            self.calls = []

        async def get_text(self, url: str, params: dict | None = None):
            self.calls.append(url)
            html = f'<html><body><a href="{series_url}">One Piece</a></body></html>' if url == search_url else '<html></html>'
            return DummyFetchResult(html, url)

    fetcher = MappingFetcher()
    service = MangaNewsService(
        settings=LightSearchSettings(tmp_path),
        fetcher=fetcher,
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    response = await service.search(query=query, kind='series', mode='best', limit=1)

    assert response.found is True
    assert fetcher.calls == [search_url, search_url_vo]


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

    async def fake_get_series_search_meta(**kwargs):
        calls['series'] += 1
        return ({'data': {'vf': {'volumes': 1}, 'vo': {'volumes': 2}}, 'source_url': 'https://example/series'}, DummyEntry(), False, False, [])

    service._get_volume_payload = fake_get_volume_payload
    service._get_series_search_meta = fake_get_series_search_meta
    service._extract_series_slug_from_volume_url = lambda url: 'One-Piece'

    payload = await service.get_volume(series_slug=None, volume_slug=None, url='https://example/volume')

    assert calls['series'] == 1
    assert payload.data['vf']['volumes'] == 1
    assert payload.data['vo']['volumes'] == 2


@pytest.mark.asyncio
async def test_volume_payload_drops_related_field(tmp_path: Path):
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=CountingFetcher('<html></html>'),
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    class DummyEntry:
        fetched_at = datetime(2026, 6, 18, 10, 0, tzinfo=UTC)
        expires_at = datetime(2026, 6, 19, 10, 0, tzinfo=UTC)

    async def fake_get_volume_payload(**kwargs):
        return (
            {
                'data': {
                    'title': 'One Piece Vol.110',
                    'number': '110',
                    'related': {'external': [{'title': 'Acheter', 'url': 'https://example.test'}]},
                },
                'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
            },
            DummyEntry(),
            True,
            False,
            [],
        )

    service._get_volume_payload = fake_get_volume_payload

    payload = await service.get_volume(series_slug='One-Piece', volume_slug='vol-110')

    assert payload.data['title'] == 'One Piece Vol.110'
    assert 'related' not in payload.data


@pytest.mark.asyncio
async def test_get_volume_by_number_resolves_volume_slug_from_vf_editions(tmp_path: Path):
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=CountingFetcher('<html></html>'),
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    async def fake_get_series_editions(**kwargs):
        assert kwargs == {'slug': 'One-piece-Edition-originale', 'edition': 'vf'}
        return Envelope(
            schema_version='1.0',
            ok=True,
            found=True,
            source='manga_news',
            source_url='https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            cached=True,
            fetched_at='2026-06-18T10:00:00+00:00',
            cache_expires_at='2026-06-19T10:00:00+00:00',
            partial=False,
            warnings=[],
            fingerprint='fp-editions',
            data={
                'title': 'One Piece',
                'series_slug': 'One-piece-Edition-originale',
                'vf': {
                    'edition': 'vf',
                    'total': 2,
                    'items': [
                        {
                            'title': 'One Piece Vol.110 Collector',
                            'url': 'https://www.manga-news.com/index.php/manga/One-Piece-Collector/vol-110',
                            'series_slug': 'One-Piece-Collector',
                            'volume_slug': 'vol-110-collector',
                            'number': '110',
                            'number_int': 110,
                            'publication_date': '2026-04-02',
                            'is_special': True,
                        },
                        {
                            'title': 'One Piece Vol.110',
                            'url': 'https://www.manga-news.com/index.php/manga/One-piece-Edition-originale/vol-110',
                            'series_slug': 'One-piece-Edition-originale',
                            'volume_slug': 'vol-110',
                            'number': '110',
                            'number_int': 110,
                            'publication_date': '2026-04-02',
                            'is_special': False,
                        },
                    ],
                },
                'vo': None,
            },
        )

    volume_calls = []

    async def fake_get_volume(**kwargs):
        volume_calls.append(kwargs)
        return Envelope(
            schema_version='1.0',
            ok=True,
            found=True,
            source='manga_news',
            source_url='https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
            cached=True,
            fetched_at='2026-06-18T10:00:00+00:00',
            cache_expires_at='2026-06-19T10:00:00+00:00',
            partial=False,
            warnings=[],
            fingerprint='fp-volume-110',
            data={'title': 'One Piece Vol.110', 'number': '110'},
        )

    service.get_series_editions = fake_get_series_editions
    service.get_volume = fake_get_volume

    payload = await service.get_volume_by_number(
        series_slug='One-piece-Edition-originale',
        number=110,
        fields='title,number',
        include_parent_editions=False,
    )

    assert payload.data['number'] == '110'
    assert volume_calls == [
        {
            'series_slug': 'One-piece-Edition-originale',
            'volume_slug': 'vol-110',
            'blocks': None,
            'fields': 'title,number',
            'include_raw_sections': False,
            'include_parent_editions': False,
        }
    ]



@pytest.mark.asyncio
async def test_search_then_get_series_reuses_raw_html_cache(tmp_path: Path):
    base_url = 'https://www.manga-news.com'
    query = 'one piece'
    search_url = f'{base_url}/index.php/recherche/?cat=manga-serie-vf&q={query}'
    search_url_vo = f'{base_url}/index.php/recherche/?cat=manga-serie-vo&q={query}'
    series_url = f'{base_url}/index.php/serie/One-piece-Edition-originale'

    class MappingFetcher:
        def __init__(self, responses):
            self.responses = responses
            self.calls = []

        async def get_text(self, url: str, params: dict | None = None):
            self.calls.append(url)
            return DummyFetchResult(self.responses[url], url)

    fetcher = MappingFetcher({
        search_url: f'<html><body><a href="{series_url}">One Piece</a></body></html>',
        search_url_vo: '<html><body></body></html>',
        series_url: Path('tests/fixtures/series_one_piece.html').read_text(encoding='utf-8'),
    })
    service = MangaNewsService(
        settings=DummySettings(tmp_path),
        fetcher=fetcher,
        cache=SQLiteCache(tmp_path / 'cache.sqlite3'),
    )

    await service.search(query=query, kind='series', mode='all', limit=5, enrich=True)
    await service.get_series(slug='One-piece-Edition-originale')

    assert fetcher.calls.count(series_url) == 1
