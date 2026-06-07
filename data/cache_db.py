"""
SQLite-backed cache layer — drop-in replacement for flat JSON cache files.
Provides TTL-aware get/set with automatic expiry cleanup.
All scrapers can use this instead of writing individual JSON files.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional, Any

from config.settings import CACHE_DIR

_DB_PATH = Path(CACHE_DIR) / "football_cache.db"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=10)
    con.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key      TEXT PRIMARY KEY,
            value    TEXT NOT NULL,
            expires  REAL NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires)")
    con.commit()
    return con


def cache_get(key: str) -> Optional[Any]:
    """Return cached value or None if missing/expired."""
    try:
        con = _conn()
        row = con.execute(
            "SELECT value, expires FROM cache WHERE key = ?", (key,)
        ).fetchone()
        con.close()
        if not row:
            return None
        value_str, expires = row
        if time.time() > expires:
            cache_delete(key)
            return None
        return json.loads(value_str)
    except Exception:
        return None


def cache_set(key: str, value: Any, ttl: int) -> None:
    """Store value in cache with TTL in seconds."""
    try:
        con = _conn()
        con.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires) VALUES (?, ?, ?)",
            (key, json.dumps(value, default=str), time.time() + ttl)
        )
        con.commit()
        con.close()
    except Exception:
        pass


def cache_delete(key: str) -> None:
    try:
        con = _conn()
        con.execute("DELETE FROM cache WHERE key = ?", (key,))
        con.commit()
        con.close()
    except Exception:
        pass


def cache_clear_pattern(prefix: str) -> int:
    """Delete all keys starting with prefix. Returns count deleted."""
    try:
        con = _conn()
        cur = con.execute("DELETE FROM cache WHERE key LIKE ?", (prefix + "%",))
        count = cur.rowcount
        con.commit()
        con.close()
        return count
    except Exception:
        return 0


def cache_cleanup_expired() -> int:
    """Remove all expired entries. Returns count removed."""
    try:
        con = _conn()
        cur = con.execute("DELETE FROM cache WHERE expires < ?", (time.time(),))
        count = cur.rowcount
        con.commit()
        con.close()
        return count
    except Exception:
        return 0


def cache_stats() -> dict:
    """Return cache statistics for health monitor."""
    try:
        con = _conn()
        total = con.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        expired = con.execute("SELECT COUNT(*) FROM cache WHERE expires < ?", (time.time(),)).fetchone()[0]
        size_kb = _DB_PATH.stat().st_size / 1024 if _DB_PATH.exists() else 0
        con.close()
        return {"total_entries": total, "expired": expired, "size_kb": round(size_kb, 1)}
    except Exception:
        return {"total_entries": 0, "expired": 0, "size_kb": 0}
