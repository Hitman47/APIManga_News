from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.exceptions import ParseError
from app.models import NewsItem, SearchResult, SeriesData, SeriesStats, EditionStatus, VolumeData
from app.utils import clean_ws, ensure_absolute_url, normalize_text, parse_french_date, score_match, slugify, unique_list

DATE_LINE_RE = re.compile(
    r'^(Lundi|Mardi|Mercredi|Jeudi|Vendredi|Samedi|Dimanche),?\s+(\d{1,2}\s+[A-Za-zéûîôàèùçÉÛÎÔÀÈÙÇ]+\s+\d{4})(?:\s+(.*))?$'
)
VALUE_LABELS = {
    'title_vo': ['Titre VO', 'Titre VO :'],
    'translated_title': ['Titre traduit', 'Titre traduit :'],
    'story': ['Scénario', 'Scénario :'],
    'art': ['Dessin', 'Dessin :'],
    'translator': ['Traducteur', 'Traducteur :'],
    'publisher_fr': ['Editeur VF', 'Editeur VF :'],
    'publisher_vo': ['Editeur VO', 'Editeur VO :'],
    'collection': ['Collection', 'Collection :'],
    'type': ['Type', 'Type :'],
    'genre': ['Genre', 'Genre :'],
    'prepublication': ['Prépublication', 'Prépublication :'],
    'illustration': ['Illustration', 'Illustration :'],
    'origin': ['Origine', 'Origine :'],
    'publication_date': ['Date de publication', 'Date de publication :'],
    'isbn_ean': ['Code EAN', 'Code EAN :'],
    'price_code': ['Code prix', 'Code prix :'],
}
SECTION_STOP_WORDS = {
    'video youtube', 'thèmes', 'themes', 'les points forts de la série', 'manga en relation', 'dossier',
    'univers', 'signaler', 'liens', 'les volumes', 'personnages', 'les images de', 'donner votre avis',
}
NEWS_STOP_WORDS = {'actus précédentes', 'actus precedentes', 'univers', 'liens', 'signaler', 'chez notre partenaire'}
NEWS_CATEGORY_HINTS = {'manga', 'anime', 'webtoon', 'presse', 'drama', 'japon', 'produits dérivés', 'produits derives'}
GENERIC_ANCHOR_TEXTS = {
    'manga news', 'facebook', 'twitter', 'instagram', 'youtube', 'dailymotion', 'pinterest',
    'voir le produit', 'voir toutes les figurines', 'lire le dossier', 'partie 1', 'partie 2',
    'partie 3', 'mot de la fin', 's inscrire', 'connexion', 'j ai oublié mes identifiants !',
}


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, 'lxml')


def _lines(soup: BeautifulSoup) -> list[str]:
    raw_lines = soup.get_text('\n', strip=True).splitlines()
    return [clean_ws(line) for line in raw_lines if clean_ws(line)]


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
        if tag and tag.get('content'):
            return clean_ws(tag['content'])
    return None


def _extract_line_value(lines: list[str], labels: Iterable[str]) -> str | None:
    for line in lines:
        for label in labels:
            normalized_label = normalize_text(label)
            normalized_line = normalize_text(line)
            if normalized_line.startswith(normalized_label):
                if ':' in line:
                    value = clean_ws(line.split(':', 1)[1])
                else:
                    value = clean_ws(re.sub(re.escape(label), '', line, flags=re.IGNORECASE))
                return value or None
    return None


def _extract_number_after(lines: list[str], label: str) -> int | None:
    for index, line in enumerate(lines):
        if normalize_text(line) == normalize_text(label):
            for offset in range(1, 3):
                if index + offset >= len(lines):
                    break
                match = re.search(r'(\d+)', lines[index + offset])
                if match:
                    return int(match.group(1))
        if normalize_text(label) in normalize_text(line):
            match = re.search(r'(\d+)', line)
            if match:
                return int(match.group(1))
    return None


