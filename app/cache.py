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


@dataclass(slots=True)
class NegativeCacheEntry:
    key: str
    error_code: str
    detail: str
    created_at: datetime
    expires_at: datetime
    namespace: str | None = None
    resource_url: str | None = None
    debug_dump_path: str | None = None

    @property
    def is_fresh(self) -> bool:
        return now_utc() <= self.expires_at


class SQLiteCache:
    def __init__(self, db_path: Path, *, busy_timeout_ms: int = 5000, memory_entries: int = 512):
        self.db_path = db_path
        self.busy_timeout_ms = max(0, int(busy_timeout_ms))
        self.memory_entries = max(0, int(memory_entries))
        self._lock = threading.RLock()
        self._memory_cache: dict[str, CacheEntry] = {}
        self._negative_memory_cache: dict[str, NegativeCacheEntry] = {}
        self._conn = self._connect()
        self._init_db()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA synchronous=NORMAL')
        connection.execute('PRAGMA temp_store=MEMORY')
        connection.execute(f'PRAGMA busy_timeout={self.busy_timeout_ms}')
        return connection

    def _evict_memory_if_needed(self) -> None:
        if self.memory_entries <= 0:
            self._memory_cache.clear()
            self._negative_memory_cache.clear()
            return
        while len(self._memory_cache) > self.memory_entries:
            oldest_key = next(iter(self._memory_cache))
            self._memory_cache.pop(oldest_key, None)
        while len(self._negative_memory_cache) > self.memory_entries:
            oldest_key = next(iter(self._negative_memory_cache))
            self._negative_memory_cache.pop(oldest_key, None)

    def _remember_cache_entry(self, entry: CacheEntry) -> None:
        if self.memory_entries <= 0:
            return
        self._memory_cache.pop(entry.key, None)
        self._memory_cache[entry.key] = entry
        self._evict_memory_if_needed()

    def _remember_negative_entry(self, entry: NegativeCacheEntry) -> None:
        if self.memory_entries <= 0:
            return
        self._negative_memory_cache.pop(entry.key, None)
        self._negative_memory_cache[entry.key] = entry
        self._evict_memory_if_needed()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, sql_type: str) -> None:
        existing_columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}
        if column not in existing_columns:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {sql_type}')

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute(
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
            self._ensure_column(self._conn, 'cache_entries', 'namespace', 'TEXT')
            self._ensure_column(self._conn, 'cache_entries', 'resource_url', 'TEXT')
            self._conn.execute(
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
            self._conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS negative_cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    error_code TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    namespace TEXT,
                    resource_url TEXT,
                    debug_dump_path TEXT
                )
                '''
            )
            self._conn.commit()

    def get(self, cache_key: str) -> CacheEntry | None:
        with self._lock:
            memory_entry = self._memory_cache.get(cache_key)
            if memory_entry is not None:
                if now_utc() <= memory_entry.stale_until:
                    self._remember_cache_entry(memory_entry)
                    return memory_entry
                self._memory_cache.pop(cache_key, None)

            row = self._conn.execute(
                'SELECT cache_key, payload, fetched_at, expires_at, stale_until, namespace, resource_url FROM cache_entries WHERE cache_key = ?',
                (cache_key,),
            ).fetchone()
            if row is None:
                return None
            entry = CacheEntry(
                key=row['cache_key'],
                payload=json.loads(row['payload']),
                fetched_at=datetime.fromisoformat(row['fetched_at']).astimezone(UTC),
                expires_at=datetime.fromisoformat(row['expires_at']).astimezone(UTC),
                stale_until=datetime.fromisoformat(row['stale_until']).astimezone(UTC),
                namespace=row['namespace'],
                resource_url=row['resource_url'],
            )
            if now_utc() <= entry.stale_until:
                self._remember_cache_entry(entry)
            return entry

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
        with self._lock:
            self._conn.execute(
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
            self._conn.commit()
            entry = CacheEntry(
                key=cache_key,
                payload=payload,
                fetched_at=fetched_at,
                expires_at=expires_at,
                stale_until=stale_until,
                namespace=namespace,
                resource_url=resource_url,
            )
            self._remember_cache_entry(entry)
            return entry

    def get_negative(self, cache_key: str) -> NegativeCacheEntry | None:
        with self._lock:
            memory_entry = self._negative_memory_cache.get(cache_key)
            if memory_entry is not None:
                if memory_entry.is_fresh:
                    self._remember_negative_entry(memory_entry)
                    return memory_entry
                self._negative_memory_cache.pop(cache_key, None)

            row = self._conn.execute(
                '''
                SELECT cache_key, error_code, detail, created_at, expires_at, namespace, resource_url, debug_dump_path
                FROM negative_cache_entries
                WHERE cache_key = ?
                ''',
                (cache_key,),
            ).fetchone()
            if row is None:
                return None
            entry = NegativeCacheEntry(
                key=row['cache_key'],
                error_code=row['error_code'],
                detail=row['detail'],
                created_at=datetime.fromisoformat(row['created_at']).astimezone(UTC),
                expires_at=datetime.fromisoformat(row['expires_at']).astimezone(UTC),
                namespace=row['namespace'],
                resource_url=row['resource_url'],
                debug_dump_path=row['debug_dump_path'],
            )
            if entry.is_fresh:
                self._remember_negative_entry(entry)
            return entry

    def set_negative(
        self,
        cache_key: str,
        *,
        error_code: str,
        detail: str,
        ttl_seconds: int,
        namespace: str | None = None,
        resource_url: str | None = None,
        debug_dump_path: str | None = None,
    ) -> NegativeCacheEntry:
        created_at = now_utc()
        expires_at = created_at.fromtimestamp(created_at.timestamp() + max(ttl_seconds, 1), tz=UTC)
        with self._lock:
            self._conn.execute(
                '''
                INSERT INTO negative_cache_entries (
                    cache_key, error_code, detail, created_at, expires_at, namespace, resource_url, debug_dump_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    error_code=excluded.error_code,
                    detail=excluded.detail,
                    created_at=excluded.created_at,
                    expires_at=excluded.expires_at,
                    namespace=excluded.namespace,
                    resource_url=excluded.resource_url,
                    debug_dump_path=excluded.debug_dump_path
                ''',
                (
                    cache_key,
                    error_code,
                    detail,
                    created_at.isoformat(),
                    expires_at.isoformat(),
                    namespace,
                    resource_url,
                    debug_dump_path,
                ),
            )
            self._conn.commit()
            entry = NegativeCacheEntry(
                key=cache_key,
                error_code=error_code,
                detail=detail,
                created_at=created_at,
                expires_at=expires_at,
                namespace=namespace,
                resource_url=resource_url,
                debug_dump_path=debug_dump_path,
            )
            self._remember_negative_entry(entry)
            return entry

    def clear_negative(self, cache_key: str) -> None:
        with self._lock:
            self._negative_memory_cache.pop(cache_key, None)
            self._conn.execute('DELETE FROM negative_cache_entries WHERE cache_key = ?', (cache_key,))
            self._conn.commit()

    def stats(self) -> dict[str, Any]:
        now = now_utc()
        with self._lock:
            rows = self._conn.execute(
                'SELECT cache_key, fetched_at, expires_at, stale_until, namespace, resource_url FROM cache_entries'
            ).fetchall()
            negative_rows = self._conn.execute(
                'SELECT cache_key, error_code, created_at, expires_at, namespace, resource_url FROM negative_cache_entries'
            ).fetchall()
            watch_rows = self._conn.execute('SELECT watch_key, updated_at FROM watch_snapshots').fetchall()

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

        negative_by_namespace: dict[str, dict[str, int]] = {}
        negative_totals = {'entries': 0, 'fresh': 0, 'expired': 0}
        for row in negative_rows:
            namespace = row['namespace'] or 'unknown'
            namespace_stats = negative_by_namespace.setdefault(namespace, {'entries': 0, 'fresh': 0, 'expired': 0})
            namespace_stats['entries'] += 1
            negative_totals['entries'] += 1
            expires_at = datetime.fromisoformat(row['expires_at']).astimezone(UTC)
            state_key = 'fresh' if now <= expires_at else 'expired'
            namespace_stats[state_key] += 1
            negative_totals[state_key] += 1

        return {
            'db_path': str(self.db_path),
            'totals': totals,
            'by_namespace': by_namespace,
            'negative_cache': {
                'totals': negative_totals,
                'by_namespace': negative_by_namespace,
            },
            'watch_snapshots': {
                'entries': len(watch_rows),
                'oldest_updated_at': min((row['updated_at'] for row in watch_rows), default=None),
                'newest_updated_at': max((row['updated_at'] for row in watch_rows), default=None),
            },
            'oldest_fetched_at': oldest_fetched_at,
            'newest_fetched_at': newest_fetched_at,
            'memory_cache': {
                'entries': len(self._memory_cache),
                'negative_entries': len(self._negative_memory_cache),
                'capacity': self.memory_entries,
            },
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
        entry_clauses = list(clauses)
        entry_params = list(params)
        negative_clauses = list(clauses)
        negative_params = list(params)
        now_iso = now_utc().isoformat()
        if expired_only:
            entry_clauses.append('stale_until < ?')
            entry_params.append(now_iso)
            negative_clauses.append('expires_at < ?')
            negative_params.append(now_iso)

        def _where_sql(table_clauses: list[str]) -> str:
            if all_entries and not table_clauses:
                return ''
            return ' WHERE ' + (' AND '.join(table_clauses) if table_clauses else '1 = 0')

        entry_where_clause = _where_sql(entry_clauses)
        negative_where_clause = _where_sql(negative_clauses)
        with self._lock:
            cursor = self._conn.execute(f'DELETE FROM cache_entries{entry_where_clause}', tuple(entry_params))
            negative_cursor = self._conn.execute(f'DELETE FROM negative_cache_entries{negative_where_clause}', tuple(negative_params))
            self._conn.commit()
            if all_entries:
                self._memory_cache.clear()
                self._negative_memory_cache.clear()
            else:
                if cache_key:
                    self._memory_cache.pop(cache_key, None)
                    self._negative_memory_cache.pop(cache_key, None)
                elif namespace or resource_url or expired_only:
                    self._memory_cache.clear()
                    self._negative_memory_cache.clear()
            return int((cursor.rowcount or 0) + (negative_cursor.rowcount or 0))

    def get_watch_snapshot(self, watch_key: str) -> WatchSnapshot | None:
        with self._lock:
            row = self._conn.execute(
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
        with self._lock:
            self._conn.execute(
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
            self._conn.commit()
        return WatchSnapshot(
            watch_key=watch_key,
            scope_hash=scope_hash,
            payload=payload,
            fingerprint=fingerprint,
            updated_at=updated_at,
        )
