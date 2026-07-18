"""demo.py — `python -m ingest.demo <doc_key>` in cây + op đề xuất để soi bằng mắt.

Không cần DB, không cần LLM (thêm --llm để gọi gateway thật). Nạp TOÀN BỘ corpus
(hoặc fixtures khi corpus chưa có) vào MemoryStore theo thứ tự ban hành để resolve
cross-doc, rồi in báo cáo cho doc_key yêu cầu.

  python -m ingest.demo 06/2023/TT-NHNN
  python -m ingest.demo --fixtures 06/2023/TT-NHNN     # dùng tests/ingest/fixtures
  python -m ingest.demo --list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ingest import manifest as mf
from ingest.model import IngestBundle
from ingest.orchestrator import ingest_corpus_pure

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "ingest" / "fixtures"


def _load_corpus(use_fixtures: bool) -> tuple[list[dict], dict[str, str]]:
    entries = [] if use_fixtures else mf.load_manifest()
    texts: dict[str, str] = {}
    if entries:
        for e in entries:
            f = mf.find_file(e)
            if f is not None:
                texts[e["doc_key"]] = f.read_text(encoding="utf-8", errors="replace")
    if not texts:
        # corpus chưa có (F2 chưa land) → fixtures mini của F3
        sys.stderr.write("[demo] corpus/manifest.json chưa có văn bản — dùng tests/ingest/fixtures\n")
        try:
            from tests.ingest.fixture_corpus import FIXTURE_ENTRIES, fixture_texts
        except ImportError:
            sys.path.insert(0, str(FIXTURE_DIR.parent.parent.parent))
            from tests.ingest.fixture_corpus import FIXTURE_ENTRIES, fixture_texts
        entries = FIXTURE_ENTRIES
        texts = fixture_texts()
    return entries, texts


def _fmt_date(d) -> str:
    return d.isoformat() if d else "—"


def print_tree(bundle: IngestBundle) -> None:
    doc = bundle.doc
    meta = bundle.meta
    print("═" * 78)
    print(f"{meta['doc_key']}  ·  {meta.get('doc_type')}  ·  {meta.get('issuer')}"
          f"  ·  ban hành {_fmt_date(meta.get('issued_date'))}"
          f"  ·  hiệu lực {_fmt_date(meta.get('effective_date'))}")
    if meta.get("title"):
        print(f"  {meta['title'][:110]}")
    print(f"  sha256={bundle.sha256[:16]}…  oracle={meta.get('is_oracle', False)}")
    print("─" * 78)
    counts = doc.counts()
    print("  Đếm R-4: " + "  ".join(f"{k}={v}" for k, v in counts.items()))
    print("─" * 78)
    for n in doc.nodes:
        depth = n.path.count("/")
        indent = "  " * (depth + 1)
        head = f" — {n.heading}" if n.heading else ""
        body_preview = (n.body[:60].replace("\n", " ") + "…") if len(n.body) > 60 \
            else n.body.replace("\n", " ")
        role_mark = f" [{n.role}]" if n.role != "rule" else ""
        print(f"{indent}{n.path}{role_mark}{head}")
        if body_preview:
            print(f"{indent}   │ {body_preview}")
    born = [n for n in bundle.nodes if n.born_of_op]
    if born:
        print("─" * 78)
        print("  Node MỚI do op insert tạo (birth-id lúc đề xuất — R-12):")
        for n in born:
            print(f"    + {n.artifact_doc_key} :: {n.path}  ({str(n.id)[:8]}…)")


def print_edges(bundle: IngestBundle) -> None:
    if bundle.meta.get("is_oracle"):
        return
    print("─" * 78)
    by_kind: dict[str, int] = {}
    unresolved = 0
    for e in bundle.edges:
        by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
        if not e.resolved:
            unresolved += 1
    print(f"  Edges: {len(bundle.edges)}  ({', '.join(f'{k}={v}' for k, v in sorted(by_kind.items()))})"
          f"  · unresolved(backlog)={unresolved}")
    for e in bundle.edges[:40]:
        dst = e.dst_path and f"{e.dst_doc_key or '?'}::{e.dst_path}" \
            or (e.frontier_ref and f"frontier:{e.frontier_ref}") \
            or (e.dst_norm and f"norm:{str(e.dst_norm)[:8]}") or "∅ UNRESOLVED"
        print(f"    {e.src_path:38s} —{e.kind:>11s}→ {dst}   ({e.confidence:.2f})")
    if len(bundle.edges) > 40:
        print(f"    … và {len(bundle.edges) - 40} edge nữa")


def print_ops(bundle: IngestBundle) -> None:
    if bundle.meta.get("is_oracle"):
        print("  (VBHN oracle — không sinh op, chỉ để diff — R-7)")
        return
    print("─" * 78)
    print(f"  OP ĐỀ XUẤT: {len(bundle.ops)} (tất cả status=proposed — chờ người phê chuẩn, D-03)")
    for op in bundle.ops:
        tgt = op.target_op and f"op:{str(op.target_op)[:8]}… (op-nhắm-op D-10)" \
            or op.target_norm and f"norm:{str(op.target_norm)[:8]}…" \
            or (op.target_doc_key or "?") + "::" + (op.target_path or "∅")
        if op.kind == "blanket_derogation":
            tgt = "(targetless)"
        window = f"{_fmt_date(op.valid_from)}"
        if op.valid_to:
            window += f" → {_fmt_date(op.valid_to)}"
        if op.valid_to_event:
            window += f" → SỰ KIỆN: “{op.valid_to_event[:60]}…”" if len(op.valid_to_event) > 60 \
                else f" → SỰ KIỆN: “{op.valid_to_event}”"
        flags = f"  ⚑{','.join(op.red_flags)}" if op.red_flags else ""
        print(f"  [{op.seq:>3}] {op.kind:<18s} {tgt}")
        print(f"        part={op.target_part} · {window} · queue={op.queue}({op.risk_class})"
              f" · conf={op.confidence:.2f} · {op.extractor}{flags}")
        if op.scope_predicate:
            print(f"        scope={op.scope_predicate}")
        if op.phrase_from:
            print(f"        phrase: “{op.phrase_from}” → “{op.phrase_to}” (D-21 materialize)")
        quote = op.source_quote.replace("\n", " ")
        print(f"        quote: {quote[:100]}{'…' if len(quote) > 100 else ''}")
        if op.new_heading:
            print(f"        new_heading: {op.new_heading[:80]}")
        if op.new_text:
            nt = op.new_text.replace("\n", " ")
            print(f"        new_text: {nt[:100]}{'…' if len(nt) > 100 else ''}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ingest.demo")
    ap.add_argument("doc_key", nargs="?", help="vd 06/2023/TT-NHNN")
    ap.add_argument("--fixtures", action="store_true", help="dùng tests/ingest/fixtures thay corpus")
    ap.add_argument("--llm", action="store_true", help="bật tầng LLM (cần API key)")
    ap.add_argument("--list", action="store_true", help="liệt kê doc_key khả dụng")
    args = ap.parse_args(argv)

    entries, texts = _load_corpus(args.fixtures)
    if args.list or not args.doc_key:
        print("doc_key khả dụng:")
        for e in entries:
            mark = "✓" if e["doc_key"] in texts else "✗ (thiếu file)"
            print(f"  {e['doc_key']:<28s} {mark}")
        return 0

    gateway = None
    if args.llm:
        from answer.llm_gateway import get_gateway
        gateway = get_gateway()

    store, bundles = ingest_corpus_pure(entries, texts, gateway=gateway)
    bundle = bundles.get(args.doc_key)
    if bundle is None:
        print(f"doc_key {args.doc_key!r} không có trong corpus/fixtures. Dùng --list để xem.")
        return 1
    print_tree(bundle)
    print_edges(bundle)
    print_ops(bundle)
    print("═" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
