"""Hybrid fuse (R-28, D-28): BM25 top-30 ∪ dense top-30 → RRF k=60 → top-12.

Chạy TRÊN các hàng đã đi qua predicate một cửa (query_builder) — module này
không chạm DB, thuần hàm để unit test tất định.
"""
from __future__ import annotations

from retrieval.bm25 import BM25Index
from retrieval.dense import DenseIndex, Embedder, get_embedder
from retrieval.query_builder import SnapshotRow, surface_of_path

BM25_TOP = 30
DENSE_TOP = 30
RRF_K = 60
FUSED_TOP = 12


def index_text(row: SnapshotRow) -> str:
    """Text đưa vào index: số hiệu + địa chỉ bề mặt + heading + body — để câu hỏi
    cite số hiệu/địa chỉ vẫn khớp lexical."""
    return f"{row.doc_key} {surface_of_path(row.path)}\n{row.text}"


def rrf_fuse(rankings: list[list[object]], k: int = RRF_K) -> list[tuple[object, float]]:
    """Reciprocal Rank Fusion: score(d) = Σ_lists 1/(k + rank_d). Tie-break tất
    định theo repr(key) để hoán vị input không đổi output."""
    scores: dict[object, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], repr(kv[0])))


def hybrid_search(rows: list[SnapshotRow], query: str,
                  embedder: Embedder | None = None,
                  bm25_top: int = BM25_TOP, dense_top: int = DENSE_TOP,
                  rrf_k: int = RRF_K, top: int = FUSED_TOP) -> list[SnapshotRow]:
    """BM25 ∪ dense trên CÙNG candidate set → RRF → top-12 hàng snapshot."""
    if not rows:
        return []
    entries = [(r.key, index_text(r)) for r in rows]
    by_key = {r.key: r for r in rows}

    bm25_ranked = [k for k, _ in BM25Index(entries).search(query, top_n=bm25_top)]
    pre = {r.key: list(r.embedding) for r in rows if r.embedding is not None}
    dense = DenseIndex(entries, embedder or get_embedder(), precomputed=pre or None)
    dense_ranked = [k for k, _ in dense.search(query, top_n=dense_top)]

    fused = rrf_fuse([bm25_ranked, dense_ranked], k=rrf_k)
    return [by_key[k] for k, _ in fused[:top]]
