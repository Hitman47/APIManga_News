from app.models import NewsResponse, PlanningResponse, ResolveResponse, SearchResponse, SeriesResponse, VolumeResponse


def test_response_models_are_importable():
    assert NewsResponse.model_fields["data"] is not None
    assert PlanningResponse.model_fields["data"] is not None
    assert ResolveResponse.model_fields["data"] is not None
    assert SearchResponse.model_fields["data"] is not None
    assert SeriesResponse.model_fields["data"] is not None
    assert VolumeResponse.model_fields["data"] is not None
