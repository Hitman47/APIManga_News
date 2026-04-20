from fastapi.testclient import TestClient

from app.main import app


class EnvelopeLike:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return self._payload


def test_health_endpoint_and_legacy_disabled_by_default():
    with TestClient(app) as client:
        response = client.get('/v1/health')
        legacy = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'ok': True}
    assert response.headers['X-Request-ID']
    assert legacy.status_code == 404



def test_planning_endpoint_with_stubbed_service():
    class DummyService:
        async def get_planning(self, **kwargs):
            assert kwargs['page'] == 1
            return EnvelopeLike({
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
                'pagination': {
                    'page': 1,
                    'limit': 25,
                    'returned': 1,
                    'total': 1,
                    'has_more': False,
                    'next_page': None,
                    'prev_page': None,
                },
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
                            'number': '110',
                            'number_int': 110,
                            'edition_label': None,
                            'is_special': None,
                            'is_one_shot': None,
                        }
                    ],
                },
            })

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/v1/planning?section=manga-vf&year=2026&month=4&publisher=Gl%C3%A9nat')
    assert response.status_code == 200
    payload = response.json()
    assert payload['ok'] is True
    assert payload['schema_version'] == '1.0'
    assert payload['data']['section'] == 'manga-vf'
    assert payload['data']['items'][0]['publisher'] == 'Glénat'
    assert payload['pagination']['returned'] == 1
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
            return EnvelopeLike({
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
            })

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/v1/series/One-piece-Edition-originale?blocks=editions,stats&fields=title,vf.volumes&include_raw_sections=true')
    assert response.status_code == 200
    payload = response.json()
    assert payload['data']['vf']['volumes'] == 112
    assert 'raw_sections' in payload['data']



def test_search_route_supports_pagination():
    class DummyService:
        async def search(self, **kwargs):
            assert kwargs['page'] == 2
            assert kwargs['limit'] == 10
            return EnvelopeLike({
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
                'fingerprint': 'fp-search-page-2',
                'pagination': {
                    'page': 2,
                    'limit': 10,
                    'returned': 1,
                    'total': 11,
                    'has_more': False,
                    'next_page': None,
                    'prev_page': 1,
                },
                'data': [
                    {
                        'title': 'One Piece Vol.91',
                        'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
                        'kind': 'volume',
                        'score': 98,
                        'slug': None,
                        'series_slug': 'One-Piece',
                        'volume_slug': 'vol-91',
                        'number': '91',
                        'number_int': 91,
                        'edition_label': None,
                        'is_special': None,
                        'is_one_shot': None,
                    }
                ],
            })

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/v1/search?q=one%20piece&kind=volume&mode=all&limit=10&page=2')
    assert response.status_code == 200
    payload = response.json()
    assert payload['pagination']['page'] == 2
    assert payload['data'][0]['number_int'] == 91



def test_search_resolve_and_etag_304():
    class DummyService:
        async def resolve_search(self, **kwargs):
            return EnvelopeLike({
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
                        'number': None,
                        'number_int': None,
                        'edition_label': None,
                        'is_special': None,
                        'is_one_shot': None,
                    },
                    'candidates': [],
                },
            })

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/v1/search/resolve?q=one%20piece&kind=series')
        assert response.status_code == 200
        assert response.json()['data']['best']['slug'] == 'One-piece-Edition-originale'
        assert response.headers['ETag'] == '"fp-resolve"'
        not_modified = client.get('/v1/search/resolve?q=one%20piece&kind=series', headers={'If-None-Match': 'W/"fp-resolve", "something-else"'})
    assert not_modified.status_code == 304
    assert not_modified.headers['X-Cache-Status'] == 'MISS'



def test_bad_request_returns_structured_400():
    class DummyService:
        async def get_series(self, **kwargs):
            from app.exceptions import BadRequestError
            raise BadRequestError('Unknown series block: bogus')

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/v1/series/One-piece-Edition-originale?blocks=bogus')
    assert response.status_code == 400
    payload = response.json()
    assert payload['code'] == 'INVALID_REQUEST'
    assert payload['detail'] == 'Unknown series block: bogus'
    assert payload['ok'] is False



