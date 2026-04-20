import json
from pathlib import Path

from app.manga_news.parsers import parse_news_page, parse_planning_page, parse_series_page, parse_volume_page


FIXTURES = Path(__file__).parent / 'fixtures'
GOLDEN = Path(__file__).parent / 'golden'


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


def _load_golden(name: str):
    return json.loads((GOLDEN / name).read_text(encoding='utf-8'))



def test_parse_series_page():
    parsed = parse_series_page(
        _load_fixture('series_one_piece.html'),
        'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
    )
    assert parsed.title == 'One Piece'
    assert parsed.title_vo == 'ワンピース'
    assert parsed.publisher_fr == 'Glénat'
    assert parsed.vf and parsed.vf.volumes == 112
    assert parsed.last_release_date == '2026-04-08'
    assert parsed.cover_image.endswith('one-piece.jpg')



def test_parse_volume_page():
    parsed = parse_volume_page(
        _load_fixture('volume_one_piece_110.html'),
        'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
    )
    assert parsed.title == 'One Piece Vol.110'
    assert parsed.publication_date == '2025-09-27'
    assert parsed.isbn_ean == '9782344064092'
    assert parsed.editorial_score == 16.0



def test_parse_news_page():
    parsed = parse_news_page(
        _load_fixture('news_one_piece.html'),
        'https://www.manga-news.com/index.php/serie/news/One-piece-Edition-originale',
        'https://www.manga-news.com',
        limit=10,
    )
    assert len(parsed) == 2
    assert parsed[0].title.startswith('La saison 2')
    assert parsed[0].published_at == '2026-03-10'
    assert parsed[0].comments == 0
    assert parsed[1].category == 'Produits dérivés'



def test_parse_planning_page():
    parsed = parse_planning_page(
        _load_fixture('planning_april_2026.html'),
        'https://www.manga-news.com/index.php/planning/?p_month=4&p_year=2026',
        'https://www.manga-news.com',
    )
    assert parsed.section == 'manga-vf'
    assert parsed.year == 2026
    assert parsed.month == 4
    assert len(parsed.items) == 2
    assert parsed.items[0].title == 'One Piece Vol.110'
    assert parsed.items[0].release_date == '2026-04-27'
    assert parsed.items[0].publisher == 'Glénat'
    assert parsed.items[0].featured is True
    assert parsed.items[0].series_slug == 'One-Piece'
    assert parsed.items[0].volume_slug == 'vol-110'



def test_golden_series_fixture():
    parsed = parse_series_page(
        _load_fixture('series_one_piece.html'),
        'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale',
    ).model_dump()
    assert parsed == _load_golden('series_one_piece.json')



def test_golden_volume_fixture():
    parsed = parse_volume_page(
        _load_fixture('volume_one_piece_110.html'),
        'https://www.manga-news.com/index.php/manga/One-Piece/vol-110',
    ).model_dump()
    assert parsed == _load_golden('volume_one_piece_110.json')



def test_golden_news_fixture():
    parsed = [
        item.model_dump()
        for item in parse_news_page(
            _load_fixture('news_one_piece.html'),
            'https://www.manga-news.com/index.php/serie/news/One-piece-Edition-originale',
            'https://www.manga-news.com',
            limit=10,
        )
    ]
    assert parsed == _load_golden('news_one_piece.json')



def test_golden_planning_fixture():
    parsed = parse_planning_page(
        _load_fixture('planning_april_2026.html'),
        'https://www.manga-news.com/index.php/planning/?p_month=4&p_year=2026',
        'https://www.manga-news.com',
    ).model_dump()
    assert parsed == _load_golden('planning_april_2026.json')
