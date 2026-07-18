"""Differential oracle (S4.7, R-22, D-22) — diff text materialize vs VBHN.

VBHN không có giá trị pháp lý chính thức (02 §7 bẫy 16): oracle là CHUÔNG BÁO, không phải
chân lý — lệch đi vào backlog phân xử (lỗi parser / lỗi precedence / lỗi nhà hợp nhất),
KHÔNG auto-fix. Quy ước v1: so sánh text ACTIVE tại as_of; node treo/bãi bỏ không đưa vào
hai phía (VBHN in kèm chú thích ngưng — chuẩn hóa chú thích là việc của F3 khi parse VBHN).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence
from uuid import UUID

from engine.fold import materialize_at
from engine.model import NodeInput, Version

_WS = re.compile(r"\s+")


def normalize_text(s: str | None) -> str:
    """NFC (bẫy 1 của 02 §7) + gộp whitespace — như nhau ở cả hai phía trước khi diff."""
    if not s:
        return ""
    return _WS.sub(" ", unicodedata.normalize("NFC", s)).strip()


@dataclass(frozen=True)
class OracleMismatch:
    doc_key: str
    path: str
    kind: str                     # missing_in_snapshot | missing_in_oracle | text_mismatch
    snapshot_text: str
    oracle_text: str


def materialize_doc(nodes: Sequence[NodeInput],
                    versions_by_node: Mapping[UUID, Sequence[Version]],
                    doc_key: str, as_of: date) -> dict[str, str]:
    """path → text active tại as_of của một văn bản (heading + body), nhánh universal.
    Node có scope split lấy MỌI nhánh nối lại (VBHN in đủ; v1 corpus không có ca này)."""
    out: dict[str, str] = {}
    for n in sorted((n for n in nodes if n.doc_key == doc_key), key=lambda n: n.path):
        active = materialize_at(versions_by_node.get(n.id, ()), as_of, status="active")
        if not active:
            continue
        parts = []
        for v in active:
            parts.extend(t for t in (v.heading, v.body) if t)
        text = normalize_text(" ".join(parts))
        if text:
            out[n.path] = text
    return out


def oracle_diff(materialized: Mapping[str, str], oracle: Mapping[str, str],
                doc_key: str = "") -> list[OracleMismatch]:
    """So khớp path→text hai phía sau chuẩn hóa; mọi lệch là một mục backlog phân xử."""
    mismatches: list[OracleMismatch] = []
    for path in sorted(set(materialized) | set(oracle)):
        snap = normalize_text(materialized.get(path))
        orc = normalize_text(oracle.get(path))
        if snap == orc:
            continue
        kind = ("missing_in_snapshot" if not snap
                else "missing_in_oracle" if not orc else "text_mismatch")
        mismatches.append(OracleMismatch(doc_key=doc_key, path=path, kind=kind,
                                         snapshot_text=snap, oracle_text=orc))
    return mismatches
