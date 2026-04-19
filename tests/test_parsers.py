from app.manga_news.parsers import parse_news_page, parse_planning_page, parse_series_page, parse_volume_page


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


def test_parse_series_page():
    parsed = parse_series_page(SERIES_HTML, 'https://www.manga-news.com/index.php/serie/One-piece-Edition-originale')
    assert parsed.title == 'One Piece'
    assert parsed.title_vo == 'ワンピース'
    assert parsed.publisher_fr == 'Glénat'
    assert parsed.vf and parsed.vf.volumes == 112
    assert parsed.last_release_date == '2026-04-08'
    assert parsed.cover_image.endswith('one-piece.jpg')



def test_parse_volume_page():
    parsed = parse_volume_page(VOLUME_HTML, 'https://www.manga-news.com/index.php/manga/One-Piece/vol-110')
    assert parsed.title == 'One Piece Vol.110'
    assert parsed.publication_date == '2025-09-27'
    assert parsed.isbn_ean == '9782344064092'
    assert parsed.editorial_score == 16.0



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
