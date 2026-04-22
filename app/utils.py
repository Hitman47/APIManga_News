from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any, Iterable
from urllib.parse import quote, urljoin, urlparse

from dateutil import parser as date_parser
from rapidfuzz import fuzz


FRENCH_MONTHS = {
    'janvier': 'January',
    'février': 'February',
    'fevrier': 'February',
    'mars': 'March',
    'avril': 'April',
    'mai': 'May',
    'juin': 'June',
    'juillet': 'July',
    'août': 'August',
    'aout': 'August',
    'septembre': 'September',
    'octobre': 'October',
    'novembre': 'November',
    'décembre': 'December',
    'decembre': 'December',
}
FRENCH_WEEKDAYS = {
    'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'
}
IGNORE_TEXTS = {
    '', 'fiche', 'news', 'critique', 'éditions', 'editions', 'images', 'personnages', 'infos+',
    'aucun commentaire... soyez le 1er !!', 'tous les volumes', 'ma note', 'rédaction', 'redaction',
    'lecteurs', 'pas lu', 'pas vu', 'volume', 'volumes', 'actus précédentes', 'actus precedentes',
}
EDITION_NOISE_PATTERN = re.compile(
    r"\b((?:tome|v(?:ol)?\.?|volume)\s*\d+|edition originale|ed\. originale|edition|collector|collectors?|"
    r"deluxe|perfect|ultimate|kanzenban|double|triple|grand format|roman|light novel|novel|tome|vol(?:ume)?)\b",
    flags=re.IGNORECASE,
)
RANKING_NOISE_PATTERN = re.compile(
    r"\b((?:tome|v(?:ol)?\.?|volume)\s*\d+|edition originale|ed\. originale|edition|collector|collectors?|"
    r"deluxe|perfect|ultimate|kanzenban|double|triple|grand format|tome|vol(?:ume)?)\b",
    flags=re.IGNORECASE,
)
LEADING_ARTICLES_PATTERN = re.compile(r'^(le|la|les|un|une|des|the)\s+', flags=re.IGNORECASE)
TITLE_METADATA_SUFFIX_PATTERN = re.compile(r'\s*\(\d{4}\).*$')

NOVEL_PATTERN = re.compile(r'\b(roman|novel|light\s*novel)\b', flags=re.IGNORECASE)
ESSAY_PATTERN = re.compile(r'\b(essai|philosophie)\b', flags=re.IGNORECASE)
COOKBOOK_PATTERN = re.compile(r'\b(recette|recettes|cook\s*book|cookbook|cuisine)\b', flags=re.IGNORECASE)
GUIDE_PATTERN = re.compile(r'\b(guide\s*book|guidebook|guide|fan\s*book|fanbook|databook)\b', flags=re.IGNORECASE)
ARTBOOK_PATTERN = re.compile(r'\b(art\s*book|artbook)\b', flags=re.IGNORECASE)
ANIME_COMICS_PATTERN = re.compile(r'\b(anime\s*comics?|anime\s*comic)\b', flags=re.IGNORECASE)
SPINOFF_PATTERN = re.compile(
    r'\b(gaiden|shinden|retsuden|kizuna|side\s*story|spin\s*off|spinoff|next\s*generations)\b',
    flags=re.IGNORECASE,
)
MANGA_TYPE_KEYWORDS = {
    'manga', 'shonen', 'shônen', 'shounen', 'shojo', 'shoujo', 'seinen', 'josei', 'kodomo',
    'manhwa', 'manhua', 'webtoon',
}
MEDIA_KIND_PRIORITY = {
    'manga': 0,
    'manga_spinoff': 1,
    'special': 2,
    'novel': 3,
    'guide': 4,
    'artbook': 5,
    'anime_comics': 6,
    'cookbook': 7,
    'essay': 8,
    'misc': 9,
}
MANGA_MEDIA_KINDS = {'manga', 'manga_spinoff'}
BOOK_MEDIA_KINDS = {'novel', 'guide', 'artbook', 'anime_comics', 'cookbook', 'essay', 'special', 'misc'}
RELATION_KIND_PRIORITY = {
    'main': 0,
    'standalone': 1,
    'related_manga': 2,
    'spinoff': 3,
    'related_book': 4,
    'unknown': 5,
}


