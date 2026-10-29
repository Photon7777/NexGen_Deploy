"""Database access that keeps row-level security in force.

The API connects as the `postgres` role, which bypasses RLS. Every request
therefore runs inside a transaction that switches to the `authenticated` role
and sets the caller's JWT claims, exactly as Supabase's own API does. The RLS
policies in supabase/migrations then decide which rows the query can touch.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Depends
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .auth import User, current_user
from .config import get_settings

_pool: ConnectionPool | None = None


def open_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            get_settings().database_url,
            min_size=1,
            max_size=5,
            # Supabase's transaction pooler does not support prepared statements.
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
            # The pooler closes idle connections, so test each one before handing it out
            # (one round trip) rather than failing the request that gets a dead one.
            check=ConnectionPool.check_connection,
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def user_transaction(user: User) -> Iterator[Connection]:
    with open_pool().connection() as conn, conn.transaction():
        conn.execute("set local role authenticated")
        conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(user.claims),))
        yield conn


def db(user: User = Depends(current_user)) -> Iterator[Connection]:
    """FastAPI dependency: a connection scoped to the signed-in user."""
    with user_transaction(user) as conn:
        yield conn
