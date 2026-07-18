"""Pending-event sweep (S4.6, R-21, D-11) — chạy sau MỖI lần ingest.

Đối chiếu văn bản vừa nạp với predicate của từng pending_event mở → phát ĐỀ XUẤT
(op `close_window` status='proposed') vào ratify queue. MÁY KHÔNG TỰ ĐÓNG — phán đoán
"văn bản X chính là sự kiện đang chờ" là ngữ nghĩa: máy đề xuất, người chốt.
Rule thiên recall (đề xuất thừa → curator reject; đề xuất thiếu → stale ngược im lặng).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

from api import schemas
from engine.model import ArtifactInput, PendingWindow, sv

QPPL_TYPES = {"luat", "nghi_quyet", "phap_lenh", "nghi_dinh", "quyet_dinh", "thong_tu"}


@dataclass(frozen=True)
class SweepProposal:
    op: schemas.Op                # close_window PROPOSED (chưa ratify — máy không tự đóng)
    pending_op: Any               # op treo-theo-sự-kiện đang chờ
    rationale: str
    confidence: float


def _rule_candidate(pw: PendingWindow, pending_op: Any, artifact: ArtifactInput,
                    artifact_ops: Sequence[Any], ops_by_id: Mapping, artifacts: Mapping,
                    ) -> str | None:
    if sv(artifact.doc_type) not in QPPL_TYPES or artifact.is_oracle:
        return None
    targeted = {o.target_node for o in artifact_ops if o.target_node is not None}
    if pw.target_node is not None and pw.target_node in targeted:
        return (f"văn bản QPPL mới {artifact.doc_key} có op nhắm đúng node đang treo "
                f"({pw.target_node})")
    haystack = " ".join(filter(None, (artifact.title, artifact.text)))
    src_doc = artifacts[pending_op.source_artifact].doc_key
    for key in (src_doc, *(artifacts[o.source_artifact].doc_key for o in [pending_op])):
        if key and key in haystack:
            return (f"văn bản QPPL mới {artifact.doc_key} nhắc tới {key} "
                    f"(nguồn của op treo-theo-sự-kiện)")
    quote = pending_op.source_quote or ""
    for token in ("39/2016/TT-NHNN",):
        if token in quote and token in haystack:
            return f"văn bản QPPL mới {artifact.doc_key} nhắc tới {token} (đích của op treo)"
    return None


def sweep_pending(
    pending: Iterable[PendingWindow], *,
    ops_by_id: Mapping[Any, Any],
    artifact: ArtifactInput,
    artifacts: Mapping[str, ArtifactInput],
    artifact_ops: Sequence[Any] = (),
    llm: Callable[[dict], dict] | None = None,
    seq_start: int = 9000,
) -> list[SweepProposal]:
    """→ đề xuất close_window cho từng pending_event khớp văn bản vừa nạp.

    `llm`: gateway role=extract đề xuất ứng viên bổ sung (D-11) — callable nhận
    {predicate, doc_key, title, excerpt} trả {"candidate": bool, "rationale": str,
    "confidence": float}; test inject fake, production wrap make_gateway_screener()."""
    proposals: list[SweepProposal] = []
    for i, pw in enumerate(sorted(pending, key=lambda p: str(p.op_id))):
        pending_op = ops_by_id[pw.op_id]
        rationale = _rule_candidate(pw, pending_op, artifact, artifact_ops,
                                    ops_by_id, artifacts)
        confidence = 0.6 if rationale else 0.0
        if rationale is None and llm is not None:
            out = llm({"predicate": pw.predicate, "doc_key": artifact.doc_key,
                       "title": artifact.title or "",
                       "excerpt": (artifact.text or "")[:2000]}) or {}
            if out.get("candidate"):
                rationale = f"llm: {out.get('rationale', 'ứng viên do LLM đề xuất')}"
                confidence = float(out.get("confidence", 0.5))
        if rationale is None:
            continue
        if artifact.effective_date is None:
            continue                                       # chưa có ngày đóng đề xuất được
        proposals.append(SweepProposal(
            op=schemas.Op(
                id=uuid5(NAMESPACE_URL, f"lawstate:sweep:{pw.op_id}:{artifact.id}"),
                kind="close_window",
                source_artifact=artifact.id,
                source_quote=f"[sweep] pending: “{pw.predicate}” ⇐ {rationale}",
                seq=seq_start + i,
                target_op=pw.op_id,
                valid_from=artifact.effective_date,        # ngày văn bản mới có hiệu lực
                extractor="sweep",
                confidence=confidence,
                status="proposed",                          # NGƯỜI chốt (D-03/D-11)
                ingested_at=artifact.ingested_at),
            pending_op=pending_op, rationale=rationale, confidence=confidence))
    return proposals


def make_gateway_screener() -> Callable[[dict], dict]:
    """Wrap LLM gateway (D-41) — import lười, không bắt buộc khi test."""
    from answer.llm_gateway import get_gateway              # noqa: PLC0415

    schema = {"type": "object",
              "properties": {"candidate": {"type": "boolean"},
                             "rationale": {"type": "string"},
                             "confidence": {"type": "number"}},
              "required": ["candidate"]}

    def _call(payload: dict) -> dict:
        return get_gateway().complete_json(
            role="extract",
            system=("Một op đang treo-theo-sự-kiện với predicate dưới đây. Văn bản mới nạp "
                    "có phải là 'văn bản QPPL mới' thỏa sự kiện đó không? Chỉ đề xuất — "
                    "người phê chuẩn quyết định."),
            user=f"PREDICATE: {payload['predicate']}\n\nVĂN BẢN: {payload['doc_key']} — "
                 f"{payload['title']}\n{payload['excerpt']}",
            schema=schema)

    return _call
