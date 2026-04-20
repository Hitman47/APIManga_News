from fastapi.testclient import TestClient

from app.exceptions import ParseError
from app.main import app


class DummyPlanningService:
    async def get_planning(self, **kwargs):
        return {
            'schema_version': '1.1',
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': 'https://www.manga-news.com/index.php/planning/',
            'cached': False,
            'cache_state': 'refreshed',
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': '2026-04-20T18:00:00+00:00',
            'partial': False,
            'parse_status': 'complete',
            'missing_fields': [],
            'fingerprint': 'abc',
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

    async def get_planning_watch(self, **kwargs):
        return {
            'schema_version': '1.1',
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': 'https://www.manga-news.com/index.php/planning/',
            'cached': True,
            'cache_state': 'fresh_hit',
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': '2026-04-20T18:00:00+00:00',
            'partial': False,
            'parse_status': 'complete',
            'missing_fields': [],
            'fingerprint': 'watch-fp',
            'warnings': [],
            'data': {
                'section': 'manga-vf',
                'year': 2026,
                'month': 4,
                'watch_id': 'kana-watch',
                'has_previous_snapshot': True,
                'scope_changed': False,
                'changed': True,
                'previous_fingerprint': 'old-fp',
                'current_fingerprint': 'new-fp',
                'total_items': 2,
                'added_count': 1,
                'removed_count': 0,
                'added_items': [
                    {
                        'title': 'Kagurabachi Vol.2',
                        'url': 'https://www.manga-news.com/index.php/manga/Kagurabachi/vol-2',
                        'release_date': '2026-04-03',
                        'authors': ['Takeru HOKAZONO'],
                        'publisher': 'Kana',
                        'summary': 'Chihiro poursuit sa traque.',
                        'featured': False,
                        'series_slug': 'Kagurabachi',
                        'volume_slug': 'vol-2'
                    }
                ],
                'removed_items': [],
                'current_items_preview': [],
                'filters': {'publisher': 'Kana'}
            },
        }

    def cache_stats(self):
        return {
            'schema_version': '1.1',
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': None,
            'cached': False,
            'cache_state': None,
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': None,
            'partial': False,
            'parse_status': 'complete',
            'missing_fields': [],
            'fingerprint': 'stats-fp',
            'warnings': [],
            'data': {
                'db_path': '/tmp/cache.sqlite3',
                'totals': {'entries': 2, 'fresh': 2, 'stale_usable': 0, 'expired': 0},
                'by_namespace': {'planning': {'entries': 1, 'fresh': 1, 'stale_usable': 0, 'expired': 0}},
                'watch_snapshots': {'entries': 1},
                'oldest_fetched_at': None,
                'newest_fetched_at': None,
            },
        }

    def invalidate_cache(self, **kwargs):
        return {
            'schema_version': '1.1',
            'ok': True,
            'found': True,
            'source': 'manga_news',
            'source_url': None,
            'cached': False,
            'cache_state': None,
            'fetched_at': '2026-04-20T12:00:00+00:00',
            'cache_expires_at': None,
            'partial': False,
            'parse_status': 'complete',
            'missing_fields': [],
            'fingerprint': 'invalidate-fp',
            'warnings': [],
            'data': {'deleted_entries': 1, 'filters': {'namespace': 'planning'}},
        }


class DummyErrorService:
    async def get_planning(self, **kwargs):
        raise ParseError('date_from must be a valid date.')


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'ok': True}
    assert response.headers['X-Request-ID']


def test_planning_endpoint_with_stubbed_service():
    with TestClient(app) as client:
        app.state.service = DummyPlanningService()
        response = client.get('/planning?section=manga-vf&year=2026&month=4&publisher=Gl%C3%A9nat')
    assert response.status_code == 200
    payload = response.json()
    assert payload['ok'] is True
    assert payload['schema_version'] == '1.1'
    assert payload['data']['section'] == 'manga-vf'
    assert payload['data']['items'][0]['publisher'] == 'Glénat'


def test_planning_watch_endpoint_with_stubbed_service():
    with TestClient(app) as client:
        app.state.service = DummyPlanningService()
        response = client.get('/planning/watch?watch_id=kana-watch&publisher=Kana')
    assert response.status_code == 200
    payload = response.json()
    assert payload['data']['changed'] is True
    assert payload['data']['added_count'] == 1
    assert payload['data']['added_items'][0]['publisher'] == 'Kana'


def test_admin_cache_endpoints_with_stubbed_service():
    with TestClient(app) as client:
        app.state.service = DummyPlanningService()
        stats_response = client.get('/admin/cache/stats')
        invalidate_response = client.post('/admin/cache/invalidate?namespace=planning')
    assert stats_response.status_code == 200
    assert stats_response.json()['data']['totals']['entries'] == 2
    assert invalidate_response.status_code == 200
    assert invalidate_response.json()['data']['deleted_entries'] == 1


def test_structured_parse_error_envelope():
    with TestClient(app) as client:
        app.state.service = DummyErrorService()
        response = client.get('/planning?date_from=not-a-date')
    assert response.status_code == 502
    payload = response.json()
    assert payload['ok'] is False
    assert payload['error_code'] == 'parse_error'
