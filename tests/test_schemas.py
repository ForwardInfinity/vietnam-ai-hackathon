"""Contracts: enum khớp từng giá trị với db/init.sql; đủ 16 model bảng; pipeline models đúng spec."""
from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api import schemas as s

# Nguồn chân lý: docs/03 S2 (db/init.sql) — nếu test này đỏ, schema hoặc DDL đã lệch spec
SQL_ENUMS = {
    s.AudienceT: {"public", "internal", "restricted"},
    s.OpKindT: {"amend", "insert", "repeal", "suspend", "close_window",
                "dinh_chinh", "norm_decl", "blanket_derogation"},
    s.OpStatusT: {"proposed", "ratified", "rejected", "superseded"},
    s.NodeRoleT: {"rule", "definition", "scope", "exception", "transition",
                  "effectivity", "amending", "form", "appendix"},
    s.NvStatusT: {"active", "suspended", "repealed"},
    s.EdgeKindT: {"dinh_nghia", "tham_quyen", "ngoai_le", "chu_de", "chuyen_tiep", "frontier"},
    s.RiskT: {"definitional", "prescriptive"},
    s.CflLabelT: {"mau_thuan", "chat_hon_ve_minh", "chat_hon_ve_doi_tac", "khac_pham_vi"},
    s.CflForkT: {"internal_internal", "internal_external", "external_external", "advisory"},
    s.CflStatusT: {"open", "resolved", "dismissed", "accepted_risk"},
    s.SevT: {"interruptive", "advisory"},
    s.PevKindT: {"open_suspension", "open_conflict"},
}

TABLE_MODELS = [
    s.Artifact, s.Node, s.Alias, s.Norm, s.Op, s.RatifyBatch, s.Edge, s.NodeVersion,
    s.ReplayRun, s.Conflict, s.Notification, s.Coverage, s.PendingEvent, s.Precedence,
    s.AnswerLog, s.Feedback,
]


def test_enums_match_sql_values_exactly():
    for enum_cls, expected in SQL_ENUMS.items():
        assert {e.value for e in enum_cls} == expected, enum_cls.__name__


def test_enum_values_present_in_init_sql():
    import pathlib
    ddl = (pathlib.Path(__file__).parent.parent / "db" / "init.sql").read_text(encoding="utf-8")
    for enum_cls, expected in SQL_ENUMS.items():
        for v in expected:
            assert f"'{v}'" in ddl, f"{enum_cls.__name__}.{v} không có trong init.sql"


def test_all_16_table_models_exist():
    assert len(TABLE_MODELS) == 16


def test_op_model_roundtrip():
    op = s.Op(kind="amend", source_artifact="sha1", source_quote="Sửa đổi khoản 2...",
              seq=1, target_node=uuid4(), new_text="Nội dung mới", extractor="rule")
    assert s.Op.model_validate_json(op.model_dump_json()) == op
    assert op.status == s.OpStatusT.proposed


def test_scope_predicate_dsl_is_closed():
    # D-25: DSL đóng — predicate lạ phải bị từ chối ngay ở parse
    s.ScopePredicate(contract_signed_before=date(2023, 9, 1))
    with pytest.raises(ValidationError):
        s.ScopePredicate(loan_amount_over=1000)


def test_compiled_question_matches_s51():
    cq = s.CompiledQuestion(topic_terms=["lãi suất", "cho vay"], as_of=date(2023, 9, 1),
                            audience="employee", mode="point_in_time")
    dumped = cq.model_dump()
    assert set(dumped) == {"topic_terms", "as_of", "as_known", "cohort", "audience", "mode", "pinpoint"}
    with pytest.raises(ValidationError):
        s.CompiledQuestion(topic_terms=[], as_of=date.today(), audience="employee", mode="latest")


def test_extracted_op_requires_source_quote():
    # R-11: source_quote NGUYÊN VĂN BẮT BUỘC
    with pytest.raises(ValidationError):
        s.ExtractedOp(kind="repeal", target_surface="Điều 8")
    op = s.ExtractedOp(kind="repeal", target_surface="Điều 8", source_quote="bãi bỏ Điều 8")
    assert "close_window" not in s.ExtractedOp.model_fields["kind"].annotation.__args__


def test_composer_output_matches_r31():
    out = s.ComposerOutput(
        answer_vi="Lãi suất thỏa thuận [1].",
        claims=[s.ComposerClaim(id="[1]", text="Lãi suất thỏa thuận", refs=["[1]"])],
        bases=[s.ComposerBasis(ref="[1]", citation_vi="Điều 13 TT 39/2016/TT-NHNN",
                               interval="15/03/2017 → nay")],
    )
    assert out.refusal is None


def test_answer_tier_d_shape():
    ans = s.Answer(tier="D", audience="customer", as_of=date.today(),
                   refusal_reason="ngoài coverage")
    data = ans.model_dump()
    for key in ("answer", "bases", "conflicts", "upcoming_changes", "banners", "coverage"):
        assert data[key] == []
    with pytest.raises(ValidationError):
        s.Answer(tier="E", audience="employee", as_of=date.today())
