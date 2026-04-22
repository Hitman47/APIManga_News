from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'ok': True}



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
            assert kwargs['enrich'] is False
            assert kwargs['include_editions'] is True
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
                        'title_vo': 'ワンピース',
                        'translated_title': 'One Piece',
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
        not_modified = client.get('/search/resolve?q=one%20piece&kind=series', headers={'If-None-Match': '"fp-resolve"'})
    assert not_modified.status_code == 304



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


def test_search_endpoint_exposes_alternate_titles():
    class DummyService:
        async def search(self, **kwargs):
            assert kwargs['enrich'] is False
            assert kwargs['include_editions'] is True
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
                'fingerprint': 'fp-search',
                'data': [
                    {
                        'title': 'Black Night Parade',
                        'title_vo': 'ブラックナイトパレード',
                        'translated_title': 'Black Night Parade',
                        'url': 'https://www.manga-news.com/index.php/serie/Black-Night-Parade',
                        'kind': 'series',
                        'score': 94,
                        'slug': 'Black-Night-Parade',
                        'series_slug': 'Black-Night-Parade',
                        'volume_slug': None,
                    }
                ],
            }})()

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/search?q=black%20night%20parade&kind=series&mode=all')
    assert response.status_code == 200
    payload = response.json()
    assert payload['data'][0]['title'] == 'Black Night Parade'
    assert payload['data'][0]['title_vo'] == 'ブラックナイトパレード'
    assert payload['data'][0]['translated_title'] == 'Black Night Parade'


def test_openapi_exposes_search_and_volume_edition_counters():
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    assert response.status_code == 200
    payload = response.json()
    schemas = payload['components']['schemas']
    search_result = schemas['SearchResult']['properties']
    volume_data = schemas['VolumeData']['properties']
    assert 'vf' in search_result
    assert 'vo' in search_result
    assert 'vf' in volume_data
    assert 'vo' in volume_data
    assert payload['info']['description']
    assert payload['paths']['/search']['get']['description']
    assert payload['paths']['/search/resolve']['get']['description']
    assert payload['paths']['/series/{slug}']['get']['description']
    assert payload['paths']['/volume/{series_slug}/{volume_slug}']['get']['description']
    assert payload['paths']['/planning']['get']['description']
