from pathlib import Path

from app.manga_news.parsers import (
    parse_news_page,
    parse_planning_page,
    parse_search_page,
    parse_series_editions_page,
    parse_series_page,
    parse_series_search_meta_page,
    parse_volume_page,
    parse_volume_search_meta_page,
)


FIXTURES_DIR = Path(__file__).parent / 'fixtures'


SERIES_HTML = '''
<html>
  <head>
    <meta property="og:title" content="One Piece - Manga série - Manga news" />
    <meta property="og:image" content="https://www.manga-news.com/public/images/series/one-piece.jpg" />
  </head>
  <body>
    <h1>One Piece</h1>
    <ul>
      <li>Titre VO : ワンピース</li>
      <li>Titre traduit : One Piece</li>
      <li>Dessin : Eiichirô ODA</li>
      <li>Scénario : Eiichirô ODA</li>
      <li>Traducteur: Djamel RABAHI , Julien FAVEREAU</li>
      <li>Editeur VF : Glénat</li>
      <li>Collection: Shonen</li>
      <li>Type: Shonen</li>
      <li>Genre: Aventure, Fantastique</li>
      <li>Editeur VO: Shûeisha</li>
      <li>Prépublication: Shônen Jump</li>
      <li>Illustration: n&b + couleurs</li>
      <li>Origine: Japon - 1997</li>
    </ul>
    <div>Age conseillé</div>
    <div>8+</div>
    <div>Résumé</div>
    <p>Résumé principal de la série.</p>
    <div>Thèmes</div>
    <p>Série manga incontournable</p>
    <p>aventure fantastique pirates</p>
    <div>Les points forts de la série</div>
    <p>Un énorme succès populaire.</p>
    <div>Manga en relation</div>
    <a href="/index.php/serie/Monster-perfect-edition">Monster Perfect Edition</a>
    <div>Univers</div>
    <a href="/index.php/univers/One-piece">Univers One Piece</a>
    <div>Liens</div>
    <a href="https://example.org/wiki/one-piece">Wiki externe</a>
    <div>VF:112 (En cours)</div>
    <div>VO : 114 (En cours)</div>
    <div>Dernier paru</div>
    <div>08/04/2026</div>
    <div>A paraître</div>
    <div>06/05/2026</div>
    <div>J'aime</div><div>531</div>
    <div>Dans ma collection</div><div>7053</div>
    <div>Dans ma liste d'achat</div><div>984</div>
    <div>Achat/vente</div><div>2</div>
    <div>Rédaction</div><div>16.23 /20</div>
    <div>Lecteurs</div><div>16.5/20</div>
  </body>
</html>
'''

VOLUME_HTML = '''
<html>
  <head>
    <meta property="og:title" content="One Piece Vol.110 - Manga - Manga news" />
    <meta property="og:image" content="https://www.manga-news.com/public/images/series/one-piece-110.jpg" />
  </head>
  <body>
    <h1>One Piece Vol.110</h1>
    <ul>
      <li>Titre VO: ワンピース</li>
      <li>Titre traduit: One Piece</li>
      <li>Dessin : Eiichirô ODA</li>
      <li>Scénario : Eiichirô ODA</li>
      <li>Traducteur: Djamel RABAHI , Julien FAVEREAU</li>
      <li>Editeur VF: Glénat</li>
      <li>Collection: Shonen</li>
      <li>Type: Shonen</li>
      <li>Genre: Aventure, Fantastique</li>
      <li>Editeur VO: Shûeisha</li>
      <li>Prépublication: Shônen Jump</li>
      <li>Date de publication: 27 Septembre 2025</li>
      <li>Illustration: 208 pages n&b + couleurs</li>
      <li>Origine: Japon - 1997</li>
      <li>Code EAN : 9782344064092</li>
      <li>Code prix: 7.20</li>
    </ul>
    <div>Age conseillé</div>
    <div>8+</div>
    <div>Résumé</div>
    <p>Résumé du volume.</p>
    <div>Liens</div>
    <a href="https://example.org/buy/one-piece-110">Acheter</a>
    <div>Rédaction</div><div>16 /20</div>
    <div>Lecteurs</div><div>15.5/20</div>
  </body>
</html>
'''

