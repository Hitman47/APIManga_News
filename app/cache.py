from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.utils import now_utc


@dataclass(slots=True)
class CacheEntry:
    key: str
    payload: dict
    fetched_at: datetime
    expires_at: datetime
    stale_until: datetime

    @property
    def is_fresh(self) -> bool:
        return now_utc() <= self.expires_at

    @property
    def is_stale_usable(self) -> bool:
        current = now_utc()
        return self.expires_at < current <= self.stale_until


class SQLiteCache:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    stale_until TEXT NOT NULL
                )
                '''
            )
            conn.commit()

    def get(self, cache_key: str) -> CacheEntry | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                'SELECT cache_key, payload, fetched_at, expires_at, stale_until FROM cache_entries WHERE cache_key = ?',
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return CacheEntry(
            key=row['cache_key'],
            payload=json.loads(row['payload']),
            fetched_at=datetime.fromisoformat(row['fetched_at']).astimezone(UTC),
            expires_at=datetime.fromisoformat(row['expires_at']).astimezone(UTC),
            stale_until=datetime.fromisoformat(row['stale_until']).astimezone(UTC),
        )

    def set(self, cache_key: str, payload: dict, ttl_seconds: int, stale_grace_seconds: int) -> CacheEntry:
        fetched_at = now_utc()
        expires_at = fetched_at.fromtimestamp(fetched_at.timestamp() + ttl_seconds, tz=UTC)
        stale_until = fetched_at.fromtimestamp(expires_at.timestamp() + stale_grace_seconds, tz=UTC)
        serialized = json.dumps(payload, ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                '''
                INSERT INTO cache_entries (cache_key, payload, fetched_at, expires_at, stale_until)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload=excluded.payload,
                    fetched_at=excluded.fetched_at,
                    expires_at=excluded.expires_at,
                    stale_until=excluded.stale_until
                ''',
                (
                    cache_key,
                    serialized,
                    fetched_at.isoformat(),
                    expires_at.isoformat(),
                    stale_until.isoformat(),
                ),
            )
            conn.commit()
        return CacheEntry(
            key=cache_key,
            payload=payload,
            fetched_at=fetched_at,
            expires_at=expires_at,
            stale_until=stale_until,
        )
