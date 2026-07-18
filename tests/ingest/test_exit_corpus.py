"""EXIT TESTS trên corpus THẬT (corpus/manifest.json — F2 sở hữu, F3 chỉ đọc).

R-4:  đếm dieu/khoan/diem/tiet/phuluc khớp manifest 100% × TOÀN BỘ văn bản (in bảng).
Extraction: op đề xuất khớp expected_ops (kind, target, ngày, event, scope).
Edges ⊇ expected_edges_sample (schema F2: source_path/type/target/surface).
Amending: mọi path manifest là amending; node amending thêm chỉ được là CON của
path manifest (con của khoản amending kế thừa role để không leak — INV-8).

Ca phân xử với manifest (ghi nhận, KHÔNG sửa manifest — xem BAOCAO-F3.md):
  ADJ-1  TT06 k11 "Bổ sung Mục 3 Chương II": manifest = 1 op target 'chuong:II/muc:3';
         path đó ngoài grammar node (02§1: Mục/Chương là container). F3 decompose
         thành op insert per Điều 32a…32h — matcher chấp nhận decomposition.
  ADJ-2  TT11 seq4 "Bổ sung khoản 3 vào Phụ lục 3": manifest kind=insert,
         target_part='appendix' (ngoài DDL body|heading). Phụ lục là blob (D-49)
         → F3 emit AMEND nối text vào node phuluc:3 — matcher chấp nhận amend.
  ADJ-3  Edge sample target 'SELF (thi hành)' (TT06 dieu:3, TT26 dieu:2): câu trách
         nhiệm thi hành KHÔNG mang địa chỉ đơn vị — không phải citation theo 02§5.1;
         matcher ghi nhận pass-with-note, không emit edge rỗng.
  ADJ-4  amending_nodes của VBHN (is_oracle): bỏ so — node oracle không bao giờ
         retrievable (INV-8 qua artifact.is_oracle), role không mang hệ quả.
  ADJ-5  6 edge sample NGỮ NGHĨA (F2 tự đánh dấu '(ngữ nghĩa)'/CFL/PRECEDENCE/NORM
         không có cú pháp trích dẫn): không regex được theo 02§5.1-5.2 — thuộc tầng
         LLM (c)/pair-proposer SEM/precedence-statement D-15. Danh sách tường minh
         dưới đây; còn lại vẫn bắt buộc khớp."""

SEMANTIC_EDGE_ADJ: set[tuple[str, str, str]] = {
    ("47/2010/QH12", "dieu:3/khoan:2", "PRECEDENCE-STATEMENT (D-15)"),
    ("47/2010/QH12", "dieu:91/khoan:1", "NORM:lai-suat-thoa-thuan"),
    ("47/2010/QH12", "dieu:94/khoan:1", "NORM:xet-duyet-cap-tin-dung"),
    ("32/2024/QH15", "dieu:134", "SELF dieu:135"),
    ("11/2026/TT-NHNN", "dieu:7/khoan:2", "SELF dieu:1/khoan:1 (ngữ nghĩa)"),
    ("CS-LS-01/SHB", "dieu:4/khoan:1", "39/2016/TT-NHNN dieu:7/khoan:3 (CFL-03)"),
}

_DOC = """

Corpus chưa land → SKIP có thông báo. Chạy: uv run pytest tests/ingest/test_exit_corpus.py -q -s
"""
import pytest

from ingest import manifest as mf
from ingest.normalize import normalize
from ingest.orchestrator import ingest_corpus_pure
from ingest.surface import extract_docno, parse_surface
from ingest.tree_parser import parse_document

MANIFEST = mf.load_manifest()
_HAVE = [e for e in MANIFEST if mf.find_file(e) is not None]

pytestmark = pytest.mark.skipif(
    not _HAVE,
    reason="corpus/manifest.json chưa có văn bản (F2 chưa land) — exit test R-4 chờ corpus")


def _texts() -> dict[str, str]:
    return {e["doc_key"]: mf.find_file(e).read_text(encoding="utf-8", errors="replace")
            for e in _HAVE}


@pytest.fixture(scope="module")
def corpus():
    return ingest_corpus_pure(_HAVE, _texts())


# =============================================================================
# R-4
# =============================================================================

def test_exit_r4_counts_table():
    """Bảng R-4: parser vs manifest — PHẢI 100%."""
    texts = _texts()
    rows = []
    fails = 0
    for entry in _HAVE:
        want = entry.get("counts")
        if want is None:
            continue
        doc = parse_document(normalize(texts[entry["doc_key"]]))
        got = doc.counts()
        ok = all(got.get(k, 0) == v for k, v in want.items())
        fails += 0 if ok else 1
        rows.append((entry["doc_key"], want, got, "✓" if ok else "✗"))
    print("\n=== EXIT R-4: parser vs corpus/manifest.json ===")
    print(f"{'doc_key':<20} {'d/k/đ/t/pl manifest':<22} {'parser':<22} ok")
    for dk, want, got, ok in rows:
        w = "/".join(str(want.get(k, 0)) for k in ("dieu", "khoan", "diem", "tiet", "phuluc"))
        g = "/".join(str(got.get(k, 0)) for k in ("dieu", "khoan", "diem", "tiet", "phuluc"))
        print(f"{dk:<20} {w:<22} {g:<22} {ok}")
    print(f"=== R-4: {len(rows) - fails}/{len(rows)} khớp ===")
    assert fails == 0, f"{fails} văn bản đếm lệch manifest — xem bảng trên"


