from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.models import ApiErrorResponse, HealthResponse, PlanningResponse, ResolveResponse, SearchResponse, SeriesEditionsResponse, SeriesRelatedResponse, SeriesResponse, VolumeResponse

ROOT_DIR = Path(__file__).resolve().parents[1]

EXAMPLE_MODEL_MAP = {
    'search_response_one_piece.json': SearchResponse,
    'resolve_response_one_piece.json': ResolveResponse,
    'series_one_piece.json': SeriesResponse,
    'volume_one_piece_91.json': VolumeResponse,
    'planning_example.json': PlanningResponse,
    'series_related_one_piece.json': SeriesRelatedResponse,
    'series_editions_one_piece.json': SeriesEditionsResponse,
    'error_upstream_parse.json': ApiErrorResponse,
    'health.json': HealthResponse,
}

MARKDOWN_LINK_RE = re.compile(r'\[[^\]]+\]\(([^)]+)\)')


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
    if 'paths' not in schema or not isinstance(schema['paths'], dict):
        errors.append('Missing top-level "paths" dictionary.')
        return errors
    required_paths = {
        '/health',
        '/search',
        '/search/resolve',
        '/series/{slug}',
        '/series/{slug}/related',
        '/series/{slug}/editions',
        '/volume/{series_slug}/{volume_slug}',
        '/news/global',
        '/planning',
    }
    missing = sorted(required_paths - set(schema['paths']))
    if missing:
        errors.append(f'Missing required OpenAPI paths: {", ".join(missing)}')
    versioned = sorted(path for path in schema['paths'] if re.match(r'^/v\d+/', path))
    if versioned:
        errors.append(f'Unexpected versioned API paths found: {", ".join(versioned)}')
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
                rel = candidate.relative_to(base) if candidate.is_absolute() and str(candidate).startswith(str(base.resolve())) else candidate
                errors.append(f'{markdown_file.relative_to(base)} -> {target} (missing: {rel})')
    return errors


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