def _extract_score_after(lines: list[str], label: str) -> float | None:
    for index, line in enumerate(lines):
        if normalize_text(line) == normalize_text(label):
            for offset in range(1, 3):
                if index + offset >= len(lines):
                    break
                match = re.search(r'(\d+(?:[\.,]\d+)?)\s*/\s*20', lines[index + offset])
                if match:
                    return float(match.group(1).replace(',', '.'))
        if normalize_text(label) in normalize_text(line):
            match = re.search(r'(\d+(?:[\.,]\d+)?)\s*/\s*20', line)
            if match:
                return float(match.group(1).replace(',', '.'))
    return None


def _extract_section(lines: list[str], heading: str) -> str | None:
    normalized_heading = normalize_text(heading)
    for index, line in enumerate(lines):
        if normalize_text(line) == normalized_heading:
            collected: list[str] = []
            for candidate in lines[index + 1 :]:
                normalized_candidate = normalize_text(candidate)
                if normalized_candidate in SECTION_STOP_WORDS:
                    break
                if any(normalized_candidate.startswith(normalize_text(prefix)) for prefix_list in VALUE_LABELS.values() for prefix in prefix_list):
                    break
                collected.append(candidate)
            text = clean_ws(' '.join(collected))
            return text or None
    return None


def _extract_vf_vo(lines: list[str]) -> tuple[EditionStatus | None, EditionStatus | None, str | None, str | None]:
    vf_status = None
    vo_status = None
    last_release = None
    next_release = None
    for index, line in enumerate(lines):
        vf_match = re.search(r'VF\s*:?\s*(\d+)\s*\(([^)]+)\)', line, flags=re.IGNORECASE)
        if vf_match:
            vf_status = EditionStatus(volumes=int(vf_match.group(1)), status=clean_ws(vf_match.group(2)))
        vo_match = re.search(r'VO\s*:?\s*(\d+)\s*\(([^)]+)\)', line, flags=re.IGNORECASE)
        if vo_match:
            vo_status = EditionStatus(volumes=int(vo_match.group(1)), status=clean_ws(vo_match.group(2)))
        if normalize_text(line) == 'dernier paru' and index + 1 < len(lines):
            last_release = parse_french_date(lines[index + 1])
        if normalize_text(line) in {'a paraitre', 'a paraître'} and index + 1 < len(lines):
            next_release = parse_french_date(lines[index + 1])
    return vf_status, vo_status, last_release, next_release


def _collect_anchor_texts(tag) -> list[str]:
    if tag is None:
        return []
    return unique_list(a.get_text(' ', strip=True) for a in tag.find_all('a'))


def _find_cover_image(soup: BeautifulSoup) -> str | None:
    return _meta(soup, 'og:image', 'twitter:image')


def parse_series_page(html: str, page_url: str) -> SeriesData:
    soup = _soup(html)
    lines = _lines(soup)
    title = clean_ws(_meta(soup, 'og:title') or (lines[0] if lines else ''))
    if not title:
        raise ParseError('Unable to extract the series title.')

    title_clean = re.sub(r'\s*-\s*Manga.*$', '', title, flags=re.IGNORECASE)
    summary = _extract_section(lines, 'Résumé') or _meta(soup, 'description')
    strengths = _extract_section(lines, 'Les points forts de la série')

    title_vo = _extract_line_value(lines, VALUE_LABELS['title_vo'])
    translated_title = _extract_line_value(lines, VALUE_LABELS['translated_title'])
    authors_story = unique_list((_extract_line_value(lines, VALUE_LABELS['story']) or '').split(','))
    authors_art = unique_list((_extract_line_value(lines, VALUE_LABELS['art']) or '').split(','))
    translators = unique_list((_extract_line_value(lines, VALUE_LABELS['translator']) or '').split(','))
    genres = unique_list((_extract_line_value(lines, VALUE_LABELS['genre']) or '').split(','))
    themes = []
    for index, line in enumerate(lines):
        if normalize_text(line) in {'thèmes', 'themes'}:
            cursor = index + 1
            while cursor < len(lines):
                candidate = lines[cursor]
                normalized_candidate = normalize_text(candidate)
                if normalized_candidate in SECTION_STOP_WORDS:
                    break
                if normalized_candidate.startswith('serie '):
                    candidate = candidate.split(' ', 1)[1]
                themes.extend(unique_list(candidate.split('   ')))
                cursor += 1
            break
    vf, vo, last_release_date, next_release_date = _extract_vf_vo(lines)
    stats = SeriesStats(
        likes=_extract_number_after(lines, "J'aime"),
        in_collection=_extract_number_after(lines, 'Dans ma collection'),
        in_wishlist=_extract_number_after(lines, "Dans ma liste d'achat"),
        marketplace=_extract_number_after(lines, 'Achat/vente'),
        editorial_score=_extract_score_after(lines, 'Rédaction'),
        reader_score=_extract_score_after(lines, 'Lecteurs'),
    )

    return SeriesData(
        title=title_clean,
        title_vo=title_vo,
        translated_title=translated_title,
        summary=summary,
        authors_story=authors_story,
        authors_art=authors_art,
        translators=translators,
        publisher_fr=_extract_line_value(lines, VALUE_LABELS['publisher_fr']),
        publisher_vo=_extract_line_value(lines, VALUE_LABELS['publisher_vo']),
        collection=_extract_line_value(lines, VALUE_LABELS['collection']),
        type=_extract_line_value(lines, VALUE_LABELS['type']),
        genres=genres,
        prepublication=_extract_line_value(lines, VALUE_LABELS['prepublication']),
        origin=_extract_line_value(lines, VALUE_LABELS['origin']),
        illustration=_extract_line_value(lines, VALUE_LABELS['illustration']),
        advisory_age=_extract_number_after(lines, 'Age conseillé') and str(_extract_number_after(lines, 'Age conseillé')) + '+',
        cover_image=_find_cover_image(soup),
        vf=vf,
        vo=vo,
        last_release_date=last_release_date,
        next_release_date=next_release_date,
        stats=stats,
        themes=unique_list(themes),
        strengths=strengths,
        source_url=page_url,
    )


