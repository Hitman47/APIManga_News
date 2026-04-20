from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'ok': True}


def test_search_resolve_endpoint_with_stubbed_service_and_etag():
    class DummyService:
        async def resolve_search(self, **kwargs):
            return {
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/recherche/?cat=manga-serie-vf&q=one%20piece',
                'cached': False,
                'fetched_at': '2026-04-20T12:00:00+00:00',
                'cache_expires_at': '2026-04-20T18:00:00+00:00',
                'partial': False,
                'warnings': [],
                'schema_version': '1.0',
                'fingerprint': 'abc123',
                'data': {
                    'query': 'one piece',
                    'kind': 'series',
                    'confidence': 'high',
                    'result': {
                        'title': 'One Piece',
                        'url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                        'kind': 'series',
                        'score': 98,
                        'slug': 'One-piece-Edition-originale',
                        'series_slug': 'One-piece-Edition-originale',
                        'volume_slug': None,
                    },
                    'candidates': [],
                },
            }

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/search/resolve?q=one%20piece')
        not_modified = client.get('/search/resolve?q=one%20piece', headers={'If-None-Match': '"abc123"'})

    assert response.status_code == 200
    assert response.headers['etag'] == '"abc123"'
    assert response.headers['x-data-fingerprint'] == 'abc123'
    assert response.json()['data']['confidence'] == 'high'
    assert not_modified.status_code == 304


def test_planning_endpoint_with_stubbed_service():
    class DummyService:
        async def get_planning(self, **kwargs):
            return {
                'ok': True,
                'found': True,
                'source': 'manga_news',
                'source_url': 'https://www.manga-news.com/index.php/planning/',
                'cached': False,
                'fetched_at': '2026-04-20T12:00:00+00:00',
                'cache_expires_at': '2026-04-20T18:00:00+00:00',
                'partial': False,
                'warnings': [],
                'schema_version': '1.0',
                'fingerprint': 'plan123',
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
            }

    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/planning?section=manga-vf&year=2026&month=4&publisher=Gl%C3%A9nat')
        openapi = client.get('/openapi.json')
    assert response.status_code == 200
    payload = response.json()
    assert payload['ok'] is True
    assert payload['schema_version'] == '1.0'
    assert payload['data']['section'] == 'manga-vf'
    assert payload['data']['items'][0]['publisher'] == 'Glénat'
    assert openapi.status_code == 200
    assert 'ResolveResponse' in openapi.text
