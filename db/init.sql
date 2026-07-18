-- =============================================================================
-- LawState DDL — NGUYÊN VĂN docs/03-SYSTEM-SPEC.md §S2 (authoritative)
-- + trigger R-1 (phần cuối file). KHÔNG sửa DDL ở đây mà không sửa spec trước.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE audience_t   AS ENUM ('public','internal','restricted');
CREATE TYPE op_kind_t    AS ENUM ('amend','insert','repeal','suspend','close_window',
                                  'dinh_chinh','norm_decl','blanket_derogation');
CREATE TYPE op_status_t  AS ENUM ('proposed','ratified','rejected','superseded');
CREATE TYPE node_role_t  AS ENUM ('rule','definition','scope','exception','transition',
                                  'effectivity','amending','form','appendix');
CREATE TYPE nv_status_t  AS ENUM ('active','suspended','repealed');
CREATE TYPE edge_kind_t  AS ENUM ('dinh_nghia','tham_quyen','ngoai_le','chu_de','chuyen_tiep','frontier');
CREATE TYPE risk_t       AS ENUM ('definitional','prescriptive');
CREATE TYPE cfl_label_t  AS ENUM ('mau_thuan','chat_hon_ve_minh','chat_hon_ve_doi_tac','khac_pham_vi');
CREATE TYPE cfl_fork_t   AS ENUM ('internal_internal','internal_external','external_external','advisory');
CREATE TYPE cfl_status_t AS ENUM ('open','resolved','dismissed','accepted_risk');
CREATE TYPE sev_t        AS ENUM ('interruptive','advisory');
CREATE TYPE pev_kind_t   AS ENUM ('open_suspension','open_conflict');

-- L0: log bất biến
CREATE TABLE artifact (
  id            text PRIMARY KEY,          -- sha256 file
  doc_key       text UNIQUE NOT NULL,      -- '39/2016/TT-NHNN'
  doc_type      text NOT NULL,             -- luat|nghi_quyet|nghi_dinh|thong_tu|quyet_dinh|cong_van|noi_bo|bieu_mau|vbhn
  issuer        text NOT NULL,             -- 'QH','CP','NHNN','HDTP','SHB.<phòng>'
  title         text,
  issued_date   date, effective_date date,
  audience      audience_t NOT NULL DEFAULT 'internal',
  owner         text,                      -- phòng ban (corpus trong) — đích blast-radius
  review_by     date,                      -- hook doctrine D-50
  channel       text,                      -- 'congbao','sbv','internal_registry',...
  is_oracle     boolean NOT NULL DEFAULT false,  -- VBHN: chỉ để diff, không vào retrieval
  synthetic     boolean NOT NULL DEFAULT false,
  ingested_at   timestamptz NOT NULL DEFAULT now(),   -- TRỤC K
  raw bytea, text text);

-- L1: danh tính bền
CREATE TABLE node (
  id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),   -- birth-id, không tái dùng (INV-2)
  artifact_id text NOT NULL REFERENCES artifact,
  parent_id   uuid REFERENCES node,
  path        text NOT NULL,               -- 'dieu:8/khoan:2/diem:a/tiet:iii' | 'phuluc:04' (địa chỉ LÚC SINH)
  label       text, seq int,
  role        node_role_t NOT NULL DEFAULT 'rule',
  page_anchor jsonb);

CREATE TABLE alias (                        -- địa chỉ bề mặt -> node, có thời gian tính
  doc_key text, path text, node_id uuid REFERENCES node,
  valid_from date, valid_to date,
  PRIMARY KEY (doc_key, path, valid_from));

CREATE TABLE norm (                         -- danh tính xuyên thay-thế-toàn-văn-bản (D-09)
  id uuid, topic text NOT NULL,             -- cùng id xuyên chuỗi kế vị; 1 hàng mỗi hiện thân
  artifact_id text REFERENCES artifact,
  valid_from date, valid_to date,
  correlation jsonb,                        -- tương chiếu cũ↔mới — NON-BINDING (D-08)
  PRIMARY KEY (id, artifact_id));