def parse_volume_page(html: str, page_url: str) -> VolumeData:
    soup = _soup(html)
    lines = _lines(soup)
    title = clean_ws(_meta(soup, 'og:title') or (lines[0] if lines else ''))
    if not title:
        raise ParseError('Unable to extract the volume title.')

    title_clean = re.sub(r'\s*-\s*Manga.*$', '', title, flags=re.IGNORECASE)
    series_title = None
    parsed_path = [part for part in urlparse(page_url).path.split('/') if part]
    if 'manga' in parsed_path and len(parsed_path) >= 4:
        possible_series = parsed_path[2].replace('-', ' ')
        series_title = clean_ws(possible_series.title())

    return VolumeData(
        title=title_clean,
        series_title=series_title,
        title_vo=_extract_line_value(lines, VALUE_LABELS['title_vo']),
        translated_title=_extract_line_value(lines, VALUE_LABELS['translated_title']),
        summary=_extract_section(lines, 'Résumé') or _meta(soup, 'description'),
        authors_story=unique_list((_extract_line_value(lines, VALUE_LABELS['story']) or '').split(',')),
        authors_art=unique_list((_extract_line_value(lines, VALUE_LABELS['art']) or '').split(',')),
        translators=unique_list((_extract_line_value(lines, VALUE_LABELS['translator']) or '').split(',')),
        publisher_fr=_extract_line_value(lines, VALUE_LABELS['publisher_fr']),
        publisher_vo=_extract_line_value(lines, VALUE_LABELS['publisher_vo']),
        collection=_extract_line_value(lines, VALUE_LABELS['collection']),
        type=_extract_line_value(lines, VALUE_LABELS['type']),
        genres=unique_list((_extract_line_value(lines, VALUE_LABELS['genre']) or '').split(',')),
        prepublication=_extract_line_value(lines, VALUE_LABELS['prepublication']),
        origin=_extract_line_value(lines, VALUE_LABELS['origin']),
        illustration=_extract_line_value(lines, VALUE_LABELS['illustration']),
        advisory_age=_extract_number_after(lines, 'Age conseillé') and str(_extract_number_after(lines, 'Age conseillé')) + '+',
        publication_date=parse_french_date(_extract_line_value(lines, VALUE_LABELS['publication_date'])),
        isbn_ean=_extract_line_value(lines, VALUE_LABELS['isbn_ean']),
        price_code=_extract_line_value(lines, VALUE_LABELS['price_code']),
        cover_image=_find_cover_image(soup),
        editorial_score=_extract_score_after(lines, 'Rédaction'),
        reader_score=_extract_score_after(lines, 'Lecteurs'),
        source_url=page_url,
    )


