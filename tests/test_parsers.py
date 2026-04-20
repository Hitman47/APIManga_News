import json
from pathlib import Path

from app.manga_news.parsers import (
    parse_news_page,
    parse_planning_page,
    parse_series_editions_page,
    parse_series_page,
    parse_volume_page,
)

FIXTURES_DIR = Path(__file__).parent / 'fixtures'
HTML_DIR = FIXTURES_DIR / 'html'
GOLDEN_DIR = FIXTURES_DIR / 'golden'
BASE_URL = 'https://www.manga-news.com'


def _read_html(name: str) -> str:
    return (HTML_DIR / name).read_text()



def _read_json(name: str):
    return json.loads((GOLDEN_DIR / name).read_text())



def test_parse_series_page_matches_golden_fixture():
    parsed = parse_series_page(_read_html('series.html'), f'{BASE_URL}/index.php/serie/One-piece-Edition-originale')
    assert parsed.model_dump() == _read_json('series.json')



def test_parse_volume_page_matches_golden_fixture():
    parsed = parse_volume_page(_read_html('volume.html'), f'{BASE_URL}/index.php/manga/One-Piece/vol-110')
    assert parsed.model_dump() == _read_json('volume.json')



def test_parse_news_page_matches_golden_fixture():
    parsed = parse_news_page(
        _read_html('news.html'),
        f'{BASE_URL}/index.php/serie/news/One-piece-Edition-originale',
        BASE_URL,
        limit=10,
    )
    assert [item.model_dump() for item in parsed] == _read_json('news.json')



def test_parse_planning_page_matches_golden_fixture():
    parsed = parse_planning_page(
        _read_html('planning.html'),
        f'{BASE_URL}/index.php/planning/?p_month=4&p_year=2026',
        BASE_URL,
    )
    assert parsed.model_dump() == _read_json('planning.json')



def test_parse_series_editions_page_matches_golden_fixture():
    parsed = parse_series_editions_page(
        _read_html('editions.html'),
        f'{BASE_URL}/index.php/serie/editions/One-piece-Edition-originale',
        BASE_URL,
        'vf',
    )
    assert parsed.model_dump() == _read_json('editions.json')
