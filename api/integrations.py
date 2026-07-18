"""Seam DUY NHẤT gọi sang module của task khác (F3/F4/F5/F7).

Các task chạy song song — phần chưa merge thì hàm ở đây trả None/raise
IntegrationMissing với cờ TODO rõ; endpoint dịch thành 501/ghi chú "stub".
KHÔNG cài logic thật của họ ở đây (out of scope F6).

Interface đoán theo CONTRACTS.md S8 + README của họ khi có; nếu chữ ký thật
khác thì sửa DUY NHẤT file này.
"""
from __future__ import annotations

import importlib
from typing import Any, Callable

TODO_F3 = "TODO(F3): ingest pipeline (parse cây → citation → op extraction) chưa merge"
TODO_F4 = "TODO(F4): engine fold/replay chưa merge"
TODO_F4_BLAST = "TODO(F4): blast_radius (R-23) chưa merge — notification chưa tự sinh khi ratify"
TODO_F5 = "TODO(F5): answering pipeline (retrieval→closure→compose→verify) chưa merge"
TODO_F7 = "TODO(F7): eval runner chưa merge"


class IntegrationMissing(RuntimeError):
    def __init__(self, todo: str):
        self.todo = todo
        super().__init__(todo)


def _try(module: str, *fn_names: str) -> Callable[..., Any] | None:
    try:
        mod = importlib.import_module(module)
    except ImportError:
        return None
    for name in fn_names:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    return None


def run_ingest_pipeline(artifact_id: str) -> dict:
    """F3: chạy S4.1–S4.3 trên artifact đã lưu L0 → đề xuất op. → {proposed_ops, nodes, ...}"""
    fn = _try("ingest.pipeline", "run", "run_pipeline", "ingest_artifact")
    if fn is None:
        raise IntegrationMissing(TODO_F3)
    return fn(artifact_id)


def run_replay(k_cutoff=None) -> dict:
    """F4: fold toàn corpus → snapshot mới. → {run_id, changed_nodes, certificates, guard_violations}"""
    fn = _try("engine.snapshot", "replay", "replay_all", "run_replay") or _try(
        "engine.fold", "replay_all"
    )
    if fn is None:
        raise IntegrationMissing(TODO_F4)
    return fn(k_cutoff=k_cutoff) if k_cutoff is not None else fn()


def notify_blast_radius(op_ids: list) -> int | None:
    """F4 R-23: where-used → notification khi op ratified. Chưa có → None (bỏ qua, TODO)."""
    fn = _try("engine.blast_radius", "on_ratified", "notify", "run")
    if fn is None:
        return None
    return fn(op_ids)


def run_answer_pipeline(req, entitlements: tuple[str, ...]):
    """F5: câu hỏi → Answer đầy đủ (compiler→retrieval→closure→compose→verify→tier)."""
    fn = _try("answer.pipeline", "answer", "run", "answer_question")
    if fn is None:
        raise IntegrationMissing(TODO_F5)
    return fn(req, entitlements=entitlements)


def run_eval(**kwargs) -> dict:
    """F7: golden set runner → report."""
    fn = _try("eval.runner", "run", "run_eval", "main")
    if fn is None:
        raise IntegrationMissing(TODO_F7)
    return fn(**kwargs)
