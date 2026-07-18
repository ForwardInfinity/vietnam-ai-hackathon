# engine — chữ ký public cho F5/F7 (spec: 03 S4.5-S4.8)

- `fold.fold_corpus(nodes: [NodeInput], ops: [schemas.Op], artifacts: {id: ArtifactInput}|[...], precedence=None, k_cutoff: datetime|None) -> CorpusFold` — pure, không DB; `.versions: {node_id: (Version,…)}`, `.certificates`, `.open_suspensions`, `.norm_events`, `.screening_seeds`.
- `fold.materialize_at(versions, as_of: date, cohort=None, status=None) -> [Version]` · `active_intervals(versions)` · `ever_active(versions)` · `verify_tiling(versions_by_node) -> [lỗi]` · `state_digest(cf) -> sha256`.
- `scope.applicability_matches(version_scope, cohort) -> bool` (cohort thiếu ⇒ match mọi nhánh; nhánh bù = `{"complement_of": P}` trong `node_version.scope_predicate`) · `scope_hash(pred) -> str` ('' = universal).
- `snapshot.replay(conn, k_cutoff=None, precedence=None, base_text_provider=..., on_snapshot_written=None) -> {run_id, versions, certificates, pending_open, state_digest}` — MỘT transaction, run_id mới; `on_snapshot_written(conn, run_id)` = hook F5 rebuild embedding/BM25 (R-19). Text gốc node đọc từ `node.page_anchor.heading/body` (F3 ghi lúc parse) hoặc provider tùy biến.
- `sweep.sweep_pending(pending, ops_by_id=, artifact=, artifacts=, artifact_ops=(), llm=None) -> [SweepProposal]` — op `close_window` status=PROPOSED (máy không tự đóng, R-21).
- `oracle_diff.materialize_doc(nodes, versions_by_node, doc_key, as_of) -> {path: text}` · `oracle_diff(materialized, oracle, doc_key) -> [OracleMismatch]` (R-22).
- `blast_radius.notifications_for_op(op, ops_by_id=, nodes_by_id=, artifacts=, edges=, norm_memberships=None) -> [schemas.Notification]` — interruptive ⟺ risk definitional (D-36).
- `conflict.default_precedence()` · `precedence_rank(doc_type, issuer, at, rows)` · `label_pair(a, b, llm) -> nhãn|None` (chat_hon_ve_minh TỰ LOẠI, D-34) · `fork_for(issuer_a, issuer_b)` (D-35).
- `invariants.run_all(EffectiveState) -> [Violation]` · `effective_state(cf, nodes, artifacts, as_of)` · registry `register/set_enabled` (ship INV-COMP-01/02).
- `fixtures.load_dir(path=tests/fixtures/ops) -> FixtureCorpus` (demo corpus, id tất định) · QA script: `python -m engine.story`.
- Quy ước op cho F3: op mang `scope_predicate` = cohort ĐƯỢC MIỄN TRỪ (điều khoản chuyển tiếp); fold tách nhánh (V∧P giữ text cũ) + (V∧¬P áp op).
