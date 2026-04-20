from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    ApiErrorResponse,
    HealthResponse,
    NewsResponse,
    PlanningResponse,
    ResolveResponse,
    SearchResponse,
    SeriesEditionsResponse,
    SeriesRelatedResponse,
    SeriesResponse,
    VolumeResponse,
)

EXPECTED_PATHS = {
    '/health',
    '/search',
    '/search/resolve',
    '/series/{slug}',
    '/series/by-url',
    '/series/{slug}/related',
    '/series/by-url/related',
    '/series/{slug}/editions',
    '/series/by-url/editions',
    '/volume/{series_slug}/{volume_slug}',
    '/volume/by-url',
    '/news/global',
    '/news/series/{slug}',
    '/news/volume/{series_slug}/{volume_slug}',
    '/news/volume/by-url',
    '/planning',
}

EXPECTED_TAGS = {'health', 'search', 'series', 'volume', 'news', 'planning'}

EXAMPLE_MODEL_MAP = {
    'health_ok.json': HealthResponse,
    'search_series_one_piece.json': SearchResponse,
    'search_resolve_series_one_piece.json': ResolveResponse,
    'series_one_piece.json': SeriesResponse,
    'series_related_one_piece.json': SeriesRelatedResponse,
    'series_editions_one_piece_all.json': SeriesEditionsResponse,
    'volume_one_piece_110.json': VolumeResponse,
    'news_global_one_piece_sample.json': NewsResponse,
    'planning_manga_vf_april_2026.json': PlanningResponse,
    'error_resource_not_found.json': ApiErrorResponse,
    'error_upstream_parse.json': ApiErrorResponse,
}

LINK_RE = re.compile(r'\[[^\]]+\]\(([^)]+)\)')


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_openapi_schema() -> dict[str, Any]:
    with TestClient(app) as client:
        response = client.get('/openapi.json')
    response.raise_for_status()
    return response.json()


def validate_openapi_schema(schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    paths = set(schema.get('paths', {}))
    missing_paths = sorted(EXPECTED_PATHS - paths)
    if missing_paths:
        errors.append(f'Missing OpenAPI paths: {", ".join(missing_paths)}')
    if any(re.match(r'^/v\d+/', path) for path in paths):
        errors.append('Unexpected version-prefixed routes present in OpenAPI schema.')
    tags = {tag['name'] for tag in schema.get('tags', []) if 'name' in tag}
    missing_tags = sorted(EXPECTED_TAGS - tags)
    if missing_tags:
        errors.append(f'Missing OpenAPI tags: {", ".join(missing_tags)}')
    for route in ('/search/resolve', '/series/{slug}', '/volume/{series_slug}/{volume_slug}', '/planning'):
        try:
            get_op = schema['paths'][route]['get']
        except KeyError:
            continue
        if not get_op.get('summary'):
            errors.append(f'Missing summary for {route}')
        if not get_op.get('description'):
            errors.append(f'Missing description for {route}')
    return errors


def validate_example_files(root: Path | None = None) -> list[str]:
    base = (root or repo_root()) / 'docs' / 'examples'
    errors: list[str] = []
    for filename, model in EXAMPLE_MODEL_MAP.items():
        path = base / filename
        if not path.exists():
            errors.append(f'Missing example file: {path}')
            continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            errors.append(f'Invalid JSON in {path}: {exc}')
            continue
        try:
            model.model_validate(payload)
        except Exception as exc:  # pragma: no cover - exact pydantic message varies
            errors.append(f'Invalid payload for {path.name}: {exc}')
    return errors


def find_broken_markdown_links(root: Path | None = None) -> list[str]:
    base = root or repo_root()
    docs = [base / 'README.md', *sorted((base / 'docs').glob('*.md'))]
    errors: list[str] = []
    for doc in docs:
        if not doc.exists():
            errors.append(f'Missing documentation file: {doc}')
            continue
        text = doc.read_text(encoding='utf-8')
        for target in LINK_RE.findall(text):
            if target.startswith(('http://', 'https://', 'mailto:', '#')):
                continue
            link_target = target.split('#', 1)[0]
            if not link_target:
                continue
            resolved = (doc.parent / link_target).resolve()
            if not resolved.exists():
                errors.append(f'Broken link in {doc.relative_to(base)} -> {target}')
    return errors


def run_all(root: Path | None = None) -> list[str]:
    base = root or repo_root()
    errors: list[str] = []
    schema = load_openapi_schema()
    errors.extend(validate_openapi_schema(schema))
    errors.extend(validate_example_files(base))
    errors.extend(find_broken_markdown_links(base))
    return errors
