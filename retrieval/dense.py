"""Dense retrieval — BGE-M3 1024d sau interface Embedder (D-40).

Local dev / smoke test: FakeDeterministicEmbedder — bag-of-words chiếu ngẫu nhiên
seed theo sha256(token), TẤT ĐỊNH tuyệt đối, không cần torch. CI/VPS muốn model
thật: `uv sync --group ml` + env `EMBEDDER=bge-m3` (test model thật mang marker
heavy, tự skip khi thiếu sentence-transformers).
"""
from __future__ import annotations

import hashlib
import os
from typing import Protocol

import numpy as np

from retrieval.bm25 import tokenize

DIM = 1024  # vector(1024) trong DDL — chốt trước schema (D-40)

# Sàn cosine: dưới ngưỡng này coi như không-liên-quan (retrieval floor trung thực —
# random projection của fake embedder cho cặp không giao token ~ ±0.05; câu liên
# quan ≥ 0.2 ở cả fake lẫn BGE-M3)
MIN_SIM = 0.1


class Embedder(Protocol):
    dim: int

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class FakeDeterministicEmbedder:
    """BoW random-projection: mỗi token → vector Gauss seed sha256(token); câu =
    trung bình chuẩn hóa. Cùng input → cùng vector ở mọi process (không phụ thuộc
    PYTHONHASHSEED). Đủ để test ngữ nghĩa giao-token; không thay thế BGE-M3."""

    dim = DIM
    _token_cache: dict[str, np.ndarray] = {}

    def _token_vec(self, tok: str) -> np.ndarray:
        v = self._token_cache.get(tok)
        if v is None:
            seed = int(hashlib.sha256(tok.encode("utf-8")).hexdigest()[:16], 16)
            v = np.random.default_rng(seed).standard_normal(self.dim)
            self._token_cache[tok] = v
        return v

    def encode(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            toks = tokenize(t)
            if not toks:
                out.append([0.0] * self.dim)
                continue
            v = np.sum([self._token_vec(tok) for tok in toks], axis=0)
            n = float(np.linalg.norm(v))
            out.append((v / n).tolist() if n > 0 else v.tolist())
        return out


class BgeM3Embedder:
    """BGE-M3 thật qua sentence-transformers (lazy import — chỉ khi được chọn)."""

    dim = DIM

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        from sentence_transformers import SentenceTransformer  # import lười — nhóm ml

        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]


def get_embedder(name: str | None = None) -> Embedder:
    """`EMBEDDER=fake` (default local) | `bge-m3` (CI/VPS, cần nhóm ml)."""
    name = (name or os.getenv("EMBEDDER", "fake")).lower()
    if name in ("bge-m3", "bge_m3", "bgem3"):
        return BgeM3Embedder()
    return FakeDeterministicEmbedder()


def on_snapshot_written(conn, run_id) -> int:
    """Hook R-19 cho engine F4 (`engine.snapshot.replay(on_snapshot_written=...)`).

    Chạy TRONG transaction replay của F4 (nơi duy nhất được UPDATE node_version —
    guard `lawstate.replay`): tính embedding cho các version retrievable của run
    và ghi vào cột vector(1024) qua một cửa query_builder. BM25 KHÔNG cần persist —
    rebuild in-process từ snapshot <1s mỗi query (D-39). Trả số hàng đã ghi."""
    from retrieval.query_builder import embedding_backlog, write_embedding

    rows = embedding_backlog(conn, run_id)
    if not rows:
        return 0
    embedder = get_embedder()
    vecs = embedder.encode([r[2] for r in rows])
    for (node_id, version, _), v in zip(rows, vecs):
        write_embedding(conn, node_id, version, v)
    return len(rows)


class DenseIndex:
    """Cosine search in-memory trên entries (key, text). Row nào snapshot đã có
    embedding thì truyền qua `precomputed` để khỏi encode lại."""

    def __init__(self, entries: list[tuple[object, str]], embedder: Embedder,
                 precomputed: dict[object, list[float]] | None = None):
        self._keys = [k for k, _ in entries]
        pre = precomputed or {}
        to_encode = [(i, t) for i, (k, t) in enumerate(entries) if k not in pre]
        vecs: list[np.ndarray | None] = [None] * len(entries)
        for (k, _), i in zip(entries, range(len(entries))):
            if k in pre:
                vecs[i] = np.asarray(pre[k], dtype=float)
        if to_encode:
            encoded = embedder.encode([t for _, t in to_encode])
            for (i, _), v in zip(to_encode, encoded):
                vecs[i] = np.asarray(v, dtype=float)
        self._matrix = np.vstack(vecs) if vecs else np.zeros((0, embedder.dim))
        # chuẩn hóa hàng để dot = cosine
        norms = np.linalg.norm(self._matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix = self._matrix / norms
        self._embedder = embedder

    def search(self, query: str, top_n: int = 30) -> list[tuple[object, float]]:
        if not self._keys:
            return []
        q = np.asarray(self._embedder.encode([query])[0], dtype=float)
        qn = float(np.linalg.norm(q))
        if qn == 0:
            return []
        sims = self._matrix @ (q / qn)
        order = sorted(range(len(sims)), key=lambda i: (-sims[i], i))
        return [(self._keys[i], float(sims[i])) for i in order[:top_n] if sims[i] >= MIN_SIM]
