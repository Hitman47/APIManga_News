import json
from pathlib import Path

from app.manga_news.parsers import parse_series_page, parse_volume_page

BASE = Path(__file__).parent


def test_series_fixture_matches_golden_output():
    html = (BASE / 'fixtures' / 'series_one_shot.html').read_text(encoding='utf-8')
    expected = json.loads((BASE / 'golden' / 'series_one_shot.json').read_text(encoding='utf-8'))
    parsed = parse_series_page(html, 'https://www.manga-news.com/index.php/serie/Look-Back').model_dump()
    for key, value in expected.items():
        assert parsed[key] == value


def test_volume_fixture_matches_golden_output():
    html = (BASE / 'fixtures' / 'volume_minimal.html').read_text(encoding='utf-8')
    expected = json.loads((BASE / 'golden' / 'volume_minimal.json').read_text(encoding='utf-8'))
    parsed = parse_volume_page(html, 'https://www.manga-news.com/index.php/manga/Goodbye-Eri/oneshot').model_dump()
    for key, value in expected.items():
        assert parsed[key] == value
