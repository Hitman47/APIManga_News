from fastapi.testclient import TestClient

from app.main import app


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

    async def get_series_summary(self, **kwargs):
        return {
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            'cached': True,
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': '2026-04-21T12:00:00+00:00',
            'partial': False,
            'warnings': [],
            'data': {
                'schema_version': 'series-summary/v1',
                'slug': 'One-piece-Edition-originale',
                'title': 'One Piece',
                'title_vo': 'ワンピース',
                'publisher_fr': 'Glénat',
                'vf': {'volumes': 112, 'status': 'En cours'},
                'vo': {'volumes': 114, 'status': 'En cours'},
                'last_release_date': '2026-04-08',
                'next_release_date': '2026-05-06',
                'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            },
        }

    async def select_series_fields(self, **kwargs):
        return {
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            'cached': True,
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': '2026-04-21T12:00:00+00:00',
            'partial': False,
            'warnings': [],
            'data': {'title': 'One Piece', 'vf': {'volumes': 112}},
        }

    async def compare_series(self, **kwargs):
        return {
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            'cached': False,
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': '2026-04-21T12:00:00+00:00',
            'partial': False,
            'warnings': [],
            'data': {
                'schema_version': 'compare/v1',
                'kind': 'series',
                'left_source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                'right_source_url': 'https://www.manga-news.com/index.php/serie/One-piece',
                'compared_fields_count': 3,
                'equal_fields': ['title', 'publisher_fr'],
                'differing_fields': [{'field': 'vf.volumes', 'left': 112, 'right': 110}],
                'similarity_score': 66,
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
    assert payload['ok'] is True
    assert payload['data']['section'] == 'manga-vf'
    assert payload['data']['items'][0]['publisher'] == 'Glénat'



def test_summary_and_select_endpoints_with_stubbed_service():
    with TestClient(app) as client:
        app.state.service = DummyService()
        response_summary = client.get('/series/One-piece-Edition-originale/summary')
        response_select = client.get('/series/One-piece-Edition-originale/select?fields=title,vf.volumes')
    assert response_summary.status_code == 200
    assert response_summary.json()['data']['schema_version'] == 'series-summary/v1'
    assert response_select.status_code == 200
    assert response_select.json()['data']['vf']['volumes'] == 112



def test_compare_series_endpoint_with_stubbed_service():
    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/compare/series?left_slug=One-piece-Edition-originale&right_slug=One-piece')
    assert response.status_code == 200
    payload = response.json()['data']
    assert payload['kind'] == 'series'
    assert payload['differing_fields'][0]['field'] == 'vf.volumes'



def test_openapi_contains_new_summary_and_compare_routes():
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    assert response.status_code == 200
    openapi = response.json()
    assert '/series/{slug}/summary' in openapi['paths']
    assert '/series/{slug}/select' in openapi['paths']
    assert '/compare/series' in openapi['paths']
