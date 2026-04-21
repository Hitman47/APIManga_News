from app.utils import normalize_text, parse_french_date, project_dict_fields, score_match


def test_normalize_text_handles_accents_and_noise():
    assert normalize_text('One Piece - Édition originale') == 'one piece'
    assert normalize_text('Le One Piece Collector Vol. 12') == 'one piece'



def test_parse_french_date():
    assert parse_french_date('Jeudi, 27 Septembre 2025') == '2025-09-27'
    assert parse_french_date('08/04/2026') == '2026-04-08'



def test_score_match():
    assert score_match('One Piece', 'One Piece') >= 95
    assert score_match('One Piece', 'Naruto') < 50
    assert score_match('One Piece', 'One Piece Collector Vol. 12') >= 90



def test_project_dict_fields_with_nested_paths():
    data = {
        'title': 'One Piece',
        'vf': {'volumes': 112, 'status': 'En cours'},
        'stats': {'likes': 531},
    }
    projected = project_dict_fields(data, ['title', 'vf.volumes'])
    assert projected == {'title': 'One Piece', 'vf': {'volumes': 112}}



def test_score_match_handles_punctuation_variants():
    assert normalize_text('Dogs: Bullets & Carnage') == 'dogs bullets and carnage'
    assert normalize_text('Dogs - Bullets & Carnage') == 'dogs bullets and carnage'
    assert score_match('Dogs - Bullets & Carnage', 'Dogs: Bullets & Carnage') >= 95
