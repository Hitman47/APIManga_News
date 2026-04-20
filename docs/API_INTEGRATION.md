# API Integration Guide

This guide is for another project, service, or AI agent that needs to consume the API without reading the whole codebase.

## Goal

This API wraps public Manga News pages and exposes normalized JSON for:
- search
- title resolution
- series details
- volume details
- related links
- editions lists
- global / series / volume news
- release planning

## Base URL

Prefer the versioned contract for all new consumers.

Choose the right base URL depending on where the caller runs:
- same Docker network: `http://manga-news-api:8000`
- host machine: `http://localhost:8017`
- remote LAN call: `http://<host-ip>:8017`

Examples below use `/v1/...`, but legacy unversioned routes still exist.

## Authentication

If `API_TOKEN` is configured, every request must include:

```http
Authorization: Bearer <token>
```

If `API_TOKEN` is empty, the API is open on the configured network.

## Common response envelope

Most endpoints return the same envelope:

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
  "fingerprint": "sha256-like-hash",
  "data": {}
}
```

## Response headers useful for clients

Responses may include:
- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`
- `X-Cache-Status: MISS|HIT|STALE`
- `Vary: Authorization, If-None-Match`
- `X-Request-ID: <request-id>`

### Conditional GET

Clients should reuse the ETag:

```http
If-None-Match: "<fingerprint>"
```

If nothing changed, the API returns `304 Not Modified` with no body.

Weak validators are also accepted by the API implementation.

## Best endpoint for automated title resolution

Use `/search/resolve` instead of `/search` when you want one best result directly.

Example:

```http
GET /v1/search/resolve?q=one%20piece&kind=series
```

Response shape:

```json
{
  "data": {
    "query": "one piece",
    "kind_requested": "series",
    "confidence": "high",
    "best": {
      "title": "One Piece",
      "url": "https://www.manga-news.com/index.php/serie/One-piece-Edition-originale",
      "kind": "series",
      "score": 98,
      "slug": "One-piece-Edition-originale"
    },
    "candidates": []
  }
}
```

### Confidence meaning
- `high`: strong match, generally safe to use directly
- `medium`: probably correct, but the caller may want to log it
- `low`: weak match, caller should confirm
- `none`: no result

## Recommended client flow

### Find and load a series
1. `GET /v1/search/resolve?q=<title>&kind=series`
2. read `data.best.slug`
3. `GET /v1/series/{slug}`
4. store the returned `ETag`
5. reuse it on future calls with `If-None-Match`

### Find and load a volume
1. `GET /v1/search/resolve?q=<title>&kind=volume`
2. read `data.best.series_slug` and `data.best.volume_slug`
3. `GET /v1/volume/{series_slug}/{volume_slug}`

### Monitor planning
1. call `GET /v1/planning?...`
2. store `fingerprint` or `ETag`
3. call again later with `If-None-Match`

## Main endpoints

### Search
- `GET /v1/search?q=...&kind=series|volume|all&mode=best|all&limit=10`
- `GET /v1/search/resolve?q=...&kind=series|volume|all&limit=10`

### Series
- `GET /v1/series/{slug}`
- `GET /v1/series/by-url?url=...`
- `GET /v1/series/{slug}/related`
- `GET /v1/series/by-url/related?url=...`
- `GET /v1/series/{slug}/editions?edition=all|vf|vo`
- `GET /v1/series/by-url/editions?url=...&edition=all|vf|vo`

Projection parameters on series endpoints:
- `blocks=editions,stats`
- `fields=title,vf.volumes`
- `include_raw_sections=true`

### Volume
- `GET /v1/volume/{series_slug}/{volume_slug}`
- `GET /v1/volume/by-url?url=...`

Projection parameters on volume endpoints:
- `blocks=release,scores`
- `fields=publication_date,isbn_ean`
- `include_raw_sections=true`

### News
- `GET /v1/news/global?limit=10`
- `GET /v1/news/series/{slug}?limit=10`
- `GET /v1/news/volume/{series_slug}/{volume_slug}?limit=10`
- `GET /v1/news/volume/by-url?url=...&limit=10`

### Planning
- `GET /v1/planning?section=manga-vf|manga-vo&year=2026&month=4&page=1&publisher=...&q=...&date_from=...&date_to=...&sort=date_asc|date_desc|title_asc|title_desc&limit=25`

### Cache admin
- `GET /v1/admin/cache/stats`
- `POST /v1/admin/cache/invalidate` with JSON filters: `cache_key`, `namespace`, `resource_url`, `expired_only`, `all_entries`

## Error handling

- `400`: invalid client parameters (unknown projection block, invalid date, invalid Manga News URL, missing slug parts, etc.)
- `404`: resource not found on Manga News
- `502`: upstream fetch failure or upstream content could not be parsed reliably
- `304`: unchanged resource when using `If-None-Match`

Clients should treat `partial=true` and `warnings` as soft issues. A common case is stale cache fallback when the upstream temporarily fails.

The upstream client automatically retries on transient network failures and `429/500/502/503/504`, so callers do not need to implement aggressive immediate retries on top of the API.

## Minimal integration prompt for another AI

Use this API as the primary manga metadata source. First call `/v1/search/resolve` with the user title. If a best result is returned, use its slug to call `/v1/series/{slug}` or `/v1/volume/{series_slug}/{volume_slug}`. Reuse the `ETag` header with `If-None-Match` to avoid reprocessing unchanged data. Log `X-Request-ID` when troubleshooting. Read the common envelope fields: `ok`, `found`, `partial`, `warnings`, `fingerprint`, and `data`. Prefer projection parameters only when the caller truly needs a reduced payload.
