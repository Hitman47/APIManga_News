from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Iterable
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.exceptions import ParseError
from app.models import (
    EditionStatus,
    IllustrationDetails,
    LinkItem,
    NewsItem,
    PlanningItem,
    PlanningPage,
    RelatedLinks,
    SearchResult,
    SeriesData,
    SeriesEditionGroup,
    SeriesEditionGroupsData,
    SeriesEditionItem,
    SeriesEditionsBlock,
    SeriesReleaseVolume,
    SeriesSearchMetaData,
    SeriesStats,
    VolumeData,
    VolumeSearchMetaData,
)
from app.utils import (
    clean_ws,
    ensure_absolute_url,
    extract_volume_number,
    infer_media_kind,
    infer_volume_edition_label,
    infer_volume_flags,
    normalize_text,
    parse_french_date,
    parse_volume_number_int,
    search_result_sort_key,
    score_match,
    slugify,
    unique_list,
)

DATE_LINE_RE = re.compile(
    r'^(Lundi|Mardi|Mercredi|Jeudi|Vendredi|Samedi|Dimanche),?\s+(\d{1,2}\s+[A-Za-zéûîôàèùçÉÛÎÔÀÈÙÇ]+\s+\d{4})(?:\s+(.*))?$'
)
PLANNING_ITEM_RE = re.compile(
    r'^(?P<title>.+?)(?:\s+à ne pas manquer !)?\s+Sortie le\s+(?P<release_date>\d{2}/\d{2}/\d{4})(?:\s+Auteurs?\(s\):\s*(?P<authors>.+?))?(?:\s+Editeur:\s*(?P<publisher>.+))$',
    flags=re.IGNORECASE,
)
PLANNING_HEADER_RE = re.compile(r'^Planning des sorties(?:\s+[A-Za-z]+)?\s+(?P<year>\d{4})/(?P<month>\d{1,2})$', flags=re.IGNORECASE)
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
    'produits derives', 'produits dérivés', 'anime', 'drama', 'lire aussi',
}
RAW_SECTION_HEADINGS = {
    'resume', 'résumé', 'themes', 'thèmes', 'les points forts de la serie', 'les points forts de la série',
    'manga en relation', 'dossier', 'dossiers', 'univers', 'liens', 'personnages', 'les volumes',
    'age conseille', 'age conseillé', 'dernier paru', 'a paraitre', 'a paraître',
}
NEWS_STOP_WORDS = {'actus précédentes', 'actus precedentes', 'univers', 'liens', 'signaler', 'chez notre partenaire'}
NEWS_CATEGORY_HINTS = {'manga', 'anime', 'webtoon', 'presse', 'drama', 'japon', 'produits dérivés', 'produits derives'}
GENERIC_ANCHOR_TEXTS = {
    'manga news', 'facebook', 'twitter', 'instagram', 'youtube', 'dailymotion', 'pinterest',
    'voir le produit', 'voir toutes les figurines', 'lire le dossier', 'partie 1', 'partie 2',
    'partie 3', 'mot de la fin', 's inscrire', 'connexion', 'j ai oublié mes identifiants !',
}
NORMALIZED_RAW_SECTION_HEADINGS = frozenset(normalize_text(heading) for heading in RAW_SECTION_HEADINGS)
NORMALIZED_VALUE_LABELS = frozenset(
    normalize_text(label)
    for labels in VALUE_LABELS.values()
    for label in labels
)

HEADING_CATEGORY_MAP = {
    'manga en relation': 'series',
    'serie en relation': 'series',
    'series en relation': 'series',
    'anime': 'anime',
    'drama': 'drama',
    'univers': 'univers',
    'dossier': 'dossiers',
    'dossiers': 'dossiers',
    'liens': 'external',
    'produits derives': 'misc',
    'produits dérivés': 'misc',
    'jeux video': 'misc',
    'jeu video': 'misc',
}


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, 'lxml')


class _TextLines(list[str]):
    normalized: list[str] | None = None
    metadata: dict[str, str] | None = None


def _value_after_dom_label(container_text: str, label_text: str) -> str | None:
    canonical_label = clean_ws(clean_ws(label_text).rstrip(':'))
    pattern = re.compile(
        rf'^\s*{re.escape(canonical_label)}\s*:?\s*(?P<value>.+)$',
        flags=re.IGNORECASE,
    )
    match = pattern.match(clean_ws(container_text))
    return clean_ws(match.group('value')) if match else None


def _extract_dom_metadata(soup: BeautifulSoup) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for label_node in soup.find_all(['strong', 'dt', 'th']):
        label_text = clean_ws(label_node.get_text(' ', strip=True))
        normalized_label = normalize_text(label_text)
        if normalized_label not in NORMALIZED_VALUE_LABELS or normalized_label in metadata:
            continue

        if label_node.name == 'dt':
            value_node = label_node.find_next_sibling('dd')
            value = clean_ws(value_node.get_text(' ', strip=True)) if value_node else None
        else:
            container = label_node.find_parent(['li', 'tr']) or label_node.parent
            value = (
                _value_after_dom_label(container.get_text(' ', strip=True), label_text)
                if container is not None
                else None
            )

        if value:
            metadata[normalized_label] = value
    return metadata


def _lines(soup: BeautifulSoup) -> list[str]:
    raw_lines = soup.get_text('\n', strip=True).splitlines()
    lines = _TextLines(clean_ws(line) for line in raw_lines if clean_ws(line))
    lines.metadata = _extract_dom_metadata(soup)
    return lines


