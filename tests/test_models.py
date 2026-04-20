from app.models import NewsResponse, PlanningResponse, ResolveResponse, SearchResponse, SeriesResponse, VolumeResponse


def test_response_models_are_importable():
    assert SearchResponse is not None
    assert ResolveResponse is not None
    assert SeriesResponse is not None
    assert VolumeResponse is not None
    assert NewsResponse is not None
    assert PlanningResponse is not None