def now_utc() -> datetime:
    return datetime.now(UTC)


def clean_ws(value: str | None) -> str:
    if value is None:
        return ''
    value = value.replace('\xa0', ' ')
    value = re.sub(r'\s+', ' ', value)
    return value.strip()


def normalize_text(value: str | None) -> str:
    cleaned = clean_ws(value).lower()
    normalized = unicodedata.normalize('NFKD', cleaned)
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = EDITION_NOISE_PATTERN.sub(' ', normalized)
    normalized = LEADING_ARTICLES_PATTERN.sub('', normalized)
    normalized = normalized.replace('&', ' and ')
    normalized = re.sub(r'\bpartie\b', 'part', normalized)
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def strip_title_metadata_suffix(value: str | None) -> str:
    cleaned = clean_ws(value)
    if not cleaned:
        return ''
    return clean_ws(TITLE_METADATA_SUFFIX_PATTERN.sub('', cleaned))


def normalize_title_for_ranking(value: str | None) -> str:
    cleaned = strip_title_metadata_suffix(value).lower()
    normalized = unicodedata.normalize('NFKD', cleaned)
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = RANKING_NOISE_PATTERN.sub(' ', normalized)
    normalized = LEADING_ARTICLES_PATTERN.sub('', normalized)
    normalized = normalized.replace('&', ' and ')
    normalized = re.sub(r'\bpartie\b', 'part', normalized)
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def slugify(value: str) -> str:
    normalized = normalize_text(value)
    return normalized.replace(' ', '-')


def extract_volume_number(*values: str | None) -> str | None:
    patterns = [
        re.compile(r'(?:^|\b)(?:tome|volume|vol(?:\.|ume)?)\s*[-.#:]?\s*([0-9]+(?:[.,][0-9]+)?)\b', flags=re.IGNORECASE),
        re.compile(r'(?:^|[-_/])vol[-_/]?([0-9]+(?:[.,][0-9]+)?)\b', flags=re.IGNORECASE),
        re.compile(r'\b([0-9]+(?:[.,][0-9]+)?)\b$'),
    ]
    for raw in values:
        candidate = clean_ws(raw)
        if not candidate:
            continue
        for pattern in patterns:
            match = pattern.search(candidate)
            if not match:
                continue
            return match.group(1).replace(',', '.')
    return None


def score_match(query: str, candidate: str, extra: str | None = None) -> int:
    normalized_query = normalize_text(query)
    normalized_candidate = normalize_text(candidate)
    base = max(
        fuzz.WRatio(normalized_query, normalized_candidate),
        fuzz.token_set_ratio(normalized_query, normalized_candidate),
        fuzz.partial_ratio(normalized_query, normalized_candidate),
    )
    if extra:
        normalized_extra = normalize_text(extra)
        base = max(base, fuzz.WRatio(normalized_query, normalized_extra), fuzz.partial_ratio(normalized_query, normalized_extra))
    return int(base)


def infer_media_kind(
    *,
    title: str | None,
    source_type: str | None = None,
    kind: str | None = None,
    is_special: bool | None = None,
    related_series_titles: Iterable[str] | None = None,
    query: str | None = None,
) -> str:
    title_blob = normalize_title_for_ranking(title)
    type_blob = normalize_title_for_ranking(source_type)
    combined = ' '.join(part for part in [title_blob, type_blob] if part)

    if ESSAY_PATTERN.search(combined):
        return 'essay'
    if COOKBOOK_PATTERN.search(combined):
        return 'cookbook'
    if GUIDE_PATTERN.search(combined):
        return 'guide'
    if ARTBOOK_PATTERN.search(combined):
        return 'artbook'
    if ANIME_COMICS_PATTERN.search(combined):
        return 'anime_comics'
    if NOVEL_PATTERN.search(combined):
        return 'novel'

    related_to_query = False
    normalized_query = normalize_title_for_ranking(query) if query else ''
    if normalized_query and related_series_titles:
        related_to_query = any(normalize_title_for_ranking(item) == normalized_query for item in related_series_titles)

    has_spinoff_hint = bool(SPINOFF_PATTERN.search(combined)) or related_to_query
    type_tokens = set(type_blob.split())
    is_manga_like = kind == 'volume' or bool(MANGA_TYPE_KEYWORDS.intersection(type_tokens)) or kind == 'series'

    if has_spinoff_hint and is_manga_like:
        return 'manga_spinoff'
    if is_manga_like:
        return 'manga'
    if is_special:
        return 'special'
    return 'misc'


