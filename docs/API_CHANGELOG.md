# API changelog

## 2026-04-20

- Added validated `docs/examples/` JSON payloads for developers and AI integrations.
- Added contract/doc validation tooling: `app/contract_validation.py` and `scripts/validate_contract_and_docs.py`.
- Search and resolve results now expose `title_vo` and `translated_title` when available.
- Documentation was aligned with the current unversioned routes.

## Compatibility note

The current contract is intentionally unversioned. Consumers should rely on the changelog plus the generated OpenAPI schema instead of guessing `/v1` style prefixes.

## 2026-04-20

- Fixed the detailed volume contract so `number`, `number_int`, `edition_label`, `is_special`, and `is_one_shot` are now actually present in the runtime models and responses.
- Fixed negative-cache reuse for parse errors on cached endpoints, preventing repeated identical upstream fetches while the negative cache entry is still fresh.
- Fixed debug HTML dumping on parse errors so the raised `UPSTREAM_PARSE_ERROR` detail includes the saved dump path when `DEBUG_CAPTURE_HTML_ON_ERROR=true`.
- Aligned planning and series-edition item models with the normalized volume metadata already produced by the parsers.

