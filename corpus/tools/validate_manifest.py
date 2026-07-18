#!/usr/bin/env python3
"""Validator for corpus/manifest.json (ground truth gate — 04 §1.4).

Checks: schema, sha256, dates + date-quotes, counts by BOTH independent methods,
every target_surface/edge surface/transition surface literally present in source,
anchor facts (verified independently against Công báo) as hard asserts, and the
structural prerequisites of the golden items that will point at the fixtures.
Exit 0 = all green.
"""
import datetime, hashlib, json, pathlib, re, sys, unicodedata

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE.parent
sys.path.insert(0, str(HERE))
from count_grammar import count  # noqa: E402
from verify_counts_sequential import audit  # noqa: E402

ERRORS = []
WARN = []


def err(msg):
    ERRORS.append(msg)


def check(cond, msg):
    if not cond:
        err(msg)
    return cond


REQUIRED = ['doc_key', 'slug', 'title', 'doc_type', 'sha256', 'issued_date',
            'synthetic', 'is_oracle', 'excerpt', 'audience', 'channel',
            'counts', 'expected_ops', 'expected_norm_events',
            'expected_edges_sample', 'amending_nodes']
OP_KINDS = {'amend', 'insert', 'repeal', 'suspend', 'close_window',
            'dinh_chinh', 'norm_decl', 'blanket_derogation'}
EDGE_TYPES = {'tham_quyen', 'dinh_nghia', 'ngoai_le', 'chuyen_tiep', 'chu_de', 'frontier', 'pinpoint'}
PATH_RE = re.compile(r'^(preamble|body|(dieu:\d+[a-zđ]?|phuluc:\d+|chuong:[IVX]+/muc:\d+)'
                     r'(/khoan:\d+[a-zđ]?)?(/diem:[a-zđ][0-9]?)?(/tiet:[ivx]+)?)$')
DSL_KEYS = {'contract_signed_before', 'not_amended_on_or_after', 'entity_class'}


def iso(d):
    try:
        datetime.date.fromisoformat(d)
        return True
    except (TypeError, ValueError):
        return False