def _guess_article_url(soup: BeautifulSoup, title: str, base_url: str) -> str | None:
    normalized_title = normalize_text(title)
    for anchor in soup.find_all('a', href=True):
        text = clean_ws(anchor.get_text(' ', strip=True))
        href = anchor['href']
        if '/index.php/actus/' not in href:
            continue
        if normalize_text(text) == normalized_title:
            return ensure_absolute_url(base_url, href)
    return None


def parse_news_page(html: str, page_url: str, base_url: str, limit: int) -> list[NewsItem]:
    soup = _soup(html)
    lines = _lines(soup)
    items: list[NewsItem] = []
    for index, line in enumerate(lines):
        normalized_line = normalize_text(line)
        if normalized_line in NEWS_STOP_WORDS:
            break
        match = DATE_LINE_RE.match(line)
        if not match:
            continue
        title = None
        category = None
        back = index - 1
        while back >= 0 and index - back <= 4:
            candidate = lines[back]
            normalized_candidate = normalize_text(candidate)
            if normalized_candidate in NEWS_CATEGORY_HINTS and category is None:
                category = candidate
            elif normalized_candidate not in NEWS_CATEGORY_HINTS and normalized_candidate not in {'', 'actualite manga news illustration'} and title is None:
                title = candidate
            if title and category:
                break
            back -= 1
        if not title:
            continue
        published_at = parse_french_date(match.group(2))
        excerpt = clean_ws(match.group(3)) or None
        comments = None
        if index + 1 < len(lines):
            comments_match = re.search(r'(\d+)\s+comment', lines[index + 1], flags=re.IGNORECASE)
            if comments_match:
                comments = int(comments_match.group(1))
            elif 'aucun commentaire' in normalize_text(lines[index + 1]):
                comments = 0
        items.append(
            NewsItem(
                title=title,
                url=_guess_article_url(soup, title, base_url),
                published_at=published_at,
                excerpt=excerpt,
                comments=comments,
                category=category,
            )
        )
        if len(items) >= limit:
            break
    if not items:
        raise ParseError('Unable to parse the news list.')
    return items


def parse_search_page(html: str, page_url: str, base_url: str, query: str, kind: str, score_threshold: int, limit: int) -> list[SearchResult]:
    soup = _soup(html)
    results: list[SearchResult] = []
    seen: set[str] = set()
    for anchor in soup.find_all('a', href=True):
        href = anchor.get('href', '')
        absolute_url = ensure_absolute_url(base_url, href)
        if not absolute_url or absolute_url in seen:
            continue
        text = clean_ws(anchor.get_text(' ', strip=True))
        normalized_text = normalize_text(text)
        if normalized_text in GENERIC_ANCHOR_TEXTS or len(normalized_text) < 2:
            continue

        result_kind = None
        slug = None
        series_slug = None
        volume_slug = None
        parsed_path = [part for part in urlparse(absolute_url).path.split('/') if part]
        if '/index.php/serie/' in absolute_url and not any(part in absolute_url for part in ['/serie/news/', '/serie/avis/', '/serie/editions', '/serie/editionsVo']):
            result_kind = 'series'
            if parsed_path:
                slug = parsed_path[-1]
                series_slug = slug
        elif '/index.php/manga/' in absolute_url and not any(part in absolute_url for part in ['/manga/news/', '/manga/critique/', '/manga/avis/', '/manga/extrait/']):
            result_kind = 'volume'
            if len(parsed_path) >= 4:
                series_slug = parsed_path[-2]
                volume_slug = parsed_path[-1]
        if result_kind is None:
            continue
        if kind != 'all' and result_kind != kind:
            continue

        score = score_match(query, text, extra=absolute_url)
        if score < score_threshold:
            continue
        seen.add(absolute_url)
        results.append(
            SearchResult(
                title=text,
                url=absolute_url,
                kind=result_kind,
                score=score,
                slug=slug,
                series_slug=series_slug,
                volume_slug=volume_slug,
            )
        )
    results.sort(key=lambda item: item.score, reverse=True)
    return results[:limit]
