from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.contract_validation import run_all


def main() -> int:
    errors = run_all(ROOT)
    if errors:
        print('Contract / docs validation failed:')
        for error in errors:
            print(f'- {error}')
        return 1
    print('Contract / docs validation OK.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
