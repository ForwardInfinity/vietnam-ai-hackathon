"""Fixture chung cho test engine — corpus op tự dựng, KHÔNG cần Postgres (S0.2)."""
from __future__ import annotations

import pytest

from engine.fixtures import FIXTURE_DIR, FixtureCorpus, load_dir
from engine.fold import fold_corpus


@pytest.fixture(scope="session")
def corpus() -> FixtureCorpus:
    return load_dir(FIXTURE_DIR)


@pytest.fixture(scope="session")
def folded(corpus):
    return fold_corpus(corpus.nodes, corpus.ops, corpus.artifacts)


def ratified_copy(op, **overrides):
    """Bản sao op với status ratified (mô phỏng người phê chuẩn — test only)."""
    return op.model_copy(update={"status": "ratified", "ratified_by": "curator:test",
                                 **overrides})