-- L2: toán tử, append-only
CREATE TABLE op (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  kind op_kind_t NOT NULL,
  source_artifact text NOT NULL REFERENCES artifact,
  source_node uuid REFERENCES node,         -- điều khoản sửa đổi sinh op này (provenance)
  source_quote text NOT NULL,               -- span nguyên văn — UI đối chiếu, bắt buộc
  seq int NOT NULL,                         -- thứ tự xuất hiện TRONG artifact (tie-break §S4.5)
  target_node uuid REFERENCES node,
  target_op   uuid REFERENCES op,           -- op nhắm op (D-10)
  target_norm uuid,
  target_part text NOT NULL DEFAULT 'body' CHECK (target_part IN ('body','heading')),
  new_text text, new_heading text,
  valid_from date, valid_to date,
  valid_to_event text,                      -- sự kiện chưa định danh (D-11)
  scope_predicate jsonb,                    -- DSL đóng D-25
  risk_class risk_t,
  extractor text NOT NULL,                  -- 'rule','llm:<model>','curator:<id>'
  confidence real,
  status op_status_t NOT NULL DEFAULT 'proposed',
  ratified_by text, ratified_at timestamptz,
  ratify_batch uuid,
  superseded_by uuid REFERENCES op,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(target_node, target_op, target_norm) = 1
         OR kind = 'blanket_derogation'),
  CHECK (kind <> 'blanket_derogation' OR num_nonnulls(target_node,target_op,target_norm) = 0),
  CHECK (kind NOT IN ('amend','insert','dinh_chinh') OR new_text IS NOT NULL OR new_heading IS NOT NULL),
  CHECK (kind <> 'close_window' OR target_op IS NOT NULL));

CREATE TABLE ratify_batch (                 -- duyệt lô D-19
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  invariant_template jsonb NOT NULL,        -- S4.4
  description text, approved_by text NOT NULL, approved_at timestamptz NOT NULL DEFAULT now(),
  spot_check_rate real NOT NULL DEFAULT 0.1, spot_checked uuid[]);

-- Edge dẫn xuất theo PHIÊN BẢN node nguồn (D-13)
CREATE TABLE edge (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  src_node uuid NOT NULL REFERENCES node, src_version int NOT NULL,
  dst_node uuid REFERENCES node, dst_norm uuid, frontier_ref text,
  kind edge_kind_t NOT NULL, raw_citation text,
  resolved_against date,                    -- alias tra tại ngày văn bản nguồn
  confidence real NOT NULL DEFAULT 1.0,
  CHECK (num_nonnulls(dst_node, dst_norm, frontier_ref) <= 1));  -- cả ba NULL = unresolved (backlog)

-- L3: SNAPSHOT — thứ DUY NHẤT được index & trích dẫn (D-01)
CREATE TABLE node_version (
  node_id uuid NOT NULL REFERENCES node, version int NOT NULL,
  heading text, body text,
  status nv_status_t NOT NULL,
  valid_from date NOT NULL, valid_to date,  -- nửa-mở [from, to)
  scope_predicate jsonb, scope_hash text NOT NULL DEFAULT '',   -- chiều s TRONG khóa (D-04)
  provenance uuid[] NOT NULL,               -- chuỗi op tạo version này
  run_id uuid NOT NULL,
  retrievable boolean NOT NULL,             -- false ⟺ role='amending' ∨ artifact.is_oracle (INV-8)
  embedding vector(1024),
  PRIMARY KEY (node_id, version),
  UNIQUE (node_id, valid_from, scope_hash, status, run_id));
CREATE INDEX ON node_version (valid_from, valid_to) WHERE retrievable;
CREATE INDEX ON node_version USING hnsw (embedding vector_cosine_ops) WHERE retrievable;

CREATE TABLE replay_run (
  run_id uuid PRIMARY KEY, k_cutoff timestamptz NOT NULL,
  corpus_hash text NOT NULL, started timestamptz, finished timestamptz, ops_count int);