def media_kind_priority(media_kind: str | None) -> int:
    return MEDIA_KIND_PRIORITY.get(media_kind or 'misc', MEDIA_KIND_PRIORITY['misc'])


def relation_kind_priority(relation_kind: str | None) -> int:
    return RELATION_KIND_PRIORITY.get(relation_kind or 'unknown', RELATION_KIND_PRIORITY['unknown'])


def extract_series_slug_from_url(url: str | None) -> str | None:
    if not url:
        return None
    path_parts = [part for part in urlparse(url).path.split('/') if part]
    if not path_parts:
        return None
    try:
        index = path_parts.index('serie')
    except ValueError:
        return None
    if len(path_parts) <= index + 1:
        return None
    return path_parts[index + 1]


def _relation_from_media_kind(media_kind: str | None, *, exact_match: bool) -> str:
    if exact_match:
        return 'main'
    if media_kind == 'manga_spinoff':
        return 'spinoff'
    if media_kind in MANGA_MEDIA_KINDS:
        return 'related_manga'
    if media_kind in BOOK_MEDIA_KINDS:
        return 'related_book'
    return 'unknown'


def infer_relation_context(
    *,
    query: str | None,
    title: str | None,
    slug: str | None = None,
    media_kind: str | None = None,
    related_series: Iterable[Any] | None = None,
) -> tuple[str | None, str | None]:
    query_norm = normalize_title_for_ranking(query)
    title_norm = normalize_title_for_ranking(title)
    slug_norm = normalize_title_for_ranking((slug or '').replace('-', ' '))
    self_slug = clean_ws(slug) or None
    exact_match = bool(query_norm) and (title_norm == query_norm or slug_norm == query_norm)
    if exact_match:
        return 'main', self_slug

    best_related_slug = None
    best_related_score = -1
    if query_norm and related_series:
        for item in related_series:
            if isinstance(item, dict):
                related_title = item.get('title')
                related_slug = item.get('slug') or extract_series_slug_from_url(item.get('url'))
            else:
                related_title = getattr(item, 'title', None)
                related_slug = getattr(item, 'slug', None) or extract_series_slug_from_url(getattr(item, 'url', None))
            related_title_norm = normalize_title_for_ranking(related_title)
            related_slug_norm = normalize_title_for_ranking((related_slug or '').replace('-', ' '))
            if not related_title_norm and not related_slug_norm:
                continue
            if related_title_norm == query_norm or related_slug_norm == query_norm:
                best_related_slug = related_slug
                best_related_score = 100
                break
            if query_norm in related_title_norm or query_norm in related_slug_norm:
                score = max(
                    fuzz.WRatio(query_norm, related_title_norm),
                    fuzz.token_set_ratio(query_norm, related_title_norm),
                    fuzz.partial_ratio(query_norm, related_title_norm),
                    fuzz.WRatio(query_norm, related_slug_norm),
                    fuzz.partial_ratio(query_norm, related_slug_norm),
                )
                if score > best_related_score:
                    best_related_score = score
                    best_related_slug = related_slug

    if best_related_slug and best_related_score >= 90:
        return _relation_from_media_kind(media_kind, exact_match=False), best_related_slug

    query_in_self = bool(query_norm) and (query_norm in title_norm or query_norm in slug_norm)
    if query_in_self:
        return _relation_from_media_kind(media_kind, exact_match=False), None

    if media_kind in MANGA_MEDIA_KINDS:
        return 'standalone', self_slug
    return 'standalone', None


def _search_result_value(result: Any, key: str) -> Any:
    if isinstance(result, dict):
        return result.get(key)
    return getattr(result, key, None)


