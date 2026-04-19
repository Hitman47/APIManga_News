from __future__ import annotations

import hashlib
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
    normalized = re.sub(r"\b(edition originale|ed\. originale|edition|vol(?:ume)?|tome)\b", ' ', normalized)
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def slugify(value: str) -> str:
    normalized = normalize_text(value)
    return normalized.replace(' ', '-')


def score_match(query: str, candidate: str, extra: str | None = None) -> int:
    base = max(
        fuzz.WRatio(normalize_text(query), normalize_text(candidate)),
        fuzz.token_set_ratio(normalize_text(query), normalize_text(candidate)),
    )
    if extra:
        base = max(base, fuzz.WRatio(normalize_text(query), normalize_text(extra)))
    return int(base)


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