def _normalized_lines(lines: list[str]) -> list[str]:
    if isinstance(lines, _TextLines):
        if lines.normalized is None:
            lines.normalized = [normalize_text(line) for line in lines]
        return lines.normalized
    return [normalize_text(line) for line in lines]


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
        if tag and tag.get('content'):
            return clean_ws(tag['content'])
    return None


def _extract_line_value(
    lines: list[str],
    labels: Iterable[str],
    normalized_lines: list[str] | None = None,
) -> str | None:
    normalized_lines = normalized_lines or _normalized_lines(lines)
    canonical_labels = tuple(dict.fromkeys(clean_ws(clean_ws(label).rstrip(':')) for label in labels))
    normalized_labels = tuple(dict.fromkeys(normalize_text(label) for label in canonical_labels))

    if isinstance(lines, _TextLines) and lines.metadata:
        for normalized_label in normalized_labels:
            value = lines.metadata.get(normalized_label)
            if value:
                return value

    for line, normalized_line in zip(lines, normalized_lines):
        for label, normalized_label in zip(canonical_labels, normalized_labels):
            if ':' in line:
                inline_label, inline_value = line.split(':', 1)
                if normalize_text(inline_label) == normalized_label:
                    return clean_ws(inline_value) or None
            if normalized_line == normalized_label:
                continue
            if not normalized_line.startswith(f'{normalized_label} '):
                continue
            match = re.match(
                rf'^\s*{re.escape(label)}(?:\s*:\s*|\s+)(?P<value>.+)$',
                line,
                flags=re.IGNORECASE,
            )
            if match:
                return clean_ws(match.group('value')) or None
    return None


def _is_value_label_line(line: str, normalized_line: str | None = None) -> bool:
    normalized_line = normalized_line or normalize_text(line)
    if normalized_line in NORMALIZED_VALUE_LABELS:
        return True
    return any(normalized_line.startswith(f'{label} ') for label in NORMALIZED_VALUE_LABELS)


def _extract_number_after(
    lines: list[str],
    label: str,
    normalized_lines: list[str] | None = None,
) -> int | None:
    normalized_lines = normalized_lines or _normalized_lines(lines)
    normalized_label = normalize_text(label)
    for index, (line, normalized_line) in enumerate(zip(lines, normalized_lines)):
        if normalized_line == normalized_label:
            for offset in range(1, 3):
                if index + offset >= len(lines):
                    break
                match = re.search(r'(\d+)', lines[index + offset])
                if match:
                    return int(match.group(1))
        if normalized_label in normalized_line:
            match = re.search(r'(\d+)', line)
            if match:
                return int(match.group(1))
    return None


def _extract_score_after(
    lines: list[str],
    label: str,
    normalized_lines: list[str] | None = None,
) -> float | None:
    normalized_lines = normalized_lines or _normalized_lines(lines)
    normalized_label = normalize_text(label)
    for index, (line, normalized_line) in enumerate(zip(lines, normalized_lines)):
        if normalized_line == normalized_label:
            for offset in range(1, 3):
                if index + offset >= len(lines):
                    break
                match = re.search(r'(\d+(?:[\.,]\d+)?)\s*/\s*20', lines[index + offset])
                if match:
                    return float(match.group(1).replace(',', '.'))
        if normalized_label in normalized_line:
            match = re.search(r'(\d+(?:[\.,]\d+)?)\s*/\s*20', line)
            if match:
                return float(match.group(1).replace(',', '.'))
    return None


def _extract_section(
    lines: list[str],
    heading: str,
    normalized_lines: list[str] | None = None,
) -> str | None:
    normalized_lines = normalized_lines or _normalized_lines(lines)
    normalized_heading = normalize_text(heading)
    for index, normalized_line in enumerate(normalized_lines):
        if normalized_line != normalized_heading:
            continue
        collected: list[str] = []
        for candidate, normalized_candidate in zip(lines[index + 1:], normalized_lines[index + 1:]):
            if normalized_candidate in NORMALIZED_RAW_SECTION_HEADINGS and normalized_candidate != normalized_heading:
                break
            if _is_value_label_line(candidate, normalized_candidate):
                break
            collected.append(candidate)
        text = clean_ws(' '.join(collected))
        return text or None
    return None


def _extract_raw_sections(
    lines: list[str],
    normalized_lines: list[str] | None = None,
) -> dict[str, list[str]]:
    normalized_lines = normalized_lines or _normalized_lines(lines)
    sections: dict[str, list[str]] = {}
    for index, normalized_line in enumerate(normalized_lines):
        if normalized_line not in NORMALIZED_RAW_SECTION_HEADINGS:
            continue
        collected: list[str] = []
        for candidate, normalized_candidate in zip(lines[index + 1:], normalized_lines[index + 1:]):
            if normalized_candidate in NORMALIZED_RAW_SECTION_HEADINGS and normalized_candidate != normalized_line:
                break
            if _is_value_label_line(candidate, normalized_candidate):
                break
            collected.append(candidate)
        key = slugify(normalized_line).replace('-', '_')
        if collected:
            sections[key] = collected
    return sections


def _edition_status_from_text(text: str | None, label: str) -> EditionStatus | None:
    cleaned = clean_ws(text)
    if not cleaned:
        return None
    pattern = re.compile(rf'{label}\s*:?\s*(\d+)\s*(?:\(([^)]+)\))?', flags=re.IGNORECASE)
    match = pattern.search(cleaned)
    if not match:
        return None
    status = clean_ws(match.group(2) or '') or None
    return EditionStatus(volumes=int(match.group(1)), status=status)