def search_result_sort_key(query: str, result: Any, *, prefer_main_series: bool = False) -> tuple[Any, ...]:
    query_norm = normalize_title_for_ranking(query)
    query_tokens = query_norm.split()
    query_volume_number = extract_volume_number(query)

    title = _search_result_value(result, 'title') or ''
    slug = _search_result_value(result, 'slug') or ''
    kind = _search_result_value(result, 'kind') or 'series'
    source_type = _search_result_value(result, 'source_type')
    is_special = _search_result_value(result, 'is_special')
    media_kind = _search_result_value(result, 'media_kind')
    if not media_kind:
        media_kind = infer_media_kind(
            title=title,
            source_type=source_type,
            kind=kind,
            is_special=is_special,
        )

    relation_kind = _search_result_value(result, 'relation_kind')
    if not relation_kind:
        relation_kind, _ = infer_relation_context(
            query=query,
            title=title,
            slug=slug,
            media_kind=media_kind,
        )

    title_norm = normalize_title_for_ranking(title)
    slug_norm = normalize_title_for_ranking((slug or '').replace('-', ' '))
    exact_title = title_norm == query_norm and bool(query_norm)
    exact_slug = slug_norm == query_norm and bool(query_norm)
    startswith_query = title_norm.startswith(f'{query_norm} ') or title_norm == query_norm
    contains_query = bool(query_norm) and query_norm in title_norm
    token_count = len(title_norm.split())
    extra_tokens = max(token_count - len(query_tokens), 0)

    kind_priority = 0
    number_match_priority = 1
    if query_volume_number:
        kind_priority = 0 if kind == 'volume' else 1
        result_number = _search_result_value(result, 'number')
        number_match_priority = 0 if clean_ws(result_number) == clean_ws(query_volume_number) else 1
    else:
        kind_priority = 0 if kind == 'series' else 1

    special_priority = 1 if is_special else 0
    score = int(_search_result_value(result, 'score') or 0)

    relation_priority_value = relation_kind_priority(relation_kind) if prefer_main_series else 0

    return (
        0 if exact_title else 1,
        0 if exact_slug else 1,
        relation_priority_value,
        kind_priority,
        media_kind_priority(media_kind),
        0 if startswith_query else 1,
        0 if contains_query else 1,
        number_match_priority,
        special_priority,
        extra_tokens,
        -score,
        token_count,
        title_norm,
    )


