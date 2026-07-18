"""manifest.py — đọc corpus/manifest.json (ground truth đếm tay của F2 — 04§1.4).

F3 CHỈ ĐỌC corpus/. Manifest mỗi văn bản: {doc_key, file?, sha256, issued_date,
effective_date, synthetic, counts{dieu,khoan,diem,tiet,phuluc}, expected_ops[],
expected_norm_events, expected_edges_sample[], amending_nodes[]} + meta artifact
(doc_type, issuer, audience, owner, channel, is_oracle).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"

_TYPE_BY_SUFFIX = [
    ("TT-", "thong_tu"), ("TTLT", "thong_tu"), ("NĐ-CP", "nghi_dinh"), ("ND-CP", "nghi_dinh"),
    ("NQ-HĐTP", "nghi_quyet"), ("NQ-", "nghi_quyet"), ("QĐ-", "quyet_dinh"),
    ("QD-", "quyet_dinh"), ("QH", "luat"), ("/SHB", "noi_bo"),
]


def load_manifest(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or MANIFEST_PATH
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("documents", "docs", "items", "corpus"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [dict(v, doc_key=k) if isinstance(v, dict) else {"doc_key": k}
                for k, v in data.items()]
    return data


def entry_for(doc_key: str, manifest: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    for e in manifest if manifest is not None else load_manifest():
        if e.get("doc_key") == doc_key:
            return e
    return None


def find_file(entry: dict[str, Any]) -> Path | None:
    """Tìm file văn bản: entry['file'] → entry['slug'] (corpus/text|raw) → đoán theo doc_key."""
    if entry.get("file"):
        p = CORPUS_DIR / entry["file"]
        if p.exists():
            return p
    if entry.get("slug"):
        for sub in ("text", "raw", "."):
            for ext in (".txt", ".md", ".html"):
                p = CORPUS_DIR / sub / f"{entry['slug']}{ext}"
                if p.exists():
                    return p
    key = entry.get("doc_key", "")
    slug = key.replace("/", "-").replace(".", "_")
    slug2 = key.replace("/", "_")
    for cand in CORPUS_DIR.iterdir() if CORPUS_DIR.exists() else []:
        if cand.is_file() and cand.stem.lower() in (slug.lower(), slug2.lower()):
            return cand
    lowered = key.lower().replace("/", "-")
    for cand in CORPUS_DIR.glob("**/*") if CORPUS_DIR.exists() else []:
        if cand.is_file() and lowered in cand.name.lower().replace("_", "-"):
            return cand
    return None


def infer_doc_type(doc_key: str, title: str | None = None) -> str:
    up = (title or "").upper()
    if up.startswith("VĂN BẢN HỢP NHẤT"):
        return "vbhn"
    if up.startswith("BỘ LUẬT") or up.startswith("LUẬT"):
        return "luat"
    if up.startswith("NGHỊ QUYẾT"):
        return "nghi_quyet"
    if up.startswith("MẪU"):
        return "bieu_mau"
    if up.startswith("CÔNG VĂN"):
        return "cong_van"
    for suffix, t in _TYPE_BY_SUFFIX:
        if suffix in doc_key:
            return t
    return "thong_tu"


def infer_issuer(doc_key: str, doc_type: str) -> str:
    if "/SHB" in doc_key:
        return "SHB"
    if doc_type == "luat" or "QH" in doc_key:
        return "QH"
    if "NĐ-CP" in doc_key or "ND-CP" in doc_key:
        return "CP"
    if "HĐTP" in doc_key or "HDTP" in doc_key:
        return "HDTP"
    tail = doc_key.rsplit("-", 1)
    if len(tail) == 2 and tail[1].isalpha():
        return tail[1]
    return "NHNN"


def artifact_meta(entry: dict[str, Any], parsed_title: str | None = None) -> dict[str, Any]:
    """Meta artifact từ manifest entry + suy luận; manifest LUÔN thắng suy luận."""
    doc_key = entry["doc_key"]
    doc_type = entry.get("doc_type") or infer_doc_type(doc_key, parsed_title)
    return {
        "doc_key": doc_key,
        "doc_type": doc_type,
        "issuer": entry.get("issuer") or infer_issuer(doc_key, doc_type),
        "title": entry.get("title") or parsed_title,
        "audience": entry.get("audience") or ("internal" if "/SHB" in doc_key else "public"),
        "owner": entry.get("owner"),
        "channel": entry.get("channel") or ("internal_registry" if "/SHB" in doc_key else "sbv"),
        "is_oracle": bool(entry.get("is_oracle", doc_type == "vbhn")),
        "synthetic": bool(entry.get("synthetic", False)),
        "issued_date": entry.get("issued_date"),
        "effective_date": entry.get("effective_date"),
    }
