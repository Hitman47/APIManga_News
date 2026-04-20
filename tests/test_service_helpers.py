from app.manga_news.service import project_resource_payload


SERIES_PAYLOAD = {
    'title': 'One Piece',
    'title_vo': 'ワンピース',
    'vf': {'volumes': 112, 'status': 'En cours'},
    'vo': {'volumes': 114, 'status': 'En cours'},
    'stats': {'likes': 531, 'reader_score': 16.5},
    'raw_sections': {'resume': ['Résumé principal de la série.']},
}



def test_project_resource_payload_fields_only():
    projected = project_resource_payload(SERIES_PAYLOAD, resource='series', fields=['vf.volumes'])
    assert projected == {'vf': {'volumes': 112}}



def test_project_resource_payload_blocks_and_fields_union():
    projected = project_resource_payload(
        SERIES_PAYLOAD,
        resource='series',
        blocks=['stats'],
        fields=['title'],
    )
    assert projected['title'] == 'One Piece'
    assert projected['stats']['likes'] == 531
    assert 'raw_sections' not in projected



def test_project_resource_payload_include_raw_sections():
    projected = project_resource_payload(SERIES_PAYLOAD, resource='series', include_raw_sections=True)
    assert projected['raw_sections']['resume'][0] == 'Résumé principal de la série.'
