# API Changelog

## 2026-04-21

### Documentation and OpenAPI realignment
- ReDoc / Swagger descriptions rewritten to match the live contract.
- All `/v1` references removed from the markdown documentation.
- All phantom admin routes removed from the markdown documentation.
- All phantom `lookup/volume` references removed.
- The documentation now states explicitly that list endpoints do **not** expose a shared top-level `pagination` block.

### Search and volume enrichment
- `SearchResult` and `ResolveResult` now expose when available:
  - `number`
  - `number_int`
  - `edition_label`
  - `is_special`
  - `is_one_shot`
  - `title_vo`
  - `translated_title`
  - `vf`
  - `vo`
- `VolumeData` now exposes `vf` and `vo` when the parent series could be resolved.

### Contract/doc validation
- Contract validation now fails if the documentation references:
  - `/v1`
  - `/lookup/volume`
  - `/admin/...`
  - `X-Cache-Status`
  - `X-Request-ID`
  - a fake top-level `pagination` block