def main():
    manifest = json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8'))
    docs = {d['doc_key']: d for d in manifest['documents']}
    texts = {}

    for key, d in docs.items():
        tag = f'[{key}]'
        for f in REQUIRED:
            check(f in d and d[f] is not None or f in d, f'{tag} thiếu field {f}')
        path = CORPUS / 'text' / f"{d['slug']}.txt"
        if not check(path.exists(), f'{tag} thiếu file text {path}'):
            continue
        text = path.read_text(encoding='utf-8')
        texts[key] = text
        check(unicodedata.is_normalized('NFC', text), f'{tag} text không NFC')
        check(hashlib.sha256(text.encode()).hexdigest() == d['sha256'], f'{tag} sha256 lệch')

        # dates
        check(iso(d['issued_date']), f"{tag} issued_date không hợp lệ: {d['issued_date']}")
        if d['is_oracle']:
            pass  # VBHN không có hiệu lực riêng (D-22)
        else:
            check(iso(d['effective_date']), f"{tag} effective_date không hợp lệ: {d['effective_date']}")
            if iso(d['issued_date']) and iso(d['effective_date']):
                check(d['issued_date'] <= d['effective_date'],
                      f"{tag} issued > effective ({d['issued_date']} > {d['effective_date']})")
        for qf in ('issued_date_quote', 'effective_date_quote'):
            q = d.get(qf)
            if q:
                check(q in text, f'{tag} {qf} không có trong text: {q[:60]}…')

        # counts — hai phương pháp độc lập
        c1 = count(text)
        m1 = {k: c1[k] for k in ('dieu', 'khoan', 'diem', 'tiet', 'phuluc')}
        check(m1 == d['counts'], f"{tag} counts lệch method-1 (pattern): manifest={d['counts']} regex={m1}")
        total2, anomalies = audit(str(path))
        m2 = {'dieu': total2['dieu'], 'khoan': total2['khoan'], 'diem': total2['diem'], 'tiet': total2['tiet']}
        m1b = {k: m1[k] for k in m2}
        check(m1b == m2, f'{tag} counts lệch method-2 (sequence): {m1b} vs {m2}')
        known = {'22/2019/TT-NHNN': 1, '41/2016/TT-NHNN': 1}  # công thức mất dòng '1.' — ghi trong transcription_notes
        check(len(anomalies) <= known.get(key, 0),
              f'{tag} sequence anomalies mới: {anomalies}')

        # ops
        seqs = set()
        for o in d['expected_ops']:
            otag = f"{tag} op#{o['seq']}"
            check(o['kind'] in OP_KINDS, f"{otag} kind lạ: {o['kind']}")
            check(o['seq'] not in seqs, f'{otag} seq trùng')
            seqs.add(o['seq'])
            check(o['target_surface'] in text, f"{otag} target_surface KHÔNG có trong nguồn: {o['target_surface'][:70]}…")
            check(iso(o['valid_from']), f"{otag} valid_from không hợp lệ")
            check(PATH_RE.match(o['source_path']), f"{otag} source_path sai convention: {o['source_path']}")
            if o['kind'] == 'suspend':
                check(bool(o.get('valid_to_event')), f'{otag} suspend thiếu valid_to_event (D-11)')
                check(o['valid_to_event'] in text, f'{otag} valid_to_event không nguyên văn trong text')
            if o['kind'] == 'dinh_chinh':
                check(o.get('retroactive_to_window_start') is True, f'{otag} dinh_chinh thiếu cờ hồi tố (D-12)')
            if o.get('target_is_op'):
                check(o['kind'] in ('repeal', 'amend', 'close_window'), f'{otag} target_is_op với kind lạ')
                check(bool(o.get('target_op', {}).get('paths')), f'{otag} target_is_op thiếu target_op.paths')

        for t in d.get('expected_transitions', []):
            check(t['surface'] in text, f"{tag} transition surface không trong text: {t['surface'][:60]}…")
            sp = t['scope_predicate']
            check(set(sp) <= DSL_KEYS, f'{tag} scope_predicate ngoài DSL D-25: {set(sp) - DSL_KEYS}')
            for v in sp.values():
                check(iso(v), f'{tag} scope_predicate value không phải date: {v}')

        for e in d['expected_edges_sample']:
            check(e['type'] in EDGE_TYPES, f"{tag} edge type lạ: {e['type']}")
            check(e['surface'] in text, f"{tag} edge surface không trong text: {e['surface'][:70]}…")
        if not d['is_oracle']:
            check(len(d['expected_edges_sample']) >= 5, f"{tag} edges_sample < 5 ({len(d['expected_edges_sample'])})")

        for p in d['amending_nodes']:
            check(PATH_RE.match(p), f'{tag} amending_node path sai: {p}')
        if not d['synthetic'] and not d['is_oracle'] and not d['excerpt']:
            check(bool(d.get('source_url')), f'{tag} thiếu source_url')

    # ===================== ANCHOR FACTS (đối chiếu độc lập Công báo) =====================
    tt06 = docs['06/2023/TT-NHNN']
    assert tt06['issued_date'] == '2023-06-28', 'ANCHOR: TT06 ban hành 28/06/2023'
    assert tt06['effective_date'] == '2023-09-01', 'ANCHOR: TT06 hiệu lực 01/09/2023'
    o_d8 = [o for o in tt06['expected_ops'] if o['source_path'] == 'dieu:1/khoan:2']
    assert len(o_d8) == 1 and o_d8[0]['kind'] == 'amend' and o_d8[0].get('target_path') == 'dieu:8', \
        'ANCHOR: k2 Đ1 TT06 sửa đổi/bổ sung Đ8'
    assert 'khoản 8' in (o_d8[0].get('notes') or '') and '10' in o_d8[0]['notes'], \
        'ANCHOR: Đ8 bản mới thêm k8–10 (ghi trong notes op)'
    assert tt06['expected_transitions'], 'ANCHOR: TT06 có điều khoản chuyển tiếp HĐ ký trước'
    assert tt06['expected_transitions'][0]['scope_predicate']['contract_signed_before'] == '2023-09-01'

    tt10 = docs['10/2023/TT-NHNN']
    assert tt10['issued_date'] == '2023-08-23', 'ANCHOR: TT10 ban hành 23/08/2023'
    sus = [o for o in tt10['expected_ops'] if o['kind'] == 'suspend']
    assert len(sus) == 3, 'ANCHOR: TT10 ngưng hiệu lực 3 khoản (k8, k9, k10 Đ8 TT39)'
    assert {o['target_path'] for o in sus} == {'dieu:8/khoan:8', 'dieu:8/khoan:9', 'dieu:8/khoan:10'}
    for o in sus:
        assert o['valid_from'] == '2023-09-01', 'ANCHOR: ngưng từ 01/09/2023'
        assert o['target_doc'] == '39/2016/TT-NHNN'
        assert 'văn bản quy phạm pháp luật mới' in o['valid_to_event'], 'ANCHOR: treo đến VBQPPL mới (nguyên văn)'

    # ===================== cấu trúc cho golden items =====================
    tt12 = docs['12/2024/TT-NHNN']
    opo_real = [o for o in tt12['expected_ops'] if o.get('target_is_op')]
    assert opo_real and opo_real[0]['target_op']['doc'] == '06/2023/TT-NHNN', 'op-nhắm-op thật (TT12 Đ4 k2)'

    tt08 = docs['08/2026/TT-NHNN']
    opo = [o for o in tt08['expected_ops'] if o.get('target_is_op')]
    assert opo and opo[0]['target_op'] == {'doc': '26/2022/TT-NHNN', 'paths': ['dieu:1/khoan:1']}, 'OPO-01/PIT: TT08 bãi bỏ k1 Đ1 TT26'
    assert opo[0]['valid_from'] == '2026-01-01', 'PIT-02: repeal-op từ 01/01/2026'
    tt26_op1 = docs['26/2022/TT-NHNN']['expected_ops'][0]
    assert tt26_op1['source_path'] == 'dieu:1/khoan:1' and tt26_op1['valid_from'] == '2022-12-31', \
        'PIT-01: cửa sổ TT26 mở 31/12/2022 (nguyên vẹn 2022→2026)'

    tt32 = docs['32/2026/TT-NHNN']
    gf3 = tt32['expected_transitions'][0]['scope_predicate']
    assert gf3 == {'contract_signed_before': '2026-07-01', 'not_amended_on_or_after': '2026-07-01'}, 'GF-03: 2 predicate lồng D-25'
    assert any(o['kind'] == 'blanket_derogation' for o in tt32['expected_ops']), 'TT32 có blanket derogation (D-14)'
    assert any(o['kind'] == 'norm_decl' for o in tt32['expected_ops']), 'TT32 norm succession'

    tt11 = docs['11/2026/TT-NHNN']
    assert tt11['effective_date'] == '2026-03-01'
    pen = [o for o in tt11['expected_ops'] if o['valid_from'] == '2026-07-01']
    assert len(pen) == 1 and 'Phiếu lý lịch tư pháp' in texts['11/2026/TT-NHNN'], 'PEN-01: op Phiếu LLTP hiệu lực 01/07/2026 ≠ 01/03/2026'
    assert any(o.get('target_part') == 'heading' for o in tt11['expected_ops']), 'TT11 có op chỉ sửa TIÊU ĐỀ'
    assert any(o.get('target_part') == 'appendix' for o in tt11['expected_ops']), 'TT11 có op nhắm Phụ lục'
    assert sum(1 for o in tt11['expected_ops'] if o['kind'] == 'repeal') >= 3, 'TT11 mass repeal'
    assert len({o['target_doc'] for o in tt11['expected_ops']}) >= 5 + 3 - 3, 'TT11 omnibus ≥5 văn bản đích'
    assert len({o['target_doc'] for o in tt11['expected_ops'] if not o['kind'] == 'repeal' or o.get('target_path')} ) >= 5

    dc = docs['DC-01/2026']
    dch = dc['expected_ops'][0]
    tt28_ins = docs['28/2026/TT-NHNN']['expected_ops'][0]
    assert dch['kind'] == 'dinh_chinh' and dch['valid_from'] == tt28_ins['valid_from'] == '2026-01-25', \
        'DCH-01: đính chính hồi tố về ĐẦU cửa sổ Đ7a (= ngày TT28 hiệu lực), không phải ngày công văn'
    assert dc['issued_date'] == '2026-02-10' > '2026-02-01', 'DCH-01: as_of 2026-02-01 nằm TRƯỚC ngày đính chính, TRONG cửa sổ'

    csls = docs['CS-LS-01/SHB']
    notes = ' '.join(csls['transcription_notes'])
    assert 'CFL-04' in notes and 'CFL-03' in notes and 'chat_hon_ve_minh' in notes and 'chat_hon_ve_doi_tac' in notes, \
        'CFL-03/04: hai hướng Liskov ghi rõ'
    qt = docs['QT-TD-01/SHB']
    assert any('STALE' in e['target'] for e in qt['expected_edges_sample']), 'SEM-01: edge stale trỏ node đã bãi bỏ'
    assert qt['owner'], 'SEM-01: owner để notice có địa chỉ'
    assert docs['06/2023/TT-NHNN']['amending_nodes'], 'CTM-01/02: amending_nodes TT06 (contamination probe)'

    # TT28 phrase-replace không được lan sang Đ24/Đ25 TT22
    tt28 = docs['28/2026/TT-NHNN']
    pr = [o for o in tt28['expected_ops'] if o.get('via', '').startswith('phrase_replace')]
    assert {o['target_path'] for o in pr} == {'dieu:7/khoan:3', 'dieu:23/khoan:2'}, 'D-21: materialize đúng 2 node liệt kê'

    # QĐ4033 (dinh_chinh thật) hồi tố về đầu cửa sổ TT52
    qd = docs['4033/QĐ-NHNN']['expected_ops'][0]
    assert qd['kind'] == 'dinh_chinh' and qd['valid_from'] == docs['52/2025/TT-NHNN']['effective_date']

    # cross-doc: target_doc trong kho phải tồn tại; ngoài kho phải ghi chú
    in_corpus = set(docs)
    for key, d in docs.items():
        for o in d['expected_ops']:
            td = o['target_doc']
            if td and td not in in_corpus and td != key:
                check('ngoài kho' in (o.get('notes') or '') or 'out-of-corpus' in (o.get('notes') or ''),
                      f'[{key}] op#{o["seq"]} target {td} ngoài kho nhưng không ghi chú')

    print(f'Docs: {len(docs)} | ops: {sum(len(d["expected_ops"]) for d in docs.values())} | '
          f'edges_sample: {sum(len(d["expected_edges_sample"]) for d in docs.values())} | '
          f'transitions: {sum(len(d.get("expected_transitions", [])) for d in docs.values())}')
    if ERRORS:
        print(f'\nFAIL — {len(ERRORS)} lỗi:')
        for e in ERRORS:
            print('  ✗', e)
        sys.exit(1)
    print('PASS — schema, sha256, dates, counts×2, surfaces, anchors, golden-prereqs đều xanh')


if __name__ == '__main__':
    main()