def _extract_vf_vo_from_numberblock(soup: BeautifulSoup) -> tuple[EditionStatus | None, EditionStatus | None]:
    container = soup.find(id='numberblock')
    if not container:
        return None, None

    vf_status: EditionStatus | None = None
    vo_status: EditionStatus | None = None

    vf_version = container.select_one('.version')
    if vf_version and normalize_text(vf_version.get_text(' ', strip=True)).startswith('vf'):
        parent = vf_version.parent if getattr(vf_version, 'parent', None) else None
        vf_status = _edition_status_from_text(parent.get_text(' ', strip=True) if parent else None, 'VF')

    for anchor in container.find_all('a', href=True):
        text = anchor.get_text(' ', strip=True)
        if '/serie-vo/' in anchor.get('href', '') or normalize_text(text).startswith('vo'):
            vo_status = _edition_status_from_text(text, 'VO')
            if vo_status:
                break

    if not vf_status or not vo_status:
        normalized_lines = [clean_ws(text) for text in container.stripped_strings]
        for idx, line in enumerate(normalized_lines):
            normalized = normalize_text(line)
            if not vf_status and normalized.startswith('vf'):
                joined = ' '.join(normalized_lines[idx:idx + 3])
                vf_status = _edition_status_from_text(joined, 'VF')
            if not vo_status and normalized.startswith('vo'):
                joined = ' '.join(normalized_lines[idx:idx + 3])
                vo_status = _edition_status_from_text(joined, 'VO')

    return vf_status, vo_status


def _extract_vf_vo(
    soup: BeautifulSoup,
    lines: list[str],
    normalized_lines: list[str] | None = None,
) -> tuple[EditionStatus | None, EditionStatus | None, str | None, str | None]:
    normalized_lines = normalized_lines or _normalized_lines(lines)
    vf_status, vo_status = _extract_vf_vo_from_numberblock(soup)
    last_release = None
    next_release = None
    for index, (line, normalized_line) in enumerate(zip(lines, normalized_lines)):
        if not vf_status:
            vf_status = _edition_status_from_text(line, 'VF')
        if not vo_status:
            vo_status = _edition_status_from_text(line, 'VO')
        if normalized_line == 'dernier paru' and index + 1 < len(lines):
            last_release = parse_french_date(lines[index + 1])
        if normalized_line in {'a paraitre', 'a paraître'} and index + 1 < len(lines):
            next_release = parse_french_date(lines[index + 1])
    return vf_status, vo_status, last_release, next_release


def _extract_series_release_volume(
    soup: BeautifulSoup,
    element_id: str,
    page_url: str,
) -> SeriesReleaseVolume | None:
    container = soup.find(id=element_id)
    if container is None:
        return None

    base_url = _base_url_from_page(page_url)
    for anchor in container.find_all('a', href=True):
        source_url = ensure_absolute_url(base_url, anchor.get('href', ''))
        if not source_url or '/index.php/manga/' not in source_url:
            continue
        parsed_path = [part for part in urlparse(source_url).path.split('/') if part]
        if len(parsed_path) < 4:
            continue
        series_slug = parsed_path[-2]
        volume_slug = parsed_path[-1]
        image = anchor.find('img')
        title = clean_ws(
            anchor.get('title')
            or anchor.get('aria-label')
            or (image.get('alt') if image is not None else None)
            or ''
        )
        number = _guess_volume_number(title, volume_slug)
        publication_date = _extract_publication_date_from_text(
            clean_ws(anchor.get_text(' ', strip=True))
            or clean_ws(container.get_text(' ', strip=True))
        )
        if not number or not publication_date:
            continue
        if not title:
            title = f'Vol.{number}'
        edition_label = infer_volume_edition_label(title)
        is_special, is_one_shot = infer_volume_flags(title)
        cover_image = None
        if image is not None and image.get('src'):
            cover_image = ensure_absolute_url(base_url, image.get('src'))
        return SeriesReleaseVolume(
            title=title,
            number=number,
            number_int=parse_volume_number_int(number),
            publication_date=publication_date,
            source_url=source_url,
            series_slug=series_slug,
            volume_slug=volume_slug,
            cover_image=cover_image,
            is_special=is_special,
            is_one_shot=is_one_shot,
            edition_label=edition_label,
        )
    return None


def _find_cover_image(soup: BeautifulSoup) -> str | None:
    return _meta(soup, 'og:image', 'twitter:image')


def _extract_page_title(soup: BeautifulSoup, lines: list[str], *, kind: str) -> str:
    raw_title = clean_ws(_meta(soup, 'og:title') or '')
    if raw_title:
        cleaned = clean_ws(re.sub(r'\s*-\s*Manga.*$', '', raw_title, flags=re.IGNORECASE))
        if cleaned:
            return cleaned

    heading = soup.find('h1')
    if heading:
        cleaned = clean_ws(heading.get_text(' ', strip=True))
        if cleaned:
            return cleaned

    fallback = clean_ws(lines[0] if lines else '')
    normalized_fallback = normalize_text(fallback)
    looks_like_value_line = _is_value_label_line(fallback, normalized_fallback) or ':' in fallback
    if (
        fallback
        and normalized_fallback not in RAW_SECTION_HEADINGS
        and normalized_fallback not in SECTION_STOP_WORDS
        and not looks_like_value_line
    ):
        return fallback

    raise ParseError(f'Unable to extract the {kind} title.')
