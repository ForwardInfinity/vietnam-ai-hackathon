"""Kết nối DB cho tầng API (F6).

Một cửa lấy connection — endpoint KHÔNG tự psycopg.connect. Test không-heavy
monkeypatch `connect()`; heavy test trỏ DATABASE_URL vào Postgres thật.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row


def database_url() -> str:
    return os.getenv(
        "DATABASE_URL", "postgresql://lawstate:lawstate@localhost:5432/lawstate"
    )


def connect() -> psycopg.Connection:
    """Connection mới, row_factory=dict_row, autocommit=False (caller commit)."""
    return psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=5)


@contextmanager
def tx() -> Iterator[psycopg.Connection]:
    """Transaction scope: commit khi ra khỏi with sạch, rollback khi exception."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def db_available() -> bool:
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
