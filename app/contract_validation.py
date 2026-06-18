from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.models import (
    ApiErrorResponse,
    HealthResponse,
    NewsResponse,
    PlanningResponse,
    ReleaseStateResponse,
    ResolveResponse,
    SearchResponse,
    SeriesEditionsResponse,
    SeriesRelatedResponse,
    SeriesResponse,
    VolumeResponse,
)

ROOT_DIR = Path(__file__).resolve().parents[1]

EXAMPLE_MODEL_MAP = {
    'health.json': HealthResponse,
    'search_response_dogs_volume.json': SearchResponse,
    'resolve_response_one_piece.json': ResolveResponse,
    'series_one_piece.json': SeriesResponse,
    'volume_one_piece_91.json': VolumeResponse,
    'news_global_one_piece_sample.json': NewsResponse,
    'planning_example.json': PlanningResponse,
    'series_related_one_piece.json': SeriesRelatedResponse,
    'series_editions_one_piece.json': SeriesEditionsResponse,
    'release_state_one_piece.json': ReleaseStateResponse,
    'error_resource_not_found.json': ApiErrorResponse,
    'error_upstream_parse.json': ApiErrorResponse,
}

MARKDOWN_LINK_RE = re.compile(r'\[[^\]]+\]\(([^)]+)\)')
METHOD_ROUTE_RE = re.compile(r'\b(?:GET|POST|PUT|DELETE|PATCH)\s+(/[^\s`]+)')
RUNTIME_URL_RE = re.compile(r'https?://(?:localhost|127\.0\.0\.1|manga-news-api|<host>|<host-ip>)(?::\d+)?(/[^\s)"`\']*)')


def load_openapi_schema() -> dict[str, Any]:
    from app.main import app

    return app.openapi()


def validate_openapi_schema(schema: dict[str, Any] | None = None) -> list[str]:
    schema = schema or load_openapi_schema()
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ['OpenAPI schema is not a dictionary.']
    if 'openapi' not in schema:
        errors.append('Missing top-level "openapi" key.')
    paths = schema.get('paths')
    if not isinstance(paths, dict):
        errors.append('Missing top-level "paths" dictionary.')
        return errors

    required_paths = {
        '/health',
        '/search',
        '/search/resolve',
        '/series/{slug}',
        '/series/by-url',
        '/series/{slug}/related',
        '/series/by-url/related',
        '/series/{slug}/editions',
        '/series/{slug}/release-state',
        '/series/by-url/editions',
        '/volume/{series_slug}/{volume_slug}',
        '/volume/by-url',
        '/news/global',
        '/news/series/{slug}',
        '/news/volume/{series_slug}/{volume_slug}',
        '/news/volume/by-url',
        '/planning',
    }
    missing = sorted(required_paths - set(paths))
    if missing:
        errors.append(f'Missing required OpenAPI paths: {", ".join(missing)}')
    versioned = sorted(path for path in paths if re.match(r'^/v\d+/', path))
    if versioned:
        errors.append(f'Unexpected versioned API paths found: {", ".join(versioned)}')

    info = schema.get('info') or {}
    if not info.get('description'):
        errors.append('OpenAPI info.description is empty.')

    for path in ['/search', '/search/resolve', '/series/{slug}', '/series/{slug}/release-state', '/volume/{series_slug}/{volume_slug}', '/planning']:
        operation = (paths.get(path) or {}).get('get') or {}
        if not operation.get('summary'):
            errors.append(f'OpenAPI summary missing for {path}')
        if not operation.get('description'):
            errors.append(f'OpenAPI description missing for {path}')
    return errors


def _iter_markdown_files(root_dir: Path) -> list[Path]:
    files = [root_dir / 'README.md']
    docs_dir = root_dir / 'docs'
    if docs_dir.exists():
        files.extend(sorted(docs_dir.rglob('*.md')))
    return [path for path in files if path.exists()]


def find_broken_markdown_links(root_dir: str | Path | None = None) -> list[str]:
    base = Path(root_dir) if root_dir else ROOT_DIR
    errors: list[str] = []
    for markdown_file in _iter_markdown_files(base):
        content = markdown_file.read_text(encoding='utf-8')
        for raw_target in MARKDOWN_LINK_RE.findall(content):
            target = raw_target.strip()
            if not target or target.startswith('#'):
                continue
            if '://' in target or target.startswith('mailto:'):
                continue
            clean_target = target.split('#', 1)[0].split('?', 1)[0]
            if not clean_target:
                continue
            candidate = (markdown_file.parent / clean_target).resolve()
            if not candidate.exists():
                rel = candidate.relative_to(base) if str(candidate).startswith(str(base.resolve())) else candidate
                errors.append(f'{markdown_file.relative_to(base)} -> {target} (missing: {rel})')
    return errors


def _path_matches_template(path: str, template: str) -> bool:
    path_parts = [part for part in path.split('/') if part]
    template_parts = [part for part in template.split('/') if part]
    if len(path_parts) != len(template_parts):
        return False
    for actual, templ in zip(path_parts, template_parts):
        if templ.startswith('{') and templ.endswith('}'):
            continue
        if actual != templ:
            return False
    return True


def _is_valid_runtime_path(path: str, templates: set[str]) -> bool:
    if path in {'/docs', '/redoc', '/openapi.json'}:
        return True
    return any(_path_matches_template(path, template) for template in templates)


def find_invalid_api_references(root_dir: str | Path | None = None, schema: dict[str, Any] | None = None) -> list[str]:
    base = Path(root_dir) if root_dir else ROOT_DIR
    schema = schema or load_openapi_schema()
    templates = set((schema.get('paths') or {}).keys())
    errors: list[str] = []
    for markdown_file in _iter_markdown_files(base):
        content = markdown_file.read_text(encoding='utf-8')
        refs = []
        refs.extend(METHOD_ROUTE_RE.findall(content))
        refs.extend(RUNTIME_URL_RE.findall(content))
        for path in refs:
            parsed_path = urlparse(path).path if '://' in path else path
            parsed_path = parsed_path.rstrip('`').split('?', 1)[0].split('#', 1)[0]
            if '...' in parsed_path:
                continue
            if not parsed_path.startswith('/'):
                continue
            if not _is_valid_runtime_path(parsed_path, templates):
                errors.append(f'{markdown_file.relative_to(base)} references unknown runtime path: {parsed_path}')
    return sorted(set(errors))


def validate_example_files(root_dir: str | Path | None = None) -> list[str]:
    base = Path(root_dir) if root_dir else ROOT_DIR
    examples_dir = base / 'docs' / 'examples'
    errors: list[str] = []
    if not examples_dir.exists():
        return ['Missing docs/examples directory.']
    for name, model in EXAMPLE_MODEL_MAP.items():
        path = examples_dir / name
        if not path.exists():
            errors.append(f'Missing example file: docs/examples/{name}')
            continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            errors.append(f'Invalid JSON in docs/examples/{name}: {exc}')
            continue
        try:
            model.model_validate(payload)
        except Exception as exc:  # pragma: no cover - pydantic error details vary
            errors.append(f'Example docs/examples/{name} does not match {model.__name__}: {exc}')
    return errors
