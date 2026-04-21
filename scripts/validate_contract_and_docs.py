from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.contract_validation import (
    find_broken_markdown_links,
    find_invalid_api_references,
    load_openapi_schema,
    validate_example_files,
    validate_openapi_schema,
)


def main() -> int:
    errors: list[str] = []
    schema = load_openapi_schema()
    errors.extend(validate_openapi_schema(schema))
    errors.extend(find_broken_markdown_links(ROOT_DIR))
    errors.extend(find_invalid_api_references(ROOT_DIR, schema))
    errors.extend(validate_example_files(ROOT_DIR))
    if errors:
        print('Contract/doc validation failed:')
        for error in errors:
            print(f'- {error}')
        return 1
    print('Contract/doc validation passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
