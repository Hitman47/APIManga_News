from app.utils import infer_media_kind, normalize_text, parse_french_date, project_dict_fields, score_match, search_result_sort_key


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


def test_infer_media_kind_distinguishes_books_from_manga():
    assert infer_media_kind(title='Naruto (1999) Masashi KISHIMOTO', kind='series', source_type='Shonen') == 'manga'
    assert infer_media_kind(title='Naruto - Roman (2008) Masashi KISHIMOTO', kind='series', source_type='Roman') == 'novel'
    assert infer_media_kind(title='Philosophie de Naruto (la) (2021)', kind='series', source_type='Essai') == 'essay'
    assert infer_media_kind(title='Recettes cachées de Naruto Shippuden (les) (2022)', kind='series') == 'cookbook'


def test_search_result_sort_key_prioritizes_main_manga_over_books():
    query = 'naruto'
    results = [
        {
            'title': 'Naruto - Roman (2008) Masashi KISHIMOTO',
            'slug': 'Naruto-Roman',
            'kind': 'series',
            'score': 100,
            'source_type': 'Roman',
            'media_kind': 'novel',
            'is_special': True,
        },
        {
            'title': 'Naruto (1999) Masashi KISHIMOTO',
            'slug': 'Naruto',
            'kind': 'series',
            'score': 100,
            'source_type': 'Shonen',
            'media_kind': 'manga',
            'is_special': False,
        },
        {
            'title': 'Philosophie de Naruto (la) (2021)',
            'slug': 'Philosophie-de-Naruto-la',
            'kind': 'series',
            'score': 100,
            'source_type': 'Essai',
            'media_kind': 'essay',
            'is_special': False,
        },
    ]

    ranked = sorted(results, key=lambda item: search_result_sort_key(query, item))

    assert ranked[0]['slug'] == 'Naruto'
    assert ranked[1]['slug'] == 'Naruto-Roman'
    assert ranked[2]['slug'] == 'Philosophie-de-Naruto-la'
