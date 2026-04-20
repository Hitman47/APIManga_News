from app.models import (
    IllustrationDetails,
    NewsResponse,
    PlanningResponse,
    RelatedLinks,
    ResolveResponse,
    SearchResponse,
    SeriesResponse,
    VolumeResponse,
)


def test_core_response_models_are_importable():
    assert ResolveResponse is not None
    assert SearchResponse is not None
    assert SeriesResponse is not None
    assert VolumeResponse is not None
    assert NewsResponse is not None
    assert PlanningResponse is not None
    assert IllustrationDetails is not None
    assert RelatedLinks is not None
