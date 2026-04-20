from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse

MONTHS_FR = {
    'janvier': 1,
    'fevrier': 2,
    'février': 2,
    'mars': 3,
    'avril': 4,
    'mai': 5,
    'juin': 6,
    'juillet': 7,
    'aout': 8,
    'août': 8,
    'septembre': 9,
    'octobre': 10,
    'novembre': 11,
    'decembre': 12,
    'décembre': 12,
}


def now_utc() -> datetime:
    return datetime.now(UTC)



def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', value)
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))



def clean_ws(value: str | None) -> str:
    if value is None:
        return ''
    return ' '.join(value.replace('\xa0', ' ').split()).strip()



def normalize_text(value: str | None) -> str:
    cleaned = clean_ws(value).lower()
    cleaned = strip_accents(cleaned)
    cleaned = re.sub(r'\b(edition originale|édition originale|vol(?:ume)?\.?\s*\d+)\b', ' ', cleaned)
    cleaned = re.sub(r'[^a-z0-9]+', ' ', cleaned)
    return clean_ws(cleaned)



def parse_french_date(value: str | None) -> str | None:
    raw = clean_ws(value)
    if not raw:
        return None
    text = strip_accents(raw).lower()

    match_numeric = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', text)
    if match_numeric:
        day = int(match_numeric.group(1))
        month = int(match_numeric.group(2))
        year = int(match_numeric.group(3))
        return f'{year:04d}-{month:02d}-{day:02d}'

    match_textual = re.search(r'(\d{1,2})\s+([a-zéûôîàèùç]+)\s+(\d{4})', text)
    if match_textual:
        day = int(match_textual.group(1))
        month_name = match_textual.group(2)
        month = MONTHS_FR.get(month_name)
        year = int(match_textual.group(3))
        if month:
            return f'{year:04d}-{month:02d}-{day:02d}'
    return None



def score_match(query: str, candidate: str, *, extra: str | None = None) -> int:
    normalized_query = normalize_text(query)
    normalized_candidate = normalize_text(candidate)
    pool = normalized_candidate
    if extra:
        pool = f'{pool} {normalize_text(extra)}'
    if not normalized_query or not pool:
        return 0
    if normalized_query == normalized_candidate:
        return 100
    if normalized_query in pool:
        return 90
    ratio = SequenceMatcher(a=normalized_query, b=normalized_candidate).ratio()
    return int(round(ratio * 100))



def ensure_absolute_url(base_url: str, maybe_url: str | None) -> str | None:
    if not maybe_url:
        return None
    return urljoin(base_url.rstrip('/') + '/', maybe_url)



def is_manga_news_url(url: str, base_url: str) -> bool:
    parsed_base = urlparse(base_url)
    parsed_url = urlparse(url)
    return parsed_url.netloc == parsed_base.netloc



def make_cache_key(*parts: str) -> str:
    joined = '||'.join(clean_ws(part) for part in parts if part is not None)
    return hashlib.sha256(joined.encode('utf-8')).hexdigest()



def unique_list(items: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw_item in items:
        item = clean_ws(raw_item)
        if not item:
            continue
        lowered = item.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(item)
    return result



def slugify(value: str | None) -> str:
    normalized = normalize_text(value)
    return normalized.replace(" ", "-")


def fingerprint_data(data) -> str:
    serialized = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()
