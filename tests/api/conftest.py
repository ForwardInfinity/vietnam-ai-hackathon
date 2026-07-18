"""Fixture heavy cho contract test bề mặt API: reset schema + seed mini-corpus mỗi MODULE.

Không có TEST_DATABASE_URL → skip (giao thức heavy của CONTRACTS.md).
CẢNH BÁO: DROP SCHEMA public CASCADE — chỉ trỏ DB vứt được.
"""
import os

import pytest


@pytest.fixture(scope="module")
def seeded_client():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL chưa set — bỏ heavy API contract tests")
    psycopg = pytest.importorskip("psycopg")
    from tests.api.seed_demo import reset, seed

    with psycopg.connect(url, autocommit=True) as conn:
        reset(conn)
        conn.autocommit = False
        seed(conn)

    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        from fastapi.testclient import TestClient

        from api.main import app

        yield TestClient(app)
    finally:
        if old is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old