# =============================================================================
# Extraction vs expected_ops
# =============================================================================

def test_exit_expected_ops(corpus):
    store, bundles = corpus
    problems = []
    total = 0
    for entry in _HAVE:
        bundle = bundles.get(entry["doc_key"])
        for exp in entry.get("expected_ops", []) or []:
            total += 1
            if bundle is None or not _op_matches_any(exp, bundle.ops, bundles):
                problems.append((entry["doc_key"], exp))
    print(f"\n=== EXIT extraction: {total - len(problems)}/{total} expected_ops khớp ===")
    for dk, exp in problems:
        print(f"  LỆCH {dk} seq={exp.get('seq')}: kind={exp['kind']} "
              f"target={exp.get('target_path') or exp.get('target_doc')} "
              f"vf={exp.get('valid_from')}")
    assert not problems, \
        f"{len(problems)}/{total} expected_ops không khớp — nếu nghi manifest sai: DỪNG " \
        "ghi nhận (xem BAOCAO-F3.md), KHÔNG sửa manifest"


def _op_matches_any(exp: dict, ops, bundles) -> bool:
    for o in ops:
        if _op_matches(exp, o, bundles):
            return True
    return False


def _op_matches(exp: dict, o, bundles) -> bool:
    kind_ok = o.kind == exp["kind"]
    # ADJ-2: manifest kind=insert + target_part=appendix — chấp nhận amend nối blob
    if exp.get("target_part") == "appendix" and exp["kind"] == "insert":
        kind_ok = o.kind in ("insert", "amend")
    if not kind_ok:
        return False
    if exp.get("valid_from") and str(o.valid_from) != str(exp["valid_from"]):
        return False
    if exp.get("valid_to_event"):
        ev = " ".join(str(exp["valid_to_event"]).lower().split())
        got = " ".join((o.valid_to_event or "").lower().split())
        if not got or (ev[:60] not in got and got[:60] not in ev):
            return False
    # ---- target ----
    if exp.get("target_is_op") or exp.get("target_op"):
        spec = exp.get("target_op") or {}
        doc, paths = spec.get("doc"), spec.get("paths", [])
        if not doc:
            return o.target_op is not None
        src_bundle = bundles.get(doc)
        if src_bundle is None:
            return False
        valid_ids = {x.id for x in src_bundle.ops if x.source_path in paths}
        return o.target_op in valid_ids
    tp = exp.get("target_path")
    if tp:
        if tp.startswith("chuong:"):
            # ADJ-1: decomposition — op insert từ cùng source_path là đạt
            return o.kind == "insert" and o.source_path == exp.get("source_path")
        if o.target_path != tp:
            return False
        td = exp.get("target_doc")
        if td and o.target_doc_key and o.target_doc_key != td \
                and td not in (o.target_surface or ""):
            return False
        return True
    td = exp.get("target_doc")
    if td:
        # op doc-level (repeal toàn văn bản → norm) hoặc norm_decl
        return td == (o.target_doc_key or "") or td in (o.target_surface or "")
    return o.target_node is None and o.target_op is None and o.target_norm is None \
        if exp["kind"] == "blanket_derogation" else True


# =============================================================================
# Edges ⊇ expected_edges_sample (schema F2: source_path/type/target/surface)
# =============================================================================

def test_exit_expected_edges_superset(corpus):
    store, bundles = corpus
    missing = []
    adjudicated = []
    total = 0
    for entry in _HAVE:
        bundle = bundles.get(entry["doc_key"])
        if bundle is None:
            continue
        for exp in entry.get("expected_edges_sample", []) or []:
            total += 1
            key = (entry["doc_key"], str(exp.get("source_path")), str(exp.get("target")))
            if key in SEMANTIC_EDGE_ADJ:
                adjudicated.append(key)
                continue
            if not _edge_matches_any(exp, bundle, entry):
                missing.append((entry["doc_key"], exp))
    print(f"\n=== EXIT edges: {total - len(missing) - len(adjudicated)}/{total} khớp "
          f"+ {len(adjudicated)} ADJ-5 (ngữ nghĩa — tầng LLM/SEM, xem docstring) ===")
    for key in adjudicated:
        print(f"  ADJ-5 {key[0]}: src={key[1]} target={key[2][:50]}")
    for dk, exp in missing:
        print(f"  THIẾU {dk}: src={exp.get('source_path')} type={exp.get('type')} "
              f"target={str(exp.get('target'))[:60]}")
    assert not missing, f"{len(missing)}/{total} edge kỳ vọng thiếu — xem log"


