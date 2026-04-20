from fastapi.testclient import TestClient

from app.main import app


class DummyService:
    async def get_planning(self, **kwargs):
        return {
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
            'fingerprint': 'planning-fingerprint',
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

    async def get_series(self, **kwargs):
        assert kwargs['slug'] == 'One-piece-Edition-originale'
        assert kwargs['blocks'] == 'editions,stats'
        assert kwargs['fields'] == 'title,vf.volumes'
        assert kwargs['include_raw_sections'] is True
        return {
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
            'fingerprint': 'series-fingerprint',
            'data': {
                'title': 'One Piece',
                'vf': {'volumes': 112},
                'stats': {'likes': 531},
                'raw_sections': {'resume': ['Résumé principal de la série.']},
            },
        }

    async def resolve_search(self, **kwargs):
        return {
            'schema_version': '1.0',
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': 'https://www.manga-news.com/index.php/recherche/?cat=manga-serie-vf&q=one%20piece',
            'cached': True,
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': '2026-04-21T12:00:00+00:00',
            'partial': False,
            'warnings': [],
            'fingerprint': 'resolve-fingerprint',
            'data': {
                'query': kwargs['query'],
                'kind': kwargs['kind'],
                'confidence': 'high',
                'result': {
                    'title': 'One Piece',
                    'url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                    'kind': 'series',
                    'score': 100,
                    'slug': 'One-piece-Edition-originale',
                    'series_slug': None,
                    'volume_slug': None,
                },
                'candidates': [],
            },
        }


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'ok': True}



def test_planning_endpoint_with_stubbed_service():
    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/planning?section=manga-vf&year=2026&month=4&publisher=Gl%C3%A9nat')
    assert response.status_code == 200
    payload = response.json()
    assert payload['schema_version'] == '1.0'
    assert payload['fingerprint'] == 'planning-fingerprint'
    assert response.headers['etag'] == '"planning-fingerprint"'
    assert payload['data']['section'] == 'manga-vf'
    assert payload['data']['items'][0]['publisher'] == 'Glénat'



def test_series_route_forwards_projection_params():
    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/series/One-piece-Edition-originale?blocks=editions,stats&fields=title,vf.volumes&include_raw_sections=true')
    assert response.status_code == 200
    payload = response.json()
    assert payload['data']['vf']['volumes'] == 112
    assert 'raw_sections' in payload['data']
    assert payload['fingerprint'] == 'series-fingerprint'



def test_search_resolve_route_and_http_304():
    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/search/resolve?q=one%20piece&kind=series')
        assert response.status_code == 200
        assert response.json()['data']['confidence'] == 'high'
        etag = response.headers['etag']
        second = client.get('/search/resolve?q=one%20piece&kind=series', headers={'If-None-Match': etag})
    assert second.status_code == 304
    assert second.text == ''



def test_openapi_exposes_resolve_route_and_examples():
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    assert response.status_code == 200
    payload = response.json()
    assert '/search/resolve' in payload['paths']
    schemas = payload['components']['schemas']
    assert 'SearchResolveResponse' in schemas
    assert 'example' in schemas['SearchResolveResponse']
