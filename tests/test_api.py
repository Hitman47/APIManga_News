from fastapi.testclient import TestClient

from app.main import app


class EnvelopeLike:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return self._payload



def test_health_endpoint_versioned_only():
    with TestClient(app) as client:
        response = client.get('/v1/health')
        legacy = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'ok': True}
    assert response.headers['X-Request-ID']
    assert legacy.status_code == 404
    assert legacy.json()['code'] == 'ENDPOINT_NOT_FOUND'



def test_planning_endpoint_with_stubbed_service_exposes_pagination():
    class DummyService:
        async def get_planning(self, **kwargs):
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
                'pagination': {'page': 1, 'limit': 10, 'returned': 1, 'total': 2, 'has_more': True},
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
                    'total_items': 2,
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
            })

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/v1/planning?section=manga-vf&year=2026&month=4&publisher=Gl%C3%A9nat')
    assert response.status_code == 200
    payload = response.json()
    assert payload['ok'] is True
    assert payload['pagination']['has_more'] is True
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
                'pagination': {'page': 1, 'limit': 10, 'returned': 1, 'total': 1, 'has_more': False},
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



def test_bad_request_returns_400_with_stable_code():
    class DummyService:
        async def get_series(self, **kwargs):
            from app.exceptions import BadRequestError
            raise BadRequestError('Unknown series block: bogus')

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/v1/series/One-piece-Edition-originale?blocks=bogus')
    assert response.status_code == 400
    assert response.json()['code'] == 'INVALID_REQUEST'
    assert response.json()['detail'] == 'Unknown series block: bogus'



def test_openapi_exposes_only_v1_routes_when_legacy_disabled():
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    assert response.status_code == 200
    payload = response.json()
    assert '/v1/search/resolve' in payload['paths']
    assert '/v1/lookup/volume' in payload['paths']
    assert '/v1/admin/cache/stats' in payload['paths']
    assert '/search/resolve' not in payload['paths']
    assert '/lookup/volume' not in payload['paths']
    schemas = payload['components']['schemas']
    assert 'ApiErrorResponse' in schemas
    assert 'PaginationMeta' in schemas
    assert 'ResolveResponse' in schemas



def test_admin_cache_stats_and_invalidate_routes_use_admin_token_when_configured(monkeypatch):
    monkeypatch.setattr(app.state.settings, 'admin_token', 'secret-admin', raising=False)
    monkeypatch.setattr(app.state.settings, 'api_token', None, raising=False)

    class DummyCache:
        def stats(self):
            return {
                'db_path': '/tmp/cache.sqlite3',
                'totals': {'entries': 2, 'fresh': 1, 'stale_usable': 1, 'expired': 0},
                'by_namespace': {
                    'series': {'entries': 1, 'fresh': 1, 'stale_usable': 0, 'expired': 0},
                    'planning': {'entries': 1, 'fresh': 0, 'stale_usable': 1, 'expired': 0},
                },
                'negative_cache': {
                    'totals': {'entries': 1, 'fresh': 1, 'expired': 0},
                    'by_namespace': {'series': {'entries': 1, 'fresh': 1, 'expired': 0}},
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
        unauthorized = client.get('/v1/admin/cache/stats')
        assert unauthorized.status_code == 401
        assert unauthorized.json()['code'] == 'AUTH_REQUIRED'
        stats = client.get('/v1/admin/cache/stats', headers={'Authorization': 'Bearer secret-admin'})
        assert stats.status_code == 200
        assert stats.json()['data']['totals']['entries'] == 2
        invalidate = client.post('/v1/admin/cache/invalidate', json={'namespace': 'planning', 'expired_only': True}, headers={'Authorization': 'Bearer secret-admin'})
    monkeypatch.setattr(app.state.settings, 'admin_token', None, raising=False)
    assert invalidate.status_code == 200
    payload = invalidate.json()
    assert payload['deleted'] == 1
    assert payload['stats']['by_namespace']['planning']['stale_usable'] == 1


def test_admin_metrics_route_uses_admin_token(monkeypatch):
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.settings, 'admin_token', 'secret-admin', raising=False)
        monkeypatch.setattr(app.state.settings, 'api_token', None, raising=False)
        app.state.metrics.increment('cache_hits', 2)
        app.state.metrics.increment('cache_misses', 1)
        app.state.metrics.increment('parse_errors', 1)
        unauthorized = client.get('/v1/admin/metrics')
        assert unauthorized.status_code == 401
        metrics = client.get('/v1/admin/metrics', headers={'Authorization': 'Bearer secret-admin'})

    monkeypatch.setattr(app.state.settings, 'admin_token', None, raising=False)
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload['ok'] is True
    assert payload['data']['counters']['cache_hits'] >= 2
    assert payload['data']['counters']['parse_errors'] >= 1
    assert payload['data']['ratios']['cache_hit_ratio'] >= 0.5



def test_lookup_volume_route_returns_resolved_volume_with_normalized_fields():
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
                'pagination': {'page': 1, 'limit': 10, 'returned': 1, 'total': 3, 'has_more': True},
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
                    },
                    'volume': {
                        'title': 'One Piece Vol.91',
                        'series_title': 'One Piece',
                        'number': '91',
                        'number_int': 91,
                        'edition_label': 'edition_originale',
                        'is_special': False,
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
    assert payload['data']['volume']['number'] == '91'
    assert payload['data']['volume']['number_int'] == 91
    assert response.headers['ETag'] == '"fp-lookup"'



def test_rate_limit_returns_429_with_headers(monkeypatch):
    monkeypatch.setattr(app.state.settings, 'rate_limit_enabled', True, raising=False)
    monkeypatch.setattr(app.state.settings, 'rate_limit_requests', 1, raising=False)
    monkeypatch.setattr(app.state.settings, 'rate_limit_window_seconds', 60, raising=False)
    monkeypatch.setattr(app.state.settings, 'rate_limit_scope', 'ip', raising=False)
    monkeypatch.setattr(app.state.settings, 'rate_limit_exempt_paths', '', raising=False)
    app.state.rate_limiter.limit = 1
    app.state.rate_limiter.window_seconds = 60
    app.state.rate_limiter._events.clear()

    with TestClient(app) as client:
        first = client.get('/v1/health')
        second = client.get('/v1/health')

    monkeypatch.setattr(app.state.settings, 'rate_limit_enabled', False, raising=False)
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()['code'] == 'RATE_LIMITED'
    assert second.headers['Retry-After']
    assert second.headers['X-RateLimit-Limit'] == '1'



def test_openapi_exposes_lookup_route_and_examples():
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    assert response.status_code == 200
    payload = response.json()
    lookup_get = payload['paths']['/v1/lookup/volume']['get']
    assert lookup_get['responses']['200']['content']['application/json']['example']['data']['requested_number'] == '91'
    search_get = payload['paths']['/v1/search']['get']
    q_param = next(param for param in search_get['parameters'] if param['name'] == 'q')
    assert q_param['examples']['one_piece_volume']['value'] == 'one piece tome 91'
    volume_schema = payload['components']['schemas']['VolumeData']
    assert 'number' in volume_schema['properties']
    assert 'number_int' in volume_schema['properties']
    assert 'edition_label' in volume_schema['properties']