CREATE TABLE conflict (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  member_versions jsonb NOT NULL,           -- [{node_id, version}] — unsat-core tối thiểu
  tier int NOT NULL CHECK (tier IN (1,2,3)),
  label cfl_label_t, fork cfl_fork_t,
  doctrine jsonb,                           -- {rank_a, rank_b, same_issuer, art156: 'ap_dung'|'khong_phan_dinh'}
  reason text NOT NULL,
  status cfl_status_t NOT NULL DEFAULT 'open',
  resolved_by_op uuid REFERENCES op, ticket_ref text,
  detected_by text, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE notification (                 -- blast-radius (D-36)
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  op_id uuid REFERENCES op, affected_node uuid, affected_doc text, owner text,
  severity sev_t NOT NULL DEFAULT 'advisory',
  acked boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE coverage (channel text PRIMARY KEY, last_seq text, last_checked timestamptz);

CREATE TABLE pending_event (                -- D-11
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  kind pev_kind_t NOT NULL,
  ref uuid NOT NULL,                        -- op có valid_to_event | conflict chờ statement giải
  predicate text NOT NULL,                  -- "văn bản QPPL mới quy định về các vấn đề này"
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
  closed_by_op uuid REFERENCES op);

CREATE TABLE precedence (                   -- quy tắc ưu tiên là statement CÓ NGUỒN (D-15)
  doc_type text, issuer text, rank int NOT NULL,
  source_node uuid, valid_from date, valid_to date);

CREATE TABLE answer_log (                   -- append-only, replay được (INV-10)
  qa_id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id uuid, question text NOT NULL,
  audience audience_t NOT NULL, as_of date NOT NULL, as_known timestamptz,
  tier char(1) NOT NULL CHECK (tier IN ('A','B','C','D')),
  claims jsonb NOT NULL,                    -- [{text, node_version_refs[], hard_pass, judge_verdict}]
  retrieved jsonb NOT NULL, conflicts uuid[], banners jsonb NOT NULL,
  run_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE feedback (                     -- kênh SEM (d) — D-37
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  qa_id uuid REFERENCES answer_log, node_id uuid, kind text NOT NULL DEFAULT 'nghi_da_cu',
  note text, created_at timestamptz NOT NULL DEFAULT now());

-- Views
CREATE VIEW v_consolidation_pending AS      -- node có op proposed đã đến hạn hiệu lực
  SELECT DISTINCT target_node AS node_id FROM op
  WHERE status='proposed' AND valid_from <= current_date AND target_node IS NOT NULL;

-- =============================================================================
-- R-1: trigger cấm UPDATE/DELETE trên artifact, op (sau ratify), answer_log,
-- node_version (chỉ replay ghi — transaction replay phải SET LOCAL lawstate.replay = 'on').
-- Đây là hiện thân DB của INV-1; test: tests/test_db_triggers.py.
-- =============================================================================

CREATE OR REPLACE FUNCTION deny_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'INV-1 append-only: % on % is forbidden', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'raise_exception';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER artifact_append_only
  BEFORE UPDATE OR DELETE ON artifact
  FOR EACH ROW EXECUTE FUNCTION deny_mutation();

CREATE TRIGGER answer_log_append_only
  BEFORE UPDATE OR DELETE ON answer_log
  FOR EACH ROW EXECUTE FUNCTION deny_mutation();

-- op: proposed sửa/xóa tự do (queue làm việc); sau ratify BẤT BIẾN (D-20) trừ đúng một
-- chuyển tiếp ratified -> superseded chỉ đổi (status, superseded_by) — mọi cột khác giữ nguyên.
CREATE OR REPLACE FUNCTION op_immutable_after_ratify() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'proposed' THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'INV-1: DELETE op % (status=%) forbidden — op sau ratify là bất biến', OLD.id, OLD.status;
  END IF;
  IF OLD.status = 'proposed' THEN
    RETURN NEW;
  END IF;
  IF OLD.status = 'ratified' AND NEW.status = 'superseded' AND NEW.superseded_by IS NOT NULL
     AND (to_jsonb(NEW) - 'status' - 'superseded_by') = (to_jsonb(OLD) - 'status' - 'superseded_by')
  THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'INV-1: UPDATE op % (status=%) forbidden — sửa lỗi = op mới + superseded_by (D-20)', OLD.id, OLD.status;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER op_append_only
  BEFORE UPDATE OR DELETE ON op
  FOR EACH ROW EXECUTE FUNCTION op_immutable_after_ratify();

-- node_version: chỉ transaction replay (SET LOCAL lawstate.replay = 'on') được UPDATE/DELETE.
CREATE OR REPLACE FUNCTION node_version_replay_only() RETURNS trigger AS $$
BEGIN
  IF current_setting('lawstate.replay', true) = 'on' THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'INV-1: % node_version ngoài replay transaction bị cấm (SET LOCAL lawstate.replay = ''on'')', TG_OP;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER node_version_replay_guard
  BEFORE UPDATE OR DELETE ON node_version
  FOR EACH ROW EXECUTE FUNCTION node_version_replay_only();
