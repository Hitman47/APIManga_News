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
            'data': {'title': 'One Piece', 'vf.volumes': 112} if kwargs.get('output_format') == 'flat' else {'title': 'One Piece', 'vf': {'volumes': 112}},
        }

    async def select_series_blocks(self, **kwargs):
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
            'data': {'title': 'One Piece', 'vf.volumes': 112, 'next_release_date': '2026-05-06'},
        }

    async def get_series_timeline(self, **kwargs):
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
                'schema_version': 'series-timeline/v1',
                'slug': 'One-piece-Edition-originale',
                'title': 'One Piece',
                'last_release_date': '2026-04-08',
                'next_release_date': '2026-05-06',
                'has_upcoming_release': True,
                'events': [
                    {'date': '2026-05-06', 'kind': 'next_release', 'title': 'Prochaine sortie', 'url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale', 'category': None},
                    {'date': '2026-04-15', 'kind': 'news', 'title': 'Nouvelle annonce', 'url': 'https://www.manga-news.com/index.php/actus/x', 'category': 'Manga'},
                ],
                'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            },
        }

    async def watch_series(self, **kwargs):
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
                'schema_version': 'watch/v1',
                'kind': 'series',
                'identifier': 'One-piece-Edition-originale',
                'fingerprint': 'newhash',
                'previous_fingerprint': kwargs.get('previous_fingerprint'),
                'changed': True,
                'watched_fields': ['vf.volumes', 'next_release_date'],
                'watched_data': {'vf.volumes': 112, 'next_release_date': '2026-05-06'},
                'checked_at': '2026-04-20T12:00:00+00:00',
                'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            },
        }

    async def get_series_field_value(self, **kwargs):
        value = 112 if kwargs.get('field') == 'vf.volumes' else '2026-05-06'
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
                'schema_version': 'field-value/v1',
                'kind': 'series',
                'identifier': 'One-piece-Edition-originale',
                'field': kwargs['field'],
                'value': value,
                'source_url': 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
            },
        }

    async def select_volume_fields(self, **kwargs):
        return {
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
            'cached': True,
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': '2026-04-21T12:00:00+00:00',
            'partial': False,
            'warnings': [],
            'data': {'publication_date': '2025-09-27', 'isbn_ean': '9782344064092'},
        }

    async def select_volume_blocks(self, **kwargs):
        return {
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
            'cached': True,
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': '2026-04-21T12:00:00+00:00',
            'partial': False,
            'warnings': [],
            'data': {'publication_date': '2025-09-27', 'isbn_ean': '9782344064092'},
        }

    async def watch_volume(self, **kwargs):
        return {
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
            'cached': True,
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': '2026-04-21T12:00:00+00:00',
            'partial': False,
            'warnings': [],
            'data': {
                'schema_version': 'watch/v1',
                'kind': 'volume',
                'identifier': 'One-Piece/vol-110',
                'fingerprint': 'volhash',
                'previous_fingerprint': kwargs.get('previous_fingerprint'),
                'changed': False,
                'watched_fields': ['publication_date'],
                'watched_data': {'publication_date': '2025-09-27'},
                'checked_at': '2026-04-20T12:00:00+00:00',
                'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
            },
        }

    async def get_volume_field_value(self, **kwargs):
        value = '2025-09-27' if kwargs.get('field') == 'publication_date' else '9782344064092'
        return {
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
            'cached': True,
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': '2026-04-21T12:00:00+00:00',
            'partial': False,
            'warnings': [],
            'data': {
                'schema_version': 'field-value/v1',
                'kind': 'volume',
                'identifier': 'One-Piece/vol-110',
                'field': kwargs['field'],
                'value': value,
                'source_url': 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
            },
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
        response_select = client.get('/series/One-piece-Edition-originale/select?fields=title,vf.volumes&format=flat')
    assert response_summary.status_code == 200
    assert response_summary.json()['data']['schema_version'] == 'series-summary/v1'
    assert response_select.status_code == 200
    assert response_select.json()['data']['vf.volumes'] == 112



def test_blocks_timeline_watch_and_value_endpoints():
    with TestClient(app) as client:
        app.state.service = DummyService()
        response_blocks = client.get('/series/One-piece-Edition-originale/blocks?blocks=identity,release&format=flat')
        response_timeline = client.get('/series/One-piece-Edition-originale/timeline?news_limit=2')
        response_watch = client.get('/series/One-piece-Edition-originale/watch?previous_fingerprint=oldhash&fields=vf.volumes,next_release_date&format=flat')
        response_value = client.get('/series/One-piece-Edition-originale/vf-volumes')
    assert response_blocks.status_code == 200
    assert response_blocks.json()['data']['vf.volumes'] == 112
    assert response_timeline.status_code == 200
    assert response_timeline.json()['data']['events'][0]['kind'] == 'next_release'
    assert response_watch.status_code == 200
    assert response_watch.json()['data']['changed'] is True
    assert response_value.status_code == 200
    assert response_value.json()['data']['value'] == 112



def test_volume_watch_and_value_endpoints():
    with TestClient(app) as client:
        app.state.service = DummyService()
        response_blocks = client.get('/volume/One-Piece/vol-110/blocks?blocks=publication,scores&format=flat')
        response_watch = client.get('/volume/One-Piece/vol-110/watch?previous_fingerprint=volhash&fields=publication_date')
        response_value = client.get('/volume/One-Piece/vol-110/isbn-ean')
    assert response_blocks.status_code == 200
    assert response_blocks.json()['data']['publication_date'] == '2025-09-27'
    assert response_watch.status_code == 200
    assert response_watch.json()['data']['kind'] == 'volume'
    assert response_value.status_code == 200
    assert response_value.json()['data']['value'] == '9782344064092'



def test_compare_series_endpoint_with_stubbed_service():
    with TestClient(app) as client:
        app.state.service = DummyService()
        response = client.get('/compare/series?left_slug=One-piece-Edition-originale&right_slug=One-piece')
    assert response.status_code == 200
    payload = response.json()['data']
    assert payload['kind'] == 'series'
    assert payload['differing_fields'][0]['field'] == 'vf.volumes'



def test_openapi_contains_new_routes():
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    assert response.status_code == 200
    openapi = response.json()
    assert '/series/{slug}/summary' in openapi['paths']
    assert '/series/{slug}/select' in openapi['paths']
    assert '/series/{slug}/blocks' in openapi['paths']
    assert '/series/{slug}/timeline' in openapi['paths']
    assert '/series/{slug}/watch' in openapi['paths']
    assert '/series/{slug}/vf-volumes' in openapi['paths']
    assert '/volume/{series_slug}/{volume_slug}/watch' in openapi['paths']
    assert '/compare/series' in openapi['paths']
