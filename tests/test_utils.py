from app.utils import normalize_text, parse_french_date, project_dict_fields, score_match, search_rank_score, search_sort_key


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


def test_search_rank_prefers_exact_series_over_related_books():
    main_score = search_rank_score('naruto', 'Naruto (1999) Masashi KISHIMOTO', 'https://www.manga-news.com/index.php/serie/Naruto')
    philosophy_score = search_rank_score('naruto', 'Philosophie de Naruto (la) (2021)', 'https://www.manga-news.com/index.php/serie/Philosophie-de-Naruto-la')
    recipe_score = search_rank_score('naruto', 'Recettes cachées de Naruto Shippuden (2022)', 'https://www.manga-news.com/index.php/serie/Recettes-cachees-de-Naruto-Shippuden-le')

    assert main_score == 100
    assert main_score > philosophy_score
    assert main_score > recipe_score


def test_search_sort_key_prefers_exact_license_before_derived_series():
    naruto_key = search_sort_key('naruto', 'Naruto (1999) Masashi KISHIMOTO', 'https://www.manga-news.com/index.php/serie/Naruto')
    gaiden_key = search_sort_key('naruto', 'Naruto Gaiden (2015) Masashi KISHIMOTO', 'https://www.manga-news.com/index.php/serie/Naruto-Gaiden-Boruto')
    philosophy_key = search_sort_key('naruto', 'Philosophie de Naruto (la) (2021)', 'https://www.manga-news.com/index.php/serie/Philosophie-de-Naruto-la')

    assert naruto_key > gaiden_key
    assert naruto_key > philosophy_key
