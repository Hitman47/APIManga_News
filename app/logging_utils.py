from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from datetime import date, datetime
from decimal import Decimal
from typing import Any

_REQUEST_ID: ContextVar[str | None] = ContextVar('request_id', default=None)


def set_request_id(request_id: str) -> Token:
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token) -> None:
    _REQUEST_ID.reset(token)


def get_request_id() -> str | None:
    return _REQUEST_ID.get()


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _normalize_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    return value


def log_event(logger: logging.Logger, level: int, event: str, *, json_mode: bool = False, **fields: Any) -> None:
    payload: dict[str, Any] = {'event': event, **{key: _normalize_value(val) for key, val in fields.items() if val is not None}}
    request_id = get_request_id()
    if request_id:
        payload.setdefault('request_id', request_id)
    if json_mode:
        logger.log(level, json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    extras = ' '.join(f'{key}={payload[key]!r}' for key in sorted(payload) if key != 'event')
    logger.log(level, f"{event}{' ' + extras if extras else ''}")