def unique_list(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = clean_ws(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def parse_french_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = clean_ws(value)
    lowered = normalize_text(raw)
    if re.fullmatch(r'\d{2}/\d{2}/\d{4}', raw):
        return datetime.strptime(raw, '%d/%m/%Y').date().isoformat()

    raw = re.sub(r'^(?:' + '|'.join(FRENCH_WEEKDAYS) + r'),?\s+', '', raw, flags=re.IGNORECASE)
    text_date_match = re.search(r'(\d{1,2})\s+([A-Za-zéûîôàèùçÉÛÎÔÀÈÙÇ]+)\s+(\d{4})', raw)
    if text_date_match:
        day = int(text_date_match.group(1))
        month_name = normalize_text(text_date_match.group(2))
        year = int(text_date_match.group(3))
        month_order = [
            'janvier', 'fevrier', 'mars', 'avril', 'mai', 'juin',
            'juillet', 'aout', 'septembre', 'octobre', 'novembre', 'decembre',
        ]
        if month_name in month_order:
            month = month_order.index(month_name) + 1
            return datetime(year, month, day).date().isoformat()

    translated = raw
    for fr, en in FRENCH_MONTHS.items():
        translated = re.sub(fr, en, translated, flags=re.IGNORECASE)
    translated = translated.replace('à', 'at')
    translated = translated.replace('h', ':')
    try:
        dt = date_parser.parse(translated, fuzzy=True, dayfirst=True)
        return dt.date().isoformat()
    except (ValueError, TypeError, OverflowError):
        match = re.search(r'(\d{2}/\d{2}/\d{4})', raw)
        if match:
            return datetime.strptime(match.group(1), '%d/%m/%Y').date().isoformat()
        if lowered in {'a venir', 'à venir'}:
            return None
        return None


def make_cache_key(*parts: str) -> str:
    raw = '|'.join(clean_ws(part) for part in parts)
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return digest


def ensure_absolute_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if not href:
        return None
    return urljoin(base_url, href)


def is_manga_news_url(url: str, base_url: str) -> bool:
    base_host = urlparse(base_url).netloc
    host = urlparse(url).netloc
    return host == base_host


def encode_query(query: str) -> str:
    return quote(query, safe='')


def parse_fields_param(fields: str | None) -> list[str]:
    if not fields:
        return []
    return unique_list(part.strip() for part in fields.split(','))


def project_dict_fields(data: dict, fields: list[str]) -> dict:
    if not fields:
        return data

    projected: dict = {}
    for field in fields:
        parts = [part for part in field.split('.') if part]
        if not parts:
            continue
        current_source = data
        current_target = projected
        valid = True
        for index, part in enumerate(parts):
            if not isinstance(current_source, dict) or part not in current_source:
                valid = False
                break
            value = current_source[part]
            is_last = index == len(parts) - 1
            if is_last:
                current_target[part] = value
            else:
                if part not in current_target or not isinstance(current_target[part], dict):
                    current_target[part] = {}
                current_target = current_target[part]
                current_source = value
        if not valid:
            continue
    return projected


def flatten_for_compare(data: dict, prefix: str = '') -> dict[str, object]:
    flattened: dict[str, object] = {}
    for key, value in data.items():
        path = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict):
            flattened.update(flatten_for_compare(value, path))
        else:
            flattened[path] = value
    return flattened


def format_output_data(data: dict, output_format: str = 'nested') -> dict:
    if output_format == 'flat':
        return flatten_for_compare(data)
    return data


def fingerprint_data(data: object) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()



def parse_volume_number_int(number: str | None) -> int | None:
    if number is None:
        return None
    try:
        if '.' in number:
            value = float(number)
            return int(value) if value.is_integer() else None
        return int(number)
    except (TypeError, ValueError):
        return None


SPECIAL_VOLUME_KEYWORDS = {
    'guidebook', 'fan book', 'fanbook', 'artbook', 'art book', 'roman', 'novel', 'light novel',
    'databook', 'anime comics', 'anime comic', 'special', 'hors serie', 'hors-série', 'spinoff',
    'spin off', 'spécial', 'special edition', 'collector', 'deluxe'
}

SPECIAL_VOLUME_PATTERNS = [
    re.compile(r'\b(one\s*shot|one-shot|roman|novel|light\s*novel|guide\s*book|guidebook|fan\s*book|fanbook|art\s*book|artbook|databook|anime\s*comics?|special|collector|deluxe|hors[-\s]?s[eé]rie|sp[ée]cial|spinoff|spin\s*off)\b', flags=re.IGNORECASE),
]

EDITION_LABEL_PATTERNS = [
    ('edition_originale', re.compile(r'\b(edition originale|ed\.? originale)\b', flags=re.IGNORECASE)),
    ('collector', re.compile(r'\bcollector\b', flags=re.IGNORECASE)),
    ('deluxe', re.compile(r'\bdeluxe\b', flags=re.IGNORECASE)),
    ('perfect', re.compile(r'\bperfect\b', flags=re.IGNORECASE)),
    ('ultimate', re.compile(r'\bultimate\b', flags=re.IGNORECASE)),
    ('kanzenban', re.compile(r'\bkanzenban\b', flags=re.IGNORECASE)),
    ('double', re.compile(r'\bdouble\b', flags=re.IGNORECASE)),
    ('triple', re.compile(r'\btriple\b', flags=re.IGNORECASE)),
    ('grand_format', re.compile(r'\bgrand format\b', flags=re.IGNORECASE)),
]


def infer_volume_edition_label(*values: str | None) -> str | None:
    for raw in values:
        candidate = clean_ws(raw)
        if not candidate:
            continue
        for label, pattern in EDITION_LABEL_PATTERNS:
            if pattern.search(candidate):
                return label
    return 'edition_originale'


def infer_volume_flags(*values: str | None) -> tuple[bool, bool]:
    texts = [clean_ws(value).lower() for value in values if clean_ws(value)]
    joined = ' '.join(texts)
    is_special = any(pattern.search(joined) for pattern in SPECIAL_VOLUME_PATTERNS)
    is_one_shot = 'one shot' in joined or 'one-shot' in joined
    return is_special, is_one_shot
