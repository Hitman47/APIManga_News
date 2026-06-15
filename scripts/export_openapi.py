from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.contract_validation import load_openapi_schema


def main() -> int:
    output_path = ROOT_DIR / 'openapi.json'
    output_path.write_text(
        json.dumps(load_openapi_schema(), ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    print(output_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
