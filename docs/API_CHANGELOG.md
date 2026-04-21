# API Changelog

## 2026-04-21 — VF/VO counters robustness and cache refresh

- Series parsing now reads VF/VO counters directly from the Manga-News `#numberblock` markup when available, with line-based fallback.
- `search`, `search/resolve`, `series` and `volume` now use a versioned cache-key schema so stale cached payloads created before VF/VO enrichment are not reused after deployment.
- Search and detailed payload docs were realigned with the actual runtime contract.

## Current compatibility note

The current public contract is **not versioned**.

Do not invent `/v1`.
Do not assume admin routes.
Start from `/openapi.json`.
