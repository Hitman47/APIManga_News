from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Iterable
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
LEADING_ARTICLES_PATTERN = re.compile(r'^(le|la|les|un|une|des|the)\s+', flags=re.IGNORECASE)
SEARCH_METADATA_SUFFIX_PATTERN = re.compile(r'\s*\(\d{4}\).*$')
SEARCH_DERIVATIVE_PHRASES = (
    'agir et penser comme',
    'philosophie de',
    'recettes cachees',
    'recettes cachées',
    'les arcanes de',
)
SEARCH_DERIVATIVE_TOKENS = {
    'roman', 'novel', 'guide', 'artbook', 'fanbook', 'databook', 'cookbook',
    'recettes', 'philosophie', 'gaiden', 'shinden', 'retsuden', 'kizuna', 'arcanes',
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


def _search_title_base(candidate: str) -> str:
    stripped = SEARCH_METADATA_SUFFIX_PATTERN.sub('', clean_ws(candidate))
    return normalize_text(stripped)


def _search_slug_base(extra: str | None) -> str:
    if not extra:
        return ''
    parsed = urlparse(extra)
    path_parts = [part for part in parsed.path.split('/') if part]
    if not path_parts:
        return ''
    return normalize_text(path_parts[-1])


def _search_rank_data(query: str, candidate: str, extra: str | None = None) -> dict[str, int | bool]:
    normalized_query = normalize_text(query)
    title_base = _search_title_base(candidate)
    slug_base = _search_slug_base(extra)
    raw_score = score_match(query, candidate, extra=extra)

    query_tokens = normalized_query.split()
    title_tokens = title_base.split()
    query_token_count = len(query_tokens)
    title_token_count = len(title_tokens)
    extra_tokens = max(0, title_token_count - query_token_count)

    exact_title = bool(normalized_query and title_base == normalized_query)
    exact_slug = bool(normalized_query and slug_base == normalized_query)
    startswith_title = bool(normalized_query and title_base.startswith(normalized_query + ' '))
    contains_title = bool(normalized_query and f' {normalized_query} ' in f' {title_base} ')

    derivative_penalty = 0
    if not exact_title and not exact_slug:
        lowered_candidate = clean_ws(candidate).lower()
        lowered_title_base = title_base.lower()
        for phrase in SEARCH_DERIVATIVE_PHRASES:
            if phrase in lowered_candidate or phrase in lowered_title_base:
                derivative_penalty += 12
        derivative_penalty += 8 * sum(1 for token in title_tokens if token in SEARCH_DERIVATIVE_TOKENS)

    rank_score = raw_score
    if exact_title:
        rank_score = max(rank_score, 100)
    elif exact_slug:
        rank_score = max(rank_score, 99)
    else:
        if startswith_title:
            rank_score += 8
        elif contains_title:
            rank_score += 4
        else:
            rank_score -= 6
        rank_score -= min(extra_tokens * 4, 24)
        rank_score -= derivative_penalty
        if query_token_count == 1 and query_tokens and query_tokens[0] in title_tokens and title_tokens and title_tokens[0] != query_tokens[0]:
            rank_score -= 6

    rank_score = max(0, min(100, int(rank_score)))
    slug_similarity = fuzz.ratio(normalized_query, slug_base) if slug_base else 0
    title_similarity = fuzz.ratio(normalized_query, title_base) if title_base else 0
    return {
        'score': rank_score,
        'raw_score': raw_score,
        'exact_title': exact_title,
        'exact_slug': exact_slug,
        'startswith_title': startswith_title,
        'contains_title': contains_title,
        'derivative_penalty': derivative_penalty,
        'extra_tokens': extra_tokens,
        'title_similarity': int(title_similarity),
        'slug_similarity': int(slug_similarity),
        'title_length': len(title_base),
    }


def search_rank_score(query: str, candidate: str, extra: str | None = None) -> int:
    return int(_search_rank_data(query, candidate, extra=extra)['score'])


def search_sort_key(query: str, candidate: str, extra: str | None = None) -> tuple[int, int, int, int, int, int, int, int, int, int]:
    data = _search_rank_data(query, candidate, extra=extra)
    return (
        int(data['score']),
        int(bool(data['exact_title'])),
        int(bool(data['exact_slug'])),
        int(bool(data['startswith_title'])),
        int(bool(data['contains_title'])),
        -int(data['derivative_penalty']),
        -int(data['extra_tokens']),
        int(data['title_similarity']),
        int(data['slug_similarity']),
        -int(data['title_length']),
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
