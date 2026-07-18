"""Loader fixture op JSON (tests/fixtures/ops/*.json) → object đúng contract (api.schemas.Op).

Fixture TỰ DỰNG theo anchor thật (04 §1.1/§1.3) để engine không chờ F3; id tất định qua
uuid5 để INV-9 (rebuild bit-exact) kiểm được. F3 thay nguồn op bằng extraction thật — format
file: {"artifact": {...}, "nodes": [...], "ops": [...]}; mọi tham chiếu id dùng TÊN chuỗi.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from api import schemas
from engine.model import ArtifactInput, NodeInput

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ops"


def fid(name: str) -> UUID:
    """UUID tất định từ tên fixture."""
    return uuid5(NAMESPACE_URL, f"lawstate:{name}")


def _d(v: Any) -> date | None:
    return date.fromisoformat(v) if isinstance(v, str) else v


def _ts(v: Any) -> datetime | None:
    return datetime.fromisoformat(v) if isinstance(v, str) else v


def _u(name: Any) -> UUID | None:
    return fid(name) if isinstance(name, str) else name


@dataclass
class FixtureCorpus:
    artifacts: list[ArtifactInput] = field(default_factory=list)
    nodes: list[NodeInput] = field(default_factory=list)
    ops: list[schemas.Op] = field(default_factory=list)
    names: dict[str, UUID] = field(default_factory=dict)          # tên → uuid (node/op)
    artifacts_by_id: dict[str, ArtifactInput] = field(default_factory=dict)

    def node(self, doc_key: str, path: str) -> NodeInput:
        for n in self.nodes:
            if n.doc_key == doc_key and n.path == path:
                return n
        raise KeyError(f"không có node {doc_key} {path}")

    def op(self, name: str) -> schemas.Op:
        oid = fid(name)
        for o in self.ops:
            if o.id == oid:
                return o
        raise KeyError(f"không có op {name}")


def _load_artifact(doc: dict, corpus: FixtureCorpus) -> ArtifactInput:
    a = doc["artifact"]
    art = ArtifactInput(
        id=a["id"], doc_key=a["doc_key"], doc_type=a["doc_type"], issuer=a["issuer"],
        issued_date=_d(a.get("issued_date")), effective_date=_d(a.get("effective_date")),
        title=a.get("title"), is_oracle=a.get("is_oracle", False),
        audience=a.get("audience", "internal"), owner=a.get("owner"),
        text=a.get("text"), ingested_at=_ts(a.get("ingested_at")))
    corpus.artifacts.append(art)
    corpus.artifacts_by_id[art.id] = art
    return art


def _load_body(doc: dict, art: ArtifactInput, corpus: FixtureCorpus) -> None:
    a = doc["artifact"]
    for n in doc.get("nodes", []):
        art_id = n.get("artifact", art.id)
        owner_art = corpus.artifacts_by_id.get(art_id, art)
        node = NodeInput(id=fid(n["id"]), artifact_id=art_id, doc_key=owner_art.doc_key,
                         path=n["path"], role=n.get("role", "rule"),
                         heading=n.get("heading"), body=n.get("body"))
        corpus.nodes.append(node)
        corpus.names[n["id"]] = node.id

    for i, o in enumerate(doc.get("ops", [])):
        op = schemas.Op(
            id=fid(o["id"]), kind=o["kind"],
            source_artifact=o.get("source_artifact", art.id),
            source_node=_u(o.get("source_node")),
            source_quote=o["source_quote"], seq=o.get("seq", i + 1),
            target_node=_u(o.get("target_node")), target_op=_u(o.get("target_op")),
            target_norm=_u(o.get("target_norm")),
            target_part=o.get("target_part", "body"),
            new_text=o.get("new_text"), new_heading=o.get("new_heading"),
            valid_from=_d(o.get("valid_from")), valid_to=_d(o.get("valid_to")),
            valid_to_event=o.get("valid_to_event"),
            scope_predicate=o.get("scope_predicate"),
            risk_class=o.get("risk_class"), extractor=o.get("extractor", "fixture"),
            confidence=o.get("confidence", 1.0), status=o.get("status", "ratified"),
            ratified_by=o.get("ratified_by", "curator:fixture"),
            ingested_at=_ts(o.get("ingested_at", a.get("ingested_at"))))
        corpus.ops.append(op)
        corpus.names[o["id"]] = op.id


def load_dir(path: Path | str = FIXTURE_DIR, exclude: frozenset[str] = frozenset(),
             ) -> FixtureCorpus:
    """Hai pha: artifact trước (node được phép trỏ artifact ở file khác), rồi node+op."""
    corpus = FixtureCorpus()
    docs = []
    for f in sorted(Path(path).glob("*.json")):
        if f.name in exclude:
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        docs.append((doc, _load_artifact(doc, corpus)))
    for doc, art in docs:
        _load_body(doc, art, corpus)
    return corpus
