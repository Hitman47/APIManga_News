from app.manga_news.parsers import parse_series_page, parse_volume_page

SERIES_HTML = """
<html><head><meta property="og:image" content="https://img.example/cover.jpg"></head><body>
<h1>One Piece</h1>
<div>Titre VO : ワンピース</div>
<div>Scénario : Eiichiro Oda</div>
<div>Dessin : Eiichiro Oda</div>
<div>Editeur VF : Glénat</div>
<div>Type : Shonen</div>
<div>Genre : Aventure</div>
<div>Illustration : 192 pages n&b</div>
<div>VF : 108 (En cours)</div>
<div>VO : 109 (En cours)</div>
<div>Résumé</div><div>Une grande aventure pirate.</div>
<div>Thèmes</div><div>Pirates</div>
</body></html>
"""

VOLUME_HTML = """
<html><head><meta property="og:image" content="https://img.example/vol.jpg"></head><body>
<h1>One Piece - Tome 108</h1>
<div>Titre VO : ワンピース 108</div>
<div>Scénario : Eiichiro Oda</div>
<div>Dessin : Eiichiro Oda</div>
<div>Editeur VF : Glénat</div>
<div>Date de publication : 03 juillet 2024</div>
<div>Code EAN : 9782344051540</div>
<div>Illustration : 208 pages n&b</div>
<div>Résumé</div><div>Le combat continue.</div>
</body></html>
"""


def test_series_fixture_parses_core_fields():
    data = parse_series_page(SERIES_HTML, 'https://www.manga-news.com/index.php/serie/One-piece')
    assert data.title == 'One Piece'
    assert data.title_vo == 'ワンピース'
    assert data.publisher_fr == 'Glénat'
    assert data.vf is not None and data.vf.volumes == 108
    assert data.illustration_details is not None and data.illustration_details.pages == 192


def test_volume_fixture_parses_core_fields():
    data = parse_volume_page(VOLUME_HTML, 'https://www.manga-news.com/index.php/manga/One-Piece/vol-108')
    assert data.title == 'One Piece - Tome 108'
    assert data.publisher_fr == 'Glénat'
    assert data.isbn_ean == '9782344051540'
    assert data.illustration_details is not None and data.illustration_details.pages == 208