def test_openapi_exposes_only_v1_routes_and_error_models():
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    assert response.status_code == 200
    payload = response.json()
    assert '/v1/series/{slug}/editions' in payload['paths']
    assert '/v1/series/{slug}/related' in payload['paths']
    assert '/v1/search/resolve' in payload['paths']
    assert '/series/{slug}/editions' not in payload['paths']
    assert '/lookup/volume' not in payload['paths']
    schemas = payload['components']['schemas']
    assert 'SeriesData' in schemas
    assert 'SeriesEditionsData' in schemas
    assert 'ResolveResponse' in schemas
    assert 'ErrorResponse' in schemas



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
        stats = client.get('/v1/admin/cache/stats')
        assert stats.status_code == 200
        assert stats.json()['data']['totals']['entries'] == 2
        invalidate = client.post('/v1/admin/cache/invalidate', json={'namespace': 'planning', 'expired_only': True})
    assert invalidate.status_code == 200
    payload = invalidate.json()
    assert payload['deleted'] == 1
    assert payload['stats']['by_namespace']['planning']['stale_usable'] == 1



def test_lookup_volume_route_returns_resolved_volume():
    class DummyService:
        async def lookup_volume(self, **kwargs):
            assert kwargs['series'] == 'One Piece'
            assert kwargs['number'] == '91'
            assert kwargs['limit'] == 10
            return EnvelopeLike({
                'schema_version': '1.0',
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
                'cached': False,
                'fetched_at': '2026-04-20T12:00:00+00:00',
                'cache_expires_at': '2026-04-20T18:00:00+00:00',
                'partial': False,
                'warnings': [],
                'fingerprint': 'fp-lookup',
                'data': {
                    'query': 'One Piece tome 91',
                    'requested_series': 'One Piece',
                    'requested_number': '91',
                    'resolved': {
                        'title': 'One Piece Vol.91',
                        'url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
                        'kind': 'volume',
                        'score': 99,
                        'slug': None,
                        'series_slug': 'One-Piece',
                        'volume_slug': 'vol-91',
                        'number': '91',
                        'number_int': 91,
                        'edition_label': None,
                        'is_special': None,
                        'is_one_shot': None,
                    },
                    'volume': {
                        'title': 'One Piece Vol.91',
                        'series_title': 'One Piece',
                        'number': '91',
                        'number_int': 91,
                        'edition_label': None,
                        'is_special': None,
                        'is_one_shot': None,
                        'publisher_fr': 'Glénat',
                        'publication_date': '2019-07-03',
                        'isbn_ean': '9782344037102',
                        'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-91',
                    },
                    'candidates': [],
                },
            })

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/v1/lookup/volume?series=One%20Piece&number=91')
    assert response.status_code == 200
    payload = response.json()
    assert payload['data']['resolved']['volume_slug'] == 'vol-91'
    assert payload['data']['volume']['number_int'] == 91
    assert response.headers['ETag'] == '"fp-lookup"'



def test_openapi_exposes_lookup_route_and_examples():
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    assert response.status_code == 200
    payload = response.json()
    assert '/v1/lookup/volume' in payload['paths']
    lookup_get = payload['paths']['/v1/lookup/volume']['get']
    assert lookup_get['responses']['200']['content']['application/json']['example']['data']['requested_number'] == '91'
    search_get = payload['paths']['/v1/search']['get']
    q_param = next(param for param in search_get['parameters'] if param['name'] == 'q')
    assert q_param['examples']['one_piece_volume']['value'] == 'one piece tome 91'
    volume_schema = payload['components']['schemas']['VolumeData']
    assert 'number' in volume_schema['properties']
    assert 'number_int' in volume_schema['properties']
    assert 'edition_label' in volume_schema['properties']
