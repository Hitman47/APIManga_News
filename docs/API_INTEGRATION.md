# API Integration Guide

This document is written for an external project or another AI agent that needs to integrate with this API without reading the whole codebase.

## Goal

This API wraps public pages from Manga News and exposes normalized JSON for:
- search
- series details
- volume details
- related links
- editions lists
- global/series/volume news
- release planning

## Base URL

Choose the right base URL depending on where the caller runs:
- same Docker network: `http://manga-news-api:8000`
- host machine: `http://localhost:8017`
- remote LAN call: `http://<host-ip>:8017`

## Authentication

If `API_TOKEN` is configured, every request must include:

```http
Authorization: Bearer <token>
```

If `API_TOKEN` is empty, the API is open on the configured network.

## Response envelope

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

## Caching contract for clients

Responses include:
- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`

Clients should reuse the ETag:

```http
If-None-Match: "<fingerprint>"
```

If nothing changed, the API returns `304 Not Modified` with no body.

## Best endpoint for automated title resolution

Use `/search/resolve` instead of `/search` when you want one best result directly.

Example:

```http
GET /search/resolve?q=one%20piece&kind=series
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
1. `GET /search/resolve?q=<title>&kind=series`
2. read `data.best.slug`
3. `GET /series/{slug}`
4. reuse the ETag on future calls

### Find and load a volume
1. `GET /search/resolve?q=<title>&kind=volume`
2. read `data.best.series_slug` and `data.best.volume_slug`
3. `GET /volume/{series_slug}/{volume_slug}`

### Monitor planning
1. call `GET /planning?...`
2. store `fingerprint` or `ETag`
3. call again later with `If-None-Match`

## Main endpoints

### Search
- `GET /search?q=...&kind=series|volume|all&mode=best|all&limit=10`
- `GET /search/resolve?q=...&kind=series|volume|all&limit=10`

### Series
- `GET /series/{slug}`
- `GET /series/by-url?url=...`
- `GET /series/{slug}/related`
- `GET /series/{slug}/editions?edition=all|vf|vo`

Projection parameters on series endpoints:
- `blocks=editions,stats`
- `fields=title,vf.volumes`
- `include_raw_sections=true`

### Volume
- `GET /volume/{series_slug}/{volume_slug}`
- `GET /volume/by-url?url=...`

Projection parameters on volume endpoints:
- `blocks=release,scores`
- `fields=publication_date,isbn_ean`
- `include_raw_sections=true`

### News
- `GET /news/global?limit=10`
- `GET /news/series/{slug}?limit=10`
- `GET /news/volume/{series_slug}/{volume_slug}?limit=10`
- `GET /news/volume/by-url?url=...&limit=10`

### Planning
- `GET /planning?section=manga-vf|manga-vo&year=2026&month=4&page=1&publisher=...&q=...&date_from=...&date_to=...&sort=date_asc|date_desc|title_asc|title_desc&limit=25`

## Error handling

- `404`: resource not found on Manga News
- `502`: upstream fetch or parse error
- `304`: unchanged resource when using `If-None-Match`

Clients should treat `partial=true` and `warnings` as non-fatal soft issues.

## Minimal integration prompt for another AI

Use this API as the primary manga metadata source. First call `/search/resolve` with the user title. If a best result is returned, use its slug to call `/series/{slug}` or `/volume/{series_slug}/{volume_slug}`. Reuse the `ETag` header with `If-None-Match` to avoid refetching unchanged data. Read the common response envelope fields: `ok`, `found`, `partial`, `warnings`, `fingerprint`, and `data`.


## Search result title variants

Both `/search` and `/search/resolve` can expose three title-related fields on each candidate or best match:
- `title`: the label found directly in the search result
- `title_vo`: original-language title parsed from the detailed series or volume page
- `translated_title`: translated title parsed from the detailed series or volume page

This matters for clients that match against Japanese titles, French catalogue names, or translated English labels.

Example candidate:

```json
{
  "title": "Black Night Parade",
  "title_vo": "ブラックナイトパレード",
  "translated_title": "Black Night Parade",
  "url": "https://www.manga-news.com/index.php/serie/Black-Night-Parade",
  "kind": "series",
  "score": 94,
  "slug": "Black-Night-Parade",
  "series_slug": "Black-Night-Parade",
  "volume_slug": null
}
```

Recommended matching strategy for another service or an AI agent:
1. Prefer `slug` or `(series_slug, volume_slug)` as stable identifiers.
2. Display `title` to users by default.
3. Use `title_vo` and `translated_title` as secondary search and disambiguation fields.
4. If multiple candidates are close, show all three title fields before picking a winner.
