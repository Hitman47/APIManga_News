# API Integration Guide

This guide is meant for a developer, another service, or an AI agent that needs to use the API without reading the whole codebase.

## 1. Base URL

Use one of these depending on where the caller runs:
- Docker network: `http://manga-news-api:8000`
- Host machine: `http://localhost:8017`
- LAN caller: `http://<host-ip>:8017`

There is no `/v1` prefix. The current public contract is unversioned.

## 2. Authentication

If `API_TOKEN` is configured, every request must send:

```http
Authorization: Bearer <token>
```

If `API_TOKEN` is empty, the API is open.

## 3. Common envelope

Most responses use this envelope:

```json
{
  "schema_version": "1.0",
  "ok": true,
  "found": true,
  "source": "manga_news",
  "source_url": "https://www.manga-news.com/...",
  "cached": false,
  "fetched_at": "2026-04-20T12:00:00+00:00",
  "cache_expires_at": "2026-04-21T12:00:00+00:00",
  "partial": false,
  "warnings": [],
  "fingerprint": "...",
  "data": {}
}
```

## 4. Key endpoints

### Search

```http
GET /search?q=one%20piece&kind=series&mode=all&limit=5
```

`kind` can be `series`, `volume`, or `all`.
`mode` can be `best` or `all`.

Each search result may expose:
- `title`
- `title_vo`
- `translated_title`
- `url`
- `kind`
- `score`
- `slug` or `series_slug` / `volume_slug`

### Resolve the best result directly

```http
GET /search/resolve?q=one%20piece%20tome%2091&kind=volume&limit=10
```

### Series details

```http
GET /series/{slug}
GET /series/by-url?url=...
```

Useful fields include:
- `title`
- `title_vo`
- `translated_title`
- `summary`
- `authors_story`
- `authors_art`
- `publisher_fr`
- `publisher_vo`
- `vf` / `vo`
- `stats`
- `related`

### Volume details

```http
GET /volume/{series_slug}/{volume_slug}
GET /volume/by-url?url=...
```

Useful fields include:
- `title`
- `series_title`
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`
- `title_vo`
- `translated_title`
- `publication_date`
- `isbn_ean`
- `price_code`
- `editorial_score`
- `reader_score`

### Related links

```http
GET /series/{slug}/related
GET /series/by-url/related?url=...
```

### Series editions

```http
GET /series/{slug}/editions?edition=all
GET /series/by-url/editions?url=...&edition=vf
```

### News

```http
GET /news/global?limit=10
GET /news/series/{slug}?limit=10
GET /news/volume/{series_slug}/{volume_slug}?limit=10
GET /news/volume/by-url?url=...&limit=10
```

### Planning

```http
GET /planning?section=manga-vf&year=2026&month=4&publisher=Glénat&limit=10
```

Supported local filters:
- `publisher`
- `q`
- `date_from`
- `date_to`
- `sort` (`date_asc`, `date_desc`, `title_asc`, `title_desc`)
- `limit`

## 5. ETag and client caching

Responses include:
- `ETag`
- `X-Data-Fingerprint`

Send the ETag back with `If-None-Match` to get `304 Not Modified` when possible.

## 6. Projection parameters on details endpoints

Series and volume detail endpoints support:
- `blocks`
- `fields`
- `include_raw_sections`

Example:

```http
GET /series/One-piece-Edition-originale?blocks=editions,stats&fields=title,vf.volumes
```

## 7. Error model

Current validation/documentation examples use this error shape:

```json
{
  "code": "UPSTREAM_PARSE_ERROR",
  "detail": "Unable to parse the requested Manga News page."
}
```

The exact runtime handlers may still map framework-level auth errors differently, so consumers should always check the HTTP status code first.

## 8. Best integration flow

### Find a series reliably
1. Call `/search/resolve?q=<title>&kind=series`
2. Read `data.best.slug`
3. Call `/series/{slug}`

### Find a specific volume
1. Call `/search/resolve?q=<series name> tome <number>&kind=volume`
2. Read `series_slug` and `volume_slug`
3. Call `/volume/{series_slug}/{volume_slug}`

## 9. Documentation assets

Use these files together:
- `README.md` for quickstart
- `docs/API_CHANGELOG.md` for contract evolution
- `docs/examples/*.json` for sample payloads
- `/openapi.json` for generated schema

## 10. Local validation

```bash
python scripts/validate_contract_and_docs.py
pytest
```

## 11. Parse errors, debug HTML, and negative cache

When `DEBUG_CAPTURE_HTML_ON_ERROR=true`, a parsing failure on a cached endpoint can save the raw upstream HTML and a sidecar JSON metadata file in `DEBUG_HTML_DUMP_DIR`. The raised `UPSTREAM_PARSE_ERROR` detail then includes `Debug HTML saved to ...`.

When `NEGATIVE_CACHE_ENABLED=true`, parse failures and not-found responses are cached briefly using `NEGATIVE_CACHE_TTL_SECONDS`. This prevents repeated identical upstream fetches while the upstream page stays broken or absent.