NEWS_HTML = '''
<html>
  <body>
    <h1>One Piece : News</h1>
    <div>Manga</div>
    <h2><a href="/index.php/actus/2026/03/10/La-saison-2-de-la-serie-live-One-Piece-disponible-sur-Netflix">La saison 2 de la série live One Piece disponible sur Netflix !</a></h2>
    <p>Mardi, 10 Mars 2026 C'est aujourd'hui ! Les fans peuvent désormais se rassasier avec les épisodes de la saison 2...</p>
    <p>Aucun commentaire... Soyez le 1er !!</p>
    <div>Produits dérivés</div>
    <h2><a href="/index.php/actus/2026/03/03/Celio-x-One-Piece-Chopper-en-guest-star">Celio x One Piece : Chopper en guest star !</a></h2>
    <p>Mardi, 03 Mars 2026 Celio x One Piece : Chopper star d’une collection printanière ultra cute ! ...</p>
    <p>1 commentaire</p>
    <div>Actus Précédentes</div>
  </body>
</html>
'''

PLANNING_HTML = '''
<html>
  <body>
    <h1>Planning des sorties manga 2026/04</h1>
    <div class="planning-item">
      <a href="/index.php/manga/One-Piece/vol-110">One Piece Vol.110</a>
      <p>One Piece Vol.110 à ne pas manquer ! Sortie le 27/04/2026 Auteur(s): Eiichirô ODA Editeur: Glénat</p>
      <p>Le retour des Mugiwara dans un nouveau volume.</p>
      <a href="/index.php/manga/One-Piece/vol-110">Fiche détaillée</a>
    </div>
    <div class="planning-item">
      <a href="/index.php/manga/Kagurabachi/vol-2">Kagurabachi Vol.2</a>
      <p>Kagurabachi Vol.2 Sortie le 03/04/2026 Auteur(s): Takeru HOKAZONO Editeur: Kana</p>
      <p>Chihiro poursuit sa traque.</p>
      <a href="/index.php/manga/Kagurabachi/vol-2">Fiche détaillée</a>
    </div>
  </body>
</html>
'''

EDITIONS_HTML = '''
<html>
  <body>
    <div class="volume-card">
      <img src="/public/images/covers/one-piece-109.jpg" />
      <a href="/index.php/manga/One-Piece/vol-109">One Piece Vol.109</a>
      <p>Sortie le 12/03/2026</p>
    </div>
    <div class="volume-card">
      <img src="/public/images/covers/one-piece-110.jpg" />
      <a href="/index.php/manga/One-Piece/vol-110">One Piece Vol.110</a>
      <p>Sortie le 27/04/2026</p>
    </div>
  </body>
</html>
'''