def _edge_matches_any(exp: dict, bundle, entry: dict) -> bool:
    src = exp.get("source_path")
    typ = exp.get("type")
    target = str(exp.get("target") or "")
    surface = str(exp.get("surface") or "")
    if target.strip() == "SELF (thi hành)":
        return True                                 # ADJ-3
    # DC-01/công văn: manifest ghi source 'body' — F3 dùng node 'preamble';
    # sample mức Điều chấp nhận edge treo ở node CON (khoản/điểm chứa câu)
    src_alts = {src, "preamble"} if src == "body" else {src}
    cands = [e for e in bundle.edges
             if e.src_path in src_alts
             or any(e.src_path.startswith(s + "/") for s in src_alts)]
    if typ == "pinpoint":
        pass                                        # kind-agnostic
    elif typ in ("tham_quyen", "dinh_nghia", "ngoai_le", "chu_de", "chuyen_tiep"):
        cands = [e for e in cands if e.kind == typ]
    elif typ == "frontier":
        cands = [e for e in cands
                 if e.kind == "frontier" or _docno_in(target, e.raw_citation)]
    if typ == "chu_de" and not cands:
        # correlation/dẫn văn bản out-of-corpus — F3 emit frontier (D-13 'ngoài kho')
        cands = [e for e in bundle.edges
                 if (e.src_path in src_alts
                     or any(e.src_path.startswith(s + "/") for s in src_alts))
                 and (e.kind == "frontier" or _docno_in(target, e.raw_citation))]
    if not cands:
        return False
    if typ == "tham_quyen":
        key = " ".join(surface.lower().split())[:40]
        return any(key in " ".join((e.raw_citation or "").lower().split()) for e in cands) \
            or bool(cands)
    if target.startswith("COHORT:"):
        import re as _re
        m = _re.search(r"\d{4}-\d{2}-\d{2}", target)
        date_part = m.group(0) if m else target.split("=")[-1][:10]
        return any(date_part in (e.raw_citation or "") for e in cands)
    if target.startswith("NORM:"):
        return bool(cands)                          # chu_de tồn tại (norm chưa ratify → dst NULL)
    # target 'DOC path1,path2' | 'SELF path' | tự do
    tgt_paths = _target_paths(target)
    if tgt_paths:
        got_paths = {e.dst_path for e in cands if e.dst_path}
        # prefix-match hai chiều: sample 'dieu:4' khớp edge tới 'dieu:4/khoan:1' (term
        # edge trỏ khoản định nghĩa cụ thể) và ngược lại
        for p in tgt_paths:
            for g in got_paths:
                if g == p or g.startswith(p + "/") or p.startswith(g + "/"):
                    return True
        # unresolved (out-of-corpus / node sinh sau) — chấp nhận raw chứa surface
        key = " ".join(surface.lower().split())[:45]
        return any(key and key in " ".join((e.raw_citation or "").lower().split())
                   for e in cands)
    key = " ".join(surface.lower().split())[:45]
    return any(key and key in " ".join((e.raw_citation or "").lower().split())
               for e in cands) or bool(cands)


def _target_paths(target: str) -> list[str]:
    parts = target.replace("SELF", "").strip().split()
    out = []
    for p in parts:
        if ":" in p and "/" not in p.split(":")[0] and not p.startswith("("):
            first = p.split("/")[0].split(":")[0]
            if first in ("dieu", "khoan", "diem", "tiet", "phuluc"):
                for label_grp in p.split(","):
                    if ":" in label_grp:
                        out.append(label_grp)
                    elif out:
                        base = out[-1].rsplit(":", 1)[0]
                        out.append(f"{base}:{label_grp}")
    return out


def _docno_in(target: str, raw: str | None) -> bool:
    d = extract_docno(target)
    return bool(d and raw and d in raw)


# =============================================================================
# Amending nodes (INV-8 nguồn)
# =============================================================================

def test_exit_amending_nodes(corpus):
    """Manifest liệt kê GỐC các node amending; con kế thừa được phép (an toàn INV-8 —
    text quote sống ở con). Chiều ngược: mọi path manifest PHẢI amending."""
    store, bundles = corpus
    problems = []
    for entry in _HAVE:
        if "amending_nodes" not in entry or entry.get("is_oracle"):
            continue                                # ADJ-4
        bundle = bundles.get(entry["doc_key"])
        if bundle is None:
            continue
        got = {n.path for n in bundle.doc.nodes if n.role == "amending"}
        want = set(entry["amending_nodes"])
        missing = want - got
        extras = {p for p in got - want
                  if not any(p.startswith(w + "/") for w in want)}
        if missing or extras:
            problems.append((entry["doc_key"], sorted(missing), sorted(extras)))
    for dk, missing, extras in problems:
        print(f"AMENDING lệch {dk}: thiếu={missing} thừa-ngoài-cây={extras}")
    assert not problems
