from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'ok': True}
    assert response.headers['X-Request-ID']



def test_planning_endpoint_with_stubbed_service():
    class DummyService:
        async def get_planning(self, **kwargs):
            return type('EnvelopeLike', (), {'model_dump': lambda self: {
                'schema_version': '1.0',
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/planning/',
                'cached': False,
                'fetched_at': '2026-04-20T12:00:00+00:00',
                'cache_expires_at': '2026-04-20T18:00:00+00:00',
                'partial': False,
                'warnings': [],
                'fingerprint': 'fp-plan',
                'data': {
                    'section': 'manga-vf',
                    'year': 2026,
                    'month': 4,
                    'page': 1,
                    'filters': {
                        'publisher': 'Glénat',
                        'query': None,
                        'date_from': None,
                        'date_to': None,
                    },
                    'sort': 'date_asc',
                    'total_items': 1,
                    'items': [
                        {
                            'title': 'One Piece Vol.110',
                            'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
                            'release_date': '2026-04-27',
                            'authors': ['Eiichirô ODA'],
                            'publisher': 'Glénat',
                            'summary': 'Résumé',
                            'featured': False,
                            'series_slug': 'One-Piece',
                            'volume_slug': 'vol-110',
                        }
                    ],
                },
            }})()

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/planning?section=manga-vf&year=2026&month=4&publisher=Gl%C3%A9nat')
    assert response.status_code == 200
    payload = response.json()
    assert payload['ok'] is True
    assert payload['schema_version'] == '1.0'
    assert payload['data']['section'] == 'manga-vf'
    assert payload['data']['items'][0]['publisher'] == 'Glénat'
    assert response.headers['X-Data-Fingerprint'] == 'fp-plan'
    assert response.headers['ETag'] == '"fp-plan"'
    assert response.headers['X-Cache-Status'] == 'MISS'
    assert response.headers['Vary'] == 'Authorization, If-None-Match'



def test_series_route_forwards_projection_params():
    class DummyService:
        async def get_series(self, **kwargs):
            assert kwargs['slug'] == 'One-piece-Edition-originale'
            assert kwargs['blocks'] == 'editions,stats'
            assert kwargs['fields'] == 'title,vf.volumes'
            assert kwargs['include_raw_sections'] is True
            return type('EnvelopeLike', (), {'model_dump': lambda self: {
                'schema_version': '1.0',
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                'cached': False,
                'fetched_at': '2026-04-20T12:00:00+00:00',
                'cache_expires_at': '2026-04-21T12:00:00+00:00',
                'partial': False,
                'warnings': [],
                'fingerprint': 'fp-series',
                'data': {
                    'title': 'One Piece',
                    'vf': {'volumes': 112},
                    'stats': {'likes': 531},
                    'raw_sections': {'resume': ['Résumé principal de la série.']},
                },
            }})()

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/series/One-piece-Edition-originale?blocks=editions,stats&fields=title,vf.volumes&include_raw_sections=true')
    assert response.status_code == 200
    payload = response.json()
    assert payload['data']['vf']['volumes'] == 112
    assert 'raw_sections' in payload['data']



def test_search_resolve_and_etag_304():
    class DummyService:
        async def resolve_search(self, **kwargs):
            return type('EnvelopeLike', (), {'model_dump': lambda self: {
                'schema_version': '1.0',
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/recherche/',
                'cached': False,
                'fetched_at': '2026-04-20T12:00:00+00:00',
                'cache_expires_at': '2026-04-20T18:00:00+00:00',
                'partial': False,
                'warnings': [],
                'fingerprint': 'fp-resolve',
                'data': {
                    'query': 'one piece',
                    'kind_requested': 'series',
                    'confidence': 'high',
                    'best': {
                        'title': 'One Piece',
                        'url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                        'kind': 'series',
                        'score': 98,
                        'slug': 'One-piece-Edition-originale',
                        'series_slug': None,
                        'volume_slug': None,
                    },
                    'candidates': [],
                },
            }})()

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/search/resolve?q=one%20piece&kind=series')
        assert response.status_code == 200
        assert response.json()['data']['best']['slug'] == 'One-piece-Edition-originale'
        assert response.headers['ETag'] == '"fp-resolve"'
        not_modified = client.get('/search/resolve?q=one%20piece&kind=series', headers={'If-None-Match': 'W/"fp-resolve", "something-else"'})
    assert not_modified.status_code == 304
    assert not_modified.headers['X-Cache-Status'] == 'MISS'


def test_bad_request_returns_400():
    class DummyService:
        async def get_series(self, **kwargs):
            from app.exceptions import BadRequestError
            raise BadRequestError('Unknown series block: bogus')

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/series/One-piece-Edition-originale?blocks=bogus')
    assert response.status_code == 400
    assert response.json()['detail'] == 'Unknown series block: bogus'



def test_openapi_exposes_series_editions_related_and_resolve_routes():
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    assert response.status_code == 200
    payload = response.json()
    assert '/series/{slug}/editions' in payload['paths']
    assert '/series/{slug}/related' in payload['paths']
    assert '/search/resolve' in payload['paths']
    schemas = payload['components']['schemas']
    assert 'SeriesData' in schemas
    assert 'SeriesEditionsData' in schemas
    assert 'ResolveResponse' in schemas



def test_admin_cache_stats_and_invalidate_routes():
    class DummyCache:
        def stats(self):
            return {
                'db_path': '/tmp/cache.sqlite3',
                'totals': {'entries': 2, 'fresh': 1, 'stale_usable': 1, 'expired': 0},
                'by_namespace': {
                    'series': {'entries': 1, 'fresh': 1, 'stale_usable': 0, 'expired': 0},
                    'planning': {'entries': 1, 'fresh': 0, 'stale_usable': 1, 'expired': 0},
                },
                'watch_snapshots': {'entries': 0, 'oldest_updated_at': None, 'newest_updated_at': None},
                'oldest_fetched_at': '2026-04-20T10:00:00+00:00',
                'newest_fetched_at': '2026-04-20T12:00:00+00:00',
            }

        def invalidate(self, **kwargs):
            assert kwargs['namespace'] == 'planning'
            assert kwargs['expired_only'] is True
            return 1

    with TestClient(app) as client:
        app.state.service = type('ServiceLike', (), {'cache': DummyCache()})()
        stats = client.get('/admin/cache/stats')
        assert stats.status_code == 200
        assert stats.json()['data']['totals']['entries'] == 2
        invalidate = client.post('/admin/cache/invalidate', json={'namespace': 'planning', 'expired_only': True})
    assert invalidate.status_code == 200
    payload = invalidate.json()
    assert payload['deleted'] == 1
    assert payload['stats']['by_namespace']['planning']['stale_usable'] == 1



def test_v1_aliases_are_available():
    with TestClient(app) as client:
        response = client.get('/v1/health')
    assert response.status_code == 200
    assert response.json() == {'ok': True}



def test_openapi_exposes_v1_and_admin_routes():
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    assert response.status_code == 200
    payload = response.json()
    assert '/v1/search/resolve' in payload['paths']
    assert '/admin/cache/stats' in payload['paths']
    assert '/v1/admin/cache/invalidate' in payload['paths']
    schemas = payload['components']['schemas']
    assert 'CacheStatsResponse' in schemas
    assert 'CacheInvalidateRequest' in schemas
