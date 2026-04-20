# API changelog

## 2026-04-20

- Added validated `docs/examples/` JSON payloads for developers and AI integrations.
- Added contract/doc validation tooling: `app/contract_validation.py` and `scripts/validate_contract_and_docs.py`.
- Search and resolve results now expose `title_vo` and `translated_title` when available.
- Documentation was aligned with the current unversioned routes.

## Compatibility note

The current contract is intentionally unversioned. Consumers should rely on the changelog plus the generated OpenAPI schema instead of guessing `/v1` style prefixes.