def _parse_illustration_details(raw: str | None) -> IllustrationDetails | None:
    if not raw:
        return None
    normalized = normalize_text(raw)
    pages = None
    pages_match = re.search(r'(\d+)\s+pages?', normalized)
    if pages_match:
        pages = int(pages_match.group(1))
    has_color_pages = None
    if 'couleur' in normalized:
        has_color_pages = True
    elif 'n&b' in normalized or 'nb' in normalized:
        has_color_pages = False
    return IllustrationDetails(raw=raw, pages=pages, has_color_pages=has_color_pages)


def _anchor_context_heading(anchor) -> str | None:
    for level in range(4):
        node = anchor if level == 0 else getattr(anchor, 'parent', None)
        if level > 0:
            for _ in range(level - 1):
                node = getattr(node, 'parent', None)
                if node is None:
                    break
        current = node
        while current is not None:
            sibling = current.previous_sibling
            while sibling is not None:
                if getattr(sibling, 'get_text', None):
                    text = clean_ws(sibling.get_text(' ', strip=True))
                    normalized_text = normalize_text(text)
                    if normalized_text in HEADING_CATEGORY_MAP:
                        return HEADING_CATEGORY_MAP[normalized_text]
                sibling = getattr(sibling, 'previous_sibling', None)
            current = getattr(current, 'parent', None)
    return None