def test_parse_series_page():
    parsed = parse_series_page(SERIES_HTML, 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale')
    assert parsed.title == 'One Piece'
    assert parsed.title_vo == 'ワンピース'
    assert parsed.publisher_fr == 'Glénat'
    assert parsed.vf and parsed.vf.volumes == 112
    assert parsed.last_release_date == '2026-04-08'
    assert parsed.cover_image.endswith('one-piece.jpg')
    assert parsed.illustration_details and parsed.illustration_details.has_color_pages is True
    assert parsed.related and parsed.related.series[0].title == 'Monster Perfect Edition'
    assert parsed.raw_sections and parsed.raw_sections['resume'][0] == 'Résumé principal de la série.'


def test_parse_series_page_uses_current_dom_metadata_without_genre_prefix_collision():
    html = (FIXTURES_DIR / 'series_blue_giant_momentum_current.html').read_text(encoding='utf-8')

    parsed = parse_series_page(
        html,
        'https://www.manga-news.com/index.php/serie/Blue-Giant-Momentum',
    )

    assert parsed.title == 'Blue Giant Momentum'
    assert parsed.type == 'Seinen'
    assert parsed.genres == ['Drame', 'Tranche-de-vie']
    assert parsed.authors_art == ['Shinichi ISHIZUKA']
    assert parsed.authors_story == ['NUMBER 8']
    assert parsed.publisher_fr == 'Glénat'
    assert parsed.publisher_vo == 'Shôgakukan'
    assert parsed.origin == 'Japon - 2023'


def test_parse_series_search_meta_page_uses_current_dom_type():
    html = (FIXTURES_DIR / 'series_blue_giant_momentum_current.html').read_text(encoding='utf-8')

    parsed = parse_series_search_meta_page(
        html,
        'https://www.manga-news.com/index.php/serie/Blue-Giant-Momentum',
    )

    assert parsed.source_type == 'Seinen'
    assert parsed.media_kind == 'manga'


def test_parse_volume_page_uses_nested_dom_metadata():
    html = '''
    <html><body>
      <nav>Genres Manga</nav>
      <h1>Blue Giant Momentum Vol.1</h1>
      <ul>
        <li class="book-type"><strong>Type</strong>: <a>Seinen</a></li>
        <li class="book-genre">
          <strong>Genre</strong>: <a>Drame</a>, <a>Tranche-de-vie</a>
        </li>
        <li class="book-publication"><strong>Date de publication</strong>: 05 Juin 2024</li>
        <li class="book-isbn"><strong>Code EAN</strong>: 9782344062463</li>
      </ul>
    </body></html>
    '''

    parsed = parse_volume_page(
        html,
        'https://www.manga-news.com/index.php/manga/Blue-Giant-Momentum/vol-1',
    )

    assert parsed.type == 'Seinen'
    assert parsed.genres == ['Drame', 'Tranche-de-vie']
    assert parsed.publication_date == '2024-06-05'
    assert parsed.isbn_ean == '9782344062463'


def test_legacy_line_metadata_requires_a_label_boundary():
    html = '''
    <html><body>
      <nav>Genres Manga</nav>
      <h1>Legacy</h1>
      <ul><li>Type: Shonen</li><li>Genre: Aventure, Fantastique</li></ul>
    </body></html>
    '''

    parsed = parse_series_page(html, 'https://www.manga-news.com/index.php/serie/Legacy')

    assert parsed.type == 'Shonen'
    assert parsed.genres == ['Aventure', 'Fantastique']



def test_parse_volume_page():
    parsed = parse_volume_page(VOLUME_HTML, 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110')
    assert parsed.title == 'One Piece Vol.110'
    assert parsed.number == '110'
    assert parsed.publication_date == '2025-09-27'
    assert parsed.isbn_ean == '9782344064092'
    assert parsed.editorial_score == 16.0
    assert parsed.illustration_details and parsed.illustration_details.pages == 208



def test_parse_volume_search_meta_page():
    parsed = parse_volume_search_meta_page(VOLUME_HTML, 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110')
    assert parsed.title == 'One Piece Vol.110'
    assert parsed.number == '110'
    assert parsed.number_int == 110
    assert parsed.edition_label == 'edition_originale'
    assert parsed.is_special is False
    assert parsed.is_one_shot is False
    assert parsed.title_vo == 'ワンピース'
    assert parsed.translated_title == 'One Piece'


def test_parse_series_search_meta_page_extracts_type_related_and_media_kind():
    html = '''
    <html>
      <body>
        <h1>Boruto - Naruto Next Generations</h1>
        <ul>
          <li>Type: Shonen</li>
        </ul>
        <div>Manga en relation</div>
        <a href="/index.php/serie/Naruto">Naruto</a>
      </body>
    </html>
    '''

    parsed = parse_series_search_meta_page(html, 'https://www.manga-news.com/index.php/serie/Boruto-Naruto-Next-Generations')

    assert parsed.source_type == 'Shonen'
    assert parsed.media_kind == 'manga_spinoff'
    assert parsed.related and parsed.related.series[0].title == 'Naruto'


def test_related_links_ignore_ambiguous_navigation_without_scanning_document_context(monkeypatch):
    import app.manga_news.parsers as parsers

    monkeypatch.setattr(
        parsers,
        '_anchor_context_heading',
        lambda anchor: (_ for _ in ()).throw(AssertionError('slow context scan should not run')),
    )
    html = '''
    <html><body>
      <h1>Test</h1>
      <div>Dossiers</div>
      <a href="/index.php/planning/">Planning</a>
      <a href="/index.php/report/One-Piece">Dossier One Piece</a>
      <a href="/index.php/serie/One-piece-Edition-originale">One Piece</a>
      <a href="/index.php/manga/One-Piece/vol-91">One Piece Vol.91</a>
    </body></html>
    '''

    parsed = parse_series_page(
        html,
        'https://www.manga-news.com/index.php/serie/Test',
    )

    assert [item.title for item in parsed.related.dossiers] == ['Dossier One Piece']
    assert [item.title for item in parsed.related.series] == ['One Piece']
    assert [item.title for item in parsed.related.volumes] == ['One Piece Vol.91']


def test_raw_sections_normalize_each_line_only_once(monkeypatch):
    import app.manga_news.parsers as parsers

    calls = 0
    original_normalize_text = parsers.normalize_text

    def counting_normalize_text(value):
        nonlocal calls
        calls += 1
        return original_normalize_text(value)

    monkeypatch.setattr(parsers, 'normalize_text', counting_normalize_text)
    lines = parsers._TextLines(['Résumé', *[f'Ligne {index}' for index in range(1000)], 'Liens', 'Fin'])

    sections = parsers._extract_raw_sections(lines)

    assert sections['resume'][0] == 'Ligne 0'
    assert calls <= len(lines) + 2


def test_parse_search_page_prioritizes_main_manga_before_books():
    html = '''
    <html>
      <body>
        <a href="/index.php/serie/Philosophie-de-Naruto-la">Philosophie de Naruto (la) (2021)</a>
        <a href="/index.php/serie/Naruto-Roman">Naruto - Roman (2008) Masashi KISHIMOTO</a>
        <a href="/index.php/serie/Naruto">Naruto (1999) Masashi KISHIMOTO</a>
      </body>
    </html>
    '''

    parsed = parse_search_page(
        html,
        'https://www.manga-news.com/index.php/recherche/?cat=manga-serie-vf&q=naruto',
        'https://www.manga-news.com',
        query='naruto',
        kind='series',
        score_threshold=1,
        limit=10,
    )

    assert [item.slug for item in parsed[:3]] == ['Naruto', 'Naruto-Roman', 'Philosophie-de-Naruto-la']



def test_parse_news_page():
    parsed = parse_news_page(
        NEWS_HTML,
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
        PLANNING_HTML,
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



def test_parse_series_editions_page():
    parsed = parse_series_editions_page(
        EDITIONS_HTML,
        'https://www.manga-news.com/index.php/serie/editions/One-piece-Edition-originale',
        'https://www.manga-news.com',
        'vf',
    )
    assert parsed.edition == 'vf'
    assert parsed.total == 2
    assert parsed.items[0].number == '109'
    assert parsed.items[1].publication_date == '2026-04-27'
    assert parsed.items[1].cover_image.endswith('one-piece-110.jpg')


def test_parse_series_editions_page_handles_image_only_volume_links():
    html = '''
    <html>
      <body>
        <div class="volume-card">
          <a href="/index.php/manga/One-piece-Edition-originale/vol-1">
            <img src="/public/images/covers/one-piece-1.jpg" alt="" />
          </a>
        </div>
        <div class="volume-card">
          <a href="/index.php/manga/One-piece-Edition-originale/vol-2">
            <img src="/public/images/covers/one-piece-2.jpg" alt="One Piece Vol.2" />
          </a>
          <span>Vol.2</span>
        </div>
      </body>
    </html>
    '''

    parsed = parse_series_editions_page(
        html,
        'https://www.manga-news.com/index.php/serie/editions/One-piece-Edition-originale',
        'https://www.manga-news.com',
        'vf',
    )

    assert parsed.total == 2
    assert parsed.items[0].title == 'Vol.1'
    assert parsed.items[0].number_int == 1
    assert parsed.items[0].series_slug == 'One-piece-Edition-originale'
    assert parsed.items[1].title == 'One Piece Vol.2'
    assert parsed.items[1].number_int == 2


def test_parse_series_page_numberblock_markup():
    html = '''
    <html>
      <body>
        <h1>One Piece</h1>
        <div id="numberblock">
          <div><div><span class="version">VF:</span><span>112</span><span class="small">(En cours)</span></div></div>
          <div><a href="https://www.manga-news.com/index.php/serie-vo/One-Piece-vo" title="One Piece vo"><span class="version">VO</span>: 114 <span class="small">(En cours)</span></a></div>
        </div>
      </body>
    </html>
    '''
    parsed = parse_series_page(html, 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale')
    assert parsed.vf and parsed.vf.volumes == 112
    assert parsed.vf.status == 'En cours'
    assert parsed.vo and parsed.vo.volumes == 114
    assert parsed.vo.status == 'En cours'


def test_parse_series_page_extracts_explicit_atom_release_cards():
    html = (FIXTURES_DIR / 'series_atom_release_cards.html').read_text(encoding='utf-8')

    parsed = parse_series_page(
        html,
        'https://www.manga-news.com/index.php/serie/Atom-The-Beginning',
    )

    assert parsed.vf and parsed.vf.volumes == 20
    assert parsed.last_release_date == '2025-10-17'
    assert parsed.next_release_date == '2026-10-02'
    assert parsed.last_release_volume is not None
    assert parsed.last_release_volume.number == '21'
    assert parsed.last_release_volume.number_int == 21
    assert parsed.last_release_volume.publication_date == '2025-10-17'
    assert parsed.last_release_volume.volume_slug == 'vol-21'
    assert parsed.next_release_volume is not None
    assert parsed.next_release_volume.number == '22'
    assert parsed.next_release_volume.number_int == 22
    assert parsed.next_release_volume.publication_date == '2026-10-02'
    assert parsed.next_release_volume.volume_slug == 'vol-22'
    assert parsed.next_release_volume.source_url.endswith('/Atom-The-Beginning/vol-22')
