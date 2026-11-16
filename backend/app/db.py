"""Pool de conexiones PostgreSQL (psycopg 3). Una transacción por caso de uso."""
from __future__ import annotations

import atexit
from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=8,
                               kwargs={"row_factory": dict_row}, open=True)
        atexit.register(close)
    return _pool


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def tx() -> Iterator[Connection]:
    """Transacción: commit al salir sin error, rollback si hay excepción."""
    with pool().connection() as conn, conn.transaction():
        yield conn