def _infer_link_kind(url: str, base_url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.netloc or url.startswith(base_url):
        path = parsed.path.lower()
        if '/index.php/serie/' in url and not any(part in url for part in ['/serie/news/', '/serie/avis/', '/serie/editions', '/serie/editionsVo']):
            return 'series'
        if '/index.php/manga/' in url and not any(part in url for part in ['/manga/news/', '/manga/critique/', '/manga/avis/', '/manga/extrait/']):
            return 'volumes'
        if '/anime' in path:
            return 'anime'
        if 'drama' in path:
            return 'drama'
        if any(token in path for token in ['/index.php/dossier', '/index.php/dossiers', '/index.php/report', '/index.php/reports']):
            return 'dossiers'
        if '/index.php/univers/' in path:
            return 'univers'
        if any(token in path for token in ['/goodies', '/jeuxvideo', '/jeu-video', '/produits']):
            return 'misc'
        return None
    return 'external'


def _extract_related_links(soup: BeautifulSoup, base_url: str, page_url: str) -> RelatedLinks:
    buckets: dict[str, list[LinkItem]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for anchor in soup.find_all('a', href=True):
        href = anchor.get('href', '')
        url = ensure_absolute_url(base_url, href)
        if not url or url == page_url:
            continue
        text = clean_ws(anchor.get_text(' ', strip=True))
        normalized_text = normalize_text(text)
        if not text or len(normalized_text) < 2 or normalized_text in GENERIC_ANCHOR_TEXTS:
            continue
        category = _infer_link_kind(url, base_url)
        if category is None:
            continue
        item = LinkItem(title=text, url=url, kind=category)
        key = (category, url)
        if key in seen:
            continue
        seen.add(key)
        buckets[category].append(item)
    return RelatedLinks(
        series=buckets.get('series', []),
        volumes=buckets.get('volumes', []),
        anime=buckets.get('anime', []),
        drama=buckets.get('drama', []),
        dossiers=buckets.get('dossiers', []),
        univers=buckets.get('univers', []),
        external=buckets.get('external', []),
        misc=buckets.get('misc', []),
    )


def parse_series_page(html: str, page_url: str) -> SeriesData:
    soup = _soup(html)
    lines = _lines(soup)
    normalized_lines = _normalized_lines(lines)
    title_clean = _extract_page_title(soup, lines, kind='series')
    summary = _extract_section(lines, 'Résumé', normalized_lines) or _meta(soup, 'description')
    strengths = _extract_section(lines, 'Les points forts de la série', normalized_lines)
    illustration = _extract_line_value(lines, VALUE_LABELS['illustration'], normalized_lines)

    title_vo = _extract_line_value(lines, VALUE_LABELS['title_vo'], normalized_lines)
    translated_title = _extract_line_value(lines, VALUE_LABELS['translated_title'], normalized_lines)
    authors_story = unique_list((_extract_line_value(lines, VALUE_LABELS['story'], normalized_lines) or '').split(','))
    authors_art = unique_list((_extract_line_value(lines, VALUE_LABELS['art'], normalized_lines) or '').split(','))
    translators = unique_list((_extract_line_value(lines, VALUE_LABELS['translator'], normalized_lines) or '').split(','))
    genres = unique_list((_extract_line_value(lines, VALUE_LABELS['genre'], normalized_lines) or '').split(','))
    themes: list[str] = []
    raw_sections = _extract_raw_sections(lines, normalized_lines)
    for value in raw_sections.get('themes', []) + raw_sections.get('thèmes', []):
        if normalize_text(value).startswith('serie '):
            value = value.split(' ', 1)[1]
        themes.extend(unique_list(value.split('   ')))
    vf, vo, last_release_date, next_release_date = _extract_vf_vo(soup, lines, normalized_lines)
    last_release_volume = _extract_series_release_volume(soup, 'lastvol', page_url)
    next_release_volume = _extract_series_release_volume(soup, 'nextvol', page_url)
    stats = SeriesStats(
        likes=_extract_number_after(lines, "J'aime", normalized_lines),
        in_collection=_extract_number_after(lines, 'Dans ma collection', normalized_lines),
        in_wishlist=_extract_number_after(lines, "Dans ma liste d'achat", normalized_lines),
        marketplace=_extract_number_after(lines, 'Achat/vente', normalized_lines),
        editorial_score=_extract_score_after(lines, 'Rédaction', normalized_lines),
        reader_score=_extract_score_after(lines, 'Lecteurs', normalized_lines),
    )
    advisory_age = _extract_number_after(lines, 'Age conseillé', normalized_lines)

    return SeriesData(
        title=title_clean,
        title_vo=title_vo,
        translated_title=translated_title,
        summary=summary,
        authors_story=authors_story,
        authors_art=authors_art,
        translators=translators,
        publisher_fr=_extract_line_value(lines, VALUE_LABELS['publisher_fr'], normalized_lines),
        publisher_vo=_extract_line_value(lines, VALUE_LABELS['publisher_vo'], normalized_lines),
        collection=_extract_line_value(lines, VALUE_LABELS['collection'], normalized_lines),
        type=_extract_line_value(lines, VALUE_LABELS['type'], normalized_lines),
        genres=genres,
        prepublication=_extract_line_value(lines, VALUE_LABELS['prepublication'], normalized_lines),
        origin=_extract_line_value(lines, VALUE_LABELS['origin'], normalized_lines),
        illustration=illustration,
        illustration_details=_parse_illustration_details(illustration),
        advisory_age=f'{advisory_age}+' if advisory_age is not None else None,
        cover_image=_find_cover_image(soup),
        vf=vf,
        vo=vo,
        last_release_date=last_release_date,
        next_release_date=next_release_date,
        last_release_volume=last_release_volume,
        next_release_volume=next_release_volume,
        stats=stats,
        themes=unique_list(themes),
        strengths=strengths,
        related=_extract_related_links(soup, _base_url_from_page(page_url), page_url),
        raw_sections=raw_sections or None,
        source_url=page_url,
    )


def parse_series_search_meta_page(html: str, page_url: str) -> SeriesSearchMetaData:
    soup = _soup(html)
    lines = _lines(soup)
    normalized_lines = _normalized_lines(lines)
    title_clean = _extract_page_title(soup, lines, kind='series')
    vf, vo, _, _ = _extract_vf_vo(soup, lines, normalized_lines)
    source_type = _extract_line_value(lines, VALUE_LABELS['type'], normalized_lines)
    related = _extract_related_links(soup, _base_url_from_page(page_url), page_url)
    return SeriesSearchMetaData(
        title=title_clean,
        title_vo=_extract_line_value(lines, VALUE_LABELS['title_vo']),
        translated_title=_extract_line_value(lines, VALUE_LABELS['translated_title']),
        source_type=source_type,
        media_kind=infer_media_kind(
            title=title_clean,
            source_type=source_type,
            kind='series',
            related_series_titles=[item.title for item in related.series],
        ),
        vf=vf,
        vo=vo,
        related=related,
        source_url=page_url,
    )


def parse_volume_search_meta_page(html: str, page_url: str) -> VolumeSearchMetaData:
    soup = _soup(html)
    lines = _lines(soup)
    normalized_lines = _normalized_lines(lines)
    title_clean = _extract_page_title(soup, lines, kind='volume')
    parsed_path = [part for part in urlparse(page_url).path.split('/') if part]
    number = extract_volume_number(title_clean, parsed_path[-1] if parsed_path else None)
    volume_type = _extract_line_value(lines, VALUE_LABELS['type'], normalized_lines)
    collection = _extract_line_value(lines, VALUE_LABELS['collection'], normalized_lines)
    edition_label = infer_volume_edition_label(title_clean, collection, volume_type)
    is_special, is_one_shot = infer_volume_flags(title_clean, collection, volume_type)

    return VolumeSearchMetaData(
        title=title_clean,
        number=number,
        number_int=parse_volume_number_int(number),
        edition_label=edition_label,
        is_special=is_special,
        is_one_shot=is_one_shot,
        title_vo=_extract_line_value(lines, VALUE_LABELS['title_vo']),
        translated_title=_extract_line_value(lines, VALUE_LABELS['translated_title']),
        source_type=volume_type,
        media_kind=infer_media_kind(
            title=title_clean,
            source_type=volume_type,
            kind='volume',
            is_special=is_special,
        ),
        source_url=page_url,
    )


def parse_volume_page(html: str, page_url: str) -> VolumeData:
    soup = _soup(html)
    lines = _lines(soup)
    normalized_lines = _normalized_lines(lines)
    title_clean = _extract_page_title(soup, lines, kind='volume')
    series_title = None
    parsed_path = [part for part in urlparse(page_url).path.split('/') if part]
    if 'manga' in parsed_path and len(parsed_path) >= 4:
        possible_series = parsed_path[2].replace('-', ' ')
        series_title = clean_ws(possible_series.title())
    illustration = _extract_line_value(lines, VALUE_LABELS['illustration'], normalized_lines)

    number = extract_volume_number(title_clean, parsed_path[-1] if parsed_path else None)
    volume_type = _extract_line_value(lines, VALUE_LABELS['type'], normalized_lines)
    collection = _extract_line_value(lines, VALUE_LABELS['collection'], normalized_lines)
    edition_label = infer_volume_edition_label(title_clean, collection, volume_type)
    is_special, is_one_shot = infer_volume_flags(title_clean, collection, volume_type)
    advisory_age = _extract_number_after(lines, 'Age conseillé', normalized_lines)

    return VolumeData(
        title=title_clean,
        series_title=series_title,
        number=number,
        number_int=parse_volume_number_int(number),
        edition_label=edition_label,
        is_special=is_special,
        is_one_shot=is_one_shot,
        title_vo=_extract_line_value(lines, VALUE_LABELS['title_vo']),
        translated_title=_extract_line_value(lines, VALUE_LABELS['translated_title']),
        summary=_extract_section(lines, 'Résumé', normalized_lines) or _meta(soup, 'description'),
        authors_story=unique_list((_extract_line_value(lines, VALUE_LABELS['story']) or '').split(',')),
        authors_art=unique_list((_extract_line_value(lines, VALUE_LABELS['art']) or '').split(',')),
        translators=unique_list((_extract_line_value(lines, VALUE_LABELS['translator']) or '').split(',')),
        publisher_fr=_extract_line_value(lines, VALUE_LABELS['publisher_fr']),
        publisher_vo=_extract_line_value(lines, VALUE_LABELS['publisher_vo']),
        collection=collection,
        type=volume_type,
        genres=unique_list((_extract_line_value(lines, VALUE_LABELS['genre']) or '').split(',')),
        prepublication=_extract_line_value(lines, VALUE_LABELS['prepublication']),
        origin=_extract_line_value(lines, VALUE_LABELS['origin']),
        illustration=illustration,
        illustration_details=_parse_illustration_details(illustration),
        advisory_age=f'{advisory_age}+' if advisory_age is not None else None,
        publication_date=parse_french_date(_extract_line_value(lines, VALUE_LABELS['publication_date'])),
        isbn_ean=_extract_line_value(lines, VALUE_LABELS['isbn_ean']),
        price_code=_extract_line_value(lines, VALUE_LABELS['price_code']),
        cover_image=_find_cover_image(soup),
        editorial_score=_extract_score_after(lines, 'Rédaction', normalized_lines),
        reader_score=_extract_score_after(lines, 'Lecteurs', normalized_lines),
        raw_sections=_extract_raw_sections(lines, normalized_lines) or None,
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
        number = extract_volume_number(text, volume_slug)
        edition_label = infer_volume_edition_label(text)
        is_special, is_one_shot = infer_volume_flags(text)
        results.append(
            SearchResult(
                title=text,
                url=absolute_url,
                kind=result_kind,
                score=score,
                slug=slug,
                series_slug=series_slug,
                volume_slug=volume_slug,
                number=number,
                number_int=parse_volume_number_int(number),
                edition_label=edition_label,
                is_special=is_special,
                is_one_shot=is_one_shot,
                media_kind=infer_media_kind(
                    title=text,
                    kind=result_kind,
                    is_special=is_special,
                ),
            )
        )
    results.sort(key=lambda item: search_result_sort_key(query, item))
    return results[:limit]



def _infer_planning_section(page_url: str) -> str:
    normalized = page_url.lower()
    if '/planning/mangas-vo' in normalized:
        return 'manga-vo'
    return 'manga-vf'



def _extract_planning_header(lines: list[str]) -> tuple[int | None, int | None]:
    for line in lines:
        match = PLANNING_HEADER_RE.match(line)
        if match:
            return int(match.group('year')), int(match.group('month'))
    return None, None



def parse_planning_page(html: str, page_url: str, base_url: str) -> PlanningPage:
    soup = _soup(html)
    lines = _lines(soup)
    year, month = _extract_planning_header(lines)

    candidate_lines: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        normalized_line = normalize_text(line)
        if 'sortie le' not in normalized_line or 'editeur' not in normalized_line:
            continue
        if 'auteur' not in normalized_line:
            continue
        candidate_lines.append((idx, line))

    urls_in_order: list[str] = []
    for anchor in soup.find_all('a', href=True):
        href = anchor.get('href', '')
        absolute_url = ensure_absolute_url(base_url, href)
        if not absolute_url:
            continue
        if '/index.php/manga/' not in absolute_url:
            continue
        if any(excluded in absolute_url for excluded in ['/manga/news/', '/manga/critique/', '/manga/avis/', '/manga/extrait/']):
            continue
        text = clean_ws(anchor.get_text(' ', strip=True))
        normalized_text = normalize_text(text)
        if not text or normalized_text in GENERIC_ANCHOR_TEXTS or normalized_text in {'fiche detaillee'}:
            continue
        if absolute_url not in urls_in_order:
            urls_in_order.append(absolute_url)

    items: list[PlanningItem] = []
    for index, (_, line) in enumerate(candidate_lines):
        match = PLANNING_ITEM_RE.match(line)
        if not match:
            continue
        release_date = parse_french_date(match.group('release_date'))
        authors_raw = clean_ws(match.group('authors') or '')
        authors = unique_list(re.split(r'\s*/\s*|\s*,\s*', authors_raw)) if authors_raw else []
        publisher = clean_ws(match.group('publisher')) or None
        title = clean_ws(match.group('title'))
        featured = 'à ne pas manquer !' in line.lower()
        summary = None
        if index + 1 < len(candidate_lines):
            next_line_index = candidate_lines[index + 1][0]
        else:
            next_line_index = len(lines)
        for cursor in range(candidate_lines[index][0] + 1, next_line_index):
            candidate = lines[cursor]
            normalized_candidate = normalize_text(candidate)
            if not candidate:
                continue
            if normalized_candidate in {'fiche detaillee'}:
                continue
            if 'sortie le' in normalized_candidate and 'editeur' in normalized_candidate:
                break
            if normalized_candidate.startswith('mois suivant') or normalized_candidate.startswith('mois precedent'):
                continue
            if normalized_candidate.startswith('tous les editeurs'):
                continue
            summary = candidate
            break

        url = urls_in_order[index] if index < len(urls_in_order) else None
        series_slug = None
        volume_slug = None
        if url:
            parsed_path = [part for part in urlparse(url).path.split('/') if part]
            if len(parsed_path) >= 4 and parsed_path[-3] == 'manga':
                series_slug = parsed_path[-2]
                volume_slug = parsed_path[-1]

        number = extract_volume_number(title, volume_slug)
        edition_label = infer_volume_edition_label(title)
        is_special, is_one_shot = infer_volume_flags(title)
        items.append(
            PlanningItem(
                title=title,
                url=url,
                release_date=release_date,
                authors=authors,
                publisher=publisher,
                summary=summary,
                featured=featured,
                series_slug=series_slug,
                volume_slug=volume_slug,
                number=number,
                number_int=parse_volume_number_int(number),
                edition_label=edition_label,
                is_special=is_special,
                is_one_shot=is_one_shot,
            )
        )

    if not items:
        raise ParseError('Unable to parse the planning list.')

    return PlanningPage(
        section=_infer_planning_section(page_url),
        year=year,
        month=month,
        items=items,
    )



def _guess_volume_number(title: str, volume_slug: str | None) -> str | None:
    return extract_volume_number(title, volume_slug)


def _edition_item_title(anchor, container_text: str, volume_slug: str | None) -> str | None:
    candidates: list[str | None] = [
        anchor.get_text(' ', strip=True),
        anchor.get('title'),
        anchor.get('aria-label'),
    ]
    image = anchor.find('img')
    if image is not None:
        candidates.extend([image.get('alt'), image.get('title')])
    candidates.append(container_text)

    for candidate in candidates:
        cleaned = clean_ws(candidate)
        if cleaned and normalize_text(cleaned) not in GENERIC_ANCHOR_TEXTS:
            return cleaned

    number = extract_volume_number(volume_slug)
    if number:
        return f'Vol.{number}'
    return volume_slug



def _extract_publication_date_from_text(text: str) -> str | None:
    match = re.search(r'(\d{2}/\d{2}/\d{4})', text)
    if match:
        return parse_french_date(match.group(1))
    match = re.search(r'(\d{1,2}\s+[A-Za-zéûîôàèùçÉÛÎÔÀÈÙÇ]+\s+\d{4})', text)
    if match:
        return parse_french_date(match.group(1))
    return None



def _base_url_from_page(page_url: str) -> str:
    parsed = urlparse(page_url)
    return f'{parsed.scheme}://{parsed.netloc}'



def parse_series_editions_page(html: str, page_url: str, base_url: str, edition: str) -> SeriesEditionsBlock:
    soup = _soup(html)
    seen: set[str] = set()
    items: list[SeriesEditionItem] = []
    for anchor in soup.find_all('a', href=True):
        href = anchor.get('href', '')
        url = ensure_absolute_url(base_url, href)
        if not url or url in seen:
            continue
        if '/index.php/manga/' not in url:
            continue
        if any(excluded in url for excluded in ['/manga/news/', '/manga/critique/', '/manga/avis/', '/manga/extrait/']):
            continue
        parsed_path = [part for part in urlparse(url).path.split('/') if part]
        if len(parsed_path) < 4:
            continue
        series_slug = parsed_path[-2]
        volume_slug = parsed_path[-1]
        container = anchor.find_parent(['article', 'li', 'div', 'tr']) or anchor.parent
        container_text = clean_ws(container.get_text(' ', strip=True)) if container else ''
        title = _edition_item_title(anchor, container_text, volume_slug)
        if not title:
            continue
        publication_date = _extract_publication_date_from_text(container_text)
        cover_image = None
        if container:
            image = container.find('img')
            if image and image.get('src'):
                cover_image = ensure_absolute_url(base_url, image['src'])
        seen.add(url)
        number = _guess_volume_number(title, volume_slug)
        edition_label = infer_volume_edition_label(title)
        is_special, is_one_shot = infer_volume_flags(title)
        items.append(
            SeriesEditionItem(
                title=title,
                url=url,
                series_slug=series_slug,
                volume_slug=volume_slug,
                number=number,
                number_int=parse_volume_number_int(number),
                edition_label=edition_label,
                is_special=is_special,
                is_one_shot=is_one_shot,
                publication_date=publication_date,
                cover_image=cover_image,
            )
        )
    if not items:
        raise ParseError('Unable to parse the editions list.')
    items.sort(key=lambda item: (int(item.number) if item.number and item.number.isdigit() else 999999, normalize_text(item.title)))
    return SeriesEditionsBlock(edition='vf' if edition == 'vf' else 'vo', source_url=page_url, total=len(items), items=items)


def _edition_group_label(raw_heading: str) -> tuple[str, str]:
    normalized = normalize_text(raw_heading)
    if normalized.startswith('volumes de la serie') or normalized == 'volumes':
        return 'edition_originale', 'Edition originale'
    inferred = infer_volume_edition_label(raw_heading)
    if inferred != 'edition_originale':
        return inferred, clean_ws(raw_heading)
    fallback = slugify(normalized).replace('-', '_') or 'inconnue'
    return f'edition_{fallback}', clean_ws(raw_heading)


def _edition_group_explicit_status(text: str) -> tuple[str, str, str, str | None]:
    normalized = normalize_text(text)
    if re.search(r'\b(termine|terminee|complete|acheve|achevee)\b', normalized):
        return 'completed', 'explicit', 'high', 'The edition section explicitly reports a completed status.'
    if re.search(r'\b(en cours|ongoing)\b', normalized):
        return 'ongoing', 'explicit', 'high', 'The edition section explicitly reports an ongoing status.'
    return 'unknown', 'unknown', 'none', None


def _edition_group_items(container, *, base_url: str, edition_label: str) -> list[SeriesEditionItem]:
    seen: set[str] = set()
    items: list[SeriesEditionItem] = []
    for anchor in container.find_all('a', href=True):
        url = ensure_absolute_url(base_url, anchor.get('href', ''))
        if not url or url in seen or '/index.php/manga/' not in url:
            continue
        if any(excluded in url for excluded in ['/manga/news/', '/manga/critique/', '/manga/avis/', '/manga/extrait/']):
            continue
        parsed_path = [part for part in urlparse(url).path.split('/') if part]
        if len(parsed_path) < 4:
            continue
        series_slug = parsed_path[-2]
        volume_slug = parsed_path[-1]
        item_container = anchor.find_parent(['article', 'li', 'div', 'tr']) or anchor.parent
        container_text = clean_ws(item_container.get_text(' ', strip=True)) if item_container else ''
        title = _edition_item_title(anchor, container_text, volume_slug)
        if not title:
            continue
        cover_image = None
        if item_container:
            image = item_container.find('img')
            if image and image.get('src'):
                cover_image = ensure_absolute_url(base_url, image['src'])
        number = _guess_volume_number(title, volume_slug)
        is_special, is_one_shot = infer_volume_flags(title)
        seen.add(url)
        items.append(
            SeriesEditionItem(
                title=title,
                url=url,
                series_slug=series_slug,
                volume_slug=volume_slug,
                number=number,
                number_int=parse_volume_number_int(number),
                edition_label=edition_label,
                is_special=is_special,
                is_one_shot=is_one_shot,
                publication_date=_extract_publication_date_from_text(container_text),
                cover_image=cover_image,
            )
        )
    items.sort(key=lambda item: (item.number_int if item.number_int is not None else 999999, normalize_text(item.title)))
    return items


def _apply_edition_group_statuses(groups: list[SeriesEditionGroup], vf_status: EditionStatus | None) -> None:
    original = next((group for group in groups if group.edition_label == 'edition_originale'), None)
    if original and vf_status and vf_status.status:
        status, source, confidence, reason = _edition_group_explicit_status(vf_status.status)
        if status != 'unknown':
            original.status = status
            original.status_source = source
            original.status_confidence = confidence
            original.status_reason = f'Series metadata reports VF status "{vf_status.status}".'

    consolidated_labels = {'perfect', 'deluxe', 'ultimate', 'kanzenban', 'double', 'triple', 'grand_format'}
    if original and original.status == 'completed' and original.volume_count:
        for group in groups:
            if group.status != 'unknown' or group.edition_label not in consolidated_labels or not group.volume_count:
                continue
            ratio_label = None
            if original.volume_count * 2 == group.volume_count * 3:
                ratio_label = '3:2'
            elif original.volume_count == group.volume_count * 2:
                ratio_label = '2:1'
            elif original.volume_count == group.volume_count * 3:
                ratio_label = '3:1'
            expected_ratio = '2:1' if group.edition_label == 'double' else '3:1' if group.edition_label == 'triple' else None
            if ratio_label is None or (expected_ratio is not None and ratio_label != expected_ratio):
                continue
            group.status = 'completed'
            group.status_source = 'inferred'
            group.status_confidence = 'medium'
            group.status_reason = (
                f'The completed original edition has {original.volume_count} volumes and this compiled edition '
                f'has {group.volume_count}, an exact {ratio_label} ratio.'
            )

    for group in groups:
        if group.status == 'completed':
            group.total_volumes = group.volume_count


def parse_series_edition_groups_page(
    html: str,
    page_url: str,
    base_url: str,
    series_slug: str,
) -> SeriesEditionGroupsData:
    soup = _soup(html)
    lines = _lines(soup)
    vf_status, _, _, _ = _extract_vf_vo(soup, lines, _normalized_lines(lines))
    groups: list[SeriesEditionGroup] = []

    for wrapper in soup.select('.boxedTitleWrapper'):
        heading = wrapper.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        raw_heading = clean_ws(heading.get_text(' ', strip=True)) if heading else ''
        if not raw_heading:
            continue
        content = wrapper.find_next_sibling()
        if content is None or 'boxedContent' not in (content.get('class') or []):
            continue
        edition_label, display_name = _edition_group_label(raw_heading)
        items = _edition_group_items(content, base_url=base_url, edition_label=edition_label)
        if not items:
            continue
        slug_counts = Counter(item.series_slug for item in items if item.series_slug)
        dominant_slug = slug_counts.most_common(1)[0][0] if slug_counts else None
        available_numbers = sorted({item.number_int for item in items if item.number_int is not None})
        status, status_source, status_confidence, status_reason = _edition_group_explicit_status(
            content.get_text(' ', strip=True)
        )
        groups.append(
            SeriesEditionGroup(
                edition_label=edition_label,
                display_name=display_name,
                raw_heading=raw_heading,
                series_slug=dominant_slug,
                volume_count=len(items),
                highest_volume_number=max(available_numbers) if available_numbers else None,
                available_numbers=available_numbers,
                status=status,
                status_source=status_source,
                status_confidence=status_confidence,
                status_reason=status_reason,
                items=items,
            )
        )

    if not groups:
        raise ParseError('Unable to parse edition groups from the editions page.')
    _apply_edition_group_statuses(groups, vf_status)
    return SeriesEditionGroupsData(
        title=_extract_page_title(soup, lines, kind='series'),
        series_slug=series_slug,
        source_url=page_url,
        groups=groups,
    )
