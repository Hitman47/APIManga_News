from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.utils import now_utc


@dataclass(slots=True)
class CacheEntry:
    key: str
    payload: dict
    fetched_at: datetime
    expires_at: datetime
    stale_until: datetime
    namespace: str | None = None
    resource_url: str | None = None

    @property
    def is_fresh(self) -> bool:
        return now_utc() <= self.expires_at

    @property
    def is_stale_usable(self) -> bool:
        current = now_utc()
        return self.expires_at < current <= self.stale_until


@dataclass(slots=True)
class WatchSnapshot:
    watch_key: str
    scope_hash: str
    payload: dict[str, Any]
    fingerprint: str
    updated_at: datetime


class SQLiteCache:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, sql_type: str) -> None:
        existing_columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}
        if column not in existing_columns:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {sql_type}')

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
            self._ensure_column(conn, 'cache_entries', 'namespace', 'TEXT')
            self._ensure_column(conn, 'cache_entries', 'resource_url', 'TEXT')
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS watch_snapshots (
                    watch_key TEXT PRIMARY KEY,
                    scope_hash TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                '''
            )
            conn.commit()

    def get(self, cache_key: str) -> CacheEntry | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                'SELECT cache_key, payload, fetched_at, expires_at, stale_until, namespace, resource_url FROM cache_entries WHERE cache_key = ?',
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
            namespace=row['namespace'],
            resource_url=row['resource_url'],
        )

    def set(
        self,
        cache_key: str,
        payload: dict,
        ttl_seconds: int,
        stale_grace_seconds: int,
        *,
        namespace: str | None = None,
        resource_url: str | None = None,
    ) -> CacheEntry:
        fetched_at = now_utc()
        expires_at = fetched_at.fromtimestamp(fetched_at.timestamp() + ttl_seconds, tz=UTC)
        stale_until = fetched_at.fromtimestamp(expires_at.timestamp() + stale_grace_seconds, tz=UTC)
        serialized = json.dumps(payload, ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                '''
                INSERT INTO cache_entries (cache_key, payload, fetched_at, expires_at, stale_until, namespace, resource_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload=excluded.payload,
                    fetched_at=excluded.fetched_at,
                    expires_at=excluded.expires_at,
                    stale_until=excluded.stale_until,
                    namespace=excluded.namespace,
                    resource_url=excluded.resource_url
                ''',
                (
                    cache_key,
                    serialized,
                    fetched_at.isoformat(),
                    expires_at.isoformat(),
                    stale_until.isoformat(),
                    namespace,
                    resource_url,
                ),
            )
            conn.commit()
        return CacheEntry(
            key=cache_key,
            payload=payload,
            fetched_at=fetched_at,
            expires_at=expires_at,
            stale_until=stale_until,
            namespace=namespace,
            resource_url=resource_url,
        )

    def stats(self) -> dict[str, Any]:
        now = now_utc()
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                'SELECT cache_key, fetched_at, expires_at, stale_until, namespace, resource_url FROM cache_entries'
            ).fetchall()
            watch_rows = conn.execute('SELECT watch_key, updated_at FROM watch_snapshots').fetchall()

        by_namespace: dict[str, dict[str, int]] = {}
        totals = {'entries': 0, 'fresh': 0, 'stale_usable': 0, 'expired': 0}
        oldest_fetched_at: str | None = None
        newest_fetched_at: str | None = None

        for row in rows:
            namespace = row['namespace'] or 'unknown'
            namespace_stats = by_namespace.setdefault(namespace, {'entries': 0, 'fresh': 0, 'stale_usable': 0, 'expired': 0})
            namespace_stats['entries'] += 1
            totals['entries'] += 1
            fetched_at = datetime.fromisoformat(row['fetched_at']).astimezone(UTC)
            expires_at = datetime.fromisoformat(row['expires_at']).astimezone(UTC)
            stale_until = datetime.fromisoformat(row['stale_until']).astimezone(UTC)
            state_key = 'expired'
            if now <= expires_at:
                state_key = 'fresh'
            elif now <= stale_until:
                state_key = 'stale_usable'
            namespace_stats[state_key] += 1
            totals[state_key] += 1
            if oldest_fetched_at is None or fetched_at.isoformat() < oldest_fetched_at:
                oldest_fetched_at = fetched_at.isoformat()
            if newest_fetched_at is None or fetched_at.isoformat() > newest_fetched_at:
                newest_fetched_at = fetched_at.isoformat()

        return {
            'db_path': str(self.db_path),
            'totals': totals,
            'by_namespace': by_namespace,
            'watch_snapshots': {
                'entries': len(watch_rows),
                'oldest_updated_at': min((row['updated_at'] for row in watch_rows), default=None),
                'newest_updated_at': max((row['updated_at'] for row in watch_rows), default=None),
            },
            'oldest_fetched_at': oldest_fetched_at,
            'newest_fetched_at': newest_fetched_at,
        }

    def invalidate(
        self,
        *,
        cache_key: str | None = None,
        namespace: str | None = None,
        resource_url: str | None = None,
        expired_only: bool = False,
        all_entries: bool = False,
    ) -> int:
        if not any([cache_key, namespace, resource_url, expired_only, all_entries]):
            return 0
        clauses: list[str] = []
        params: list[Any] = []
        if cache_key:
            clauses.append('cache_key = ?')
            params.append(cache_key)
        if namespace:
            clauses.append('namespace = ?')
            params.append(namespace)
        if resource_url:
            clauses.append('resource_url = ?')
            params.append(resource_url)
        if expired_only:
            clauses.append('stale_until < ?')
            params.append(now_utc().isoformat())
        where_clause = ''
        if not all_entries or clauses:
            where_clause = ' WHERE ' + (' AND '.join(clauses) if clauses else '1 = 0')
        with self._lock, self._connect() as conn:
            cursor = conn.execute(f'DELETE FROM cache_entries{where_clause}', tuple(params))
            conn.commit()
            return int(cursor.rowcount or 0)

    def get_watch_snapshot(self, watch_key: str) -> WatchSnapshot | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                'SELECT watch_key, scope_hash, payload, fingerprint, updated_at FROM watch_snapshots WHERE watch_key = ?',
                (watch_key,),
            ).fetchone()
        if row is None:
            return None
        return WatchSnapshot(
            watch_key=row['watch_key'],
            scope_hash=row['scope_hash'],
            payload=json.loads(row['payload']),
            fingerprint=row['fingerprint'],
            updated_at=datetime.fromisoformat(row['updated_at']).astimezone(UTC),
        )

    def upsert_watch_snapshot(self, watch_key: str, *, scope_hash: str, payload: dict[str, Any], fingerprint: str) -> WatchSnapshot:
        updated_at = now_utc()
        with self._lock, self._connect() as conn:
            conn.execute(
                '''
                INSERT INTO watch_snapshots (watch_key, scope_hash, payload, fingerprint, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(watch_key) DO UPDATE SET
                    scope_hash=excluded.scope_hash,
                    payload=excluded.payload,
                    fingerprint=excluded.fingerprint,
                    updated_at=excluded.updated_at
                ''',
                (watch_key, scope_hash, json.dumps(payload, ensure_ascii=False), fingerprint, updated_at.isoformat()),
            )
            conn.commit()
        return WatchSnapshot(
            watch_key=watch_key,
            scope_hash=scope_hash,
            payload=payload,
            fingerprint=fingerprint,
            updated_at=updated_at,
        )
