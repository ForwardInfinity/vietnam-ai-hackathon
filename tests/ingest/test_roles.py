"""roles — R-3/R-5, bẫy #14: amending vs transition/effectivity."""
from ingest.normalize import normalize
from ingest.roles import assign_roles
from ingest.tree_parser import parse_document

from tests.ingest.fixture_corpus import FIXTURE_ENTRIES, fixture_texts


def _roles(doc_key: str):
    doc = parse_document(normalize(fixture_texts()[doc_key]))
    entry = next(e for e in FIXTURE_ENTRIES if e["doc_key"] == doc_key)
    assign_roles(doc, entry.get("doc_type", "thong_tu"))
    return doc


def test_definition_role():
    doc = _roles("39/2016/TT-NHNN")
    assert doc.node_at("dieu:2").role == "definition"
    assert doc.node_at("dieu:2/khoan:1").role == "definition"     # con kế thừa


def test_scope_effectivity_appendix():
    doc = _roles("39/2016/TT-NHNN")
    assert doc.node_at("dieu:1").role == "scope"
    assert doc.node_at("dieu:34").role == "effectivity"
    assert doc.node_at("phuluc:01").role == "appendix"


def test_rule_default():
    doc = _roles("39/2016/TT-NHNN")
    assert doc.node_at("dieu:8").role == "rule"
    assert doc.node_at("dieu:8/khoan:5").role == "rule"           # "trừ trường hợp" giữ rule (R-3)


def test_amending_nodes_per_manifest():
    """amending đúng danh sách đếm tay của từng fixture (⇒ retrievable=false — INV-8)."""
    for entry in FIXTURE_ENTRIES:
        doc = _roles(entry["doc_key"])
        got = sorted(n.path for n in doc.nodes if n.role == "amending")
        assert got == sorted(entry.get("amending_nodes", [])), \
            f"{entry['doc_key']}: amending={got}, expected={entry.get('amending_nodes')}"


def test_trap14_transition_effectivity_of_amending_doc_not_amending():
    """Bẫy contamination #14: Đ3 (chuyển tiếp — chứa cả chữ 'sửa đổi, bổ sung hợp đồng')
    và Đ4 (hiệu lực) của TT06 mang quy phạm thật — KHÔNG phải amending."""
    doc = _roles("06/2023/TT-NHNN")
    assert doc.node_at("dieu:3").role == "transition"
    assert doc.node_at("dieu:4").role == "effectivity"
    assert doc.node_at("dieu:2").role == "rule"                   # trách nhiệm tổ chức thực hiện


def test_trap14_tt10_suspension_not_amending_no_quote():
    """R-3 đúng chữ: amending = động-từ-hiệu-lực + QUOTE. TT10 Đ1 không quote →
    không có text để contaminate → KHÔNG amending (khớp quy ước manifest F2);
    nội dung ngưng vẫn sống qua op suspend."""
    doc = _roles("10/2023/TT-NHNN")
    assert doc.node_at("dieu:1").role == "rule"
    assert doc.node_at("dieu:3").role == "effectivity"            # "Hiệu lực thi hành" của chính TT10


def test_effectivity_containing_norm_decl_stays_effectivity():
    # TT32 Đ4 chứa norm_decl + blanket nhưng heading 'Hiệu lực thi hành' → effectivity
    doc = _roles("32/2026/TT-NHNN")
    assert doc.node_at("dieu:4").role == "effectivity"
    assert doc.node_at("dieu:3").role == "transition"
