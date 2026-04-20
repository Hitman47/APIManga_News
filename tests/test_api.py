from fastapi.testclient import TestClient

from app.main import app
from app.models import PlanningData, PlanningFilters, PlanningResponse, ResolveData, ResolveResponse, SCHEMA_VERSION, SearchResponse, SearchResult


class DummyService:
    async def get_planning(self, **kwargs):
        return PlanningResponse(
            schema_version=SCHEMA_VERSION,
            ok=True,
            found=True,
            source='manga_news',
            source_url='https://www.manga-news.com/index.php/planning/',
            cached=False,
            fetched_at='2026-04-20T12:00:00+00:00',
            cache_expires_at='2026-04-20T18:00:00+00:00',
            partial=False,
            warnings=[],
            data=PlanningData(
                section='manga-vf',
                year=2026,
                month=4,
                page=1,
                filters=PlanningFilters(
                    publisher='Glénat',
                    query=None,
                    date_from=None,
                    date_to=None,
                ),
                sort='date_asc',
                total_items=1,
                items=[
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
            ),
        )

    async def search(self, **kwargs):
        return SearchResponse(
            schema_version=SCHEMA_VERSION,
            ok=True,
            found=True,
            source='manga_news',
            source_url='https://www.manga-news.com/index.php/recherche/?cat=manga-serie-vf&q=one%20piece',
            cached=False,
            fetched_at='2026-04-20T12:00:00+00:00',
            cache_expires_at='2026-04-21T12:00:00+00:00',
            partial=False,
            warnings=[],
            data=[
                SearchResult(
                    title='One Piece',
                    url='https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                    kind='series',
                    score=98,
                    slug='One-piece-Edition-originale',
                    series_slug='One-piece-Edition-originale',
                )
            ],
        )

    async def resolve_search(self, **kwargs):
        return ResolveResponse(
            schema_version=SCHEMA_VERSION,
            ok=True,
            found=True,
            source='manga_news',
            source_url='https://www.manga-news.com/index.php/recherche/?cat=manga-serie-vf&q=one%20piece',
            cached=False,
            fetched_at='2026-04-20T12:00:00+00:00',
            cache_expires_at='2026-04-21T12:00:00+00:00',
            partial=False,
            warnings=[],
            data=ResolveData(
                query='one piece',
                result=SearchResult(
                    title='One Piece',
                    url='https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
                    kind='series',
                    score=98,
                    slug='One-piece-Edition-originale',
                    series_slug='One-piece-Edition-originale',
                ),
                confidence='high',
                alternatives_count=2,
            ),
        )



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
    assert payload['schema_version'] == SCHEMA_VERSION
    assert payload['ok'] is True
    assert payload['data']['section'] == 'manga-vf'
    assert payload['data']['items'][0]['publisher'] == 'Glénat'
    assert response.headers['ETag']
    assert response.headers['X-Data-Fingerprint'] == payload['fingerprint']



def test_search_resolve_endpoint_and_304():
    with TestClient(app) as client:
        app.state.service = DummyService()
        first = client.get('/search/resolve?q=one%20piece&kind=series')
        assert first.status_code == 200
        payload = first.json()
        assert payload['data']['confidence'] == 'high'
        etag = first.headers['ETag']
        second = client.get('/search/resolve?q=one%20piece&kind=series', headers={'If-None-Match': etag})
    assert second.status_code == 304
    assert second.text == ''



def test_openapi_exposes_response_models():
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    assert response.status_code == 200
    spec = response.json()
    schemas = spec['components']['schemas']
    assert 'ResolveResponse' in schemas
    assert 'SeriesResponse' in schemas
    assert '/search/resolve' in spec['paths']
