from app.models import NewsResponse, PlanningResponse, ResolveResponse, SearchResponse, SeriesResponse, VolumeResponse


def test_response_models_can_be_imported():
    for cls in (SearchResponse, ResolveResponse, NewsResponse, SeriesResponse, VolumeResponse, PlanningResponse):
        assert cls is not None
